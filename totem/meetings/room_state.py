from enum import Enum

from ninja import Schema


class SessionStatus(str, Enum):
    WAITING = "waiting"
    STARTED = "started"
    ENDED = "ended"


class TotemStatus(str, Enum):
    NONE = "none"
    ACCEPTED = "accepted"
    PASSING = "passing"


class SessionState(Schema):
    keeper_slug: str
    status: SessionStatus = SessionStatus.WAITING
    speaking_order: list[str]
    speaking_now: str | None = None
    next_speaker: str | None = None
    totem_status: TotemStatus = TotemStatus.NONE

    def start(self):
        """
        Starts the session by setting the status to 'started'.

        The keeper is always the first speaker and starts speaking.
        """
        self.validate_order(self.speaking_order)
        self.status = SessionStatus.STARTED
        if self.speaking_order:
            self.speaking_now = self.speaking_order[0]
            self.totem_status = TotemStatus.ACCEPTED
            self._update_next_speaker()

    def end(self):
        """
        Ends the session by setting the status to 'ended' and clearing the current speaker.
        """
        self.status = SessionStatus.ENDED
        self.speaking_now = None
        self.totem_status = TotemStatus.NONE

    def pass_totem(self):
        """
        Passes the totem to the next person in the speaking order.
        Sets totem_status to PASSING.
        """
        self.totem_status = TotemStatus.PASSING
        self._update_next_speaker()

    def accept_totem(self):
        """
        Accepts the totem.
        It sets the current speaker to the next speaker.

        If the totem is not being passed, raises a ValueError.
        """
        if self.totem_status != TotemStatus.PASSING:
            raise ValueError("Totem can only be accepted when it is being passed.")

        self.speaking_now = self.next_speaker
        self.totem_status = TotemStatus.ACCEPTED
        self._update_next_speaker()

    def reorder(self, new_order: list[str]):
        """
        Reorders the speaking order.
        """
        new_order = list(new_order)
        if self.keeper_slug in new_order:
            new_order.remove(self.keeper_slug)
            new_order.insert(0, self.keeper_slug)

        self.speaking_order = new_order
        if self.speaking_now and self.speaking_now not in new_order:
            self.speaking_now = new_order[0] if new_order else None
        self._update_next_speaker()

    def validate_order(self, users: list[str]):
        """
        Validates the speaking order by removing users who left and adding new users.

        Args:
            users: The list of user slugs in the room. Duplicates will be removed.
        """
        # Deduplicate users list (preserves order)
        users = list(dict.fromkeys(users))

        valid_order = []
        seen = set()

        if self.keeper_slug in users:
            valid_order.append(self.keeper_slug)
            seen.add(self.keeper_slug)

        for user in self.speaking_order:
            if user in users and user not in seen:
                valid_order.append(user)
                seen.add(user)

        for user in users:
            if user not in seen:
                valid_order.append(user)
                seen.add(user)

        self.speaking_order = valid_order

        if self.speaking_now is not None and self.speaking_now not in valid_order:
            self.speaking_now = valid_order[0] if valid_order else None
        self._update_next_speaker()

    def _update_next_speaker(self):
        """
        Updates the next_speaker attribute based on the current speaking_now.
        """
        order = self.speaking_order
        if len(order) == 0:
            self.next_speaker = None
            return

        current_speaker = self.speaking_now
        if current_speaker is None or current_speaker not in order:
            next_index = 0
        else:
            current_index = order.index(current_speaker)
            next_index = (current_index + 1) % len(order)
        self.next_speaker = order[next_index]
