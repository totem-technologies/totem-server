from datetime import timedelta
from enum import Enum

import jwt
from django.conf import settings
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import AuthenticationError
from datetime import datetime

from totem.email import emails
from totem.email.emails import login_pin_email
from totem.users import analytics
from totem.users.models import LoginPin, RefreshToken, User

# Create router
router = Router()


# Enum for error messages
class AuthErrors(Enum):
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    PIN_EXPIRED = "PIN_EXPIRED"
    INCORRECT_PIN = "INCORRECT_PIN"
    TOO_MANY_ATTEMPTS = "TOO_MANY_ATTEMPTS"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    NETWORK_ERROR = "NETWORK_ERROR"
    ACCOUNT_DEACTIVATED = "ACCOUNT_DEACTIVATED"


# Schemas
class JWTSchema(Schema):
    pk: int
    api_key: str
    exp: datetime


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


# JWT Token Helpers
def generate_jwt_token(user: User, expire_at: datetime | None = None) -> str:
    """Generate a JWT token for the user."""
    if expire_at is None:
        expire_at = timezone.now() + timedelta(minutes=60)
    payload = JWTSchema(pk=user.pk, api_key=str(user.api_key), exp=expire_at)
    return jwt.encode(payload.model_dump(), settings.SECRET_KEY, algorithm="HS256")


# Check if account is deactivated
def check_account_deactivated(user: User) -> bool:
    return not user.is_active


# Endpoints
@router.post("/request-pin", response={200: MessageResponse, 429: ErrorResponse}, url_name="auth_request_pin")
def request_pin(request, data: PinRequestSchema):
    """
    Request a PIN code to be sent via email.
    This endpoint handles both new and existing users.
    """
    # Get or create user
    user, created = User.objects.get_or_create(
        email=data.email.lower(), defaults={"newsletter_consent": data.newsletter_consent}
    )
    user.set_unusable_password()

    # If existing user, update newsletter preference if provided
    if not created and data.newsletter_consent:
        user.newsletter_consent = data.newsletter_consent

    user.save()

    # Generate and send PIN
    pin = LoginPin.objects.generate_pin(user)
    login_pin_email(user.email, pin.pin).send()

    if created:
        emails.welcome_email(user).send()
        analytics.user_signed_up(user)

    user.identify()

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
        user = User.objects.get(email=data.email.lower())
    except User.DoesNotExist:
        raise AuthenticationError(message=AuthErrors.INCORRECT_PIN.value)

    # Validate PIN
    is_valid, pin_obj = LoginPin.objects.validate_pin(user, data.pin)

    if not is_valid:
        if pin_obj and pin_obj.has_too_many_attempts():
            raise AuthenticationError(message=AuthErrors.TOO_MANY_ATTEMPTS.value)
        elif pin_obj is None:
            # No active PIN found - check if fixed PIN is enabled to provide better error message
            if user.fixed_pin_enabled and user.fixed_pin:
                raise AuthenticationError(message=AuthErrors.INCORRECT_PIN.value)
            else:
                raise AuthenticationError(message=AuthErrors.PIN_EXPIRED.value)
        else:
            raise AuthenticationError(message=AuthErrors.INCORRECT_PIN.value)

    # Check if account is deactivated
    if check_account_deactivated(user):
        raise AuthenticationError(message=AuthErrors.ACCOUNT_DEACTIVATED.value)

    # Generate tokens
    refresh_token_string, _ = RefreshToken.objects.generate_token(user)
    access_token = generate_jwt_token(user)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token_string,
        "expires_in": 3600,  # 60 minutes in seconds
    }


@router.post("/refresh", response={200: TokenResponse, 400: ErrorResponse, 429: ErrorResponse}, url_name="auth_refresh")
def refresh_token(request, data: RefreshTokenSchema):
    """
    Refresh access token using a valid refresh token.
    """
    # Validate refresh token
    user, token_obj = RefreshToken.objects.validate_token(data.refresh_token)

    if not user or not token_obj:
        raise AuthenticationError(message=AuthErrors.REAUTH_REQUIRED.value)

    # Check if account is deactivated
    if check_account_deactivated(user):
        # Invalidate token since account is deactivated
        token_obj.invalidate()
        raise AuthenticationError(message=AuthErrors.ACCOUNT_DEACTIVATED.value)

    # Generate new access token
    access_token = generate_jwt_token(user)

    return {
        "access_token": access_token,
        "refresh_token": data.refresh_token,  # Return the same refresh token
        "expires_in": 3600,  # 60 minutes in seconds
    }


@router.post("/logout", response={200: MessageResponse, 400: ErrorResponse}, url_name="auth_logout")
def logout(request, data: RefreshTokenSchema):
    """
    Logout by invalidating a refresh token.
    """
    # Find and invalidate the token
    user, token_obj = RefreshToken.objects.validate_token(data.refresh_token)

    if user and token_obj:
        token_obj.invalidate()

    # Always return success to avoid information leakage
    return {"message": "Successfully logged out"}
