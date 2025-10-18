from typing import List, Optional


class SessionStatus(str):
    STARTED = "started"
    ENDED = "ended"


class SessionState(dict):
    status: str = SessionStatus.STARTED
    speakingOrder: List[str]
    speakingNow: Optional[str] = None

    def pass_totem(self) -> Optional["SessionState"]:
        """
        Passes the totem to the next person and returns the new state.
        """
        order = self.speakingOrder
        current_speaker = self.speakingNow

        if current_speaker not in order:
            next_index = 0
        else:
            current_index = order.index(current_speaker)
            next_index = (current_index + 1) % len(order)

        self.speakingNow = order[next_index]
        return self

    def dict(self):
        return {
            "status": self.status,
            "speakingOrder": self.speakingOrder,
            "speakingNow": self.speakingNow,
        }
