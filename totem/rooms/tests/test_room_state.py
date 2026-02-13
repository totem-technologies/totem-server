import pytest

from totem.meetings.room_state import SessionState, SessionStatus, TotemStatus


class TestSessionState:
    def test_initial_state(self):
        """Test that SessionState initializes with correct default values."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        assert state.status == SessionStatus.WAITING
        assert state.speaking_order == ["user1", "user2", "user3"]
        assert state.speaking_now is None
        assert state.next_speaker is None
        assert state.totem_status == TotemStatus.NONE

    def test_start_with_order(self):
        """Test starting a session with a speaking order."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.start()
        assert state.status == SessionStatus.STARTED
        assert state.speaking_now == "user1"
        assert state.next_speaker == "user2"

    def test_keeper_starts_speaking(self):
        """Test that the keeper automatically starts speaking when the session starts."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user3")
        state.start()
        assert state.status == SessionStatus.STARTED
        assert state.totem_status == TotemStatus.ACCEPTED
        assert state.speaking_order == ["user3", "user1", "user2"]
        assert state.speaking_now == "user3"
        assert state.next_speaker == "user1"

    def test_start_without_order(self):
        """Test starting a session without a speaking order."""
        state = SessionState(speaking_order=[], keeper_slug="user1")
        state.start()
        assert state.status == SessionStatus.STARTED
        assert state.speaking_now is None
        assert state.next_speaker is None

    def test_end(self):
        """Test ending a session."""
        state = SessionState(speaking_order=["user1", "user2"], keeper_slug="user1")
        state.start()
        assert state.speaking_now == "user1"
        state.end()
        assert state.status == SessionStatus.ENDED
        assert state.speaking_now is None

    def test_pass_totem_sets_next_speaker(self):
        """Test pass_totem sets the next speaker without changing the current one."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.speaking_now = "user1"
        state.pass_totem()
        assert state.speaking_now == "user1"  # Current speaker does not change
        assert state.next_speaker == "user2"
        assert state.totem_status == TotemStatus.PASSING

    def test_pass_totem_wraps_around(self):
        """Test that passing the totem wraps around to the first person for next_speaker."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.speaking_now = "user3"
        state.pass_totem()
        assert state.totem_status == TotemStatus.PASSING
        assert state.speaking_now == "user3"
        assert state.next_speaker == "user1"

    def test_pass_totem_current_speaker_not_in_order(self):
        """Test passing totem when current speaker is not in order sets next_speaker to first person."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.speaking_now = "user4"  # Not in the order
        state.pass_totem()
        assert state.next_speaker == "user1"

    def test_pass_totem_empty_order(self):
        """Test passing totem with an empty order."""
        state = SessionState(speaking_order=[], keeper_slug="user1")
        state.speaking_now = "user1"
        state.pass_totem()
        assert state.totem_status == TotemStatus.PASSING
        assert state.next_speaker is None

    def test_pass_totem_no_current_speaker(self):
        """Test passing totem when no one is speaking."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.speaking_now = None
        state.pass_totem()
        assert state.next_speaker == "user1"
        assert state.totem_status == TotemStatus.PASSING
        assert state.speaking_now is None

    def test_accept_totem_success(self):
        """Test that accept_totem updates the speaker, status, and next speaker."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.speaking_now = "user1"
        state.pass_totem()  # user1 passes, next is user2

        assert state.speaking_now == "user1"
        assert state.next_speaker == "user2"
        assert state.totem_status == TotemStatus.PASSING

        state.accept_totem()  # user2 accepts

        assert state.speaking_now == "user2"
        assert state.next_speaker == "user3"
        assert state.totem_status == TotemStatus.ACCEPTED

    def test_accept_totem_raises_error_if_not_passing(self):
        """Test that accept_totem raises a ValueError if totem_status is not PASSING."""
        state = SessionState(speaking_order=["user1", "user2"], keeper_slug="user1")

        # Test from NONE status
        assert state.totem_status == TotemStatus.NONE
        with pytest.raises(ValueError, match="Totem can only be accepted when it is being passed."):
            state.accept_totem()

        # Test from ACCEPTED status
        state.speaking_now = "user1"
        state.pass_totem()
        state.accept_totem()
        assert state.totem_status == TotemStatus.ACCEPTED
        with pytest.raises(ValueError, match="Totem can only be accepted when it is being passed."):
            state.accept_totem()

    def test_totem_status_cycle(self):
        """Test the complete totem passing cycle."""
        state = SessionState(speaking_order=["user1", "user2"], keeper_slug="user1")
        state.speaking_now = "user1"
        state.next_speaker = "user2"

        # Initial state
        assert state.totem_status == TotemStatus.NONE

        # Pass totem
        state.pass_totem()
        assert state.totem_status == TotemStatus.PASSING
        assert state.speaking_now == "user1"
        assert state.next_speaker == "user2"

        # Accept totem
        state.accept_totem()
        assert state.totem_status == TotemStatus.ACCEPTED
        assert state.speaking_now == "user2"
        assert state.next_speaker == "user1"

        # Pass totem again
        state.pass_totem()
        assert state.totem_status == TotemStatus.PASSING
        assert state.speaking_now == "user2"
        assert state.next_speaker == "user1"

        # Accept totem again
        state.accept_totem()
        assert state.totem_status == TotemStatus.ACCEPTED
        assert state.speaking_now == "user1"
        assert state.next_speaker == "user2"

    def test_totem_status_with_session_end(self):
        """Test that ending a session resets totem_status to NONE."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.speaking_now = "user1"
        state.pass_totem()
        assert state.totem_status == TotemStatus.PASSING
        state.end()
        assert state.totem_status == TotemStatus.NONE
        assert state.speaking_now is None

    def test_reorder(self):
        """Test reordering the speaking order."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.speaking_now = "user2"
        state._update_next_speaker()
        assert state.next_speaker == "user3"

        state.reorder(["user3", "user1", "user2"])
        assert state.speaking_order == ["user1", "user3", "user2"]
        assert state.speaking_now == "user2"  # Still in order, so unchanged
        assert state.next_speaker == "user1"  # Next speaker is updated

    def test_reorder_current_speaker_not_in_new_order(self):
        """Test reordering when current speaker is not in the new order."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.speaking_now = "user2"
        state.reorder(["user1", "user3"])
        assert state.speaking_order == ["user1", "user3"]
        assert state.speaking_now == "user1"  # Should be first in new order
        assert state.next_speaker == "user3"

    def test_reorder_empty_order(self):
        """Test reordering to an empty order."""
        state = SessionState(speaking_order=["user1", "user2"], keeper_slug="user1")
        state.speaking_now = "user1"
        state.reorder([])
        assert state.speaking_order == []
        assert state.speaking_now is None
        assert state.next_speaker is None

    def test_reorder_maintains_current_speaker(self):
        """Test reordering maintains current speaker when it is None."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.speaking_now = None
        state.reorder(["user2", "user3", "user1"])
        assert state.speaking_now is None
        assert state.next_speaker == "user1"

    def test_validate_order_preserves_existing_order(self):
        """Test that validate_order preserves the order of existing users."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.validate_order(["user2", "user1", "user3"])
        assert state.speaking_order == ["user1", "user2", "user3"]

    def test_validate_order_removes_users_who_left(self):
        """Test that validate_order removes users who are no longer in the room."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.validate_order(["user1", "user3"])
        assert state.speaking_order == ["user1", "user3"]
        assert state.next_speaker == "user1"

    def test_validate_order_adds_new_users(self):
        """Test that validate_order adds new users at the end."""
        state = SessionState(speaking_order=["user1", "user2"], keeper_slug="user1")
        state.validate_order(["user1", "user2", "user3", "user4"])
        assert state.speaking_order == ["user1", "user2", "user3", "user4"]
        assert state.next_speaker == "user1"

    def test_validate_order_removes_and_adds(self):
        """Test validate_order when some users left and new ones joined."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.validate_order(["user2", "user4", "user5"])
        assert state.speaking_order == ["user2", "user4", "user5"]

    def test_validate_order_empty_users_list(self):
        """Test validate_order with an empty users list."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.speaking_now = "user1"
        state.validate_order([])
        assert state.speaking_order == []
        assert state.speaking_now is None
        assert state.next_speaker is None

    def test_validate_order_empty_speaking_order(self):
        """Test validate_order when speaking_order is initially empty."""
        state = SessionState(speaking_order=[], keeper_slug="user1")
        state.validate_order(["user1", "user2", "user3"])
        assert state.speaking_order == ["user1", "user2", "user3"]

    def test_validate_order_removes_duplicates_from_users(self):
        """Test that validate_order removes duplicates from the users list."""
        state = SessionState(speaking_order=["user1", "user2"], keeper_slug="user1")
        state.validate_order(["user1", "user2", "user2", "user3", "user3"])
        assert state.speaking_order == ["user1", "user2", "user3"]

    def test_validate_order_removes_duplicates_from_speaking_order(self):
        """Test that validate_order removes duplicates from existing speaking_order."""
        state = SessionState(speaking_order=["user1", "user2", "user1", "user3"], keeper_slug="user1")
        state.validate_order(["user1", "user2", "user3"])
        assert state.speaking_order == ["user1", "user2", "user3"]

    def test_validate_order_updates_speaking_now_when_removed(self):
        """Test that validate_order updates speaking_now when current speaker is removed."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.speaking_now = "user2"
        state.validate_order(["user1", "user3"])
        assert state.speaking_order == ["user1", "user3"]
        assert state.speaking_now == "user1"  # Should be first in validated order
        assert state.next_speaker == "user3"

    def test_validate_order_keeps_speaking_now_when_present(self):
        """Test that validate_order keeps speaking_now when current speaker is still in order."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.speaking_now = "user2"
        state._update_next_speaker()
        assert state.next_speaker == "user3"
        state.validate_order(["user1", "user2", "user3", "user4"])
        assert state.speaking_order == ["user1", "user2", "user3", "user4"]
        assert state.speaking_now == "user2"  # Should remain unchanged
        assert state.next_speaker == "user3"  # Should remain unchanged

    def test_validate_order_sets_speaking_now_to_none_when_empty(self):
        """Test that validate_order sets speaking_now to None when order becomes empty."""
        state = SessionState(speaking_order=["user1", "user2"], keeper_slug="user1")
        state.speaking_now = "user1"
        state.validate_order([])
        assert state.speaking_order == []
        assert state.speaking_now is None
        assert state.next_speaker is None

    def test_validate_order_complex_scenario(self):
        """Test a complex scenario with duplicates, removals, and additions."""
        state = SessionState(speaking_order=["user1", "user2", "user1", "user3", "user4"], keeper_slug="user1")
        state.speaking_now = "user2"
        # user1 and user2 stay, user3 and user4 leave, user5 and user6 join, duplicates in input
        state.validate_order(["user2", "user1", "user5", "user5", "user6"])
        assert state.speaking_order == ["user1", "user2", "user5", "user6"]
        assert state.speaking_now == "user2"  # Still in order
        assert state.next_speaker == "user5"

    def test_validate_order_all_users_removed(self):
        """Test validate_order when all users are removed."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.speaking_now = "user2"
        state.validate_order(["user4", "user5"])
        assert state.speaking_order == ["user4", "user5"]
        assert state.speaking_now == "user4"  # Should be first in new order
        assert state.next_speaker == "user5"

    def test_validate_order_preserves_order_with_mixed_scenario(self):
        """Test that validate_order preserves relative order even with complex changes."""
        state = SessionState(speaking_order=["A", "B", "C", "D", "E"], keeper_slug="A")
        # B and D left, F and G joined, but users list has different order
        state.validate_order(["C", "A", "E", "F", "G"])
        # Should preserve A, C, E order, then add F, G
        assert state.speaking_order == ["A", "C", "E", "F", "G"]
        assert state.next_speaker == "A"

    def test_keeper_always_first_in_validate_order(self):
        """Test that the keeper is always moved to the front in validate_order."""
        state = SessionState(speaking_order=["user2", "user1", "user3"], keeper_slug="user1")
        state.validate_order(["user2", "user1", "user3"])
        assert state.speaking_order == ["user1", "user2", "user3"]

    def test_keeper_always_first_in_reorder(self):
        """Test that the keeper is always moved to the front in reorder."""
        state = SessionState(speaking_order=["user1", "user2", "user3"], keeper_slug="user1")
        state.reorder(["user2", "user1", "user3"])
        assert state.speaking_order == ["user1", "user2", "user3"]
