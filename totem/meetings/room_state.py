from typing import List, Optional

from ninja import Schema


class SessionStatus(str):
    WAITING = "waiting"
    STARTED = "started"
    ENDED = "ended"


class SessionState(Schema):
    status: str = SessionStatus.WAITING
    speaking_order: List[str]
    speaking_now: Optional[str] = None

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
