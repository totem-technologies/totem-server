from enum import Enum
from typing import List, Optional

from ninja import Schema


class SessionStatus(str, Enum):
    WAITING = "waiting"
    STARTED = "started"
    ENDED = "ended"


class SessionState(Schema):
    status: str = SessionStatus.WAITING
    speaking_order: List[str]
    speaking_now: Optional[str] = None

    def start(self):
        """
        Starts the session by setting the status to 'started' and the first speaker.
        """
        self.status = SessionStatus.STARTED
        if self.speaking_order:
            self.speaking_now = self.speaking_order[0]

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

    def reorder(self, new_order: List[str]):
        """
        Reorders the speaking order.
        """
        self.speaking_order = new_order
        if self.speaking_now not in new_order:
            self.speaking_now = new_order[0] if new_order else None
