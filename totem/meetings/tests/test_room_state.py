import pytest

from totem.meetings.room_state import SessionState, SessionStatus, TotemStatus


class TestSessionState:
    def test_initial_state(self):
        """Test that SessionState initializes with correct default values."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        assert state.status == SessionStatus.WAITING
        assert state.speaking_order == ["user1", "user2", "user3"]
        assert state.speaking_now is None
        assert state.totem_status == TotemStatus.NONE

    def test_start_with_order(self):
        """Test starting a session with a speaking order."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.start()
        assert state.status == SessionStatus.STARTED
        assert state.speaking_now == "user1"

    def test_start_without_order(self):
        """Test starting a session without a speaking order."""
        state = SessionState(speaking_order=[])
        state.start()
        assert state.status == SessionStatus.STARTED
        assert state.speaking_now is None

    def test_end(self):
        """Test ending a session."""
        state = SessionState(speaking_order=["user1", "user2"])
        state.start()
        assert state.speaking_now == "user1"
        state.end()
        assert state.status == SessionStatus.ENDED
        assert state.speaking_now is None

    def test_pass_totem_normal(self):
        """Test passing the totem to the next person in order."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.speaking_now = "user1"
        state.pass_totem()
        assert state.speaking_now == "user2"

    def test_pass_totem_wraps_around(self):
        """Test that passing the totem wraps around to the first person."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.speaking_now = "user3"
        state.pass_totem()
        assert state.speaking_now == "user1"

    def test_pass_totem_current_speaker_not_in_order(self):
        """Test passing totem when current speaker is not in the order."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.speaking_now = "user4"  # Not in order
        state.pass_totem()
        assert state.speaking_now == "user1"  # Should go to first person

    def test_pass_totem_empty_order(self):
        """Test passing totem with an empty order."""
        state = SessionState(speaking_order=[])
        state.speaking_now = "user1"
        with pytest.raises(IndexError):
            state.pass_totem()

    def test_pass_totem_sets_status_to_passing(self):
        """Test that pass_totem sets totem_status to PASSING."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.speaking_now = "user1"
        assert state.totem_status == TotemStatus.NONE
        state.pass_totem()
        assert state.totem_status == TotemStatus.PASSING

    def test_accept_totem_sets_status_to_accepted(self):
        """Test that accept_totem sets totem_status to ACCEPTED."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        assert state.totem_status == TotemStatus.NONE
        state.accept_totem()
        assert state.totem_status == TotemStatus.ACCEPTED

    def test_accept_totem_from_passing_status(self):
        """Test that accept_totem can be called when status is already PASSING."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.speaking_now = "user1"
        state.pass_totem()
        assert state.totem_status == TotemStatus.PASSING
        state.accept_totem()
        assert state.totem_status == TotemStatus.ACCEPTED

    def test_accept_totem_from_none_status(self):
        """Test that accept_totem can be called from NONE status."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        assert state.totem_status == TotemStatus.NONE
        state.accept_totem()
        assert state.totem_status == TotemStatus.ACCEPTED

    def test_accept_totem_from_accepted_status(self):
        """Test that accept_totem can be called multiple times (idempotent)."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.accept_totem()
        assert state.totem_status == TotemStatus.ACCEPTED
        state.accept_totem()
        assert state.totem_status == TotemStatus.ACCEPTED

    def test_totem_status_cycle(self):
        """Test the complete cycle: NONE -> PASSING -> ACCEPTED -> PASSING -> ACCEPTED."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.speaking_now = "user1"

        # Initial state
        assert state.totem_status == TotemStatus.NONE

        # Pass totem
        state.pass_totem()
        assert state.totem_status == TotemStatus.PASSING

        # Accept totem
        state.accept_totem()
        assert state.totem_status == TotemStatus.ACCEPTED

        # Pass totem again
        state.pass_totem()
        assert state.totem_status == TotemStatus.PASSING

        # Accept totem again
        state.accept_totem()
        assert state.totem_status == TotemStatus.ACCEPTED

    def test_totem_status_with_session_start(self):
        """Test that starting a session doesn't affect totem_status."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        assert state.totem_status == TotemStatus.NONE
        state.start()
        assert state.totem_status == TotemStatus.NONE
        assert state.speaking_now == "user1"

    def test_totem_status_with_session_end(self):
        """Test that ending a session doesn't reset totem_status."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.speaking_now = "user1"
        state.pass_totem()
        assert state.totem_status == TotemStatus.PASSING
        state.end()
        assert state.totem_status == TotemStatus.PASSING
        assert state.speaking_now is None

    def test_reorder(self):
        """Test reordering the speaking order."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.speaking_now = "user2"
        state.reorder(["user3", "user1", "user2"])
        assert state.speaking_order == ["user3", "user1", "user2"]
        assert state.speaking_now == "user2"  # Still in order, so unchanged

    def test_reorder_current_speaker_not_in_new_order(self):
        """Test reordering when current speaker is not in the new order."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.speaking_now = "user2"
        state.reorder(["user1", "user3"])
        assert state.speaking_order == ["user1", "user3"]
        assert state.speaking_now == "user1"  # Should be first in new order

    def test_reorder_empty_order(self):
        """Test reordering to an empty order."""
        state = SessionState(speaking_order=["user1", "user2"])
        state.speaking_now = "user1"
        state.reorder([])
        assert state.speaking_order == []
        assert state.speaking_now is None

    def test_validate_order_preserves_existing_order(self):
        """Test that validate_order preserves the order of existing users."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.validate_order(["user2", "user1", "user3"])
        assert state.speaking_order == ["user1", "user2", "user3"]

    def test_validate_order_removes_users_who_left(self):
        """Test that validate_order removes users who are no longer in the room."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.validate_order(["user1", "user3"])
        assert state.speaking_order == ["user1", "user3"]

    def test_validate_order_adds_new_users(self):
        """Test that validate_order adds new users at the end."""
        state = SessionState(speaking_order=["user1", "user2"])
        state.validate_order(["user1", "user2", "user3", "user4"])
        assert state.speaking_order == ["user1", "user2", "user3", "user4"]

    def test_validate_order_removes_and_adds(self):
        """Test validate_order when some users left and new ones joined."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.validate_order(["user2", "user4", "user5"])
        assert state.speaking_order == ["user2", "user4", "user5"]

    def test_validate_order_empty_users_list(self):
        """Test validate_order with an empty users list."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.speaking_now = "user1"
        state.validate_order([])
        assert state.speaking_order == []
        assert state.speaking_now is None

    def test_validate_order_empty_speaking_order(self):
        """Test validate_order when speaking_order is initially empty."""
        state = SessionState(speaking_order=[])
        state.validate_order(["user1", "user2", "user3"])
        assert state.speaking_order == ["user1", "user2", "user3"]

    def test_validate_order_removes_duplicates_from_users(self):
        """Test that validate_order removes duplicates from the users list."""
        state = SessionState(speaking_order=["user1", "user2"])
        state.validate_order(["user1", "user2", "user2", "user3", "user3"])
        assert state.speaking_order == ["user1", "user2", "user3"]

    def test_validate_order_removes_duplicates_from_speaking_order(self):
        """Test that validate_order removes duplicates from existing speaking_order."""
        state = SessionState(speaking_order=["user1", "user2", "user1", "user3"])
        state.validate_order(["user1", "user2", "user3"])
        assert state.speaking_order == ["user1", "user2", "user3"]

    def test_validate_order_updates_speaking_now_when_removed(self):
        """Test that validate_order updates speaking_now when current speaker is removed."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.speaking_now = "user2"
        state.validate_order(["user1", "user3"])
        assert state.speaking_order == ["user1", "user3"]
        assert state.speaking_now == "user1"  # Should be first in validated order

    def test_validate_order_keeps_speaking_now_when_present(self):
        """Test that validate_order keeps speaking_now when current speaker is still in order."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.speaking_now = "user2"
        state.validate_order(["user1", "user2", "user3", "user4"])
        assert state.speaking_order == ["user1", "user2", "user3", "user4"]
        assert state.speaking_now == "user2"  # Should remain unchanged

    def test_validate_order_sets_speaking_now_to_none_when_empty(self):
        """Test that validate_order sets speaking_now to None when order becomes empty."""
        state = SessionState(speaking_order=["user1", "user2"])
        state.speaking_now = "user1"
        state.validate_order([])
        assert state.speaking_order == []
        assert state.speaking_now is None

    def test_validate_order_complex_scenario(self):
        """Test a complex scenario with duplicates, removals, and additions."""
        state = SessionState(speaking_order=["user1", "user2", "user1", "user3", "user4"])
        state.speaking_now = "user2"
        # user1 and user2 stay, user3 and user4 leave, user5 and user6 join, duplicates in input
        state.validate_order(["user2", "user1", "user5", "user5", "user6"])
        assert state.speaking_order == ["user1", "user2", "user5", "user6"]
        assert state.speaking_now == "user2"  # Still in order

    def test_validate_order_all_users_removed(self):
        """Test validate_order when all users are removed."""
        state = SessionState(speaking_order=["user1", "user2", "user3"])
        state.speaking_now = "user2"
        state.validate_order(["user4", "user5"])
        assert state.speaking_order == ["user4", "user5"]
        assert state.speaking_now == "user4"  # Should be first in new order

    def test_validate_order_preserves_order_with_mixed_scenario(self):
        """Test that validate_order preserves relative order even with complex changes."""
        state = SessionState(speaking_order=["A", "B", "C", "D", "E"])
        # B and D left, F and G joined, but users list has different order
        state.validate_order(["C", "A", "E", "F", "G"])
        # Should preserve A, C, E order, then add F, G
        assert state.speaking_order == ["A", "C", "E", "F", "G"]
