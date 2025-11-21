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
    status: str = SessionStatus.WAITING
    speaking_order: list[str]
    speaking_now: str | None = None
    totem_status: TotemStatus = TotemStatus.NONE

    def start(self):
        """
        Starts the session by setting the status to 'started' and the first speaker.
        """
        self.status = SessionStatus.STARTED
        if self.speaking_order:
            self.speaking_now = self.speaking_order[0]

    def end(self):
        """
        Ends the session by setting the status to 'ended' and clearing the current speaker.
        """
        self.status = SessionStatus.ENDED
        self.speaking_now = None

    def pass_totem(self):
        """
        Passes the totem to the next person and returns the new state.
        """
        order = self.speaking_order
        current_speaker = self.speaking_now

        if current_speaker not in order:
            next_index = 0
        else:
            current_index = order.index(current_speaker)
            next_index = (current_index + 1) % len(order)

        self.speaking_now = order[next_index]
        self.totem_status = TotemStatus.PASSING

    def accept_totem(self):
        """
        Accepts the totem by setting the totem status to 'accepted'.
        """
        self.totem_status = TotemStatus.ACCEPTED

    def reorder(self, new_order: list[str]):
        """
        Reorders the speaking order.
        """

        self.speaking_order = new_order
        if self.speaking_now not in new_order:
            self.speaking_now = new_order[0] if new_order else None

    def validate_order(self, users: list[str]):
        """
        Validates the speaking order by removing users who left and adding new users.

        Args:
            users: The list of user slugs in the room. Duplicates will be removed.
        """
        # Deduplicate users list (preserves order)
        users = list(dict.fromkeys(users))

        # Start with existing users who are still in the room (preserves their order)
        # Also deduplicate in case self.speaking_order had duplicates
        valid_order = []
        seen = set()
        for user in self.speaking_order:
            if user in users and user not in seen:
                valid_order.append(user)
                seen.add(user)

        for user in users:
            if user not in seen:
                valid_order.append(user)
                seen.add(user)

        self.speaking_order = valid_order

        # Update speaking_now if the current speaker is no longer in the validated order
        if self.speaking_now not in valid_order:
            self.speaking_now = valid_order[0] if valid_order else None
