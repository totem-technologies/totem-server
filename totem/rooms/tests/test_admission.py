import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import jwt
import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import close_old_connections, connection, connections, transaction
from django.http import HttpRequest
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from livekit import api
from livekit import api as livekit_api

from totem.api.auth import generate_jwt_token
from totem.rooms import admission, livekit, tasks
from totem.rooms import admission as capacity_admission
from totem.rooms import api as room_api
from totem.rooms import livekit as room_livekit
from totem.rooms.admission import AdmissionError, request_admission
from totem.rooms.admission import permissions as admission_permissions
from totem.rooms.admission import services as admission_http
from totem.rooms.admission.capacity import admission_limit
from totem.rooms.admission.schemas import BatchCommandInput, MembershipCommandInput, SettingsCommandInput
from totem.rooms.livekit import LiveKitConfigurationError, LiveKitPermissionError
from totem.rooms.models import (
    AdmissionAttempt,
    AdmissionCommand,
    AdmissionPermissionSync,
    AdmissionState,
    AttemptStatus,
    Room,
    SessionAdmission,
)
from totem.rooms.schemas import (
    BanParticipantEvent,
    EndReason,
    EndRoomEvent,
    ErrorCode,
    EventRequest,
    RemoveReason,
    RoomStatus,
    StartRoomEvent,
    TransitionError,
    UnbanParticipantEvent,
)
from totem.rooms.state_machine import apply_event, record_join
from totem.rooms.tasks import _end_session, end_sessions_without_keeper
from totem.spaces.actions import JoinSessionAction
from totem.spaces.filters import join_listing_queryset
from totem.spaces.models import Session, Space
from totem.spaces.tests.factories import SessionFactory
from totem.users.models import User
from totem.users.tests.factories import UserFactory


def domain_request(admission, session, user):
    return admission.request_admission(session.slug, user, uuid4(), uuid4())


def domain_decide(admission, room, keeper, attempt, decision):
    room.refresh_from_db()
    return admission.decide_admission(
        room.session.slug,
        keeper,
        attempt.request_id,
        attempt.attempt_id,
        decision,
        expected_version=attempt.version,
        expected_room_version=room.state_version,
    )


def set_policy(admission, room, keeper, required):
    room.refresh_from_db()
    return admission.update_approval_required(
        room.session.slug,
        keeper,
        required,
        expected_revision=room.admission_revision,
        expected_room_version=room.state_version,
    )


def assert_error(admission, code, operation):
    with pytest.raises(admission.AdmissionError) as error:
        operation()
    assert error.value.code == code


def run_concurrently(operation):
    barrier = Barrier(2)

    def run():
        try:
            barrier.wait(timeout=10)
            return operation()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        return [future.result(timeout=20) for future in futures]


def add_users(session, count):
    users = [UserFactory() for _ in range(count)]
    session.attendees.add(*users)
    return users


def capacity_request(session, user):
    return capacity_admission.request_admission(session.slug, user, uuid4(), uuid4())


def domain_approve(room, keeper, attempt):
    return capacity_admission.decide_admission(
        room.session.slug,
        keeper,
        attempt.request_id,
        attempt.attempt_id,
        "approve",
        expected_version=attempt.version,
        expected_room_version=room.state_version,
    )


BASE = "/api/mobile/protected/rooms"


def post(client, url, body):
    return client.post(url, data=body, content_type="application/json")


def endpoint_cases():
    ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
    decision = {**ids, "command_id": str(uuid4()), "expected_version": 0, "expected_room_version": 0}
    membership = {"command_id": str(uuid4()), "expected_version": 0, "expected_room_version": 0}
    return [
        ("post", "/request", ids, False),
        ("get", "", None, True),
        ("get", "/me", None, False),
        ("post", "/admit-all", {"command_id": str(uuid4()), "expected_room_version": 0}, True),
        ("post", "/activated", {**ids, "expected_version": 0}, False),
        ("post", "/cancel", {**ids, "expected_version": 0}, False),
        (
            "patch",
            "/settings",
            {
                "command_id": str(uuid4()),
                "approval_required": False,
                "expected_revision": 0,
                "expected_room_version": 0,
            },
            True,
        ),
        ("post", "/target/approve", decision, True),
        ("post", "/target/decline", decision, True),
        ("post", "/target/allow", membership, True),
        ("post", "/target/revoke", membership, True),
    ]


def send(client, method, url, body):
    if body is None:
        return client.get(url)
    return getattr(client, method)(url, data=body, content_type="application/json")


def request_attempt(context):
    client, _, _, _, session, _ = context
    ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
    response = post(client, f"{BASE}/{session.slug}/admission/request", ids)
    assert response.status_code == 200, response.content
    return ids, response.json()["me"]


def decision_body(room, ids, attempt, command_id=None):
    room.refresh_from_db()
    return {
        **ids,
        "command_id": command_id or str(uuid4()),
        "expected_version": attempt["attempt_version"],
        "expected_room_version": room.state_version,
    }


def http_request(session, user):
    return admission.request_admission(session.slug, user, uuid4(), uuid4())


def http_decide(room, keeper, attempt, decision="approve"):
    room.refresh_from_db()
    return admission.decide_admission(
        room.session.slug,
        keeper,
        attempt.request_id,
        attempt.attempt_id,
        decision,
        expected_version=attempt.version,
        expected_room_version=room.state_version,
    )


def require_admission(session_slug, user) -> SessionAdmission:
    durable = admission.get_admission(session_slug, user)
    assert durable is not None
    return durable


def revoke(room, keeper, user):
    durable = require_admission(room.session.slug, user)
    room.refresh_from_db()
    return admission.revoke_admission(
        room.session.slug,
        keeper,
        user,
        expected_version=durable.version,
        expected_room_version=room.state_version,
    )


KEY = "test-key-test-key-test-key-test-key-test-key"


SECRET = "test-secret-test-secret-test-secret-test-secret-test-secret"


def join(client, session, body=None):
    url = f"{BASE}/{session.slug}/join"
    if body is None:
        return client.post(url)
    return client.post(url, data=body, content_type="application/json")


def ids():
    return {"request_id": str(uuid4()), "attempt_id": str(uuid4())}


def assert_token(response, user, session, *, admitted, attempt_id=None):
    assert response.status_code == 200, response.content
    claims = jwt.decode(response.json()["token"], SECRET, algorithms=["HS256"])
    assert claims["sub"] == user.slug
    assert claims["name"] == (user.name or "Anonymous")
    assert claims["exp"] - claims["nbf"] == 60
    assert claims["video"] == {
        "room": session.slug,
        "roomJoin": True,
        "roomAdmin": False,
        "canPublish": admitted,
        "canSubscribe": admitted,
        "canPublishData": admitted,
        "canUpdateOwnMetadata": False,
        "hidden": False,
    }
    if attempt_id is not None:
        assert claims["attributes"] == {
            "totem.admission": "admitted" if admitted else "waiting",
            "totem.admission_attempt": attempt_id,
        }
    return claims


def assert_admission(response, session, user, *, status, permissions):
    assert response.status_code == 200, response.content
    data = response.json()["admission"]
    attempt = AdmissionAttempt.objects.get(attempt_id=UUID(data["attempt_id"]))
    assert str(attempt.request_id) == data["request_id"]
    assert attempt.admission.session_id == session.pk
    assert attempt.admission.user_id == user.pk
    assert data["status"] == status == attempt.status
    assert data["durable_state"] == attempt.admission.state
    assert abs(parse_datetime(data["expires_at"]) - attempt.expires_at) < timedelta(milliseconds=1)
    assert data["permissions"] == permissions
    sync = getattr(attempt.admission, "permission_sync", None)
    assert data["revision"] == (sync.revision if sync else 0)
    expected_sync = "pending"
    if sync:
        expected_sync = sync.last_error or ("applied" if sync.applied_revision == sync.revision else "pending")
    assert data["permission_sync"] == expected_sync
    return data


def permissions_request(session, user):
    return admission.request_admission(session.slug, user, uuid4(), uuid4())


def permissions_approve(room, keeper, attempt):
    room.refresh_from_db()
    return admission.decide_admission(
        room.session.slug,
        keeper,
        attempt.request_id,
        attempt.attempt_id,
        "approve",
        expected_version=attempt.version,
        expected_room_version=room.state_version,
    )


def queue_without_callback(durable):
    with patch.object(admission_permissions, "reconcile_admission_permissions"):
        with transaction.atomic():
            Session.objects.select_for_update().get(pk=durable.session_id)
            admission_permissions.queue_permission_sync(durable)


def participant(identity):
    return api.ParticipantInfo(
        sid=f"sid-{identity}",
        identity=identity,
        permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
    )


class TestAdmissionDomain:
    def test_join_readiness_openapi_contract(self):
        from totem.api.api import mobile_api

        schemas = mobile_api.get_openapi_schema()["components"]["schemas"]
        join = schemas["AdmissionJoinState"]
        assert {"readiness", "observed_at"} <= set(join["required"])
        readiness_ref = {"$ref": "#/components/schemas/AdmissionReadiness"}
        assert join["properties"]["readiness"] == readiness_ref
        me = schemas["AdmissionMeSnapshot"]
        assert "readiness" in me["required"]
        assert me["properties"]["readiness"] == readiness_ref
        participant = schemas["Participant"]
        assert participant["properties"]["readiness"]["anyOf"] == [readiness_ref, {"type": "null"}]

        readiness = schemas["AdmissionReadiness"]
        assert "state" in readiness["required"]
        assert readiness["properties"]["state"] == {"$ref": "#/components/schemas/ReadinessState"}
        assert readiness["properties"]["reason"]["anyOf"] == [
            {"$ref": "#/components/schemas/ReadinessReason"},
            {"type": "null"},
        ]
        assert schemas["ReadinessState"]["type"] == "string"
        assert set(schemas["ReadinessState"]["enum"]) == {
            "waiting_for_approval",
            "applying_permissions",
            "ready_to_activate",
            "activated",
            "blocked",
            "ended",
            "requires_new_attempt",
        }
        assert schemas["ReadinessReason"]["type"] == "string"
        assert set(schemas["ReadinessReason"]["enum"]) == {
            "session_ended",
            "not_eligible",
            "no_request",
            "request_expired",
            "request_declined",
            "request_permanently_declined",
            "request_cancelled",
            "request_superseded",
            "request_revoked",
            "request_failed",
            "invalid_request",
            "requires_reapproval",
            "permanently_declined",
            "not_admitted",
            "admission_full",
            "approval_required",
            "connection_required",
            "permission_pending",
            "connection_changed",
        }

    @pytest.fixture
    def readiness_context(self):
        keeper = User(slug="keeper")
        user = User(slug="user")
        session = Session()
        room = Room(session=session, keeper=keeper.slug)
        return session, room, keeper, user

    @pytest.mark.parametrize(
        "change,state,reason",
        [
            ("pending", "waiting_for_approval", "approval_required"),
            ("ended", "ended", "session_ended"),
            ("ineligible", "blocked", "not_eligible"),
            ("no_attempt", "requires_new_attempt", "no_request"),
            ("expired", "requires_new_attempt", "request_expired"),
            ("revoked", "blocked", "requires_reapproval"),
            ("declined", "blocked", "permanently_declined"),
            ("unadmitted", "blocked", "not_admitted"),
            ("full", "blocked", "admission_full"),
            ("no_sid", "applying_permissions", "connection_required"),
            ("no_receipt", "applying_permissions", "connection_required"),
            ("no_sync", "applying_permissions", "permission_pending"),
            ("denied", "applying_permissions", "permission_pending"),
            ("revision", "applying_permissions", "permission_pending"),
            ("keeper_changed", "applying_permissions", "permission_pending"),
            ("operation", "applying_permissions", "permission_pending"),
            ("lease", "applying_permissions", "permission_pending"),
            ("error", "applying_permissions", "permission_pending"),
            ("no_sync_sid", "applying_permissions", "permission_pending"),
            ("sid_mismatch", "applying_permissions", "connection_changed"),
            ("activated", "activated", None),
            ("activated_mismatch", "requires_new_attempt", "connection_changed"),
        ],
    )
    def test_readiness_snapshot_states(self, readiness_context, change, state, reason):
        from totem.rooms.admission.services import project_readiness
        from totem.rooms.models import AdmissionPermissionSync

        _, room, _, user = readiness_context
        now = timezone.now()
        durable = SessionAdmission(session=room.session, user=user, state=AdmissionState.ADMITTED)
        attempt = AdmissionAttempt(
            admission=durable,
            status=AttemptStatus.GRANTING,
            participant_sid="sid-1",
            connected_at=now,
            expires_at=now + timedelta(minutes=1),
        )
        sync = AdmissionPermissionSync(
            admission=durable,
            desired_admitted=True,
            authority_keeper=room.keeper,
            revision=2,
            applied_revision=2,
            participant_sid="sid-1",
        )
        eligible, capacity, slots_used, ended = True, 5, 2, False
        if change == "pending":
            attempt.status = AttemptStatus.PENDING
        elif change == "ended":
            ended = True
        elif change == "ineligible":
            eligible = False
        elif change == "no_attempt":
            attempt = None
        elif change == "expired":
            attempt.expires_at = now

        elif change == "revoked":
            durable.state = AdmissionState.REVOKED
        elif change == "declined":
            durable.state = AdmissionState.PERMANENTLY_DECLINED
        elif change == "unadmitted":
            durable.state = AdmissionState.NONE
        elif change == "full":
            slots_used = 6
        elif change == "no_sid":
            attempt.participant_sid = ""
        elif change == "no_receipt":
            attempt.connected_at = None
        elif change == "no_sync":
            sync = None
        elif change == "denied":
            sync.desired_admitted = False
        elif change == "revision":
            sync.applied_revision = 1
        elif change == "keeper_changed":
            room.keeper = user.slug
        elif change == "operation":
            sync.operation_id = uuid4()
        elif change == "lease":
            sync.lease_until = now - timedelta(seconds=1)
        elif change == "error":
            sync.last_error = "timeout"
        elif change == "no_sync_sid":
            sync.participant_sid = ""
        elif change == "sid_mismatch":
            sync.participant_sid = "sid-2"
        elif change in ("activated", "activated_mismatch"):
            attempt.status = AttemptStatus.ADMITTED
            attempt.expires_at = now - timedelta(seconds=1)
            if change == "activated_mismatch":
                sync.participant_sid = "sid-2"
        result = project_readiness(room, durable, attempt, sync, eligible, capacity, slots_used, now, ended)
        assert result.state == state
        assert result.reason == reason

    @pytest.mark.parametrize(
        "status,reason",
        [
            (AttemptStatus.DECLINED, "request_declined"),
            (AttemptStatus.PERMANENTLY_DECLINED, "request_permanently_declined"),
            (AttemptStatus.CANCELLED, "request_cancelled"),
            (AttemptStatus.EXPIRED, "request_expired"),
            (AttemptStatus.SUPERSEDED, "request_superseded"),
            (AttemptStatus.REVOKED, "request_revoked"),
            (AttemptStatus.FAILED, "request_failed"),
        ],
    )
    def test_readiness_terminal_attempt_reasons_and_membership_precedence(self, readiness_context, status, reason):
        from totem.rooms.admission.services import project_readiness

        _, room, keeper, user = readiness_context
        now = timezone.now()
        durable = SessionAdmission(session=room.session, user=user, state=AdmissionState.NONE)
        attempt = AdmissionAttempt(admission=durable, status=status, expires_at=now)

        def project():
            return project_readiness(room, durable, attempt, None, True, 5, 2, now, False)

        assert (project().state, project().reason) == ("requires_new_attempt", reason)
        durable.state = AdmissionState.REVOKED
        assert (project().state, project().reason) == ("blocked", "requires_reapproval")
        durable.state = AdmissionState.PERMANENTLY_DECLINED
        assert (project().state, project().reason) == ("blocked", "permanently_declined")
        durable.user = keeper
        assert (project().state, project().reason) == ("requires_new_attempt", reason)

    @pytest.mark.parametrize("status", [None, AttemptStatus.PENDING, AttemptStatus.GRANTING])
    @pytest.mark.parametrize(
        "membership,reason",
        [
            (AdmissionState.REVOKED, "requires_reapproval"),
            (AdmissionState.PERMANENTLY_DECLINED, "permanently_declined"),
        ],
    )
    def test_readiness_membership_blocks_missing_or_expired_attempt(
        self, readiness_context, status, membership, reason
    ):
        from totem.rooms.admission.services import project_readiness

        _, room, _, user = readiness_context
        now = timezone.now()
        durable = SessionAdmission(session=room.session, user=user, state=membership)
        attempt = AdmissionAttempt(admission=durable, status=status, expires_at=now) if status else None
        result = project_readiness(room, durable, attempt, None, True, 5, 2, now, False)
        assert (result.state, result.reason) == ("blocked", reason)

    @pytest.fixture
    def admission(self):
        from totem.rooms import admission

        return admission

    @pytest.fixture
    def context(self, db):
        keeper = UserFactory()
        user = UserFactory()
        session = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=timezone.now() + timedelta(minutes=5),
        )
        session.attendees.add(keeper, user)
        room = Room.objects.get_or_create_for_session(session)
        return session, room, keeper, user

    @pytest.mark.parametrize("keeper_view", [True, False])
    def test_snapshot_query_count_does_not_grow_with_participants_or_history(self, context, keeper_view):
        session, room, keeper, user = context
        actor = keeper if keeper_view else user
        durable = SessionAdmission.objects.create(session=session, user=user, version=7)
        session.joined.add(user)
        SessionFactory().joined.add(user)

        def add_history(membership, count):
            AdmissionAttempt.objects.bulk_create(
                [
                    AdmissionAttempt(
                        admission=membership,
                        request_id=uuid4(),
                        attempt_id=uuid4(),
                        status=AttemptStatus.CANCELLED,
                        version=3,
                        expires_at=timezone.now() + timedelta(minutes=5),
                    )
                    for _ in range(count)
                ]
            )

        add_history(durable, 1)
        with patch("totem.rooms.admission.services.get_room_participant_sids", return_value={}):
            with CaptureQueriesContext(connection) as initial_queries:
                admission_http.admission_snapshot(session.slug, actor, keeper=keeper_view)
            extra_users = UserFactory.create_batch(4)
            session.attendees.add(*extra_users)
            for extra in extra_users:
                membership = SessionAdmission.objects.create(session=session, user=extra)
                add_history(membership, 4)
            add_history(durable, 4)
            with CaptureQueriesContext(connection) as grown_queries:
                snapshot = admission_http.admission_snapshot(session.slug, actor, keeper=keeper_view)

        assert len(grown_queries) == len(initial_queries)
        if keeper_view:
            rows = [item for item in snapshot.participants if item.identity == user.slug]
            assert len(rows) == 1
            assert rows[0].eligible and rows[0].admission_version == 7
            assert rows[0].user.circle_count == 2
            assert all(item.eligible and item.attempt_version == 3 for item in snapshot.requests)
            assert all(item.user.circle_count == (2 if item.identity == user.slug else 0) for item in snapshot.requests)
            assert all(item.user.circle_count == 0 for item in snapshot.participants if item.identity != user.slug)
        else:
            assert snapshot.me.eligible and snapshot.me.admission_version == 7
            assert snapshot.me.user.circle_count == 2

    @pytest.mark.parametrize("cancelled", [False, True])
    def test_snapshot_eligibility_uses_current_attendance_account_and_bans(self, context, cancelled):
        session, room, keeper, user = context
        inactive, removed, banned = UserFactory.create_batch(3)
        session.attendees.add(inactive, removed, banned)
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])
        session.attendees.remove(removed)
        session.cancelled = cancelled
        session.save(update_fields=["cancelled"])
        room.banned_participants = [banned.slug]
        room.save(update_fields=["banned_participants"])
        for person in (user, inactive, removed, banned):
            membership = SessionAdmission.objects.create(session=session, user=person)
            AdmissionAttempt.objects.create(
                admission=membership,
                request_id=uuid4(),
                attempt_id=uuid4(),
                status=AttemptStatus.CANCELLED,
                expires_at=timezone.now() + timedelta(minutes=5),
            )
        with patch("totem.rooms.admission.services.get_room_participant_sids", return_value={}):
            snapshot = admission_http.admission_snapshot(session.slug, keeper)
        expected = {user.slug: not cancelled, inactive.slug: False, removed.slug: False, banned.slug: False}
        assert {item.identity: item.eligible for item in snapshot.participants} == expected
        assert {item.identity: item.eligible for item in snapshot.requests} == expected
        reason = "session_ended" if cancelled else "not_eligible"
        assert all(item.readiness.reason == reason for item in snapshot.participants if not item.eligible)

    @pytest.fixture
    def livekit_permissions(self):
        participant = api.ParticipantInfo(
            sid="participant-1",
            permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
        )
        with (
            patch("totem.rooms.admission.permissions.get_participant_snapshot", return_value=participant),
            patch("totem.rooms.admission.permissions.update_participant_permissions", return_value=participant),
            patch("totem.rooms.admission.permissions.hard_disconnect_participant"),
            patch("totem.rooms.state_machine.publish_state"),
        ):
            yield

    @pytest.fixture
    def clear_content_type_cache(self, transactional_db):
        ContentType.objects.clear_cache()
        yield
        ContentType.objects.clear_cache()

    def test_request_waits_until_twenty_minutes_after_start(self, admission, context):
        session, _, _, user = context
        attempt = domain_request(admission, session, user)
        assert attempt.status == "pending"
        assert attempt.admission.session_id == session.pk
        assert attempt.admission.user_id == user.pk
        assert attempt.expires_at == session.start + timedelta(minutes=20)
        assert not admission.is_authorized_to_enter(session.slug, user)
        assert admission.get_admission(session.slug, user).state == "none"

    def test_request_for_started_session_expires_twenty_minutes_from_now(self, admission, context):
        session, _, _, user = context
        session.start = timezone.now() - timedelta(minutes=1)
        session.save(update_fields=["start"])
        before = timezone.now()
        attempt = domain_request(admission, session, user)
        after = timezone.now()
        assert before + timedelta(minutes=20) <= attempt.expires_at <= after + timedelta(minutes=20)

    @pytest.mark.parametrize("eligibility", ["not_attending", "inactive", "too_early", "cancelled"])
    def test_request_rejects_ineligible_user(self, admission, context, eligibility):
        session, _, _, user = context
        if eligibility == "not_attending":
            session.attendees.remove(user)
        elif eligibility == "inactive":
            user.is_active = False
            user.save(update_fields=["is_active"])
        elif eligibility == "too_early":
            session.start = timezone.now() + timedelta(hours=2)
            session.save(update_fields=["start"])
        else:
            session.cancelled = True
            session.save(update_fields=["cancelled"])
        assert_error(admission, "not_eligible", lambda: domain_request(admission, session, user))

    def test_keeper_skips_approval_but_not_join_eligibility(self, admission, context):
        session, _, keeper, _ = context
        assert admission.is_authorized_to_enter(session.slug, keeper)
        session.attendees.remove(keeper)
        assert not admission.is_authorized_to_enter(session.slug, keeper)

    @pytest.mark.django_db(transaction=True)
    def test_approve_grant_and_complete(self, admission, context, livekit_permissions):
        session, room, keeper, user = context
        attempt = domain_request(admission, session, user)
        waiting_deadline = attempt.expires_at
        before = timezone.now()
        attempt = domain_decide(admission, room, keeper, attempt, "approve")
        after = timezone.now()
        assert attempt.status == "granting"
        assert before + timedelta(minutes=2) <= attempt.expires_at <= after + timedelta(minutes=2)
        assert attempt.expires_at <= waiting_deadline
        assert attempt.decision_actor_id == keeper.pk
        durable = admission.get_admission(session.slug, user)
        assert durable.state == "admitted"
        assert durable.decision_actor_id == keeper.pk
        assert admission.is_authorized_to_enter(session.slug, user)
        attempt = admission.complete_admission(
            session.slug,
            user,
            attempt.request_id,
            attempt.attempt_id,
            expected_version=attempt.version,
        )
        assert attempt.status == "admitted"
        assert admission.get_admission(session.slug, user).state == "admitted"

    def test_grant_deadline_does_not_extend_waiting_deadline(self, admission, context):
        session, room, keeper, user = context
        attempt = domain_request(admission, session, user)
        attempt.expires_at = timezone.now() + timedelta(seconds=30)
        attempt.save(update_fields=["expires_at"])
        deadline = attempt.expires_at
        attempt = domain_decide(admission, room, keeper, attempt, "approve")
        assert attempt.expires_at == deadline

    def test_grant_expiry_does_not_erase_durable_admission(self, admission, context):
        session, room, keeper, user = context
        attempt = domain_decide(admission, room, keeper, domain_request(admission, session, user), "approve")
        attempt.expires_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["expires_at"])
        try:
            result = admission.complete_admission(
                session.slug,
                user,
                attempt.request_id,
                attempt.attempt_id,
                expected_version=attempt.version,
            )
            assert result.status != "admitted"
        except admission.AdmissionError:
            pass
        assert admission.get_admission(session.slug, user).state == "admitted"

    def test_duplicate_request_ids_are_idempotent_and_new_ids_supersede_pending(self, admission, context):
        session, _, keeper, user = context
        first = domain_request(admission, session, user)
        duplicate = admission.request_admission(session.slug, user, first.request_id, first.attempt_id)
        assert duplicate.pk == first.pk
        second = domain_request(admission, session, user)
        first.refresh_from_db()
        assert first.status == "superseded"
        assert second.status == "pending"
        replay = admission.request_admission(session.slug, user, first.request_id, first.attempt_id)
        assert replay.status == "superseded"
        assert [attempt.pk for attempt in admission.pending_queue(session.slug, keeper)] == [second.pk]

    def test_decline_allows_new_explicit_request_and_supersedes_old_ids(self, admission, context):
        session, room, keeper, user = context
        first = domain_request(admission, session, user)
        declined = domain_decide(admission, room, keeper, first, "decline")
        assert declined.status == "declined"
        second = domain_request(admission, session, user)
        assert second.status == "pending"
        old = admission.request_admission(session.slug, user, first.request_id, first.attempt_id)
        assert old.status != "pending"
        assert admission.pending_queue(session.slug, keeper)[0].pk == second.pk

    def test_permanent_decline_overrides_disabled_policy_until_explicitly_allowed(self, admission, context):
        session, room, keeper, user = context
        attempt = domain_decide(
            admission, room, keeper, domain_request(admission, session, user), "permanently_decline"
        )
        assert attempt.status == "permanently_declined"
        durable = admission.get_admission(session.slug, user)
        assert durable.state == "permanently_declined"
        set_policy(admission, room, keeper, False)
        assert not admission.is_authorized_to_enter(session.slug, user)
        assert_error(admission, "not_eligible", lambda: domain_request(admission, session, user))
        room.refresh_from_db()
        durable = admission.allow_previously_declined(
            session.slug,
            keeper,
            user,
            expected_version=durable.version,
            expected_room_version=room.state_version,
        )
        assert durable.state == "none"
        attempt.refresh_from_db()
        assert attempt.status == "permanently_declined"
        assert not admission.is_authorized_to_enter(session.slug, user)
        new_attempt = domain_request(admission, session, user)
        assert new_attempt.status == "granting"
        assert admission.get_admission(session.slug, user).state == "admitted"
        assert admission.is_authorized_to_enter(session.slug, user)

    def test_disabled_policy_auto_grants_only_after_request(self, admission, context):
        session, room, keeper, user = context
        set_policy(admission, room, keeper, False)
        assert admission.get_admission(session.slug, user) is None
        assert not admission.is_authorized_to_enter(session.slug, user)
        attempt = domain_request(admission, session, user)
        assert attempt.status == "granting"
        assert admission.get_admission(session.slug, user).state == "admitted"
        assert admission.is_authorized_to_enter(session.slug, user)
        session.attendees.remove(user)
        assert not admission.is_authorized_to_enter(session.slug, user)

    def test_disabling_policy_auto_grants_only_eligible_pending_attempts(self, admission, context):
        session, room, keeper, user = context
        ineligible = UserFactory()
        session.attendees.add(ineligible)
        eligible_attempt = domain_request(admission, session, user)
        ineligible_attempt = domain_request(admission, session, ineligible)
        session.attendees.remove(ineligible)
        updated = set_policy(admission, room, keeper, False)
        eligible_attempt.refresh_from_db()
        ineligible_attempt.refresh_from_db()
        assert updated.approval_required is False
        assert eligible_attempt.status == "granting"
        assert admission.get_admission(session.slug, user).state == "admitted"
        assert admission.is_authorized_to_enter(session.slug, user)
        assert ineligible_attempt.status != "granting"
        assert admission.get_admission(session.slug, ineligible).state != "admitted"
        assert not admission.is_authorized_to_enter(session.slug, ineligible)

    def test_enabling_policy_preserves_durable_admission(self, admission, context):
        session, room, keeper, user = context
        set_policy(admission, room, keeper, False)
        attempt = domain_request(admission, session, user)
        assert attempt.status == "granting"
        updated = set_policy(admission, room, keeper, True)
        assert updated.approval_required is True
        assert admission.get_admission(session.slug, user).state == "admitted"
        assert admission.is_authorized_to_enter(session.slug, user)

    def test_policy_survives_room_reload_and_keeper_reassignment(self, admission, context):
        session, room, keeper, user = context
        updated = set_policy(admission, room, keeper, False)
        revision = updated.admission_revision
        new_keeper = UserFactory()
        session.attendees.add(new_keeper)
        room.refresh_from_db()
        room.keeper = new_keeper.slug
        room.save(update_fields=["keeper"])
        room = Room.objects.get(pk=room.pk)
        assert room.approval_required is False
        assert room.admission_revision == revision
        assert_error(admission, "not_keeper", lambda: set_policy(admission, room, keeper, True))
        assert_error(admission, "not_keeper", lambda: admission.pending_queue(session.slug, keeper))
        updated = set_policy(admission, room, new_keeper, True)
        assert updated.approval_required is True
        assert updated.admission_revision == revision + 1
        assert not admission.is_authorized_to_enter(session.slug, user)

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize("departure", ["cancelled", "completed"])
    def test_durable_admission_auto_grants_return_after_cancel_or_normal_leave(
        self, admission, context, departure, livekit_permissions
    ):
        session, room, keeper, user = context
        attempt = domain_decide(admission, room, keeper, domain_request(admission, session, user), "approve")
        if departure == "cancelled":
            attempt = admission.cancel_admission(
                session.slug,
                user,
                attempt.request_id,
                attempt.attempt_id,
                expected_version=attempt.version,
            )
            assert attempt.status == "cancelled"
        else:
            attempt = admission.complete_admission(
                session.slug,
                user,
                attempt.request_id,
                attempt.attempt_id,
                expected_version=attempt.version,
            )
            assert attempt.status == "admitted"
        assert admission.get_admission(session.slug, user).state == "admitted"
        returning = domain_request(admission, session, user)
        assert returning.status == "granting"
        assert admission.is_authorized_to_enter(session.slug, user)

    @pytest.mark.parametrize("terminal", ["expired", "cancelled", "superseded"])
    def test_keeper_cannot_decide_terminal_attempt(self, admission, context, terminal):
        session, room, keeper, user = context
        attempt = domain_request(admission, session, user)
        if terminal == "expired":
            attempt.expires_at = timezone.now() - timedelta(seconds=1)
            attempt.save(update_fields=["expires_at"])
            admission.pending_queue(session.slug, keeper)
        elif terminal == "cancelled":
            admission.cancel_admission(
                session.slug,
                user,
                attempt.request_id,
                attempt.attempt_id,
                expected_version=attempt.version,
            )
        else:
            domain_request(admission, session, user)
        attempt.refresh_from_db()
        assert attempt.status == terminal
        assert_error(admission, "invalid_attempt", lambda: domain_decide(admission, room, keeper, attempt, "approve"))
        attempt.refresh_from_db()
        assert attempt.status == terminal
        assert not admission.is_authorized_to_enter(session.slug, user)

    def test_revoke_removes_access_and_revokes_active_attempt(self, admission, context):
        session, room, keeper, user = context
        attempt = domain_decide(admission, room, keeper, domain_request(admission, session, user), "approve")
        durable = admission.get_admission(session.slug, user)
        room.refresh_from_db()
        durable = admission.revoke_admission(
            session.slug,
            keeper,
            user,
            expected_version=durable.version,
            expected_room_version=room.state_version,
        )
        attempt.refresh_from_db()
        assert durable.state == "revoked"
        assert attempt.status == "revoked"
        assert not admission.is_authorized_to_enter(session.slug, user)
        assert domain_request(admission, session, user).status == "pending"
        assert not admission.is_authorized_to_enter(session.slug, user)

    def test_stale_revoke_does_not_change_admission(self, admission, context):
        session, room, keeper, user = context
        domain_decide(admission, room, keeper, domain_request(admission, session, user), "approve")
        durable = admission.get_admission(session.slug, user)
        room.refresh_from_db()
        for version, room_version in [
            (durable.version + 1, room.state_version),
            (durable.version, room.state_version + 1),
        ]:
            assert_error(
                admission,
                "stale_version",
                lambda: admission.revoke_admission(
                    session.slug,
                    keeper,
                    user,
                    expected_version=version,
                    expected_room_version=room_version,
                ),
            )
        assert admission.get_admission(session.slug, user).state == "admitted"

    def test_cancel_is_owned_by_requesting_user(self, admission, context):
        session, _, _, user = context
        other = UserFactory()
        session.attendees.add(other)
        attempt = domain_request(admission, session, user)
        assert_error(
            admission,
            "invalid_attempt",
            lambda: admission.cancel_admission(
                session.slug,
                other,
                attempt.request_id,
                attempt.attempt_id,
                expected_version=attempt.version,
            ),
        )
        assert_error(
            admission,
            "stale_version",
            lambda: admission.cancel_admission(
                session.slug,
                user,
                attempt.request_id,
                attempt.attempt_id,
                expected_version=attempt.version + 1,
            ),
        )
        cancelled = admission.cancel_admission(
            session.slug,
            user,
            attempt.request_id,
            attempt.attempt_id,
            expected_version=attempt.version,
        )
        assert cancelled.status == "cancelled"
        assert not admission.is_authorized_to_enter(session.slug, user)

    def test_keeper_only_operations_reject_attendee(self, admission, context):
        session, room, _, user = context
        attempt = domain_request(admission, session, user)
        assert_error(admission, "not_keeper", lambda: domain_decide(admission, room, user, attempt, "approve"))
        assert_error(admission, "not_keeper", lambda: set_policy(admission, room, user, False))
        assert_error(admission, "not_keeper", lambda: admission.pending_queue(session.slug, user))

    def test_stale_attempt_and_room_versions_leave_request_pending(self, admission, context):
        session, room, keeper, user = context
        attempt = domain_request(admission, session, user)
        room.refresh_from_db()
        for version, room_version in [
            (attempt.version + 1, room.state_version),
            (attempt.version, room.state_version + 1),
        ]:
            assert_error(
                admission,
                "stale_version",
                lambda: admission.decide_admission(
                    session.slug,
                    keeper,
                    attempt.request_id,
                    attempt.attempt_id,
                    "approve",
                    expected_version=version,
                    expected_room_version=room_version,
                ),
            )
        attempt.refresh_from_db()
        assert attempt.status == "pending"
        assert not admission.is_authorized_to_enter(session.slug, user)

    def test_stale_policy_revision_and_room_version_do_not_change_policy(self, admission, context):
        session, room, keeper, _ = context
        for revision, version in [
            (room.admission_revision + 1, room.state_version),
            (room.admission_revision, room.state_version + 1),
        ]:
            assert_error(
                admission,
                "stale_version",
                lambda: admission.update_approval_required(
                    session.slug,
                    keeper,
                    False,
                    expected_revision=revision,
                    expected_room_version=version,
                ),
            )
        room.refresh_from_db()
        assert room.approval_required is True

    def test_ending_room_invalidates_pending_and_granting_attempts(self, admission, context):
        session, room, keeper, user = context
        other = UserFactory()
        session.attendees.add(other)
        pending = domain_request(admission, session, user)
        granting = domain_decide(admission, room, keeper, domain_request(admission, session, other), "approve")
        room.refresh_from_db()
        apply_event(
            session.slug, keeper.slug, EndRoomEvent(reason=EndReason.KEEPER_ENDED), room.state_version, {keeper.slug}
        )
        pending.refresh_from_db()
        granting.refresh_from_db()
        assert pending.status not in {"pending", "granting"}
        assert granting.status not in {"pending", "granting"}
        assert not admission.is_authorized_to_enter(session.slug, user)
        assert not admission.is_authorized_to_enter(session.slug, other)
        assert_error(admission, "ended", lambda: domain_request(admission, session, user))

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_duplicate_request_is_idempotent(self, admission, clear_content_type_cache, livekit_permissions):
        keeper = UserFactory()
        user = UserFactory()
        session = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=timezone.now() + timedelta(minutes=5),
        )
        session.attendees.add(keeper, user)
        Room.objects.get_or_create_for_session(session)
        request_id, attempt_id = uuid4(), uuid4()
        results = run_concurrently(lambda: admission.request_admission(session.slug, user, request_id, attempt_id))
        assert results[0].pk == results[1].pk
        assert results[0].status == results[1].status == "pending"
        assert len(admission.pending_queue(session.slug, keeper)) == 1

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_conflicting_decisions_have_one_winner(
        self, admission, clear_content_type_cache, livekit_permissions
    ):
        keeper = UserFactory()
        user = UserFactory()
        session = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=timezone.now() + timedelta(minutes=5),
        )
        session.attendees.add(keeper, user)
        room = Room.objects.get_or_create_for_session(session)
        attempt = domain_request(admission, session, user)
        room.refresh_from_db()
        decisions = iter(["approve", "permanently_decline"])

        def decide_once():
            decision = next(decisions)
            try:
                result = admission.decide_admission(
                    session.slug,
                    keeper,
                    attempt.request_id,
                    attempt.attempt_id,
                    decision,
                    expected_version=attempt.version,
                    expected_room_version=room.state_version,
                )
                return result.status
            except admission.AdmissionError as error:
                return error.code

        results = run_concurrently(decide_once)
        assert results.count("stale_version") == 1
        assert len(set(results) & {"granting", "permanently_declined"}) == 1
        attempt.refresh_from_db()
        durable = admission.get_admission(session.slug, user)
        assert (attempt.status, durable.state) in {
            ("granting", "admitted"),
            ("permanently_declined", "permanently_declined"),
        }

    @pytest.fixture
    def capacity_context(self, settings):
        settings.LIVEKIT_API_KEY = "test-key-test-key-test-key-test-key"
        settings.LIVEKIT_API_SECRET = "test-secret-test-secret-test-secret-test-secret-test-secret"
        keeper = UserFactory()
        session = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=timezone.now() - timedelta(minutes=1),
        )
        session.attendees.add(keeper)
        room = Room.objects.get_or_create_for_session(session)

        def missing(*args, **kwargs):
            assert not connection.in_atomic_block
            raise LiveKitPermissionError("participant_missing", "Not connected")

        with (
            patch("totem.rooms.admission.permissions.get_participant_snapshot", side_effect=missing),
            patch("totem.rooms.state_machine.publish_state"),
        ):
            yield session, room, keeper

    @pytest.mark.django_db(transaction=True)
    def test_join_operation_retries_and_supersession(self, capacity_context):
        session, _, _ = capacity_context
        user, other = add_users(session, 2)
        existing = capacity_request(session, user)
        operation = uuid4()
        first = capacity_admission.prepare_admission_join(
            session.slug, user, operation_id=operation, connected=set()
        ).admission
        assert (first.request_id, first.attempt_id) == (existing.request_id, existing.attempt_id)
        retry = capacity_admission.prepare_admission_join(
            session.slug, user, operation_id=operation, connected=set()
        ).admission
        resumed = capacity_admission.prepare_admission_join(session.slug, user, connected=set()).admission
        assert (first.request_id, first.attempt_id) == (retry.request_id, retry.attempt_id)
        assert (first.request_id, first.attempt_id) == (resumed.request_id, resumed.attempt_id)
        assert first.readiness.state == "waiting_for_approval"
        with pytest.raises(capacity_admission.AdmissionError):
            capacity_admission.prepare_admission_join(
                session.slug, user, operation_id=operation, fresh=True, connected=set()
            )
        with pytest.raises(capacity_admission.AdmissionError) as error:
            capacity_admission.prepare_admission_join(session.slug, other, operation_id=operation, connected=set())
        assert error.value.code == "invalid_attempt"
        new_operation = uuid4()
        second = capacity_admission.prepare_admission_join(
            session.slug, user, operation_id=new_operation, fresh=True, connected=set()
        ).admission
        fresh_retry = capacity_admission.prepare_admission_join(
            session.slug, user, operation_id=new_operation, fresh=True, connected=set()
        ).admission
        assert second.attempt_id == fresh_retry.attempt_id != first.attempt_id
        with pytest.raises(capacity_admission.AdmissionError) as error:
            capacity_admission.prepare_admission_join(session.slug, user, operation_id=operation, connected=set())
        assert error.value.code == "invalid_attempt"
        assert AdmissionAttempt.objects.filter(admission__session=session, admission__user=user).count() == 2

    @pytest.mark.parametrize("is_keeper", [False, True])
    @pytest.mark.parametrize("connected", [False, True])
    @pytest.mark.django_db(transaction=True)
    def test_join_operation_returning_attempt(self, capacity_context, is_keeper, connected):
        session, room, keeper = capacity_context
        user = keeper if is_keeper else add_users(session, 1)[0]
        existing = capacity_request(session, user)
        if not is_keeper:
            existing = domain_approve(room, keeper, existing)
        existing.status = AttemptStatus.ADMITTED
        existing.participant_sid = "sid-1"
        existing.connected_at = timezone.now()
        existing.save(update_fields=["status", "participant_sid", "connected_at"])
        operation = uuid4()
        presence = {user.slug} if connected else set()
        result = capacity_admission.prepare_admission_join(
            session.slug, user, operation_id=operation, connected=presence
        )
        retry = capacity_admission.prepare_admission_join(session.slug, user, operation_id=operation, connected=set())
        assert result.admission.attempt_id == retry.admission.attempt_id
        assert result.admission.request_id == retry.admission.request_id
        assert (result.admission.attempt_id == existing.attempt_id) == connected
        assert result.admission.status == (AttemptStatus.ADMITTED if connected else AttemptStatus.GRANTING)
        assert result.admission.permissions == "admitted"
        assert AdmissionAttempt.objects.filter(admission=existing.admission).count() == (1 if connected else 2)

    @pytest.mark.parametrize("status", [AttemptStatus.DECLINED, AttemptStatus.EXPIRED, AttemptStatus.SUPERSEDED])
    @pytest.mark.django_db(transaction=True)
    def test_join_operation_returning_terminal_requires_fresh(self, capacity_context, status):
        session, room, keeper = capacity_context
        (user,) = add_users(session, 1)
        attempt = domain_approve(room, keeper, capacity_request(session, user))
        attempt.status = status
        attempt.save(update_fields=["status"])
        with pytest.raises(capacity_admission.AdmissionError) as error:
            capacity_admission.prepare_admission_join(session.slug, user, operation_id=uuid4(), connected=set())
        assert error.value.code == "invalid_attempt"
        assert AdmissionAttempt.objects.filter(admission=attempt.admission).count() == 1

    @pytest.mark.django_db(transaction=True)
    def test_join_operation_survives_capacity_failure(self, capacity_context):
        session, _, _ = capacity_context
        (user,) = add_users(session, 1)
        operation = uuid4()
        with pytest.raises(capacity_admission.AdmissionError) as error:
            capacity_admission.prepare_admission_join(
                session.slug, user, operation_id=operation, connected={f"waiter-{i}" for i in range(5)}
            )
        assert error.value.code == "waiting_full"
        attempt = AdmissionAttempt.objects.get(admission__session=session, admission__user=user)
        result = capacity_admission.prepare_admission_join(session.slug, user, operation_id=operation, connected=set())
        assert result.admission.attempt_id == attempt.attempt_id
        assert AdmissionAttempt.objects.filter(admission__session=session, admission__user=user).count() == 1

    @pytest.mark.django_db(transaction=True)
    def test_join_operation_expiry_requires_new_id(self, capacity_context):
        session, _, _ = capacity_context
        (user,) = add_users(session, 1)
        operation = uuid4()
        first = capacity_admission.prepare_admission_join(
            session.slug, user, operation_id=operation, connected=set()
        ).admission
        attempt = AdmissionAttempt.objects.get(attempt_id=first.attempt_id)
        attempt.expires_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["expires_at"])
        with pytest.raises(capacity_admission.AdmissionError) as error:
            capacity_admission.prepare_admission_join(session.slug, user, operation_id=operation, connected=set())
        assert error.value.code == "invalid_attempt"
        attempt.refresh_from_db()
        assert attempt.status == AttemptStatus.EXPIRED
        with pytest.raises(capacity_admission.AdmissionError) as error:
            capacity_admission.prepare_admission_join(session.slug, user, operation_id=uuid4(), connected=set())
        assert error.value.code == "invalid_attempt"
        assert AdmissionAttempt.objects.filter(admission__session=session, admission__user=user).count() == 1
        fresh = capacity_admission.prepare_admission_join(
            session.slug, user, operation_id=uuid4(), fresh=True, connected=set()
        ).admission
        assert fresh.attempt_id != first.attempt_id

    @pytest.mark.parametrize("fresh", [False, True])
    @pytest.mark.django_db(transaction=True)
    def test_concurrent_join_operation_is_idempotent(self, capacity_context, clear_content_type_cache, fresh):
        session, _, _ = capacity_context
        (user,) = add_users(session, 1)
        existing = capacity_request(session, user)
        operation = uuid4()
        results = run_concurrently(
            lambda: capacity_admission.prepare_admission_join(
                session.slug, user, operation_id=operation, fresh=fresh, connected=set()
            )
        )
        assert results[0].admission.attempt_id == results[1].admission.attempt_id
        assert (results[0].admission.attempt_id != existing.attempt_id) == fresh
        assert AdmissionAttempt.objects.filter(admission__session=session, admission__user=user).count() == (
            2 if fresh else 1
        )

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_operation_collision_across_sessions_is_rejected(
        self, capacity_context, clear_content_type_cache
    ):
        session, _, keeper = capacity_context
        (user,) = add_users(session, 1)
        other = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=timezone.now() - timedelta(minutes=1),
        )
        other.attendees.add(keeper, user)
        Room.objects.get_or_create_for_session(other)
        operation = uuid4()
        sessions = iter([session, other])

        def join():
            target = next(sessions)
            try:
                capacity_admission.prepare_admission_join(target.slug, user, operation_id=operation, connected=set())
                return "ok"
            except capacity_admission.AdmissionError as error:
                return error.code

        assert sorted(run_concurrently(join)) == ["invalid_attempt", "ok"]
        assert (
            AdmissionAttempt.objects.filter(admission__session__in=[session, other], admission__user=user).count() == 1
        )

    @pytest.mark.django_db(transaction=True)
    def test_join_readiness_requires_current_attempt_connection(self, capacity_context):
        from totem.rooms.models import AdmissionPermissionSync

        session, room, keeper = capacity_context
        (user,) = add_users(session, 1)
        first = capacity_admission.prepare_admission_join(session.slug, user, connected=set()).admission
        assert first.readiness.state == "waiting_for_approval"
        attempt = AdmissionAttempt.objects.get(attempt_id=first.attempt_id)
        domain_approve(room, keeper, attempt)
        sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
        sync.desired_admitted = True
        sync.authority_keeper = room.keeper
        sync.applied_revision = sync.revision
        sync.participant_sid = "sid-1"
        sync.last_error = ""
        sync.operation_id = None
        sync.lease_until = None
        sync.save()

        before = timezone.now()
        unconfirmed = capacity_admission.prepare_admission_join(session.slug, user, connected=set()).admission
        assert before <= unconfirmed.observed_at <= timezone.now()
        assert unconfirmed.readiness.model_dump(mode="json") == {
            "state": "applying_permissions",
            "reason": "connection_required",
        }

        attempt.refresh_from_db()
        attempt.participant_sid = "sid-2"
        attempt.connected_at = timezone.now()
        attempt.save(update_fields=["participant_sid", "connected_at"])
        mismatch = capacity_admission.prepare_admission_join(session.slug, user, connected={user.slug}).admission
        assert mismatch.readiness.model_dump(mode="json") == {
            "state": "applying_permissions",
            "reason": "connection_changed",
        }

        sync.participant_sid = "sid-2"
        sync.save(update_fields=["participant_sid"])
        ready = capacity_admission.prepare_admission_join(session.slug, user, connected={user.slug}).admission
        assert ready.readiness.model_dump(mode="json") == {"state": "ready_to_activate", "reason": None}

    @pytest.mark.parametrize(
        ("error", "expected"), [("unknown_failure", "unavailable"), ("applied", "unavailable"), ("timeout", "timeout")]
    )
    @pytest.mark.django_db(transaction=True)
    def test_join_permission_error_fails_closed(self, capacity_context, error, expected):
        from totem.rooms.models import AdmissionPermissionSync

        session, room, keeper = capacity_context
        first = capacity_admission.prepare_admission_join(session.slug, keeper, connected=set()).admission
        attempt = AdmissionAttempt.objects.get(attempt_id=first.attempt_id)
        attempt.participant_sid = "sid-1"
        attempt.connected_at = timezone.now()
        attempt.save(update_fields=["participant_sid", "connected_at"])
        sync, _ = AdmissionPermissionSync.objects.get_or_create(admission=attempt.admission)
        sync.desired_admitted = True
        sync.authority_keeper = room.keeper
        sync.applied_revision = sync.revision
        sync.participant_sid = "sid-1"
        sync.operation_id = None
        sync.lease_until = None
        sync.last_error = error
        sync.save()

        result = capacity_admission.prepare_admission_join(session.slug, keeper, connected={keeper.slug}).admission
        assert result.permission_sync == expected
        assert result.readiness.state == "applying_permissions"
        assert result.readiness.reason == "permission_pending"
        sync.refresh_from_db()
        assert sync.last_error == error

    @pytest.mark.django_db(transaction=True)
    def test_empty_room_reserves_only_seat_for_keeper(self, capacity_context):
        session, room, keeper = capacity_context
        session.seats = 1
        session.save(update_fields=["seats"])
        (user,) = add_users(session, 1)
        attempt = capacity_request(session, user)
        with pytest.raises(capacity_admission.AdmissionError) as error:
            domain_approve(room, keeper, attempt)
        assert error.value.code == "admission_full"
        attempt.refresh_from_db()
        assert attempt.status == AttemptStatus.PENDING
        assert attempt.admission.state == AdmissionState.NONE

    @pytest.mark.parametrize(("seats", "limit"), [(0, 1), (1, 1), (8, 8), (100, 10)])
    @pytest.mark.django_db(transaction=True)
    def test_admission_limit_includes_keeper_and_is_clamped(self, capacity_context, seats, limit):
        _, room, _ = capacity_context
        room.session.seats = seats
        assert admission_limit(room) == limit

    @pytest.mark.django_db(transaction=True)
    def test_policy_off_keeps_full_and_removed_requests_pending(self, capacity_context):
        session, room, keeper = capacity_context
        session.seats = 2
        session.save(update_fields=["seats"])
        admitted, removed, newcomer = add_users(session, 3)
        SessionAdmission.objects.create(session=session, user=admitted, state=AdmissionState.ADMITTED)
        SessionAdmission.objects.create(session=session, user=removed, state=AdmissionState.REVOKED)
        old = capacity_request(session, removed)
        room.refresh_from_db()
        capacity_admission.update_approval_required(
            session.slug,
            keeper,
            False,
            expected_revision=room.admission_revision,
            expected_room_version=room.state_version,
        )
        old.refresh_from_db()
        assert old.status == AttemptStatus.PENDING
        new = capacity_request(session, newcomer)
        assert new.status == AttemptStatus.PENDING
        SessionAdmission.objects.filter(session=session, user=admitted).update(state=AdmissionState.REVOKED)
        retry = capacity_admission.request_admission(session.slug, removed, old.request_id, old.attempt_id)
        assert retry.status == AttemptStatus.PENDING
        room.refresh_from_db()
        assert domain_approve(room, keeper, retry).status == AttemptStatus.GRANTING

    @pytest.mark.parametrize("action", ["admit_all", "settings"])
    @pytest.mark.django_db(transaction=True)
    def test_batch_capacity_reports_per_person_and_snapshot_excludes_waiters(self, capacity_context, action):
        session, room, keeper = capacity_context
        session.seats = 2
        session.save(update_fields=["seats"])
        first, second = add_users(session, 2)
        for user in (first, second):
            capacity_admission.prepare_admission_join(session.slug, user, connected=set())
        room.refresh_from_db()
        if action == "admit_all":
            body = BatchCommandInput(command_id=uuid4(), expected_room_version=room.state_version)
        else:
            body = SettingsCommandInput(
                command_id=uuid4(),
                expected_room_version=room.state_version,
                expected_revision=room.admission_revision,
                approval_required=False,
            )
        with patch.object(
            admission_http, "get_room_participant_sids", return_value={first.slug: "first", second.slug: "second"}
        ):
            response = admission_http.execute_keeper_command(session.slug, keeper, action, body)
        results = {item.identity: item for item in response.results}
        assert results[first.slug].outcome == "approved"
        assert results[first.slug].error is None
        assert results[second.slug].outcome == "skipped"
        assert results[second.slug].error == "admission_full"
        assert response.partial_failure
        assert response.snapshot.admission_capacity == 2
        assert response.snapshot.admission_slots_used == 2
        assert response.snapshot.waiting_slots_used == 1
        assert [item.identity for item in response.snapshot.waiting] == [second.slug]
        assert (
            AdmissionAttempt.objects.get(admission__session=session, admission__user=second).status
            == AttemptStatus.PENDING
        )

    @pytest.mark.django_db(transaction=True)
    def test_removed_new_request_stays_pending_when_policy_already_off(self, capacity_context):
        session, room, keeper = capacity_context
        (user,) = add_users(session, 1)
        member = SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.REVOKED)
        capacity_admission.update_approval_required(
            session.slug,
            keeper,
            False,
            expected_revision=room.admission_revision,
            expected_room_version=room.state_version,
        )
        first = capacity_request(session, user)
        room.refresh_from_db()
        capacity_admission.update_approval_required(
            session.slug,
            keeper,
            False,
            expected_revision=room.admission_revision,
            expected_room_version=room.state_version,
        )
        second = capacity_request(session, user)
        first.refresh_from_db()
        member.refresh_from_db()
        assert first.status == AttemptStatus.SUPERSEDED
        assert second.status == AttemptStatus.PENDING
        assert member.state == AdmissionState.REVOKED
        room.refresh_from_db()
        assert domain_approve(room, keeper, second).status == AttemptStatus.GRANTING
        member.refresh_from_db()
        assert member.state == AdmissionState.ADMITTED

    @pytest.mark.django_db(transaction=True)
    def test_waiting_limit_retains_request_and_refresh_does_not_use_extra_slot(self, capacity_context):
        session, _, _ = capacity_context
        users = add_users(session, 6)
        before = timezone.now()
        responses = [
            capacity_admission.prepare_admission_join(session.slug, user, connected=set()) for user in users[:5]
        ]
        after = timezone.now()
        attempts = list(AdmissionAttempt.objects.filter(admission__session=session))
        assert len(attempts) == 5
        assert all(
            before + timedelta(seconds=60) <= a.token_expires_at <= after + timedelta(seconds=60) for a in attempts
        )
        capacity_admission.prepare_admission_join(session.slug, users[0], connected=set())
        with pytest.raises(capacity_admission.AdmissionError) as error:
            capacity_admission.prepare_admission_join(session.slug, users[5], connected=set())
        assert error.value.code == "waiting_full"
        assert (
            AdmissionAttempt.objects.get(admission__session=session, admission__user=users[5]).status
            == AttemptStatus.PENDING
        )
        assert len(responses) == 5

    @pytest.mark.django_db(transaction=True)
    def test_raw_presence_counts_waiters_and_an_expired_lease_is_reusable(self, capacity_context):
        session, _, _ = capacity_context
        first, second = add_users(session, 2)
        capacity_admission.prepare_admission_join(session.slug, first, connected=set())
        attempt = AdmissionAttempt.objects.get(admission__session=session, admission__user=first)
        attempt.token_expires_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["token_expires_at"])
        raw = {f"waiting-{i}" for i in range(5)}
        with pytest.raises(capacity_admission.AdmissionError) as error:
            capacity_admission.prepare_admission_join(session.slug, second, connected=raw)
        assert error.value.code == "waiting_full"
        result = capacity_admission.prepare_admission_join(session.slug, second, connected=set())
        assert result.admission is not None
        assert result.admission.permissions == "waiting"

    @pytest.mark.django_db(transaction=True)
    def test_physical_full_keeps_admitted_request(self, capacity_context):
        session, _, keeper = capacity_context
        (user,) = add_users(session, 1)
        SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.ADMITTED)
        connected = {keeper.slug} | {f"occupant-{i}" for i in range(14)}
        with pytest.raises(capacity_admission.AdmissionError) as error:
            capacity_admission.prepare_admission_join(session.slug, user, connected=connected)
        assert error.value.code == "room_full"
        assert (
            AdmissionAttempt.objects.get(admission__session=session, admission__user=user).status
            == AttemptStatus.GRANTING
        )

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_approvals_compete_for_last_seat(self, capacity_context):
        session, room, keeper = capacity_context
        session.seats = 2
        session.save(update_fields=["seats"])
        attempts = [capacity_request(session, user) for user in add_users(session, 2)]
        barrier = Barrier(2)

        def worker(attempt):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:
                    return domain_approve(room, keeper, attempt).status
                except capacity_admission.AdmissionError as error:
                    return error.code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(worker, attempts))
        assert sorted(results) == ["admission_full", AttemptStatus.GRANTING]
        assert SessionAdmission.objects.filter(session=session, state=AdmissionState.ADMITTED).count() == 1
        assert AdmissionAttempt.objects.filter(admission__session=session, status=AttemptStatus.PENDING).count() == 1

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_waiting_tokens_never_exceed_five(self, capacity_context):
        session, _, _ = capacity_context
        users = add_users(session, 6)
        barrier = Barrier(6)

        def worker(user):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:
                    capacity_admission.prepare_admission_join(session.slug, user, connected=set())
                    return "issued"
                except capacity_admission.AdmissionError as error:
                    return error.code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(worker, users))
        assert results.count("issued") == 5
        assert results.count("waiting_full") == 1
        assert AdmissionAttempt.objects.filter(admission__session=session, status=AttemptStatus.PENDING).count() == 6
        assert (
            AdmissionAttempt.objects.filter(admission__session=session, token_expires_at__gt=timezone.now()).count()
            == 5
        )

    @pytest.fixture
    def livekit_api(self):
        client = MagicMock()
        client.room.send_data = AsyncMock()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)
        with patch.object(livekit, "_get_api", return_value=context) as get_api:
            yield client, get_api

    def test_notification_is_reliable_targeted_and_contains_no_decision(self, livekit_api):
        client, _ = livekit_api

        assert livekit.publish_admission_changed("session", 42, ["keeper", "attendee", "keeper"]) is True

        client.room.send_data.assert_awaited_once()
        packet = client.room.send_data.await_args.args[0]
        assert packet.room == "session"
        assert packet.topic == "totem.admission.v2"
        assert packet.kind == api.DataPacket.Kind.RELIABLE
        assert list(packet.destination_identities) == ["keeper", "attendee"]
        assert json.loads(packet.data) == {"type": "admission.changed", "session_slug": "session", "version": 42}

    def test_empty_destinations_never_broadcast(self, livekit_api):
        _, get_api = livekit_api
        assert livekit.publish_admission_changed("session", 1, []) is True
        get_api.assert_not_called()

    def test_missing_room_notification_is_expected_before_first_connection(self, livekit_api, caplog):
        client, _ = livekit_api
        client.room.send_data.side_effect = api.TwirpError(
            code="not_found", msg="requested room does not exist", status=404
        )
        with caplog.at_level(logging.INFO, logger=livekit.__name__):
            assert livekit.publish_admission_changed("session", 1, ["keeper"]) is False
        assert all(record.levelno < logging.WARNING for record in caplog.records)
        assert any("room" in record.getMessage().lower() for record in caplog.records)

    @pytest.mark.parametrize("error", [OSError("offline"), livekit.LiveKitPermissionError("unavailable", "offline")])
    def test_notification_failure_is_best_effort(self, livekit_api, caplog, error):
        client, _ = livekit_api
        client.room.send_data.side_effect = error
        with caplog.at_level(logging.WARNING, logger=livekit.__name__):
            assert livekit.publish_admission_changed("session", 1, ["keeper"]) is False
        assert caplog.records

    def test_notification_times_out(self, livekit_api, caplog):
        client, _ = livekit_api

        async def wait_forever(*args):
            await asyncio.Event().wait()

        client.room.send_data.side_effect = wait_forever
        timeout = asyncio.timeout
        with (
            patch.object(livekit.asyncio, "timeout", side_effect=lambda seconds: timeout(0.01)) as timeout_mock,
            caplog.at_level(logging.WARNING, logger=livekit.__name__),
        ):
            assert livekit.publish_admission_changed("session", 1, ["keeper"]) is False
        timeout_mock.assert_called_once_with(5)
        assert caplog.records


class TestAdmissionHttp:
    @pytest.fixture
    def context(self, client_with_user):
        client, user = client_with_user
        keeper = UserFactory()
        session = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=timezone.now() - timedelta(minutes=1),
        )
        session.attendees.add(keeper, user)
        room = Room.objects.get_or_create_for_session(session)
        keeper_client = Client(HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(keeper)}")
        return client, user, keeper_client, keeper, session, room

    @pytest.fixture
    def livekit(self):
        def participant(room_name, identity):
            assert not connection.in_atomic_block
            return api.ParticipantInfo(
                identity=identity,
                sid=f"sid-{identity}",
                permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
            )

        def update(*args, **kwargs):
            assert not connection.in_atomic_block
            return participant(args[0], args[1])

        with (
            patch("totem.rooms.admission.services.get_room_participant_sids", return_value={}) as presence,
            patch("totem.rooms.admission.services.get_participant_snapshot", side_effect=participant, create=True),
            patch("totem.rooms.admission.permissions.get_participant_snapshot", side_effect=participant),
            patch("totem.rooms.admission.permissions.update_participant_permissions", side_effect=update),
            patch("totem.rooms.admission.permissions.hard_disconnect_participant"),
            patch("totem.rooms.state_machine.publish_state"),
        ):
            yield presence

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize("method,suffix,body,keeper_only", [case for case in endpoint_cases() if case[0] != "get"])
    @pytest.mark.parametrize("existing_room", [False, True])
    def test_mutations_reject_non_livekit_without_side_effects(
        self, context, livekit, admission_notification_transport, method, suffix, body, keeper_only, existing_room
    ):
        client, user, keeper_client, _, session, room = context
        if existing_room:
            request_attempt(context)
            attempt = AdmissionAttempt.objects.get(admission__session=session)
            attempt.expires_at = timezone.now() - timedelta(seconds=1)
            attempt.save(update_fields=["expires_at"])
        else:
            room.delete()
        session.space.meeting_provider = Space.MeetingProviderChoices.GOOGLE_MEET
        session.space.save(update_fields=["meeting_provider"])
        models = (Room, SessionAdmission, AdmissionAttempt, AdmissionCommand, AdmissionPermissionSync)
        before = [list(model.objects.order_by("pk").values()) for model in models]
        livekit.reset_mock()
        admission_notification_transport.reset_mock()

        response = send(
            keeper_client if keeper_only else client,
            method,
            f"{BASE}/{session.slug}/admission{suffix.replace('target', user.slug)}",
            body,
        )

        assert response.status_code == 404, response.content
        assert [list(model.objects.order_by("pk").values()) for model in models] == before
        livekit.assert_not_called()
        admission_notification_transport.assert_not_called()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize("method,suffix,body,keeper_only", endpoint_cases())
    def test_unauthenticated_endpoints(self, context, method, suffix, body, keeper_only):
        _, _, _, _, session, _ = context
        url = f"{BASE}/{session.slug}/admission{suffix}"
        response = send(Client(), method, url, body)
        assert response.status_code == 401

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize("method,suffix,body,keeper_only", [case for case in endpoint_cases() if case[3]])
    def test_keeper_endpoints_reject_non_keeper(self, context, livekit, method, suffix, body, keeper_only):
        client, _, _, _, session, _ = context
        response = send(client, method, f"{BASE}/{session.slug}/admission{suffix}", body)
        assert response.status_code == 403, response.content

    @pytest.mark.django_db(transaction=True)
    def test_readiness_no_record_and_pending(self, context, livekit):
        client, user, keeper_client, _, session, _ = context
        url = f"{BASE}/{session.slug}/admission"
        response = client.get(f"{url}/me")
        assert response.status_code == 200, response.content
        assert response.json()["me"] is None
        assert response.json()["readiness"] == {"state": "requires_new_attempt", "reason": "no_request"}

        ids, _ = request_attempt(context)
        response = client.get(f"{url}/me")
        snapshot = keeper_client.get(url)
        assert response.status_code == snapshot.status_code == 200
        expected = {"state": "waiting_for_approval", "reason": "approval_required"}
        assert response.json()["readiness"] == response.json()["me"]["readiness"] == expected
        participant = next(p for p in snapshot.json()["participants"] if p["identity"] == user.slug)
        assert participant["request_id"] == ids["request_id"]
        assert participant["readiness"] == expected
        assert snapshot.json()["waiting"][0]["readiness"] == expected
        assert snapshot.json()["requests"][0]["readiness"] == expected

    @pytest.mark.django_db(transaction=True)
    def test_readiness_grant_revisions_activation_and_revoke(self, context, livekit):
        client, user, keeper_client, _, session, room = context
        url = f"{BASE}/{session.slug}/admission"
        ids, attempt = request_attempt(context)
        approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, attempt))
        assert approved.status_code == 200, approved.content
        me = client.get(f"{url}/me").json()
        assert me["readiness"] == {"state": "applying_permissions", "reason": "connection_required"}
        assert me["me"]["readiness"] == me["readiness"]

        livekit.return_value = {user.slug: f"sid-{user.slug}"}
        connected = post(client, f"{url}/request", {**ids, "connected": True})
        assert connected.status_code == 200, connected.content
        assert connected.json()["readiness"] == {"state": "ready_to_activate", "reason": None}
        sync = AdmissionPermissionSync.objects.get(admission__session=session, admission__user=user)
        assert sync.applied_revision == sync.revision
        sync.revision += 1
        sync.save(update_fields=["revision"])
        me = client.get(f"{url}/me").json()
        assert me["readiness"] == {"state": "applying_permissions", "reason": "permission_pending"}
        assert me["me"]["permission_revision"] > me["me"]["applied_permission_revision"]
        sync.applied_revision = sync.revision
        sync.save(update_fields=["applied_revision"])
        me = client.get(f"{url}/me").json()
        assert me["readiness"] == {"state": "ready_to_activate", "reason": None}
        activated = post(client, f"{url}/activated", {**ids, "expected_version": me["me"]["attempt_version"]})
        assert activated.status_code == 200, activated.content
        assert activated.json()["readiness"] == {"state": "activated", "reason": None}

        membership = SessionAdmission.objects.get(session=session, user=user)
        room.refresh_from_db()
        revoked = post(
            keeper_client,
            f"{url}/{user.slug}/revoke",
            {
                "command_id": str(uuid4()),
                "expected_version": membership.version,
                "expected_room_version": room.state_version,
            },
        )
        assert revoked.status_code == 200, revoked.content
        me = client.get(f"{url}/me").json()
        assert me["readiness"] == me["me"]["readiness"] == {"state": "blocked", "reason": "requires_reapproval"}
        room.status = RoomStatus.ENDED
        room.end_reason = EndReason.KEEPER_ENDED
        room.save(update_fields=["status", "end_reason"])
        ended = client.get(f"{url}/me")
        assert ended.status_code == 200, ended.content
        assert (
            ended.json()["readiness"]
            == ended.json()["me"]["readiness"]
            == {"state": "ended", "reason": "session_ended"}
        )

    @pytest.mark.django_db(transaction=True)
    def test_readiness_current_and_historical_attempts(self, context, livekit):
        client, user, keeper_client, _, session, _ = context
        url = f"{BASE}/{session.slug}/admission"
        old_ids, attempt = request_attempt(context)
        cancelled = post(client, f"{url}/cancel", {**old_ids, "expected_version": attempt["attempt_version"]})
        assert cancelled.status_code == 200, cancelled.content
        assert cancelled.json()["readiness"] == {"state": "requires_new_attempt", "reason": "request_cancelled"}
        new_ids, _ = request_attempt(context)
        snapshot = keeper_client.get(url)
        assert snapshot.status_code == 200, snapshot.content
        data = snapshot.json()
        current = next(p for p in data["participants"] if p["identity"] == user.slug)
        history = {p["attempt_id"]: p for p in data["requests"] if p["identity"] == user.slug}
        expected = {"state": "waiting_for_approval", "reason": "approval_required"}
        assert current["attempt_id"] == new_ids["attempt_id"]
        assert current["readiness"] == history[new_ids["attempt_id"]]["readiness"] == expected
        assert history[old_ids["attempt_id"]]["readiness"] is None

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize("suffix", ["", "/me"])
    def test_snapshot_without_room_does_not_create_one(self, client_with_user, livekit, suffix):
        client, user = client_with_user
        session = SessionFactory(space__author=user, space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT)
        session.attendees.add(user)
        response = client.get(f"{BASE}/{session.slug}/admission{suffix}")
        assert response.status_code == 200, response.content
        assert response.json()["keeper"] == user.slug
        assert not Room.objects.filter(session=session).exists()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize("suffix", ["", "/me"])
    def test_snapshot_rejects_non_livekit_without_creating_room(self, client_with_user, livekit, suffix):
        client, user = client_with_user
        session = SessionFactory(space__author=user, space__meeting_provider=Space.MeetingProviderChoices.GOOGLE_MEET)
        response = client.get(f"{BASE}/{session.slug}/admission{suffix}")
        assert response.status_code == 404
        assert not Room.objects.filter(session=session).exists()
        livekit.assert_not_called()

    @pytest.mark.django_db(transaction=True)
    def test_snapshot_projects_expiry_without_writes(self, context, livekit, admission_notification_transport):
        client, user, keeper_client, _, session, room = context
        request_attempt(context)
        attempt = AdmissionAttempt.objects.get(admission__session=session, admission__user=user)
        attempt.expires_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["expires_at"])
        room.refresh_from_db()
        original_version = room.admission_version
        admission_notification_transport.reset_mock()
        url = f"{BASE}/{session.slug}/admission"
        snapshot = keeper_client.get(url)
        me = client.get(f"{url}/me")
        assert snapshot.status_code == me.status_code == 200
        assert snapshot.json()["pending_count"] == 0
        assert snapshot.json()["waiting"] == []
        assert me.json()["me"]["status"] == "expired"
        attempt.refresh_from_db()
        room.refresh_from_db()
        assert attempt.status == AttemptStatus.PENDING
        assert room.admission_version == original_version
        admission_notification_transport.assert_not_called()

    @pytest.mark.django_db(transaction=True)
    def test_snapshot_rechecks_keeper_after_presence(self, context, livekit):
        _, _, keeper_client, _, session, room = context
        replacement = UserFactory()

        def reassign(_slug):
            Room.objects.filter(pk=room.pk).update(keeper=replacement.slug)
            return {}

        livekit.side_effect = reassign
        assert keeper_client.get(f"{BASE}/{session.slug}/admission").status_code == 403

    @pytest.mark.django_db(transaction=True)
    def test_snapshot_rechecks_access_after_assembling(self, context, livekit):
        from totem.rooms.admission import services as http

        _, _, keeper_client, _, session, room = context
        request_attempt(context)
        replacement = UserFactory()
        participant = http._participant

        def reassign(*args, **kwargs):
            result = participant(*args, **kwargs)
            Room.objects.filter(pk=room.pk).update(keeper=replacement.slug)
            return result

        with patch.object(http, "_participant", side_effect=reassign):
            response = keeper_client.get(f"{BASE}/{session.slug}/admission")
        assert response.status_code == 403

    @pytest.mark.django_db(transaction=True)
    def test_snapshot_recipients_follow_activation_presence_and_revocation(self, context, livekit):
        client, user, keeper_client, keeper, session, room = context
        url = f"{BASE}/{session.slug}/admission"
        ids, attempt = request_attempt(context)
        livekit.return_value = {keeper.slug: "keeper-sid", user.slug: f"sid-{user.slug}", "unrecognized": "other-sid"}
        livekit.reset_mock()
        before = timezone.now()
        pending = keeper_client.get(url).json()
        assert before <= parse_datetime(pending["observed_at"]) <= timezone.now()
        livekit.assert_called_once_with(session.slug)
        assert pending["admitted_recipients"] == [keeper.slug]
        assert pending["room_state"]["version"] == pending["room_version"]
        assert pending["room_state"]["keeper"] == pending["keeper"]

        assert post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, attempt)).status_code == 200
        assert keeper_client.get(url).json()["admitted_recipients"] == [keeper.slug]
        connected = post(client, f"{url}/request", {**ids, "connected": True}).json()
        activated = post(client, f"{url}/activated", {**ids, "expected_version": connected["me"]["attempt_version"]})
        assert activated.status_code == 200, activated.content
        assert activated.json()["admitted_recipients"] == sorted([keeper.slug, user.slug])
        # The same identity on a replacement connection is not the activated SID.
        livekit.return_value = {keeper.slug: "new-keeper-sid", user.slug: "replacement-sid"}
        replacement = client.get(f"{url}/me").json()
        assert replacement["me"]["connected"] is True
        assert replacement["admitted_recipients"] == [keeper.slug]
        attempt_row = AdmissionAttempt.objects.get(request_id=ids["request_id"])
        attempt_row.participant_sid = ""
        attempt_row.save(update_fields=["participant_sid"])
        livekit.return_value = {keeper.slug: "keeper-sid", user.slug: ""}
        assert client.get(f"{url}/me").json()["admitted_recipients"] == [keeper.slug]
        livekit.return_value = {keeper.slug: "keeper-sid"}
        assert client.get(f"{url}/me").json()["admitted_recipients"] == [keeper.slug]
        livekit.return_value = {keeper.slug: "keeper-sid", user.slug: f"sid-{user.slug}"}
        membership = SessionAdmission.objects.get(session=session, user=user)
        room.refresh_from_db()
        result = post(
            keeper_client,
            f"{url}/{user.slug}/revoke",
            {
                "command_id": str(uuid4()),
                "expected_version": membership.version,
                "expected_room_version": room.state_version,
            },
        )
        assert result.status_code == 200, result.content
        assert result.json()["snapshot"]["admitted_recipients"] == [keeper.slug]

    @pytest.mark.django_db(transaction=True)
    def test_snapshot_serializes_room_and_admission_reads(self, context, livekit):
        from totem.rooms.admission import services as http
        from totem.spaces.models import Session

        _, _, keeper_client, _, session, room = context
        request_attempt(context)
        assembling = Event()
        attempted = Event()
        committed = Event()
        participant = http._participant

        def pause(*args, **kwargs):
            assembling.set()
            assert attempted.wait(5)
            assert not committed.wait(0.2)
            return participant(*args, **kwargs)

        def writer():
            close_old_connections()
            try:
                assert assembling.wait(5)
                with transaction.atomic():
                    attempted.set()
                    Session.objects.select_for_update().get(pk=session.pk)
                    Room.objects.filter(pk=room.pk).update(state_version=room.state_version + 1)
                committed.set()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool, patch.object(http, "_participant", side_effect=pause):
            future = pool.submit(writer)
            response = keeper_client.get(f"{BASE}/{session.slug}/admission")
            future.result(timeout=10)
        assert response.status_code == 200, response.content
        assert response.json()["room_version"] == response.json()["room_state"]["version"] == room.state_version
        assert committed.is_set()

    @pytest.mark.django_db(transaction=True)
    def test_snapshot_recovers_queue_and_survives_keeper_reassignment(self, context, livekit):
        _, user, keeper_client, _, session, room = context
        ids, _ = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission"
        snapshot = keeper_client.get(url)
        assert snapshot.status_code == 200, snapshot.content
        assert any(
            p["identity"] == user.slug and p["request_id"] == ids["request_id"] for p in snapshot.json()["waiting"]
        )
        replacement = UserFactory()
        session.attendees.add(replacement)
        room.keeper = replacement.slug
        room.save(update_fields=["keeper"])
        assert keeper_client.get(url).status_code == 403
        new_client = Client(HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(replacement)}")
        recovered = new_client.get(url)
        assert recovered.status_code == 200, recovered.content
        assert any(p["request_id"] == ids["request_id"] for p in recovered.json()["waiting"])

    @pytest.mark.django_db(transaction=True)
    def test_approval_replay_does_not_reverse_later_revoke_and_requires_current_keeper(self, context, livekit):
        _, user, keeper_client, _, session, room = context
        ids, attempt = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission"
        body = decision_body(room, ids, attempt)
        first = post(keeper_client, f"{url}/{user.slug}/approve", body)
        assert first.status_code == 200, first.content
        membership = SessionAdmission.objects.get(session=session, user=user)
        room.refresh_from_db()
        revoke = post(
            keeper_client,
            f"{url}/{user.slug}/revoke",
            {
                "command_id": str(uuid4()),
                "expected_version": membership.version,
                "expected_room_version": room.state_version,
            },
        )
        assert revoke.status_code == 200, revoke.content
        replay = post(keeper_client, f"{url}/{user.slug}/approve", body)
        assert replay.status_code == 200, replay.content
        assert replay.json()["replayed"] is True
        membership.refresh_from_db()
        assert membership.state == AdmissionState.REVOKED
        room.keeper = user.slug
        room.save(update_fields=["keeper"])
        assert post(keeper_client, f"{url}/{user.slug}/approve", body).status_code == 403

    @pytest.mark.django_db(transaction=True)
    def test_same_command_id_with_changed_target_or_body_conflicts(self, context, livekit):
        _, user, keeper_client, _, session, room = context
        ids, attempt = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission"
        body = decision_body(room, ids, attempt)
        assert post(keeper_client, f"{url}/{user.slug}/approve", body).status_code == 200
        assert (
            post(
                keeper_client, f"{url}/{user.slug}/approve", {**body, "expected_version": body["expected_version"] + 1}
            ).status_code
            == 409
        )
        other = UserFactory()
        assert post(keeper_client, f"{url}/{other.slug}/approve", body).status_code == 409
        assert post(keeper_client, f"{url}/{user.slug}/decline", body).status_code == 409

    @pytest.mark.django_db(transaction=True)
    def test_cancel_then_stale_approval_cannot_admit(self, context, livekit):
        client, user, keeper_client, _, session, room = context
        ids, attempt = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission"
        decision = decision_body(room, ids, attempt)
        cancelled = post(client, f"{url}/cancel", {**ids, "expected_version": attempt["attempt_version"]})
        assert cancelled.status_code == 200, cancelled.content
        assert post(keeper_client, f"{url}/{user.slug}/approve", decision).status_code == 409
        assert SessionAdmission.objects.get(session=session, user=user).state != AdmissionState.ADMITTED

    @pytest.mark.django_db(transaction=True)
    def test_presence_failure_preserves_snapshot_and_private_me(self, context, livekit):
        client, user, keeper_client, _, session, _ = context
        request_attempt(context)
        livekit.side_effect = LiveKitPermissionError("unavailable", "presence unavailable")
        url = f"{BASE}/{session.slug}/admission"
        for response in (client.get(f"{url}/me"), keeper_client.get(url)):
            assert response.status_code == 200, response.content
            assert response.json()["connected_count"] is None
            assert response.json()["admitted_recipients"] is None
            assert response.json()["presence_error"]
            assert parse_datetime(response.json()["observed_at"]) is not None
        data = client.get(f"{url}/me").json()
        assert data["me"]["identity"] == user.slug
        assert not {"participants", "waiting", "requests"} & data.keys()

    @pytest.mark.django_db(transaction=True)
    def test_decision_cannot_target_another_sessions_attempt(self, context, livekit):
        _, user, keeper_client, keeper, session, room = context
        other = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=timezone.now() - timedelta(minutes=1),
        )
        other.attendees.add(keeper, user)
        Room.objects.get_or_create_for_session(other)
        attempt = admission.request_admission(other.slug, user, uuid4(), uuid4())
        body = {
            "command_id": str(uuid4()),
            "request_id": str(attempt.request_id),
            "attempt_id": str(attempt.attempt_id),
            "expected_version": attempt.version,
            "expected_room_version": room.state_version,
        }
        response = post(keeper_client, f"{BASE}/{session.slug}/admission/{user.slug}/approve", body)
        assert response.status_code in (404, 409)
        attempt.refresh_from_db()
        assert attempt.status == "pending"

    @pytest.mark.django_db(transaction=True)
    def test_activation_requires_connected_receipt(self, context, livekit):
        client, user, keeper_client, _, session, room = context
        ids, attempt = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission"
        approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, attempt))
        assert approved.status_code == 200, approved.content
        current = client.get(f"{url}/me").json()["me"]
        response = post(client, f"{url}/activated", {**ids, "expected_version": current["attempt_version"]})
        assert response.status_code == 409
        assert response.json()["code"] == "connection_required"

    @pytest.mark.django_db(transaction=True)
    def test_connected_receipt_requires_matching_identity(self, context, livekit):
        client, _, _, _, session, _ = context
        ids, _ = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission/request"
        livekit.return_value = {"somebody-else": "other-sid"}
        with patch(
            "totem.rooms.admission.services.get_participant_snapshot",
            return_value=api.ParticipantInfo(identity="somebody-else", sid="foreign"),
            create=True,
        ):
            response = post(client, url, {**ids, "connected": True})
        assert response.status_code in (409, 503, 504)
        attempt = AdmissionAttempt.objects.get(request_id=ids["request_id"])
        assert attempt.connected_at is None

    @pytest.mark.django_db(transaction=True)
    def test_toggle_off_promotes_waiter_and_toggle_on_does_not_revoke(self, context, livekit):
        _, user, keeper_client, _, session, room = context
        request_attempt(context)
        url = f"{BASE}/{session.slug}/admission/settings"
        room.refresh_from_db()
        body = {
            "command_id": str(uuid4()),
            "approval_required": False,
            "expected_revision": room.admission_revision,
            "expected_room_version": room.state_version,
        }
        response = send(keeper_client, "patch", url, body)
        assert response.status_code == 200, response.content
        assert SessionAdmission.objects.get(session=session, user=user).state == AdmissionState.ADMITTED
        room.refresh_from_db()
        response = send(
            keeper_client,
            "patch",
            url,
            {
                **body,
                "command_id": str(uuid4()),
                "approval_required": True,
                "expected_revision": room.admission_revision,
                "expected_room_version": room.state_version,
            },
        )
        assert response.status_code == 200, response.content
        assert SessionAdmission.objects.get(session=session, user=user).state == AdmissionState.ADMITTED

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize("nested", [False, True])
    def test_connection_receipt_reconciles_once_and_same_sid_retries(self, context, livekit, nested):
        from totem.rooms.admission.services import confirm_connection

        _, user, _, _, session, _ = context
        ids, _ = request_attempt(context)
        attempt = AdmissionAttempt.objects.get(request_id=ids["request_id"])
        args = (session.slug, user, UUID(ids["request_id"]), UUID(ids["attempt_id"]))
        participant = api.ParticipantInfo(identity=user.slug, sid="new-sid")
        with (
            patch("totem.rooms.admission.services.get_participant_snapshot", return_value=participant),
            patch("totem.rooms.admission.permissions.reconcile_admission_permissions") as reconcile,
        ):
            if nested:
                with transaction.atomic():
                    confirm_connection(*args)
                    reconcile.assert_not_called()
                reconcile.assert_called_once_with(attempt.admission_id)
            else:
                confirm_connection(*args)
                reconcile.assert_called_once_with(attempt.admission_id)

            reconcile.reset_mock()
            confirm_connection(*args)
            reconcile.assert_called_once_with(attempt.admission_id)
            attempt.refresh_from_db()
            assert attempt.participant_sid == "new-sid"

    @pytest.mark.django_db(transaction=True)
    def test_connected_receipt_activation_and_duplicate_are_idempotent(self, context, livekit):
        client, user, keeper_client, _, session, room = context
        url = f"{BASE}/{session.slug}/admission"
        ids, attempt = request_attempt(context)
        initial_version = client.get(f"{url}/me").json()["version"]
        livekit.return_value = {user.slug: f"sid-{user.slug}"}
        connected = post(client, f"{url}/request", {**ids, "connected": True})
        assert connected.status_code == 200, connected.content
        assert connected.json()["me"]["connected_at"] is not None
        assert connected.json()["activated_count"] == 0
        assert connected.json()["version"] > initial_version
        attempt = connected.json()["me"]
        approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, attempt))
        assert approved.status_code == 200, approved.content
        assert approved.json()["snapshot"]["activated_count"] == 0
        assert approved.json()["snapshot"]["version"] > connected.json()["version"]
        current = client.get(f"{url}/me").json()["me"]
        receipt = {**ids, "expected_version": current["attempt_version"]}
        activated = post(client, f"{url}/activated", receipt)
        assert activated.status_code == 200, activated.content
        data = activated.json()
        assert data["me"]["status"] == "activated"
        assert data["activated_count"] == 1
        assert data["version"] > approved.json()["snapshot"]["version"]
        duplicate = post(client, f"{url}/activated", receipt)
        assert duplicate.status_code == 200, duplicate.content
        assert duplicate.json()["activated_count"] == 1
        assert duplicate.json()["version"] == data["version"]
        assert duplicate.json()["me"]["activated_at"] == data["me"]["activated_at"]
        assert session.joined.filter(pk=user.pk).count() == 1

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize("code", ["participant_missing", "disconnected"])
    def test_failed_connection_receipt_keeps_waiter_in_queue(self, context, livekit, code):
        client, user, keeper_client, _, session, _ = context
        ids, _ = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission"
        with patch(
            "totem.rooms.admission.services.get_participant_snapshot", side_effect=LiveKitPermissionError(code, code)
        ):
            response = post(client, f"{url}/request", {**ids, "connected": True})
        assert response.status_code == 409
        assert response.json()["code"] == code
        attempt = AdmissionAttempt.objects.get(request_id=ids["request_id"])
        assert attempt.connected_at is None
        snapshot = keeper_client.get(url)
        assert snapshot.status_code == 200
        assert any(
            p["identity"] == user.slug and p["request_id"] == ids["request_id"] for p in snapshot.json()["waiting"]
        )

    @pytest.mark.django_db(transaction=True)
    def test_reconnection_receipt_replaces_sid_and_allows_activation(self, context, livekit):
        client, user, keeper_client, _, session, room = context
        ids, _ = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission"
        livekit.return_value = {user.slug: f"sid-{user.slug}"}
        first = post(client, f"{url}/request", {**ids, "connected": True})
        assert first.status_code == 200, first.content
        approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, first.json()["me"]))
        assert approved.status_code == 200, approved.content

        def replacement(room_name, identity):
            assert not connection.in_atomic_block
            return api.ParticipantInfo(
                identity=identity,
                sid="replacement-sid",
                permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
            )

        with (
            patch("totem.rooms.admission.services.get_participant_snapshot", side_effect=replacement),
            patch("totem.rooms.admission.permissions.get_participant_snapshot", side_effect=replacement),
            patch(
                "totem.rooms.admission.permissions.update_participant_permissions",
                side_effect=lambda room_name, identity, **kwargs: replacement(room_name, identity),
            ),
        ):
            reconnected = post(client, f"{url}/request", {**ids, "connected": True})
            assert reconnected.status_code == 200, reconnected.content
            assert reconnected.json()["me"]["attempt_version"] > first.json()["me"]["attempt_version"]
            assert AdmissionAttempt.objects.get(request_id=ids["request_id"]).participant_sid == "replacement-sid"
            activated = post(
                client, f"{url}/activated", {**ids, "expected_version": reconnected.json()["me"]["attempt_version"]}
            )
            assert activated.status_code == 200, activated.content
            assert activated.json()["me"]["status"] == "activated"

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize(
        ("state", "eligible", "seats", "error"),
        [
            (AdmissionState.REVOKED, True, 2, "requires_reapproval"),
            (AdmissionState.REVOKED, False, 2, "not_eligible"),
            (AdmissionState.PERMANENTLY_DECLINED, True, 2, "not_eligible"),
            (AdmissionState.NONE, True, 1, "admission_full"),
        ],
    )
    def test_settings_reports_why_pending_attempt_was_skipped(self, context, livekit, state, eligible, seats, error):
        _, user, keeper_client, _, session, room = context
        request_attempt(context)
        SessionAdmission.objects.filter(session=session, user=user).update(state=state)
        if not eligible:
            session.attendees.remove(user)
        session.seats = seats
        session.save(update_fields=["seats"])
        room.refresh_from_db()
        response = send(
            keeper_client,
            "patch",
            f"{BASE}/{session.slug}/admission/settings",
            {
                "command_id": str(uuid4()),
                "expected_room_version": room.state_version,
                "expected_revision": room.admission_revision,
                "approval_required": False,
            },
        )
        assert response.status_code == 200, response.content
        result = response.json()["results"][0]
        assert (result["identity"], result["outcome"], result["error"]) == (user.slug, "skipped", error)

    @pytest.mark.django_db(transaction=True)
    def test_settings_reports_domain_capacity_error_and_replays_it(self, context, livekit):
        _, user, keeper_client, _, session, room = context
        request_attempt(context)
        session.seats = 10
        session.save(update_fields=["seats"])
        room.refresh_from_db()
        url = f"{BASE}/{session.slug}/admission/settings"
        body = {
            "command_id": str(uuid4()),
            "expected_room_version": room.state_version,
            "expected_revision": room.admission_revision,
            "approval_required": False,
        }
        with patch(
            "totem.rooms.admission.ensure_admission_capacity",
            side_effect=admission.AdmissionError("admission_full", "capacity check failed"),
        ):
            response = send(keeper_client, "patch", url, body)
        assert response.status_code == 200, response.content
        result = response.json()["results"][0]
        assert (result["identity"], result["outcome"], result["error"]) == (user.slug, "skipped", "admission_full")
        replay = send(keeper_client, "patch", url, body)
        assert replay.status_code == 200, replay.content
        assert replay.json()["replayed"] is True
        assert replay.json()["results"][0]["error"] == "admission_full"

    @pytest.mark.django_db(transaction=True)
    def test_settings_reports_attempt_expiring_during_command(self, context, livekit):
        _, user, keeper_client, _, session, room = context
        request_attempt(context)
        update = admission.update_approval_required

        def expire_then_update(*args, **kwargs):
            AdmissionAttempt.objects.filter(admission__session=session, admission__user=user).update(
                expires_at=timezone.now() - timedelta(seconds=1)
            )
            return update(*args, **kwargs)

        room.refresh_from_db()
        with patch("totem.rooms.admission.update_approval_required", side_effect=expire_then_update):
            response = send(
                keeper_client,
                "patch",
                f"{BASE}/{session.slug}/admission/settings",
                {
                    "command_id": str(uuid4()),
                    "expected_room_version": room.state_version,
                    "expected_revision": room.admission_revision,
                    "approval_required": False,
                },
            )
        assert response.status_code == 200, response.content
        result = response.json()["results"][0]
        assert (result["identity"], result["outcome"], result["error"]) == (user.slug, "skipped", "invalid_attempt")

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize("action", ["admit-all", "settings"])
    def test_batch_permission_timeout_is_partial_and_durable(self, context, livekit, action):
        client, user, keeper_client, _, session, room = context
        request_attempt(context)
        other = UserFactory()
        session.attendees.add(other)
        other_client = Client(HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(other)}")
        ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
        url = f"{BASE}/{session.slug}/admission"
        assert post(other_client, f"{url}/request", ids).status_code == 200

        def update(room_name, identity, **kwargs):
            assert not connection.in_atomic_block
            if identity == user.slug and kwargs["admitted"]:
                raise LiveKitPermissionError("timeout", "update timed out")
            return api.ParticipantInfo(
                identity=identity,
                sid=f"sid-{identity}",
                permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
            )

        room.refresh_from_db()
        body = {"command_id": str(uuid4()), "expected_room_version": room.state_version}
        with patch("totem.rooms.admission.permissions.update_participant_permissions", side_effect=update):
            if action == "settings":
                response = send(
                    keeper_client,
                    "patch",
                    f"{url}/settings",
                    {**body, "approval_required": False, "expected_revision": room.admission_revision},
                )
            else:
                response = post(keeper_client, f"{url}/admit-all", body)
        assert response.status_code == 200, response.content
        data = response.json()
        assert data["partial_failure"] is True
        results = {row["identity"]: row for row in data["results"]}
        assert results[user.slug]["participant"]["permission_status"] == "error"
        assert results[user.slug]["participant"]["last_error"] == "timeout"
        assert results[other.slug]["participant"]["permission_status"] == "applied"
        assert results[other.slug]["participant"]["last_error"] is None
        assert {row["identity"] for row in data["snapshot"]["participants"]} >= {user.slug, other.slug}
        sync = AdmissionPermissionSync.objects.get(admission__session=session, admission__user=user)
        assert sync.applied_revision != sync.revision
        assert sync.retry_count > 0
        assert sync.next_retry_at is not None
        assert SessionAdmission.objects.get(session=session, user=other).state == AdmissionState.ADMITTED

    @pytest.mark.django_db(transaction=True)
    def test_permanent_decline_allow_does_not_admit_or_replay_decline(self, context, livekit):
        client, user, keeper_client, _, session, room = context
        ids, attempt = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission"
        body = {**decision_body(room, ids, attempt), "permanent": True}
        declined = post(keeper_client, f"{url}/{user.slug}/decline", body)
        assert declined.status_code == 200, declined.content
        membership = SessionAdmission.objects.get(session=session, user=user)
        assert membership.state == AdmissionState.PERMANENTLY_DECLINED
        room.refresh_from_db()
        allowed = post(
            keeper_client,
            f"{url}/{user.slug}/allow",
            {
                "command_id": str(uuid4()),
                "expected_version": membership.version,
                "expected_room_version": room.state_version,
            },
        )
        assert allowed.status_code == 200, allowed.content
        membership.refresh_from_db()
        assert membership.state == AdmissionState.NONE
        replay = post(keeper_client, f"{url}/{user.slug}/decline", body)
        assert replay.status_code == 200 and replay.json()["replayed"] is True
        membership.refresh_from_db()
        assert membership.state == AdmissionState.NONE
        assert client.get(f"{url}/me").json()["admitted_count"] == 0

    @pytest.mark.django_db(transaction=True)
    def test_returning_and_late_arrival_flags_are_snapshot_stable(self, context, livekit):
        client, user, keeper_client, _, session, room = context
        ids, attempt = request_attempt(context)
        room.status = "active"
        room.save(update_fields=["status"])
        url = f"{BASE}/{session.slug}/admission"
        approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, attempt))
        assert approved.status_code == 200, approved.content
        first = client.get(f"{url}/me").json()["me"]
        assert (first["returning"], first["session_started"], first["late_arrival"]) == (False, True, True)
        new_ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
        returned = post(client, f"{url}/request", new_ids)
        assert returned.status_code == 200, returned.content
        me = returned.json()["me"]
        assert (me["returning"], me["session_started"], me["late_arrival"]) == (True, True, False)
        assert client.get(f"{url}/me").json()["me"]["attempt_id"] == new_ids["attempt_id"]

    @pytest.mark.django_db(transaction=True)
    def test_banned_and_wrong_identity_decisions_do_not_admit(self, context, livekit):
        _, user, keeper_client, _, session, room = context
        ids, attempt = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission"
        other = UserFactory()
        session.attendees.add(other)
        body = decision_body(room, ids, attempt)
        assert post(keeper_client, f"{url}/{other.slug}/approve", body).status_code == 409
        room.banned_participants = [user.slug]
        room.save(update_fields=["banned_participants"])
        assert post(keeper_client, f"{url}/{user.slug}/approve", body).status_code == 403
        assert SessionAdmission.objects.get(session=session, user=user).state == AdmissionState.NONE

    @pytest.mark.django_db(transaction=True)
    def test_me_does_not_disclose_other_waiting_participant(self, context, livekit):
        client, _, keeper_client, _, session, _ = context
        request_attempt(context)
        other = UserFactory()
        session.attendees.add(other)
        other_client = Client(HTTP_AUTHORIZATION=f"Bearer {generate_jwt_token(other)}")
        other_ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
        url = f"{BASE}/{session.slug}/admission"
        assert post(other_client, f"{url}/request", other_ids).status_code == 200
        me = client.get(f"{url}/me")
        assert me.status_code == 200
        assert me.json()["pending_count"] == 2
        assert other.slug not in me.content.decode()
        assert other_ids["request_id"] not in me.content.decode()
        assert other_ids["attempt_id"] not in me.content.decode()
        assert len(keeper_client.get(url).json()["waiting"]) == 2

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize("duplicate", [True, False])
    def test_concurrent_http_decisions_are_serialized(self, context, livekit, duplicate):
        _, user, _, keeper, session, room = context
        ids, attempt = request_attempt(context)
        body = decision_body(room, ids, attempt)
        url = f"{BASE}/{session.slug}/admission/{user.slug}"
        token = generate_jwt_token(keeper)
        barrier = Barrier(2, timeout=10)

        def decide(action, payload):
            close_old_connections()
            try:
                client = Client(HTTP_AUTHORIZATION=f"Bearer {token}")
                barrier.wait()
                response = post(client, f"{url}/{action}", payload)
                return response.status_code, response.json()
            finally:
                close_old_connections()

        second_action = "approve" if duplicate else "decline"
        second_body = body if duplicate else {**body, "command_id": str(uuid4())}
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(decide, "approve", body), executor.submit(decide, second_action, second_body)]
            responses = [future.result(timeout=30) for future in futures]
        if duplicate:
            assert [status for status, _ in responses] == [200, 200]
            assert sorted(data["replayed"] for _, data in responses) == [False, True]
        else:
            assert sorted(status for status, _ in responses) == [200, 409]
        assert AdmissionCommand.objects.filter(session=session).count() == 1
        attempt = AdmissionAttempt.objects.get(request_id=ids["request_id"])
        assert attempt.status in ("granting", "declined")

    @pytest.mark.django_db(transaction=True)
    def test_out_of_order_connection_receipt_cannot_overwrite_newer_sid(self, context, livekit):
        from totem.rooms.admission.services import confirm_connection

        client, user, _, _, session, _ = context
        ids, _ = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission/request"
        calls = 0

        def observe(room_name, identity):
            nonlocal calls
            assert not connection.in_atomic_block
            calls += 1
            if calls == 1:
                confirm_connection(session.slug, user, UUID(ids["request_id"]), UUID(ids["attempt_id"]))
                return api.ParticipantInfo(identity=identity, sid="old-sid")
            return api.ParticipantInfo(identity=identity, sid="new-sid")

        with patch("totem.rooms.admission.services.get_participant_snapshot", side_effect=observe):
            response = post(client, url, {**ids, "connected": True})
        assert response.status_code == 409, response.content
        assert response.json()["code"] == "stale_version"
        attempt = AdmissionAttempt.objects.get(request_id=ids["request_id"])
        assert attempt.participant_sid == "new-sid"
        assert attempt.connected_at is not None

    @pytest.mark.django_db(transaction=True)
    def test_connection_receipt_accepts_approval_during_presence_lookup(self, context, livekit):
        client, user, keeper_client, _, session, room = context
        ids, attempt = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission"

        def observe(room_name, identity):
            response = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, attempt))
            assert response.status_code == 200, response.content
            return api.ParticipantInfo(identity=identity, sid=f"sid-{identity}")

        with patch("totem.rooms.admission.services.get_participant_snapshot", side_effect=observe):
            response = post(client, f"{url}/request", {**ids, "connected": True})
        assert response.status_code == 200, response.content
        assert response.json()["me"]["connected_at"] is not None
        assert SessionAdmission.objects.get(session=session, user=user).state == AdmissionState.ADMITTED

    @pytest.mark.django_db(transaction=True)
    def test_batch_in_progress_lease_is_partial_failure(self, context, livekit):
        _, user, keeper_client, _, session, room = context
        request_attempt(context)
        sync = AdmissionPermissionSync.objects.get(admission__session=session, admission__user=user)
        sync.operation_id = uuid4()
        sync.lease_until = timezone.now() + timedelta(minutes=1)
        sync.save(update_fields=["operation_id", "lease_until"])
        room.refresh_from_db()
        response = post(
            keeper_client,
            f"{BASE}/{session.slug}/admission/admit-all",
            {"command_id": str(uuid4()), "expected_room_version": room.state_version},
        )
        assert response.status_code == 200, response.content
        assert response.json()["partial_failure"] is True
        result = response.json()["results"][0]
        assert result["identity"] == user.slug
        assert result["participant"]["permission_status"] == "in_progress"
        assert result["participant"]["last_error"] is None
        sync.refresh_from_db()
        assert sync.operation_id is not None
        assert sync.applied_revision != sync.revision

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize("foreign", [False, True])
    def test_connected_request_rejects_unknown_or_cross_session_ids(self, context, livekit, foreign):
        client, user, _, keeper, session, _ = context
        attempt = None
        if foreign:
            other = SessionFactory(
                space__author=keeper,
                space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
                start=timezone.now() - timedelta(minutes=1),
            )
            other.attendees.add(keeper, user)
            Room.objects.get_or_create_for_session(other)
            attempt = admission.request_admission(other.slug, user, uuid4(), uuid4())
            ids = {"request_id": str(attempt.request_id), "attempt_id": str(attempt.attempt_id)}
        else:
            ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
        response = post(client, f"{BASE}/{session.slug}/admission/request", {**ids, "connected": True})
        assert response.status_code == 409
        assert response.json()["code"] == "invalid_attempt"
        assert not SessionAdmission.objects.filter(session=session, user=user).exists()
        if foreign:
            assert attempt is not None
            attempt.refresh_from_db()
            assert attempt.connected_at is None

    @pytest.mark.django_db(transaction=True)
    def test_ended_snapshot_reads_do_not_reschedule_intents_or_notify(
        self, context, livekit, admission_notification_transport
    ):
        client, user, keeper_client, _, session, room = context
        request_attempt(context)
        room.status = "ended"
        room.end_reason = EndReason.KEEPER_ENDED
        room.save(update_fields=["status", "end_reason"])
        url = f"{BASE}/{session.slug}/admission"
        first = keeper_client.get(url)
        assert first.status_code == 200, first.content
        sync = AdmissionPermissionSync.objects.get(admission__session=session, admission__user=user)
        state = (sync.revision, sync.desired_admitted, sync.applied_revision, sync.retry_count, sync.next_retry_at)
        admission_notification_transport.reset_mock()
        for response in (client.get(f"{url}/me"), keeper_client.get(url), keeper_client.get(url)):
            assert response.status_code == 200, response.content
            assert response.json()["version"] == first.json()["version"]
        sync.refresh_from_db()
        assert (
            sync.revision,
            sync.desired_admitted,
            sync.applied_revision,
            sync.retry_count,
            sync.next_retry_at,
        ) == state
        admission_notification_transport.assert_not_called()

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_duplicate_activation_receipts(self, context, livekit):
        client, user, keeper_client, _, session, room = context
        ids, _ = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission"
        livekit.return_value = {user.slug: f"sid-{user.slug}"}
        connected = post(client, f"{url}/request", {**ids, "connected": True})
        assert connected.status_code == 200, connected.content
        approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, connected.json()["me"]))
        assert approved.status_code == 200, approved.content
        current = client.get(f"{url}/me").json()["me"]
        receipt = {**ids, "expected_version": current["attempt_version"]}
        barrier = Barrier(2, timeout=10)
        token = generate_jwt_token(user)

        def activate():
            close_old_connections()
            try:
                thread_client = Client(HTTP_AUTHORIZATION=f"Bearer {token}")
                barrier.wait()
                response = post(thread_client, f"{url}/activated", receipt)
                return response.status_code, response.json()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(activate) for _ in range(2)]
            responses = [future.result(timeout=30) for future in futures]
        assert [status for status, _ in responses] == [200, 200], responses
        assert all(data["me"]["status"] == "activated" and data["activated_count"] == 1 for _, data in responses)
        assert session.joined.filter(pk=user.pk).count() == 1

    @pytest.mark.django_db(transaction=True)
    def test_activated_replacement_uses_a_fresh_attempt_without_reconnecting(self, context, livekit):
        client, user, keeper_client, _, session, room = context
        url = f"{BASE}/{session.slug}/admission"
        ids, _ = request_attempt(context)
        livekit.return_value = {user.slug: f"sid-{user.slug}"}
        connected = post(client, f"{url}/request", {**ids, "connected": True})
        approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, connected.json()["me"]))
        assert approved.status_code == 200
        current = client.get(f"{url}/me").json()["me"]
        assert (
            post(client, f"{url}/activated", {**ids, "expected_version": current["attempt_version"]}).status_code == 200
        )
        livekit.return_value = {user.slug: "new-activated-sid"}
        assert client.get(f"{url}/me").json()["admitted_recipients"] == []

        def replacement(room_name, identity, **kwargs):
            assert not connection.in_atomic_block
            return api.ParticipantInfo(
                identity=identity,
                sid="new-activated-sid",
                permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
            )

        with (
            patch("totem.rooms.admission.services.get_participant_snapshot", side_effect=replacement),
            patch("totem.rooms.admission.permissions.get_participant_snapshot", side_effect=replacement),
            patch("totem.rooms.admission.permissions.update_participant_permissions", side_effect=replacement),
        ):
            assert post(client, f"{url}/request", {**ids, "connected": True}).status_code == 409
            fresh_ids = {"request_id": str(uuid4()), "attempt_id": str(uuid4())}
            assert post(client, f"{url}/request", fresh_ids).status_code == 200
            receipt = post(client, f"{url}/request", {**fresh_ids, "connected": True})
            assert receipt.status_code == 200, receipt.content
            assert receipt.json()["me"]["returning"] is True
            activated = post(
                client, f"{url}/activated", {**fresh_ids, "expected_version": receipt.json()["me"]["attempt_version"]}
            )
            assert activated.status_code == 200, activated.content
            assert activated.json()["me"]["status"] == "activated"
            assert activated.json()["admitted_recipients"] == [user.slug]

    @pytest.mark.django_db(transaction=True)
    def test_failed_notification_does_not_block_http_recovery(self, context, livekit, admission_notification_transport):
        client, user, keeper_client, _, session, room = context
        admission_notification_transport.side_effect = RuntimeError("missed notification")
        ids, attempt = request_attempt(context)
        url = f"{BASE}/{session.slug}/admission"
        approved = post(keeper_client, f"{url}/{user.slug}/approve", decision_body(room, ids, attempt))
        assert approved.status_code == 200, approved.content
        recovered = client.get(f"{url}/me")
        assert recovered.status_code == 200
        assert recovered.json()["me"]["admission_state"] == "admitted"
        assert recovered.json()["me"]["permission_status"] == "applied"
        assert recovered.json()["me"]["status"] == "approved"

    @pytest.mark.django_db(transaction=True)
    def test_refresh_hints_run_after_commit_and_use_current_keeper(
        self, context, livekit, admission_notification_transport
    ):
        from django.db import transaction

        _, user, _, old_keeper, session, room = context
        replacement = UserFactory()
        session.attendees.add(replacement)

        def publish(room_name, version, destinations):
            assert not connection.in_atomic_block
            assert room_name == session.slug
            assert replacement.slug in destinations
            assert old_keeper.slug not in destinations
            assert version > 0
            return True

        admission_notification_transport.side_effect = publish
        with transaction.atomic():
            admission.request_admission(session.slug, user, uuid4(), uuid4())
            admission_notification_transport.assert_not_called()
            Room.objects.filter(pk=room.pk).update(keeper=replacement.slug)
        assert admission_notification_transport.call_count > 0

    @pytest.fixture
    def setup_room(self, db):
        keeper = UserFactory()
        user = UserFactory()
        session = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=timezone.now() - timedelta(minutes=1),
        )
        session.attendees.add(keeper, user)
        room = Room.objects.get_or_create_for_session(session)
        return session, room, keeper, user

    @pytest.mark.django_db
    @pytest.mark.parametrize("is_keeper", [True, False])
    def test_record_join_requires_admission_without_mutating_join_or_order(self, setup_room, is_keeper):
        session, room, keeper, participant = setup_room
        user = keeper if is_keeper else participant
        original_order = room.talking_order.copy()
        with pytest.raises(TransitionError) as error:
            record_join(session, user)
        assert error.value.code == ErrorCode.NOT_JOINABLE
        room.refresh_from_db()
        assert not session.joined.filter(pk=user.pk).exists()
        assert room.talking_order == original_order

    @pytest.mark.django_db
    def test_record_join_admitted_succeeds_but_revoked_cannot_rejoin(self, setup_room):
        session, room, keeper, user = setup_room
        attempt = http_decide(room, keeper, http_request(session, user))
        with pytest.raises(TransitionError) as error:
            record_join(session, user)
        assert error.value.code == ErrorCode.NOT_JOINABLE
        assert not session.joined.filter(pk=user.pk).exists()

        attempt.status = AttemptStatus.ADMITTED
        attempt.participant_sid = "participant-1"
        attempt.connected_at = timezone.now()
        attempt.save(update_fields=["status", "participant_sid", "connected_at"])
        sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
        sync.applied_revision = sync.revision
        sync.participant_sid = attempt.participant_sid
        sync.save(update_fields=["applied_revision", "participant_sid"])
        record_join(session, user)
        room.refresh_from_db()
        assert session.joined.filter(pk=user.pk).exists()
        assert user.slug in room.talking_order
        revoke(room, keeper, user)
        room.refresh_from_db()
        assert user.slug not in room.talking_order
        original_order = room.talking_order.copy()
        with pytest.raises(TransitionError) as error:
            record_join(session, user)
        assert error.value.code == ErrorCode.NOT_JOINABLE
        room.refresh_from_db()
        assert room.talking_order == original_order

    @pytest.mark.django_db
    def test_remove_revokes_before_livekit_failure(self, client_with_user):
        client, keeper = client_with_user
        user = UserFactory()
        session = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=timezone.now() - timedelta(minutes=1),
        )
        session.attendees.add(keeper, user)
        room = Room.objects.get_or_create_for_session(session)
        http_decide(room, keeper, http_request(session, user))

        def fail_livekit(*args, **kwargs):
            assert require_admission(session.slug, user).state == "revoked"
            raise LiveKitConfigurationError("unavailable")

        with patch("totem.rooms.api.remove_participant", side_effect=fail_livekit) as remove:
            response = client.post(f"/api/mobile/protected/rooms/{session.slug}/remove/{user.slug}")
        assert response.status_code == 500
        remove.assert_called_once()
        assert require_admission(session.slug, user).state == "revoked"
        assert not admission.is_authorized_to_enter(session.slug, user)

    @pytest.mark.django_db
    def test_ban_revokes_admission_and_unban_does_not_restore(self, setup_room):
        session, room, keeper, user = setup_room
        attempt = http_decide(room, keeper, http_request(session, user))
        room.refresh_from_db()
        state = apply_event(
            session.slug,
            keeper.slug,
            BanParticipantEvent(participantSlug=user.slug),
            room.state_version,
            {keeper.slug, user.slug},
        )
        attempt.refresh_from_db()
        assert attempt.status == "revoked"
        assert require_admission(session.slug, user).state == "revoked"
        assert not admission.is_authorized_to_enter(session.slug, user)
        apply_event(
            session.slug, keeper.slug, UnbanParticipantEvent(participantSlug=user.slug), state.version, {keeper.slug}
        )
        room.refresh_from_db()
        assert user.slug not in room.banned_participants
        assert require_admission(session.slug, user).state == "revoked"
        assert not admission.is_authorized_to_enter(session.slug, user)

    @pytest.mark.django_db
    def test_background_end_invalidates_attempts_even_when_room_event_fails(self, setup_room):
        session, room, keeper, user = setup_room
        other = UserFactory()
        session.attendees.add(other)
        pending = http_request(session, user)
        granting = http_decide(room, keeper, http_request(session, other))
        with patch("totem.rooms.tasks.apply_event", side_effect=RuntimeError("event failed")) as event:
            _end_session(session, set())
        event.assert_called_once()
        session.refresh_from_db()
        pending.refresh_from_db()
        granting.refresh_from_db()
        assert session.ended_at is not None
        assert pending.status not in {"pending", "granting"}
        assert granting.status not in {"pending", "granting"}

    @pytest.mark.django_db
    @pytest.mark.parametrize("current_keeper_connected", [False, True])
    def test_watchdog_uses_room_keeper_not_space_author(self, setup_room, current_keeper_connected):
        session, room, author, _ = setup_room
        session.start = timezone.now() - timedelta(minutes=10)
        session.save(update_fields=["start"])
        current_keeper = UserFactory()
        room.keeper = current_keeper.slug
        room.save(update_fields=["keeper"])
        connected = {current_keeper.slug} if current_keeper_connected else {author.slug}
        with (
            patch("totem.rooms.tasks.get_admission_participants", return_value=connected),
            patch("totem.rooms.tasks.publish_state"),
        ):
            count = end_sessions_without_keeper()
        session.refresh_from_db()
        assert count == (0 if current_keeper_connected else 1)
        assert (session.ended_at is None) == current_keeper_connected

    @pytest.mark.django_db
    def test_permanent_decline_survives_temporary_keeper_role(self, setup_room):
        session, room, keeper, user = setup_room
        http_decide(room, keeper, http_request(session, user), "permanently_decline")
        assert require_admission(session.slug, user).state == "permanently_declined"
        room.keeper = user.slug
        room.save(update_fields=["keeper"])
        attempt = http_request(session, user)
        assert attempt.status == "granting"
        assert require_admission(session.slug, user).state == "permanently_declined"
        room.keeper = keeper.slug
        room.save(update_fields=["keeper"])
        assert not admission.is_authorized_to_enter(session.slug, user)
        with pytest.raises(admission.AdmissionError) as error:
            http_request(session, user)
        assert error.value.code == "not_eligible"
        assert require_admission(session.slug, user).state == "permanently_declined"

    @pytest.mark.django_db
    def test_expired_decision_persists_expiration_immediately(self, setup_room):
        session, room, keeper, user = setup_room
        attempt = http_request(session, user)
        attempt.expires_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["expires_at"])
        with pytest.raises(admission.AdmissionError):
            http_decide(room, keeper, attempt)
        attempt.refresh_from_db()
        assert attempt.status == "expired"
        assert require_admission(session.slug, user).state == "none"

    @pytest.mark.django_db
    def test_completion_rejects_other_user_and_mismatched_ids(self, setup_room):
        session, room, keeper, user = setup_room
        attempt = http_decide(room, keeper, http_request(session, user))
        other = UserFactory()
        session.attendees.add(other)
        for actor, request_id, attempt_id in [
            (other, attempt.request_id, attempt.attempt_id),
            (user, uuid4(), attempt.attempt_id),
            (user, attempt.request_id, uuid4()),
        ]:
            with pytest.raises(admission.AdmissionError) as error:
                admission.complete_admission(
                    session.slug, actor, request_id, attempt_id, expected_version=attempt.version
                )
            assert error.value.code == "invalid_attempt"
        attempt.refresh_from_db()
        assert attempt.status == "granting"

    @pytest.mark.django_db
    @pytest.mark.parametrize("permanently_declined", [False, True])
    def test_keeper_bypass_cannot_complete_after_reassignment(self, setup_room, permanently_declined):
        session, room, keeper, user = setup_room
        if permanently_declined:
            http_decide(room, keeper, http_request(session, user), "permanently_decline")
        room.keeper = user.slug
        room.save(update_fields=["keeper"])
        attempt = http_request(session, user)
        assert attempt.status == "granting"
        room.keeper = keeper.slug
        room.save(update_fields=["keeper"])
        with (
            patch("totem.rooms.admission.verify_current_permissions", return_value=(1, "participant-1")) as verify,
            pytest.raises(admission.AdmissionError) as error,
        ):
            admission.complete_admission(
                session.slug, user, attempt.request_id, attempt.attempt_id, expected_version=attempt.version
            )
        verify.assert_called_once_with(attempt.admission.pk)
        assert error.value.code == "not_eligible"
        attempt.refresh_from_db()
        assert attempt.status == "granting"
        assert not admission.is_authorized_to_enter(session.slug, user)

    @pytest.fixture
    def join_context(self, client_with_user, settings):
        settings.LIVEKIT_API_KEY = KEY
        settings.LIVEKIT_API_SECRET = SECRET
        client, user = client_with_user
        keeper = UserFactory()
        session = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=timezone.now() - timedelta(minutes=5),
            duration_minutes=60,
        )
        session.attendees.add(keeper, user)
        room = Room.objects.get_or_create_for_session(session)
        with patch("totem.rooms.api.get_admission_participants", return_value=set()) as presence:
            yield client, user, keeper, session, room, presence

    @pytest.mark.django_db
    def test_waiting_join_returns_restricted_token_without_recording_join(self, join_context):
        client, user, _, session, _, presence = join_context
        requested = ids()
        response = join(client, session, requested)
        data = assert_admission(response, session, user, status="pending", permissions="waiting")
        assert {key: data[key] for key in requested} == requested
        assert data["approval_required"] is True
        assert data["durable_state"] == "none"
        assert_token(response, user, session, admitted=False, attempt_id=data["attempt_id"])
        assert not session.joined.filter(pk=user.pk).exists()
        presence.assert_called_once_with(session.slug)

    @pytest.mark.django_db
    def test_keeper_join_bypasses_approval_without_recording_join(self, join_context):
        client, user, _, session, _, _ = join_context
        session.space.author = user
        session.space.save(update_fields=["author"])
        Room.objects.filter(session=session).update(keeper=user.slug)
        response = join(client, session)
        data = assert_admission(response, session, user, status="granting", permissions="admitted")
        assert_token(response, user, session, admitted=True, attempt_id=data["attempt_id"])
        assert not session.joined.filter(pk=user.pk).exists()

    @pytest.mark.django_db
    def test_durable_admitted_member_can_return_after_newcomer_window(self, join_context):
        client, user, _, session, _, _ = join_context
        session.start = timezone.now() - timedelta(minutes=15)
        session.save(update_fields=["start"])
        SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.ADMITTED)
        assert not session.joined.filter(pk=user.pk).exists()
        response = join(client, session)
        data = assert_admission(response, session, user, status="granting", permissions="admitted")
        assert_token(response, user, session, admitted=True, attempt_id=data["attempt_id"])
        assert not session.joined.filter(pk=user.pk).exists()

    @pytest.mark.django_db
    @pytest.mark.parametrize("state", [AdmissionState.NONE, AdmissionState.REVOKED])
    def test_legacy_joined_does_not_extend_newcomer_window(self, join_context, state):
        client, user, _, session, _, _ = join_context
        session.start = timezone.now() - timedelta(minutes=15)
        session.save(update_fields=["start"])
        session.joined.add(user)
        SessionAdmission.objects.create(session=session, user=user, state=state)
        response = join(client, session)
        assert response.status_code == 403
        assert response.json()["detail"] == "not_eligible"
        assert "token" not in response.json()

    @pytest.mark.django_db
    def test_policy_toggle_promotes_pending_on_repeat(self, join_context):
        client, user, keeper, session, room, _ = join_context
        first = join(client, session)
        waiting = assert_admission(first, session, user, status="pending", permissions="waiting")
        assert_token(first, user, session, admitted=False, attempt_id=waiting["attempt_id"])
        room.refresh_from_db()
        admission.update_approval_required(
            session.slug,
            keeper,
            False,
            expected_revision=room.admission_revision,
            expected_room_version=room.state_version,
        )
        second = join(client, session)
        granted = assert_admission(second, session, user, status="granting", permissions="admitted")
        assert (granted["request_id"], granted["attempt_id"]) == (waiting["request_id"], waiting["attempt_id"])
        assert granted["approval_required"] is False
        assert_token(second, user, session, admitted=True, attempt_id=granted["attempt_id"])
        assert not session.joined.filter(pk=user.pk).exists()

    @pytest.mark.django_db
    def test_explicit_approval_with_failed_sync_issues_token_without_recording_attendance(self, join_context):
        client, user, keeper, session, room, _ = join_context
        waiting = assert_admission(join(client, session), session, user, status="pending", permissions="waiting")
        attempt = AdmissionAttempt.objects.get(attempt_id=waiting["attempt_id"])
        room.refresh_from_db()
        admission.decide_admission(
            session.slug,
            keeper,
            attempt.request_id,
            attempt.attempt_id,
            "approve",
            expected_version=attempt.version,
            expected_room_version=room.state_version,
        )
        sync = AdmissionPermissionSync.objects.get(admission__session=session, admission__user=user)
        sync.last_error = "unavailable"
        sync.save(update_fields=["last_error"])

        response = join(client, session)
        granted = assert_admission(response, session, user, status="granting", permissions="admitted")
        assert granted["attempt_id"] == waiting["attempt_id"]
        assert granted["permission_sync"] == "unavailable"
        assert_token(response, user, session, admitted=True, attempt_id=granted["attempt_id"])
        assert not session.joined.filter(pk=user.pk).exists()

    @pytest.mark.django_db
    def test_revoked_previous_attendee_needs_fresh_waiting_attempt(self, join_context):
        client, user, keeper, session, room, _ = join_context
        initial = assert_admission(join(client, session), session, user, status="pending", permissions="waiting")
        attempt = AdmissionAttempt.objects.get(attempt_id=initial["attempt_id"])
        room.refresh_from_db()
        admission.decide_admission(
            session.slug,
            keeper,
            attempt.request_id,
            attempt.attempt_id,
            "approve",
            expected_version=attempt.version,
            expected_room_version=room.state_version,
        )
        session.joined.add(user)
        membership = SessionAdmission.objects.get(session=session, user=user)
        room.refresh_from_db()
        admission.revoke_admission(
            session.slug,
            keeper,
            user,
            expected_version=membership.version,
            expected_room_version=room.state_version,
        )
        rejected = join(client, session)
        assert rejected.status_code == 403
        assert rejected.json()["detail"] == "invalid_attempt"
        assert "token" not in rejected.json()

        fresh_ids = ids()
        response = join(client, session, fresh_ids)
        waiting = assert_admission(response, session, user, status="pending", permissions="waiting")
        assert waiting["attempt_id"] == fresh_ids["attempt_id"]
        assert waiting["durable_state"] == "revoked"
        assert_token(response, user, session, admitted=False, attempt_id=waiting["attempt_id"])
        assert session.joined.filter(pk=user.pk).exists()

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "body",
        [
            "{",
            '{"request_id":"not-a-uuid"}',
            '{"request_id":"00000000-0000-0000-0000-000000000001"}',
            '{"attempt_id":"00000000-0000-0000-0000-000000000001"}',
        ],
    )
    def test_invalid_json_join_body_is_rejected(self, join_context, body):
        client, user, _, session, _, presence = join_context
        response = client.post(f"{BASE}/{session.slug}/join", data=body, content_type="application/json")
        assert response.status_code == 400
        assert "token" not in response.json()
        assert not SessionAdmission.objects.filter(session=session, user=user).exists()
        presence.assert_not_called()

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ("body", "content_type"),
        [("", "application/json"), ("", "application/x-www-form-urlencoded"), ("{}", "application/json")],
    )
    def test_empty_body_reuses_pending_attempt(self, join_context, body, content_type):
        client, user, _, session, _, _ = join_context
        first = assert_admission(join(client, session), session, user, status="pending", permissions="waiting")
        response = client.post(f"{BASE}/{session.slug}/join", data=body, content_type=content_type)
        retry = assert_admission(response, session, user, status="pending", permissions="waiting")
        assert (retry["request_id"], retry["attempt_id"]) == (first["request_id"], first["attempt_id"])
        assert_token(response, user, session, admitted=False, attempt_id=retry["attempt_id"])
        assert not session.joined.filter(pk=user.pk).exists()

    @pytest.mark.django_db
    def test_permanent_decline_denied_even_when_approval_disabled(self, join_context):
        client, user, _, session, room, _ = join_context
        room.approval_required = False
        room.save(update_fields=["approval_required"])
        SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.PERMANENTLY_DECLINED)
        for body in (None, ids()):
            response = join(client, session, body)
            assert response.status_code == 403
            assert response.json()["detail"] == "permanently_declined"
            assert "token" not in response.json()
        assert not session.joined.filter(pk=user.pk).exists()

    @pytest.mark.django_db
    def test_pending_attempt_remains_valid_after_newcomer_window_until_expiry(self, join_context):
        client, user, _, session, _, _ = join_context
        first = join(client, session)
        waiting = assert_admission(first, session, user, status="pending", permissions="waiting")
        session.start = timezone.now() - timedelta(minutes=15)
        session.save(update_fields=["start"])
        repeat = join(client, session)
        again = assert_admission(repeat, session, user, status="pending", permissions="waiting")
        assert again["request_id"] == waiting["request_id"]
        assert again["attempt_id"] == waiting["attempt_id"]
        assert_token(repeat, user, session, admitted=False, attempt_id=again["attempt_id"])
        assert not session.joined.filter(pk=user.pk).exists()
        AdmissionAttempt.objects.filter(attempt_id=again["attempt_id"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        expired = join(client, session)
        assert expired.status_code == 403
        assert expired.json()["detail"] == "invalid_attempt"
        assert "token" not in expired.json()
        fresh = join(client, session, ids())
        assert fresh.status_code == 403
        assert fresh.json()["detail"] == "not_eligible"

    @pytest.mark.django_db
    @pytest.mark.parametrize("terminal", [AttemptStatus.DECLINED, AttemptStatus.CANCELLED, AttemptStatus.EXPIRED])
    def test_terminal_attempt_requires_explicit_new_ids(self, join_context, terminal):
        client, user, _, session, _, _ = join_context
        initial = ids()
        response = join(client, session, initial)
        assert_admission(response, session, user, status="pending", permissions="waiting")
        AdmissionAttempt.objects.filter(attempt_id=initial["attempt_id"]).update(status=terminal)
        for body in (None, initial):
            rejected = join(client, session, body)
            assert rejected.status_code == 403
            assert rejected.json()["detail"] == "invalid_attempt"
            assert "token" not in rejected.json()
        fresh_ids = ids()
        fresh = join(client, session, fresh_ids)
        data = assert_admission(fresh, session, user, status="pending", permissions="waiting")
        assert data["attempt_id"] == fresh_ids["attempt_id"]
        assert_token(fresh, user, session, admitted=False, attempt_id=data["attempt_id"])

    @pytest.mark.django_db
    def test_superseded_explicit_ids_never_return_normal_token(self, join_context):
        client, user, _, session, _, _ = join_context
        old_ids, new_ids = ids(), ids()
        assert join(client, session, old_ids).status_code == 200
        assert join(client, session, new_ids).status_code == 200
        SessionAdmission.objects.filter(session=session, user=user).update(state=AdmissionState.ADMITTED)
        rejected = join(client, session, old_ids)
        assert rejected.status_code == 403
        assert rejected.json()["detail"] == "invalid_attempt"
        assert "token" not in rejected.json()

    @pytest.mark.django_db
    def test_waiting_duplicate_presence_does_not_depend_on_joined(self, join_context):
        client, user, _, session, _, presence = join_context
        presence.return_value = {user.slug}
        response = join(client, session)
        data = assert_admission(response, session, user, status="pending", permissions="waiting")
        assert response.json()["is_already_present"] is True
        assert_token(response, user, session, admitted=False, attempt_id=data["attempt_id"])
        assert not session.joined.filter(pk=user.pk).exists()
        presence.assert_called_once_with(session.slug)

    @pytest.mark.django_db
    @pytest.mark.parametrize("code", ["unavailable", "timeout"])
    def test_presence_failure_fails_closed(self, join_context, code):
        client, user, _, session, _, presence = join_context
        presence.side_effect = LiveKitPermissionError(code, "presence failed")
        response = join(client, session)
        assert response.status_code == 500
        assert response.json()["code"] == "livekit_error"
        assert response.json()["detail"] == code
        assert "token" not in response.json()
        assert not session.joined.filter(pk=user.pk).exists()
        assert not SessionAdmission.objects.filter(session=session, user=user).exists()

    @pytest.mark.django_db
    def test_missing_livekit_configuration_fails_closed(self, join_context, settings):
        client, user, _, session, _, _ = join_context
        settings.LIVEKIT_API_KEY = None
        response = join(client, session)
        assert response.status_code == 500
        assert response.json()["code"] == "livekit_error"
        assert response.json()["detail"] == "unavailable"
        assert "token" not in response.json()
        assert not session.joined.filter(pk=user.pk).exists()

    @pytest.mark.django_db
    @pytest.mark.parametrize("reason", ["ended", "banned", "cancelled", "not_attending", "too_early"])
    def test_ineligible_join_is_denied(self, join_context, reason):
        client, user, _, session, room, _ = join_context
        if reason == "ended":
            room.status = RoomStatus.ENDED
            room.save(update_fields=["status"])
        elif reason == "banned":
            room.banned_participants = [user.slug]
            room.save(update_fields=["banned_participants"])
        elif reason == "cancelled":
            session.cancelled = True
            session.save(update_fields=["cancelled"])
        elif reason == "not_attending":
            session.attendees.remove(user)
        else:
            session.start = timezone.now() + timedelta(hours=2)
            session.save(update_fields=["start"])
        response = join(client, session)
        assert response.status_code == 403
        assert "token" not in response.json()
        assert not session.joined.filter(pk=user.pk).exists()

    def test_presence_is_raw_and_lookup_errors_are_not_empty(self):
        with patch(
            "totem.rooms.livekit._get_connected_participants", new=AsyncMock(return_value={"waiting", "member"})
        ):
            assert room_livekit.get_admission_participants("room") == {"waiting", "member"}
        with patch("totem.rooms.livekit._get_connected_participants", new=AsyncMock(side_effect=TimeoutError)):
            with pytest.raises(room_livekit.LiveKitPermissionError):
                room_livekit.get_admission_participants("room")

    def test_first_join_proceeds_when_livekit_room_does_not_exist(self):
        user = User(is_active=True, pk=1, slug="keeper")
        session = MagicMock(slug="room")
        session.attendees.filter.return_value.exists.return_value = True
        session.ended.return_value = False
        response = SimpleNamespace(is_already_present=True)
        missing = livekit_api.TwirpError(code="not_found", msg="room not found", status=404)
        with (
            patch.object(room_livekit, "_get_connected_participants", new=AsyncMock(side_effect=missing)),
            patch.object(room_api.Room.objects, "filter") as rooms,
            patch("totem.rooms.admission.prepare_admission_join", return_value=response) as prepare,
        ):
            rooms.return_value.first.return_value = SimpleNamespace(keeper="keeper")
            result = cast(Any, room_api._join_with_admission(session, user, None))
        assert result.status_code == 200
        assert prepare.call_args.kwargs["connected"] == set()
        assert not response.is_already_present

    def test_admission_presence_internal_error_is_not_empty(self):
        error = livekit_api.TwirpError(code="internal", msg="unavailable", status=500)
        with patch.object(room_livekit, "_get_connected_participants", new=AsyncMock(side_effect=error)):
            with pytest.raises(room_livekit.LiveKitPermissionError, match="unavailable") as exc:
                room_livekit.get_admission_participants("room")
        assert exc.value.code == "unavailable"

    def test_enforced_remove_is_hard_even_when_hint_succeeds(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.room.send_data = AsyncMock()
        client.room.remove_participant = AsyncMock()
        with patch("totem.rooms.livekit._get_api", return_value=client):
            room_livekit.remove_participant("room", "member", RemoveReason.REMOVE)
        client.room.remove_participant.assert_awaited_once()
        assert client.room.remove_participant.call_args.args[0].revoke_token_ts > 0

    def test_event_passes_sid_snapshot_to_state_machine_and_projection(self):
        request = cast(HttpRequest, SimpleNamespace(user=SimpleNamespace(slug="keeper")))
        body = EventRequest(event=StartRoomEvent(prompt=None), last_seen_version=0)
        sids = {"keeper": "sid-keeper", "waiting": "sid-waiting"}
        with (
            patch.object(room_api, "get_room_participant_sids", return_value=sids),
            patch.object(room_api, "_project_connected", return_value={"keeper"}) as project,
            patch.object(room_api, "apply_event", return_value=SimpleNamespace(current_speaker="keeper")) as apply,
            patch.object(room_api, "publish_state"),
            patch.object(room_api, "mute_all_participants") as mute,
        ):
            room_api.post_event(request, "room", body)
        project.assert_called_once_with("room", set(sids), participant_sids=sids)
        assert apply.call_args.kwargs["connected"] == set(sids)
        assert apply.call_args.kwargs["participant_sids"] == sids
        mute.assert_called_once_with("room", except_identity="keeper", identities={"keeper"})

    def test_unknown_presence_rejects_event_without_state_change(self):
        request = cast(HttpRequest, SimpleNamespace(user=SimpleNamespace(slug="keeper")))
        body = EventRequest(event=StartRoomEvent(prompt=None), last_seen_version=0)
        with (
            patch.object(
                room_api,
                "get_room_participant_sids",
                side_effect=room_livekit.LiveKitPermissionError("timeout", "timeout"),
            ),
            patch.object(room_api, "apply_event") as apply,
        ):
            result = cast(Any, room_api.post_event(request, "room", body))
        assert result.status_code == 500
        assert result.value.code == room_api.ErrorCode.LIVEKIT_ERROR
        apply.assert_not_called()

    def test_waiting_participant_cannot_be_muted(self):
        request = cast(HttpRequest, SimpleNamespace(user=SimpleNamespace(slug="keeper")))
        with (
            patch.object(room_api, "_get_room_and_require_keeper", return_value=MagicMock()),
            patch.object(room_api, "get_room_participant_sids", return_value={"waiting": "sid-waiting"}),
            patch.object(room_api, "_project_connected", return_value=set()),
            patch.object(room_api, "mute_participant") as mute,
        ):
            result = cast(Any, room_api.mute(request, "room", "waiting"))
        assert result.value.code == room_api.ErrorCode.NOT_IN_ROOM
        mute.assert_not_called()

    def test_livekit_sid_snapshot_filters_disconnected_and_handles_errors(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.room.list_participants = AsyncMock(
            return_value=SimpleNamespace(
                participants=[
                    SimpleNamespace(identity="member", sid="sid-1", state=livekit_api.ParticipantInfo.State.ACTIVE),
                    SimpleNamespace(identity="gone", sid="sid-2", state=livekit_api.ParticipantInfo.State.DISCONNECTED),
                    SimpleNamespace(identity="no-sid", sid="", state=livekit_api.ParticipantInfo.State.ACTIVE),
                ]
            )
        )
        with patch.object(room_livekit, "_get_api", return_value=client):
            assert room_livekit.get_room_participant_sids("room") == {"member": "sid-1"}
            client.room.list_participants.side_effect = livekit_api.TwirpError(
                code="not_found", msg="room not found", status=404
            )
            assert room_livekit.get_room_participant_sids("room") == {}
            client.room.list_participants.side_effect = TimeoutError()
            with pytest.raises(room_livekit.LiveKitPermissionError) as exc:
                room_livekit.get_room_participant_sids("room")
            assert exc.value.code == "timeout"

    @pytest.mark.django_db
    def test_replaced_connection_cannot_be_muted(self):
        keeper, member = UserFactory(), UserFactory()
        session = SessionFactory(space__author=keeper, start=timezone.now() - timedelta(minutes=1))
        session.attendees.add(keeper, member)
        Room.objects.get_or_create_for_session(session)
        admission = SessionAdmission.objects.create(session=session, user=member, state=AdmissionState.ADMITTED)
        attempt = AdmissionAttempt.objects.create(
            admission=admission,
            request_id=uuid4(),
            attempt_id=uuid4(),
            status=AttemptStatus.ADMITTED,
            expires_at=timezone.now() + timedelta(minutes=10),
            participant_sid="original-sid",
        )
        AdmissionPermissionSync.objects.create(
            admission=admission,
            desired_admitted=True,
            revision=1,
            applied_revision=1,
            participant_sid=attempt.participant_sid,
        )
        request = cast(HttpRequest, SimpleNamespace(user=keeper))
        with (
            patch.object(room_api, "get_room_participant_sids", return_value={member.slug: "replacement-sid"}),
            patch.object(room_api, "mute_participant") as mute,
        ):
            result = cast(Any, room_api.mute(request, session.slug, member.slug))
        assert result.value.code == room_api.ErrorCode.NOT_IN_ROOM
        mute.assert_not_called()
        with (
            patch.object(room_api, "get_room_participant_sids", return_value={member.slug: attempt.participant_sid}),
            patch.object(room_api, "mute_participant") as mute,
        ):
            result = cast(Any, room_api.mute(request, session.slug, member.slug))
        assert result.status_code == 200
        mute.assert_called_once_with(session.slug, member.slug)

    def test_remove_ban_passes_domain_flag_and_hard_removes(self):
        keeper = SimpleNamespace(slug="keeper")
        target = SimpleNamespace(slug="member")
        request = cast(HttpRequest, SimpleNamespace(user=keeper))
        room = SimpleNamespace(state_version=3)
        with (
            patch.object(room_api, "_get_room_and_require_keeper", return_value=room),
            patch.object(room_api.User.objects, "filter") as users,
            patch("totem.rooms.admission.record_removal") as record,
            patch.object(room_api, "remove_participant") as remove,
            patch.object(room_api.analytics, "user_removed_from_room"),
        ):
            users.return_value.first.return_value = target
            room_api.remove(request, "room", "member", reason=RemoveReason.BAN)
        record.assert_called_once_with("room", keeper, target, expected_room_version=3, ban=True)
        remove.assert_called_once_with("room", "member", reason=RemoveReason.BAN)


@pytest.mark.django_db(transaction=True)
class TestAdmissionPermissions:
    @pytest.fixture(autouse=True)
    def livekit(self):
        participant = api.ParticipantInfo(
            sid="participant-1",
            identity="attendee",
            permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
        )

        def snapshot(*args, **kwargs):
            assert not connection.in_atomic_block
            return participant

        def update(*args, **kwargs):
            assert not connection.in_atomic_block
            return participant

        def disconnect(*args, **kwargs):
            assert not connection.in_atomic_block

        with (
            patch.object(admission_permissions, "get_participant_snapshot", side_effect=snapshot) as get,
            patch.object(admission_permissions, "update_participant_permissions", side_effect=update) as update_mock,
            patch.object(
                admission_permissions, "hard_disconnect_participant", side_effect=disconnect
            ) as hard_disconnect,
            patch(
                "totem.rooms.livekit.get_participant_snapshot", side_effect=lambda *args, **kwargs: get(*args, **kwargs)
            ),
            patch("totem.rooms.state_machine.publish_state"),
        ):
            yield get, update_mock, hard_disconnect

    @pytest.fixture
    def room_context(self, livekit):
        keeper = UserFactory()
        user = UserFactory()
        session = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=timezone.now() - timedelta(minutes=1),
        )
        session.attendees.add(keeper, user)
        room = Room.objects.get_or_create_for_session(session)
        return session, room, keeper, user

    @pytest.fixture
    def queued_grant(self, room_context):
        session, room, keeper, user = room_context
        with patch.object(admission, "_queue_permissions"):
            attempt = permissions_approve(room, keeper, permissions_request(session, user))
        queue_without_callback(attempt.admission)
        return attempt

    def test_approval_queues_and_grants_connected_participant(self, room_context, livekit):
        session, room, keeper, user = room_context
        attempt = permissions_approve(room, keeper, permissions_request(session, user))
        sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
        assert attempt.status == "granting"
        assert sync.desired_admitted
        assert sync.applied_revision == sync.revision
        assert sync.participant_sid == "participant-1"
        assert sync.checked_at is not None
        assert sync.operation_id is None and sync.lease_until is None
        _, update, _ = livekit
        update.assert_called_with(
            session.slug,
            user.slug,
            admitted=True,
            expected_sid="participant-1",
            attributes={"totem.admission": "admitted", "totem.admission_revision": str(sync.revision)},
        )

    @pytest.mark.parametrize("code", ["participant_missing", "timeout", "identity_replaced"])
    def test_failed_grant_stays_pending_until_retry(self, room_context, queued_grant, livekit, code):
        session, _, _, user = room_context
        attempt = queued_grant
        get, update, _ = livekit

        def fail(*args, **kwargs):
            assert not connection.in_atomic_block
            raise LiveKitPermissionError(code, "unavailable")

        get.side_effect = fail
        admission_permissions.reconcile_admission_permissions(attempt.admission_id)
        sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
        assert sync.last_error == code
        assert sync.applied_revision is None
        assert sync.checked_at is not None
        attempt.refresh_from_db()
        assert attempt.status == "granting"
        with pytest.raises(admission.AdmissionError):
            admission.complete_admission(
                session.slug,
                user,
                attempt.request_id,
                attempt.attempt_id,
                expected_version=attempt.version,
            )

        def recovered(*args):
            assert not connection.in_atomic_block
            return api.ParticipantInfo(sid="participant-1", identity=user.slug)

        get.side_effect = recovered
        sync.next_retry_at = timezone.now() - timedelta(seconds=1)
        sync.save(update_fields=["next_retry_at"])
        assert admission_permissions.reconcile_session_permissions() >= 1
        sync.refresh_from_db()
        assert sync.last_error == ""
        assert sync.applied_revision == sync.revision
        assert update.call_args.kwargs["admitted"] is True

    def test_stale_grant_is_restricted_and_not_acknowledged(self, room_context, queued_grant, livekit):
        session, _, _, user = room_context
        attempt = queued_grant
        _, update, _ = livekit

        def race(*args, **kwargs):
            assert not connection.in_atomic_block
            if kwargs["admitted"]:
                with transaction.atomic():
                    Session.objects.select_for_update().get(pk=session.pk)
                    durable = admission.get_admission(session.slug, user)
                    assert durable is not None
                    durable.state = AdmissionState.REVOKED
                    durable.save(update_fields=["state"])
                    admission_permissions.queue_permission_sync(durable)
            return api.ParticipantInfo(sid="participant-1", identity=user.slug)

        update.side_effect = race
        admission_permissions.reconcile_admission_permissions(attempt.admission_id)
        sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
        assert not sync.desired_admitted
        assert sync.applied_revision is None
        assert sync.last_error == "stale_operation"
        assert [call.kwargs["admitted"] for call in update.call_args_list] == [True, False]

    def test_active_lease_skips_and_expired_lease_recovers(self, queued_grant, livekit):
        sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
        sync.operation_id = uuid4()
        sync.lease_until = timezone.now() + timedelta(minutes=1)
        sync.save()
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
        livekit[0].assert_not_called()
        sync.refresh_from_db()
        assert sync.operation_id is not None
        sync.lease_until = timezone.now() - timedelta(seconds=1)
        sync.save(update_fields=["lease_until"])
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
        sync.refresh_from_db()
        assert sync.applied_revision is None
        assert sync.last_error == "lease_recovered"
        assert sync.operation_id is None and sync.lease_until is None
        assert livekit[1].call_count > 0
        assert all(call.kwargs["admitted"] is False for call in livekit[1].call_args_list)
        sync.next_retry_at = timezone.now() - timedelta(seconds=1)
        sync.save(update_fields=["next_retry_at"])
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
        sync.refresh_from_db()
        assert sync.applied_revision == sync.revision
        assert sync.last_error == ""

    def test_periodic_rechecks_clean_row_for_replaced_identity(self, queued_grant, livekit):
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
        get, update, _ = livekit
        replacement = api.ParticipantInfo(sid="participant-2", identity="attendee")

        def snapshot(*args):
            assert not connection.in_atomic_block
            return replacement

        def apply(*args, **kwargs):
            assert not connection.in_atomic_block
            return replacement

        get.side_effect = snapshot
        update.side_effect = apply
        admission_permissions.reconcile_session_permissions()
        sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
        assert sync.participant_sid == "participant-2"
        assert sync.applied_revision == sync.revision
        assert update.call_args.kwargs["expected_sid"] == "participant-2"

    def test_revocation_applies_waiting_permissions(self, room_context, queued_grant, livekit):
        session, _, _, user = room_context
        durable = queued_grant.admission
        durable.state = AdmissionState.REVOKED
        durable.save(update_fields=["state"])
        queue_without_callback(durable)

        def disconnect_after_restrict(*args, **kwargs):
            assert not connection.in_atomic_block
            assert livekit[1].call_args.kwargs["admitted"] is False

        livekit[2].side_effect = disconnect_after_restrict
        admission_permissions.reconcile_admission_permissions(durable.pk)
        sync = AdmissionPermissionSync.objects.get(admission=durable)
        assert not sync.desired_admitted
        assert sync.applied_revision == sync.revision
        livekit[1].assert_called_with(
            session.slug,
            user.slug,
            admitted=False,
            expected_sid="participant-1",
            attributes={"totem.admission": "waiting", "totem.admission_revision": str(sync.revision)},
        )
        livekit[2].assert_called_once_with(session.slug, user.slug)

    def test_revocation_failure_uses_hard_disconnect(self, room_context, queued_grant, livekit):
        session, _, _, user = room_context
        durable = queued_grant.admission
        durable.state = AdmissionState.REVOKED
        durable.save(update_fields=["state"])
        queue_without_callback(durable)
        _, update, disconnect = livekit

        def fail(*args, **kwargs):
            assert not connection.in_atomic_block
            raise LiveKitPermissionError("timeout", "unavailable")

        update.side_effect = fail
        admission_permissions.reconcile_admission_permissions(durable.pk)
        assert all(call.kwargs["admitted"] is False for call in update.call_args_list)
        disconnect.assert_called_once_with(session.slug, user.slug)
        sync = AdmissionPermissionSync.objects.get(admission=durable)
        assert not sync.desired_admitted
        assert sync.applied_revision is None
        assert sync.last_error == "timeout"

    @pytest.mark.parametrize("implicit", [False, True])
    def test_old_clean_grant_is_denied_before_retirement(self, room_context, queued_grant, livekit, implicit):
        session, _, _, _ = room_context
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
        sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
        assert sync.desired_admitted and sync.applied_revision == sync.revision
        if implicit:
            session.start = timezone.now() - timedelta(days=2)
            session.save(update_fields=["start"])
        else:
            session.ended_at = timezone.now() - timedelta(minutes=5)
            session.save(update_fields=["ended_at"])
        livekit[1].reset_mock()
        assert admission_permissions.reconcile_session_permissions() == 1
        sync.refresh_from_db()
        assert not sync.desired_admitted and sync.applied_revision == sync.revision
        assert livekit[1].call_args.kwargs["admitted"] is False
        livekit[0].reset_mock()
        assert admission_permissions.reconcile_session_permissions() == 0
        livekit[0].assert_not_called()

    def test_implicit_end_backstop_and_replay_boundary(self, room_context, queued_grant, livekit):
        session, room, _, _ = room_context
        now = timezone.now()
        end = now - timedelta(hours=3) + timedelta(minutes=1)
        session.start = end - timedelta(minutes=session.duration_minutes)
        session.save(update_fields=["start"])
        Room.objects.filter(pk=room.pk).update(date_created=end - timedelta(minutes=1))
        sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
        sync.desired_admitted = False
        sync.applied_revision = sync.revision
        sync.checked_at = now
        sync.save()
        with patch.object(admission_permissions, "reconcile_admission_permissions") as reconcile:
            assert admission_permissions.reconcile_session_permissions() == 1
            reconcile.assert_called_once_with(sync.admission_id)
            # Once past the backstop, an observation before its TTL is insufficient.
            session.start -= timedelta(minutes=2)
            session.save(update_fields=["start"])
            sync.checked_at = end - timedelta(minutes=2) + timedelta(hours=3, minutes=2) - timedelta(microseconds=1)
            sync.save(update_fields=["checked_at"])
            reconcile.reset_mock()
            assert admission_permissions.reconcile_session_permissions() == 1
            reconcile.assert_called_once()
            sync.checked_at += timedelta(microseconds=1)
            sync.save(update_fields=["checked_at"])
            reconcile.reset_mock()
            assert admission_permissions.reconcile_session_permissions() == 0
            reconcile.assert_not_called()
            for applied_revision in [None, sync.revision + 1]:
                sync.applied_revision = applied_revision
                sync.save(update_fields=["applied_revision"])
                assert admission_permissions.reconcile_session_permissions() == 1

    def test_dirty_old_ended_session_is_retried(self, room_context, queued_grant, livekit):
        session, _, _, _ = room_context
        session.ended_at = timezone.now() - timedelta(minutes=5)
        session.save(update_fields=["ended_at"])
        admission_permissions.reconcile_session_permissions()
        sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
        assert not sync.desired_admitted
        assert sync.applied_revision == sync.revision
        assert livekit[1].call_args.kwargs["admitted"] is False
        livekit[2].assert_called_once()

    @pytest.mark.parametrize("denied", [False, True])
    def test_absent_participant_only_acknowledges_denial(self, queued_grant, livekit, denied):
        durable = queued_grant.admission
        if denied:
            durable.state = AdmissionState.REVOKED
            durable.save(update_fields=["state"])
            queue_without_callback(durable)

        def missing(*args, **kwargs):
            assert not connection.in_atomic_block
            raise LiveKitPermissionError("participant_missing", "Not connected")

        livekit[0].side_effect = missing
        admission_permissions.reconcile_admission_permissions(durable.pk)
        sync = AdmissionPermissionSync.objects.get(admission=durable)
        if denied:
            assert sync.applied_revision == sync.revision
            assert sync.last_error == ""
        else:
            assert sync.applied_revision is None
            assert sync.last_error == "participant_missing"

    @pytest.mark.parametrize("implicit", [False, True])
    def test_clean_ended_row_is_rechecked_after_token_ttl_before_retirement(
        self, room_context, queued_grant, livekit, implicit
    ):
        session, _, _, user = room_context
        ended_at = timezone.now() - timedelta(minutes=3)
        if implicit:
            session.start = ended_at - timedelta(hours=3, minutes=session.duration_minutes)
            session.save(update_fields=["start"])
        else:
            session.ended_at = ended_at
            session.save(update_fields=["ended_at"])
        get, update, disconnect = livekit

        def missing(*args, **kwargs):
            assert not connection.in_atomic_block
            raise LiveKitPermissionError("participant_missing", "Not connected")

        get.side_effect = missing
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
        sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
        assert sync.applied_revision == sync.revision
        assert not sync.desired_admitted
        # The first absent observation occurred before the issued token's TTL elapsed.
        sync.checked_at = ended_at + timedelta(minutes=1)
        sync.save(update_fields=["checked_at"])

        def replayed(*args, **kwargs):
            assert not connection.in_atomic_block
            return api.ParticipantInfo(sid="replayed", identity=user.slug)

        get.side_effect = replayed
        update.side_effect = replayed
        assert admission_permissions.reconcile_session_permissions() == 1
        sync.refresh_from_db()
        assert sync.checked_at >= ended_at + timedelta(minutes=2)
        assert sync.applied_revision == sync.revision
        assert update.call_args.kwargs["admitted"] is False
        disconnect.assert_called_once_with(session.slug, user.slug)
        get.reset_mock()
        assert admission_permissions.reconcile_session_permissions() == 0
        get.assert_not_called()

    def test_fresh_request_after_revocation_remains_waiting(self, room_context, queued_grant, livekit):
        session, room, keeper, user = room_context
        durable = queued_grant.admission
        room.refresh_from_db()
        admission.revoke_admission(
            session.slug,
            keeper,
            user,
            expected_version=durable.version,
            expected_room_version=room.state_version,
        )
        for mock in livekit:
            mock.reset_mock()
        attempt = permissions_request(session, user)
        durable.refresh_from_db()
        sync = AdmissionPermissionSync.objects.get(admission=durable)
        assert durable.state == AdmissionState.REVOKED
        assert attempt.status == "pending"
        assert not sync.desired_admitted
        assert sync.applied_revision == sync.revision
        assert livekit[1].call_args.kwargs["admitted"] is False
        livekit[2].assert_not_called()

    def test_disabling_approval_grants_pending_without_new_token(self, room_context, livekit):
        session, room, keeper, user = room_context
        attempt = permissions_request(session, user)
        sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
        assert not sync.desired_admitted
        assert livekit[1].call_args.kwargs["admitted"] is False
        livekit[2].assert_not_called()
        for mock in livekit:
            mock.reset_mock()
        room.refresh_from_db()
        with patch("totem.rooms.livekit.create_access_token") as token:
            admission.update_approval_required(
                session.slug,
                keeper,
                False,
                expected_revision=room.admission_revision,
                expected_room_version=room.state_version,
            )
        attempt.refresh_from_db()
        assert attempt.status == "granting"
        sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
        assert sync.desired_admitted and sync.applied_revision == sync.revision
        assert any(call.kwargs["admitted"] is True for call in livekit[1].call_args_list)
        token.assert_not_called()

    @pytest.mark.parametrize("stale", ["keeper", "attempt", "room"])
    def test_stale_decision_never_grants(self, room_context, livekit, stale):
        session, room, keeper, user = room_context
        attempt = permissions_request(session, user)
        for mock in livekit:
            mock.reset_mock()
        room.refresh_from_db()
        if stale == "keeper":
            room.keeper = user.slug
            room.save(update_fields=["keeper"])
        with pytest.raises(admission.AdmissionError):
            admission.decide_admission(
                session.slug,
                keeper,
                attempt.request_id,
                attempt.attempt_id,
                "approve",
                expected_version=attempt.version + (stale == "attempt"),
                expected_room_version=room.state_version + (stale == "room"),
            )
        attempt.refresh_from_db()
        assert attempt.status == "pending"
        assert not any(call.kwargs["admitted"] for call in livekit[1].call_args_list)

    def test_completion_reconciles_when_participant_connects_after_initial_miss(self, room_context, livekit):
        session, room, keeper, user = room_context
        get, update, _ = livekit

        def missing(*args, **kwargs):
            assert not connection.in_atomic_block
            raise LiveKitPermissionError("participant_missing", "Not connected")

        get.side_effect = missing
        attempt = permissions_approve(room, keeper, permissions_request(session, user))
        sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
        assert sync.last_error == "participant_missing"
        assert sync.applied_revision is None
        update.reset_mock()
        participant = api.ParticipantInfo(
            sid="connected-after-approval",
            identity=user.slug,
            permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
        )

        def connected(*args, **kwargs):
            assert not connection.in_atomic_block
            return participant

        get.side_effect = connected
        get.reset_mock()
        update.side_effect = connected
        sync.next_retry_at = timezone.now() - timedelta(seconds=1)
        sync.save(update_fields=["next_retry_at"])
        completed = admission.complete_admission(
            session.slug,
            user,
            attempt.request_id,
            attempt.attempt_id,
            expected_version=attempt.version,
        )
        sync.refresh_from_db()
        assert completed.status == "admitted"
        assert sync.applied_revision == sync.revision
        assert sync.participant_sid == participant.sid
        assert update.call_args.kwargs["admitted"] is True
        assert get.call_count >= 2

    @pytest.mark.parametrize("failure", ["replaced", "disconnected", "timeout", "revision_changed"])
    def test_completion_rechecks_live_participant_and_journal(self, room_context, queued_grant, livekit, failure):
        session, _, _, user = room_context
        attempt = queued_grant
        admission_permissions.reconcile_admission_permissions(attempt.admission_id)
        sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
        assert sync.applied_revision == sync.revision

        def snapshot(*args, **kwargs):
            assert not connection.in_atomic_block
            if failure in {"disconnected", "timeout"}:
                raise LiveKitPermissionError(
                    "participant_missing" if failure == "disconnected" else "timeout", "unavailable"
                )
            if failure == "revision_changed":
                AdmissionPermissionSync.objects.filter(pk=sync.pk).update(revision=sync.revision + 1)
            return api.ParticipantInfo(
                sid="participant-2" if failure == "replaced" else "participant-1",
                identity=user.slug,
                permission=api.ParticipantPermission(can_publish=True, can_subscribe=True, can_publish_data=True),
            )

        livekit[0].side_effect = snapshot
        with pytest.raises(admission.AdmissionError) as error:
            admission.complete_admission(
                session.slug,
                user,
                attempt.request_id,
                attempt.attempt_id,
                expected_version=attempt.version,
            )
        assert error.value.code == "permission_pending"
        attempt.refresh_from_db()
        assert attempt.status == "granting"

    def test_failures_back_off_and_periodic_scans_wait_until_due(self, queued_grant, livekit):
        get, update, disconnect = livekit
        get.side_effect = LiveKitPermissionError("participant_missing", "Not connected")
        for count, delay in enumerate([2, 4, 8, 16, 32, 60, 60], 1):
            before = timezone.now()
            admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
            after = timezone.now()
            sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
            assert sync.retry_count == count
            assert before + timedelta(seconds=delay) <= sync.next_retry_at <= after + timedelta(seconds=delay)
            calls = (get.call_count, update.call_count, disconnect.call_count)
            for _ in range(3):
                admission_permissions.reconcile_session_permissions()
            assert (get.call_count, update.call_count, disconnect.call_count) == calls
            sync.refresh_from_db()
            assert sync.retry_count == count
            sync.next_retry_at = timezone.now() - timedelta(seconds=1)
            sync.save(update_fields=["next_retry_at"])

        get.side_effect = None
        get.return_value = api.ParticipantInfo(sid="recovered")
        admission_permissions.reconcile_session_permissions()
        sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
        sync.refresh_from_db()
        assert sync.applied_revision == sync.revision
        assert sync.retry_count == 0 and sync.next_retry_at is None

    def test_revoke_preempts_failed_grant_and_never_retries_it(self, room_context, queued_grant, livekit):
        session, room, keeper, user = room_context
        get, update, _ = livekit
        get.side_effect = LiveKitPermissionError("participant_missing", "Not connected")
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
        sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
        old_revision = sync.revision
        assert sync.next_retry_at > timezone.now()
        get.side_effect = None
        get.return_value = api.ParticipantInfo(sid="participant-1", identity=user.slug)
        update.reset_mock()
        room.refresh_from_db()
        durable = queued_grant.admission
        admission.revoke_admission(
            session.slug, keeper, user, expected_version=durable.version, expected_room_version=room.state_version
        )
        sync.refresh_from_db()
        assert sync.revision > old_revision
        assert not sync.desired_admitted and sync.applied_revision == sync.revision
        assert sync.retry_count == 0 and sync.next_retry_at is None
        assert update.call_args.kwargs["admitted"] is False
        admission_permissions.reconcile_session_permissions()
        assert all(not call.kwargs["admitted"] for call in update.call_args_list)

    def test_connection_sid_change_preempts_backoff_but_same_sid_does_not(self, room_context, queued_grant, livekit):
        session, _, _, user = room_context
        get, update, _ = livekit
        attempt = queued_grant
        participant = api.ParticipantInfo(sid="new-sid", identity=user.slug)
        get.side_effect = LiveKitPermissionError("participant_missing", "Not connected")
        admission_permissions.reconcile_admission_permissions(attempt.admission_id)
        sync = AdmissionPermissionSync.objects.get(admission=attempt.admission)
        old_revision = sync.revision
        get.side_effect = None
        get.return_value = participant
        update.return_value = participant
        with patch.object(admission_http, "get_participant_snapshot", return_value=participant):
            admission_http.confirm_connection(session.slug, user, attempt.request_id, attempt.attempt_id)
            sync.refresh_from_db()
            assert sync.revision > old_revision
            assert sync.applied_revision == sync.revision
            assert sync.retry_count == 0 and sync.next_retry_at is None
            assert update.call_args.kwargs["expected_sid"] == participant.sid
            get.side_effect = LiveKitPermissionError("participant_missing", "Not connected")
            admission_permissions.reconcile_admission_permissions(attempt.admission_id)
            sync.refresh_from_db()
            revision, due = sync.revision, sync.next_retry_at
            calls = (get.call_count, update.call_count)
            admission_http.confirm_connection(session.slug, user, attempt.request_id, attempt.attempt_id)
            sync.refresh_from_db()
            assert (sync.revision, sync.next_retry_at, sync.retry_count) == (revision, due, 1)
            assert (get.call_count, update.call_count) == calls

    def test_removal_during_backoff_never_retries_grant(self, room_context, queued_grant, livekit):
        session, _, _, user = room_context
        get, update, _ = livekit
        get.side_effect = LiveKitPermissionError("participant_missing", "Not connected")
        admission_permissions.reconcile_admission_permissions(queued_grant.admission_id)
        sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
        assert sync.desired_admitted and sync.next_retry_at > timezone.now()
        session.attendees.remove(user)
        get.side_effect = None
        get.return_value = api.ParticipantInfo(sid="participant-1", identity=user.slug)
        update.reset_mock()
        admission_permissions.reconcile_session_permissions()
        sync.refresh_from_db()
        assert not sync.desired_admitted
        assert sync.applied_revision == sync.revision
        assert update.call_args.kwargs["admitted"] is False
        assert all(not call.kwargs["admitted"] for call in update.call_args_list)

    def test_command_response_reports_current_version_and_retry_status(self, room_context, queued_grant, livekit):
        session, room, keeper, user = room_context
        get, update, disconnect = livekit
        for mock in (get, update, disconnect):
            mock.side_effect = LiveKitPermissionError("timeout", "unavailable")
        room.refresh_from_db()
        body = MembershipCommandInput(
            command_id=uuid4(),
            expected_version=queued_grant.admission.version,
            expected_room_version=room.state_version,
        )
        with patch.object(admission_http, "get_room_participant_sids", return_value={}):
            response = admission_http.execute_keeper_command(session.slug, keeper, "revoke", body, user.slug)
        sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
        room.refresh_from_db()
        assert response.snapshot.version == room.admission_version
        assert response.partial_failure
        participant = response.results[0].participant
        assert participant is not None
        assert participant.permission_revision == sync.revision
        assert participant.last_error == "timeout"
        assert participant.next_retry_at == sync.next_retry_at
        assert sync.next_retry_at > timezone.now()

    def test_ended_cleanup_reads_do_not_reset_denial_backoff(self, room_context, queued_grant, livekit):
        session, room, _, user = room_context
        session.ended_at = timezone.now()
        session.save(update_fields=["ended_at"])
        get, update, disconnect = livekit
        get.side_effect = LiveKitPermissionError("timeout", "unavailable")
        update.side_effect = LiveKitPermissionError("timeout", "unavailable")
        disconnect.side_effect = LiveKitPermissionError("timeout", "unavailable")
        admission.get_admission(session.slug, user)
        sync = AdmissionPermissionSync.objects.get(admission=queued_grant.admission)
        assert not sync.desired_admitted and sync.retry_count > 0
        before = (sync.revision, sync.retry_count, sync.next_retry_at)
        room.refresh_from_db()
        version = room.admission_version
        calls = (get.call_count, update.call_count, disconnect.call_count)
        for _ in range(3):
            admission.get_admission(session.slug, user)
        sync.refresh_from_db()
        room.refresh_from_db()
        assert (sync.revision, sync.retry_count, sync.next_retry_at) == before
        assert room.admission_version == version
        assert (get.call_count, update.call_count, disconnect.call_count) == calls

    @pytest.fixture
    def context(self):
        keeper, user = UserFactory(), UserFactory()
        session = SessionFactory(
            space__author=keeper,
            space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT,
            start=timezone.now() - timedelta(minutes=1),
        )
        session.attendees.add(keeper, user)
        room = Room.objects.get_or_create_for_session(session)
        with patch("totem.rooms.state_machine.publish_state"):
            yield session, room, keeper, user

    @pytest.fixture
    def race_queued_grant(self, context):
        session, room, keeper, user = context
        with patch.object(admission_permissions, "reconcile_admission_permissions"):
            attempt = admission.request_admission(session.slug, user, uuid4(), uuid4())
            room.refresh_from_db()
            attempt = admission.decide_admission(
                session.slug,
                keeper,
                attempt.request_id,
                attempt.attempt_id,
                "approve",
                expected_version=attempt.version,
                expected_room_version=room.state_version,
            )
        return attempt

    class TestPermissionRaces:
        @pytest.fixture
        def livekit(self):
            pass

        def test_keeper_change_during_grant_fences_revision_and_compensates(self, context, race_queued_grant):
            session, room, _, user = context
            replacement = UserFactory()
            session.attendees.add(replacement)
            sync = AdmissionPermissionSync.objects.get(admission=race_queued_grant.admission)
            original_revision = sync.revision
            calls = []

            def snapshot(room_name, identity):
                assert not connection.in_atomic_block
                return participant(identity)

            def update(room_name, identity, *, admitted, **kwargs):
                assert not connection.in_atomic_block
                calls.append(admitted)
                if admitted:
                    Room.objects.filter(pk=room.pk).update(keeper=replacement.slug)
                return participant(identity)

            with (
                patch.object(admission_permissions, "get_participant_snapshot", side_effect=snapshot),
                patch.object(admission_permissions, "update_participant_permissions", side_effect=update),
            ):
                admission_permissions.reconcile_admission_permissions(race_queued_grant.admission_id)
            sync.refresh_from_db()
            assert calls == [True, False]
            assert sync.revision > original_revision
            assert sync.authority_keeper == replacement.slug
            assert sync.applied_revision != sync.revision

        @pytest.mark.parametrize("change", ["remove", "ban", "end"])
        def test_grant_side_effect_after_removal_or_end_is_compensated(self, context, race_queued_grant, change):
            session, room, keeper, user = context
            calls = []
            if change == "ban":
                room.talking_order = [user.slug]
                room.save(update_fields=["talking_order"])

            def snapshot(room_name, identity):
                assert not connection.in_atomic_block
                return participant(identity)

            def update(room_name, identity, *, admitted, **kwargs):
                assert not connection.in_atomic_block
                calls.append(admitted)
                if admitted:
                    if change == "ban":
                        room.refresh_from_db()
                        apply_event(
                            session.slug,
                            keeper.slug,
                            BanParticipantEvent(participantSlug=user.slug),
                            room.state_version,
                            connected=None,
                        )
                    elif change == "remove":
                        room.refresh_from_db()
                        admission.record_removal(session.slug, keeper, user, expected_room_version=room.state_version)
                    else:
                        session.ended_at = timezone.now()
                        session.save(update_fields=["ended_at"])
                return participant(identity)

            with (
                patch.object(admission_permissions, "get_participant_snapshot", side_effect=snapshot),
                patch.object(admission_permissions, "update_participant_permissions", side_effect=update),
                patch.object(admission_permissions, "hard_disconnect_participant"),
            ):
                admission_permissions.reconcile_admission_permissions(race_queued_grant.admission_id)
                admission_permissions.reconcile_admission_permissions(race_queued_grant.admission_id, force=True)
            sync = AdmissionPermissionSync.objects.get(admission=race_queued_grant.admission)
            assert calls[0:2] == [True, False]
            assert all(not admitted for admitted in calls[1:])
            assert not sync.desired_admitted
            if change == "ban":
                room.refresh_from_db()
                race_queued_grant.admission.refresh_from_db()
                assert user.slug in room.banned_participants
                assert user.slug not in room.talking_order
                assert race_queued_grant.admission.state == AdmissionState.REVOKED

        @pytest.mark.parametrize("role", ["keeper", "attendee"])
        def test_confirmed_activation_records_join_once(self, context, role):
            session, room, keeper, attendee = context
            user = keeper if role == "keeper" else attendee

            def snapshot(room_name, identity):
                assert not connection.in_atomic_block
                return participant(identity)

            def update(room_name, identity, **kwargs):
                assert not connection.in_atomic_block
                return participant(identity)

            with (
                patch.object(admission_permissions, "get_participant_snapshot", side_effect=snapshot),
                patch.object(admission_permissions, "update_participant_permissions", side_effect=update),
                patch.object(admission_http, "get_participant_snapshot", side_effect=snapshot),
                patch("totem.users.analytics.event_joined") as joined,
            ):
                attempt = admission.request_admission(session.slug, user, uuid4(), uuid4())
                if role == "attendee":
                    room.refresh_from_db()
                    attempt = admission.decide_admission(
                        session.slug,
                        keeper,
                        attempt.request_id,
                        attempt.attempt_id,
                        "approve",
                        expected_version=attempt.version,
                        expected_room_version=room.state_version,
                    )
                assert not session.joined.filter(pk=user.pk).exists()
                assert joined.call_count == 0
                attempt = admission_http.confirm_connection(session.slug, user, attempt.request_id, attempt.attempt_id)
                attempt = admission.complete_admission(
                    session.slug, user, attempt.request_id, attempt.attempt_id, expected_version=attempt.version
                )
                admission.complete_admission(
                    session.slug, user, attempt.request_id, attempt.attempt_id, expected_version=attempt.version
                )
                assert session.joined.filter(pk=user.pk).exists()
                joined.assert_called_once()

        def test_removal_before_activation_and_replayed_receipt_cannot_grant(self, context, race_queued_grant):
            session, room, keeper, user = context
            room.refresh_from_db()
            with patch.object(admission_permissions, "reconcile_admission_permissions"):
                admission.record_removal(session.slug, keeper, user, expected_room_version=room.state_version)
                replay = admission.request_admission(
                    session.slug, user, race_queued_grant.request_id, race_queued_grant.attempt_id
                )
                assert replay.status == AttemptStatus.REVOKED
                with pytest.raises(admission.AdmissionError):
                    admission.prepare_admission_join(
                        session.slug, user, request_id=replay.request_id, attempt_id=replay.attempt_id, connected=set()
                    )
            assert not session.joined.filter(pk=user.pk).exists()

        def test_activated_attempt_cannot_grant_replacement_connection(self, context, race_queued_grant):
            session, _, _, user = context
            original = participant(user.slug)
            replacement = participant(user.slug)
            replacement.sid = "replacement-sid"
            with (
                patch.object(admission_permissions, "get_participant_snapshot", return_value=original),
                patch.object(admission_permissions, "update_participant_permissions", return_value=original),
                patch("totem.users.analytics.event_joined"),
            ):
                admission_permissions.reconcile_admission_permissions(race_queued_grant.admission_id)
                activated = admission.complete_admission(
                    session.slug,
                    user,
                    race_queued_grant.request_id,
                    race_queued_grant.attempt_id,
                    expected_version=race_queued_grant.version,
                )
            assert activated.status == AttemptStatus.ADMITTED
            with (
                patch.object(admission_permissions, "get_participant_snapshot", return_value=replacement),
                patch.object(
                    admission_permissions, "update_participant_permissions", return_value=replacement
                ) as update,
            ):
                admission_permissions.reconcile_admission_permissions(race_queued_grant.admission_id, force=True)
            assert [call.kwargs["admitted"] for call in update.call_args_list] == [False]
            sync = AdmissionPermissionSync.objects.get(admission=race_queued_grant.admission)
            assert sync.applied_revision is None
            assert sync.last_error == "identity_replaced"
            race_queued_grant.admission.refresh_from_db()
            assert race_queued_grant.admission.state == AdmissionState.ADMITTED
            with (
                patch.object(admission_permissions, "get_participant_snapshot", return_value=replacement),
                patch.object(admission_permissions, "update_participant_permissions", return_value=replacement),
                patch.object(admission_http, "get_participant_snapshot", return_value=replacement),
                patch("totem.users.analytics.event_joined"),
            ):
                fresh = admission.request_admission(session.slug, user, uuid4(), uuid4())
                fresh = admission_http.confirm_connection(session.slug, user, fresh.request_id, fresh.attempt_id)
                fresh = admission.complete_admission(
                    session.slug,
                    user,
                    fresh.request_id,
                    fresh.attempt_id,
                    expected_version=fresh.version,
                )
            assert fresh.status == AttemptStatus.ADMITTED
            assert fresh.participant_sid == replacement.sid

        def test_watchdog_retries_partial_room_end_without_presence(self, context):
            session, room, _, user = context
            with patch.object(admission_permissions, "reconcile_admission_permissions"):
                pending = admission.request_admission(session.slug, user, uuid4(), uuid4())
            session.start = timezone.now() - timedelta(minutes=10)
            session.save(update_fields=["start"])
            with (
                patch.object(tasks, "get_admission_participants", return_value=set()),
                patch.object(tasks, "apply_event", side_effect=RuntimeError("temporary cleanup failure")),
                patch.object(admission_permissions, "reconcile_admission_permissions"),
            ):
                assert tasks.end_sessions_without_keeper() == 1
            session.refresh_from_db()
            ended_at = session.ended_at
            assert ended_at is not None
            pending.refresh_from_db()
            assert pending.status == AttemptStatus.CANCELLED
            room.refresh_from_db()
            assert room.status != RoomStatus.ENDED
            with (
                patch.object(tasks, "get_admission_participants") as presence,
                patch.object(tasks, "publish_state") as publish,
                patch.object(admission_permissions, "reconcile_admission_permissions"),
            ):
                assert tasks.end_sessions_without_keeper() == 0
            presence.assert_not_called()
            publish.assert_called_once()
            room.refresh_from_db()
            session.refresh_from_db()
            assert room.status == RoomStatus.ENDED
            assert session.ended_at == ended_at

        def test_watchdog_rechecks_keeper_changed_during_presence_lookup(self, context):
            session, room, _, user = context
            session.start = timezone.now() - timedelta(minutes=10)
            session.save(update_fields=["start"])

            def presence(slug):
                assert not connection.in_atomic_block
                Room.objects.filter(pk=room.pk).update(keeper=user.slug)
                return {user.slug}

            with patch.object(tasks, "get_admission_participants", side_effect=presence) as lookup:
                assert tasks.end_sessions_without_keeper() == 0
            lookup.assert_called_once_with(session.slug)
            session.refresh_from_db()
            assert session.ended_at is None

        def test_watchdog_presence_failure_does_not_end_session(self, context):
            session, _, _, _ = context
            session.start = timezone.now() - timedelta(minutes=10)
            session.save(update_fields=["start"])
            with patch.object(
                tasks, "get_admission_participants", side_effect=LiveKitPermissionError("timeout", "offline")
            ):
                assert tasks.end_sessions_without_keeper() == 0
            session.refresh_from_db()
            assert session.ended_at is None


class TestAdmissionEntry:
    @pytest.fixture
    def admission_notification_transport(self):
        # Entry tests did not use the rooms notification transport fixture.
        pass

    @pytest.fixture
    def entry(self, db):
        session = SessionFactory(
            start=timezone.now() - timedelta(minutes=30), space__meeting_provider=Space.MeetingProviderChoices.LIVEKIT
        )
        user = UserFactory()
        session.attendees.add(user)
        room = Room.objects.get_or_create_for_session(session)
        return session, room, user

    def test_current_keeper_and_admitted_attendee_have_returning_window(self, entry):
        session, room, user = entry
        keeper = UserFactory()
        session.attendees.add(keeper)
        room.keeper = keeper.slug
        room.save(update_fields=["keeper"])
        SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.ADMITTED)
        assert session.space.author != keeper
        assert session.can_join(keeper)
        assert session.can_join(user)
        session.ended_at = timezone.now()
        assert not session.can_join(keeper)
        assert not session.can_join(user)

    @pytest.mark.parametrize("state", [AdmissionState.NONE, AdmissionState.REVOKED])
    def test_legacy_join_does_not_extend_unadmitted_window(self, entry, state):
        session, _, user = entry
        session.joined.add(user)
        SessionAdmission.objects.create(session=session, user=user, state=state)
        assert not session.can_join(user)

    @pytest.mark.parametrize("status", [AttemptStatus.PENDING, AttemptStatus.GRANTING])
    def test_existing_attempt_continues_until_expiry(self, entry, status):
        session, _, user = entry
        admission = SessionAdmission.objects.create(session=session, user=user)
        attempt = AdmissionAttempt.objects.create(
            admission=admission,
            request_id=uuid4(),
            attempt_id=uuid4(),
            status=status,
            expires_at=timezone.now() + timedelta(minutes=1),
        )
        assert session.can_join(user)
        attempt.expires_at = timezone.now() - timedelta(seconds=1)
        attempt.save(update_fields=["expires_at"])
        assert not session.can_join(user)

    def test_prefetched_attempt_expiry_and_other_user_isolation(self, entry):
        session, room, user = entry
        admission = SessionAdmission.objects.create(session=session, user=user)
        attempt = AdmissionAttempt.objects.create(
            admission=admission,
            request_id=uuid4(),
            attempt_id=uuid4(),
            status=AttemptStatus.PENDING,
            expires_at=timezone.now() + timedelta(minutes=1),
        )
        listed = join_listing_queryset(Session.objects.filter(pk=session.pk), user).get()
        assert listed.can_join(user)
        other = UserFactory()
        session.attendees.add(other)
        assert not listed.join_window(other)[1] == attempt.expires_at
        with patch("django.utils.timezone.now", return_value=attempt.expires_at + timedelta(seconds=1)):
            assert not listed.can_join(user)

    def test_pending_continuation_does_not_authorize_a_new_request(self, entry):
        session, _, user = entry
        admission = SessionAdmission.objects.create(session=session, user=user)
        AdmissionAttempt.objects.create(
            admission=admission,
            request_id=uuid4(),
            attempt_id=uuid4(),
            status=AttemptStatus.PENDING,
            expires_at=timezone.now() + timedelta(minutes=1),
        )
        assert session.can_join(user)
        with pytest.raises(AdmissionError) as error:
            request_admission(session.slug, user, uuid4(), uuid4())
        assert error.value.code == "not_eligible"

    @pytest.mark.parametrize(
        ("provider", "joinable"),
        [
            (Space.MeetingProviderChoices.LIVEKIT, False),
            (Space.MeetingProviderChoices.GOOGLE_MEET, True),
        ],
    )
    def test_inactive_user_joinability(self, entry, provider, joinable):
        session, _, user = entry
        session.space.meeting_provider = provider
        session.start = timezone.now() - timedelta(minutes=1)
        user.is_active = False
        assert session.can_join(user) is joinable

    @pytest.mark.parametrize(
        ("provider", "joinable"),
        [
            (Space.MeetingProviderChoices.LIVEKIT, False),
            (Space.MeetingProviderChoices.GOOGLE_MEET, True),
        ],
    )
    def test_ended_room_joinability_before_session_end_sync(self, entry, provider, joinable):
        session, room, user = entry
        session.space.meeting_provider = provider
        session.start = timezone.now() - timedelta(minutes=1)
        room.status = RoomStatus.ENDED
        room.save(update_fields=["status"])
        assert session.ended_at is None
        assert session.can_join(user) is joinable

    def test_keeper_still_requires_rsvp(self, entry):
        session, room, user = entry
        room.keeper = user.slug
        room.save(update_fields=["keeper"])
        session.attendees.remove(user)
        assert not session.can_join(user)

    def test_bans_and_declines_deny_but_keeper_bypasses_decline(self, entry):
        session, room, user = entry
        SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.PERMANENTLY_DECLINED)
        assert not session.can_join(user)
        room.keeper = user.slug
        room.save(update_fields=["keeper"])
        assert session.can_join(user)
        room.banned_participants = [user.slug]
        room.save(update_fields=["banned_participants"])
        assert not session.can_join(user)

    @pytest.mark.parametrize("signed", [False, True])
    def test_livekit_browser_redirect_does_not_record_attendance(self, entry, client, signed):
        session, _, user = entry
        SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.ADMITTED)
        if signed:
            url = JoinSessionAction(user=user, parameters={"session_slug": session.slug}).build_url()
        else:
            client.force_login(user)
            url = reverse("spaces:join", kwargs={"session_slug": session.slug})
        with patch("totem.spaces.views.analytics.event_joined") as analytics:
            response = client.get(url)
        assert response.url == session.room_url()
        assert not session.joined.filter(pk=user.pk).exists()
        analytics.assert_not_called()

    def test_signed_link_obeys_decline(self, entry, client):
        session, _, user = entry
        SessionAdmission.objects.create(session=session, user=user, state=AdmissionState.PERMANENTLY_DECLINED)
        url = JoinSessionAction(user=user, parameters={"session_slug": session.slug}).build_url()
        response = client.get(url)
        assert response.url != session.room_url()
        assert not session.joined.filter(pk=user.pk).exists()

    def test_google_meet_browser_records_redirect(self, entry, client):
        session, _, user = entry
        session.space.meeting_provider = Space.MeetingProviderChoices.GOOGLE_MEET
        session.space.save(update_fields=["meeting_provider"])
        session.start = timezone.now() - timedelta(minutes=1)
        session.save(update_fields=["start"])
        client.force_login(user)
        with patch("totem.spaces.views.analytics.event_joined") as analytics:
            response = client.get(reverse("spaces:join", kwargs={"session_slug": session.slug}))
        assert response.url == session.room_url()
        assert session.joined.filter(pk=user.pk).exists()
        analytics.assert_called_once()
