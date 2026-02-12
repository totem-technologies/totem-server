from datetime import timedelta

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.utils import timezone

from totem.spaces.admin import SessionAdmin
from totem.spaces.models import Session
from totem.spaces.tests.factories import SessionFactory
from totem.users.tests.factories import UserFactory
from totem.utils.admin import STALE_DATA_ERROR, STALE_DATA_HIDDEN_FIELD


class TestStaleDataCheck:
    def test_save_succeeds_when_data_is_fresh(self, db):
        """Normal save works when no one else modified the record."""
        session = SessionFactory()
        admin_user = UserFactory(is_staff=True, is_superuser=True)
        site = AdminSite()
        model_admin = SessionAdmin(Session, site)
        factory = RequestFactory()
        request = factory.get("/")
        request.user = admin_user

        FormClass = model_admin.get_form(request, obj=session)
        form = FormClass(instance=session)

        # Simulate submitting the form with the loaded_at timestamp
        data = {}
        for name, field in form.fields.items():
            value = form.initial.get(name, field.initial)
            if value is None:
                value = ""
            data[name] = value
        # Fill in required fields
        data["space"] = session.space_id
        data["start_0"] = session.start.strftime("%Y-%m-%d")
        data["start_1"] = session.start.strftime("%H:%M:%S")
        data["duration_minutes"] = session.duration_minutes
        data["seats"] = session.seats

        submit_form = FormClass(data=data, instance=session)
        assert submit_form.is_valid(), submit_form.errors

    def test_save_rejected_when_data_is_stale(self, db):
        """Save is rejected when the record was modified after the form was loaded."""
        session = SessionFactory()
        admin_user = UserFactory(is_staff=True, is_superuser=True)
        site = AdminSite()
        model_admin = SessionAdmin(Session, site)
        factory = RequestFactory()
        request = factory.get("/")
        request.user = admin_user

        FormClass = model_admin.get_form(request, obj=session)
        form = FormClass(instance=session)

        # Capture the loaded_at timestamp
        loaded_at = form.fields[STALE_DATA_HIDDEN_FIELD].initial

        # Simulate the record being modified by the system
        Session.objects.filter(pk=session.pk).update(date_modified=timezone.now() + timedelta(seconds=10))

        # Submit with the stale timestamp
        data = {}
        for name, field in form.fields.items():
            value = form.initial.get(name, field.initial)
            if value is None:
                value = ""
            data[name] = value
        data[STALE_DATA_HIDDEN_FIELD] = loaded_at
        data["space"] = session.space_id
        data["start_0"] = session.start.strftime("%Y-%m-%d")
        data["start_1"] = session.start.strftime("%H:%M:%S")
        data["duration_minutes"] = session.duration_minutes
        data["seats"] = session.seats

        submit_form = FormClass(data=data, instance=session)
        assert not submit_form.is_valid()
        assert STALE_DATA_ERROR in str(submit_form.errors)

    def test_new_object_skips_stale_check(self, db):
        """Creating a new object should not trigger the stale data check."""
        admin_user = UserFactory(is_staff=True, is_superuser=True)
        site = AdminSite()
        model_admin = SessionAdmin(Session, site)
        factory = RequestFactory()
        request = factory.get("/")
        request.user = admin_user

        FormClass = model_admin.get_form(request, obj=None)
        # Just verify the form class can be instantiated without errors
        form = FormClass()
        assert STALE_DATA_HIDDEN_FIELD in form.fields
