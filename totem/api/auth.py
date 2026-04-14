from enum import Enum

from django.core.exceptions import ValidationError as DjangoValidationError
from ninja import Router, Schema
from ninja.errors import AuthenticationError

from totem.email import emails
from totem.email.emails import login_pin_email
from totem.email.exceptions import EmailBounced
from totem.users import analytics
from totem.users.models import LoginPin, User

from .oauth import create_oauth_tokens, refresh_oauth_tokens, revoke_oauth_refresh_token

# Create router
router = Router()


# Enum for error messages
class AuthErrors(Enum):
    INVALID_EMAIL = "INVALID_EMAIL"
    PIN_EXPIRED = "PIN_EXPIRED"
    INCORRECT_PIN = "INCORRECT_PIN"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    ACCOUNT_DEACTIVATED = "ACCOUNT_DEACTIVATED"


# Schemas
class PinRequestSchema(Schema):
    email: str
    newsletter_consent: bool = False


class MessageResponse(Schema):
    message: str


class ErrorResponse(Schema):
    error: str


class ValidatePinSchema(Schema):
    email: str
    pin: str


class TokenResponse(Schema):
    access_token: str
    refresh_token: str
    expires_in: int


class RefreshTokenSchema(Schema):
    refresh_token: str


# Endpoints
@router.post("/request-pin", response={200: MessageResponse, 429: ErrorResponse}, url_name="auth_request_pin")
def request_pin(request, data: PinRequestSchema):
    """
    Request a PIN code to be sent via email.
    This endpoint handles both new and existing users.
    """
    # Validate email using model validators (includes blocked email check)
    try:
        User(email=data.email).full_clean(exclude=["password"], validate_unique=False)
    except DjangoValidationError:
        raise AuthenticationError(message=AuthErrors.INVALID_EMAIL.value)

    # Get or create user
    user, created = User.objects.get_or_create(
        email=data.email, defaults={"newsletter_consent": data.newsletter_consent}
    )

    # If existing user, update newsletter preference if provided
    if not created and data.newsletter_consent:
        user.newsletter_consent = data.newsletter_consent

    user.save()
    user.identify()

    if user.fixed_pin_enabled:
        return {"message": "PIN sent to your email"}

    # Generate and send PIN
    pin = LoginPin.objects.generate_pin(user)
    try:
        login_pin_email(user.email, pin.pin).send()
    except EmailBounced:
        raise AuthenticationError(message=AuthErrors.INVALID_EMAIL.value)

    if created:
        emails.welcome_email(user).send()
        analytics.user_signed_up(user)

    return {"message": "PIN sent to your email"}


@router.post(
    "/validate-pin", response={200: TokenResponse, 400: ErrorResponse, 429: ErrorResponse}, url_name="auth_validate_pin"
)
def validate_pin(request, data: ValidatePinSchema):
    """
    Validate PIN and issue token pair.
    """
    # Find user by email
    try:
        normalized_email = User.objects.normalize_email(data.email)
        user = User.objects.get(email=normalized_email)
    except User.DoesNotExist:
        raise AuthenticationError(message=AuthErrors.INCORRECT_PIN.value)

    # Validate PIN
    is_valid, _ = LoginPin.objects.validate_pin(user, data.pin)

    if not is_valid:
        raise AuthenticationError(message=AuthErrors.PIN_EXPIRED.value)

    if not user.is_active:
        raise AuthenticationError(message=AuthErrors.ACCOUNT_DEACTIVATED.value)

    # Generate OAuth tokens
    tokens = create_oauth_tokens(user)

    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_in": tokens.expires_in,
    }


@router.post("/refresh", response={200: TokenResponse, 400: ErrorResponse, 429: ErrorResponse}, url_name="auth_refresh")
def refresh_token(request, data: RefreshTokenSchema):
    """
    Refresh access token using a valid refresh token.
    Rotates the refresh token: returns a new token pair and revokes the old one.
    """
    tokens, user = refresh_oauth_tokens(data.refresh_token)

    if tokens is None and user is None:
        raise AuthenticationError(message=AuthErrors.REAUTH_REQUIRED.value)

    if tokens is None:
        # User exists but account is deactivated (token was revoked by refresh_oauth_tokens)
        raise AuthenticationError(message=AuthErrors.ACCOUNT_DEACTIVATED.value)

    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_in": tokens.expires_in,
    }


@router.post("/logout", response={200: MessageResponse, 400: ErrorResponse}, url_name="auth_logout")
def logout(request, data: RefreshTokenSchema):
    """
    Logout by revoking a refresh token and its associated access token.
    """
    revoke_oauth_refresh_token(data.refresh_token)

    # Always return success to avoid information leakage
    return {"message": "Successfully logged out"}
