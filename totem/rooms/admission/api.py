from collections.abc import Callable
from typing import TypeVar, cast

from django.http import HttpRequest
from ninja import Router, Status

from totem.spaces.models import Session
from totem.users.models import User

from ..livekit import LiveKitPermissionError
from . import AdmissionError
from . import services as service
from .schemas import (
    AdmissionCommandResponse,
    AdmissionMeSnapshot,
    AdmissionRequestInput,
    AdmissionSnapshot,
    AttemptReceiptInput,
    BatchCommandInput,
    DeclineInput,
    ErrorSchema,
    KeeperDecisionInput,
    MembershipCommandInput,
    SettingsCommandInput,
)

router = Router(tags=["admission"])
ERROR_RESPONSES = {code: ErrorSchema for code in (400, 403, 404, 409, 503, 504)}

_ADMISSION_ERRORS = {
    "not_keeper": 403,
    "not_eligible": 403,
    "permanently_declined": 403,
    "ended": 403,
    "not_found": 404,
    "feature_disabled": 404,
    "stale_version": 409,
    "invalid_attempt": 409,
    "permission_pending": 409,
    "connection_required": 409,
    "command_conflict": 409,
    "admission_full": 409,
    "waiting_full": 409,
    "room_full": 409,
    "presence_unavailable": 503,
}
_LIVEKIT_ERRORS = {
    "room_missing": 409,
    "participant_missing": 409,
    "missing": 409,
    "disconnected": 409,
    "identity_replaced": 409,
    "permission_mismatch": 409,
    "unavailable": 503,
    "timeout": 504,
}
T = TypeVar("T")


def _call(action: Callable[[], T]) -> T | Status:
    try:
        return action()
    except AdmissionError as error:
        if error.code not in _ADMISSION_ERRORS:
            raise
        return Status(_ADMISSION_ERRORS[error.code], ErrorSchema(code=error.code, message=str(error)))
    except LiveKitPermissionError as error:
        if error.code not in _LIVEKIT_ERRORS:
            raise
        return Status(_LIVEKIT_ERRORS[error.code], ErrorSchema(code=error.code, message=str(error)))
    except (Session.DoesNotExist, User.DoesNotExist):
        return Status(404, ErrorSchema(code="not_found", message="Session or user not found"))


@router.post("/{session_slug}/admission/request", response={200: AdmissionMeSnapshot, **ERROR_RESPONSES})
def request_admission(request: HttpRequest, session_slug: str, body: AdmissionRequestInput):
    return _call(lambda: service.request_admission_http(session_slug, cast(User, request.user), body))


@router.get("/{session_slug}/admission", response={200: AdmissionSnapshot, **ERROR_RESPONSES})
def get_admission(request: HttpRequest, session_slug: str):
    return _call(lambda: service.admission_snapshot(session_slug, cast(User, request.user), keeper=True))


@router.get("/{session_slug}/admission/me", response={200: AdmissionMeSnapshot, **ERROR_RESPONSES})
def get_my_admission(request: HttpRequest, session_slug: str):
    return _call(lambda: service.admission_snapshot(session_slug, cast(User, request.user), keeper=False))


@router.post("/{session_slug}/admission/admit-all", response={200: AdmissionCommandResponse, **ERROR_RESPONSES})
def admit_all(request: HttpRequest, session_slug: str, body: BatchCommandInput):
    return _call(lambda: service.execute_keeper_command(session_slug, cast(User, request.user), "admit_all", body))


@router.post("/{session_slug}/admission/activated", response={200: AdmissionMeSnapshot, **ERROR_RESPONSES})
def activate_admission(request: HttpRequest, session_slug: str, body: AttemptReceiptInput):
    return _call(lambda: service.activate_admission_http(session_slug, cast(User, request.user), body))


@router.post("/{session_slug}/admission/cancel", response={200: AdmissionMeSnapshot, **ERROR_RESPONSES})
def cancel_admission(request: HttpRequest, session_slug: str, body: AttemptReceiptInput):
    return _call(lambda: service.cancel_admission_http(session_slug, cast(User, request.user), body))


@router.patch("/{session_slug}/admission/settings", response={200: AdmissionCommandResponse, **ERROR_RESPONSES})
def update_settings(request: HttpRequest, session_slug: str, body: SettingsCommandInput):
    return _call(lambda: service.execute_keeper_command(session_slug, cast(User, request.user), "settings", body))


@router.post(
    "/{session_slug}/admission/{identity}/approve", response={200: AdmissionCommandResponse, **ERROR_RESPONSES}
)
def approve(request: HttpRequest, session_slug: str, identity: str, body: KeeperDecisionInput):
    return _call(
        lambda: service.execute_keeper_command(
            session_slug, cast(User, request.user), "approve", body, identity=identity
        )
    )


@router.post(
    "/{session_slug}/admission/{identity}/decline", response={200: AdmissionCommandResponse, **ERROR_RESPONSES}
)
def decline(request: HttpRequest, session_slug: str, identity: str, body: DeclineInput):
    action = "permanentdecline" if body.permanent else "decline"
    return _call(
        lambda: service.execute_keeper_command(session_slug, cast(User, request.user), action, body, identity=identity)
    )


@router.post("/{session_slug}/admission/{identity}/allow", response={200: AdmissionCommandResponse, **ERROR_RESPONSES})
def allow(request: HttpRequest, session_slug: str, identity: str, body: MembershipCommandInput):
    return _call(
        lambda: service.execute_keeper_command(session_slug, cast(User, request.user), "allow", body, identity=identity)
    )


@router.post("/{session_slug}/admission/{identity}/revoke", response={200: AdmissionCommandResponse, **ERROR_RESPONSES})
def revoke(request: HttpRequest, session_slug: str, identity: str, body: MembershipCommandInput):
    return _call(
        lambda: service.execute_keeper_command(
            session_slug, cast(User, request.user), "revoke", body, identity=identity
        )
    )
