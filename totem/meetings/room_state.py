from typing import List, Optional

from django.core.cache import cache
from ninja import Schema


class SessionStatus(str):
    STARTED = "started"
    ENDED = "ended"


class SessionState(Schema):
    status: str = SessionStatus.STARTED
    speakingOrder: List[str]
    speakingNow: Optional[str] = None


def get_session_state_key(event_id: str) -> str:
    return f"session_state_{event_id}"


def initial_state(event_id: str, participants: List[str]) -> SessionState:
    """
    Creates the initial state for a session using the SessionState schema.
    """
    state = SessionState(
        speakingOrder=participants,
        speakingNow=participants[0] if participants else None,
    )
    # Cache the dictionary representation of the state
    cache.set(get_session_state_key(event_id), state.dict(), timeout=3600)
    return state


def pass_totem(event_id: str) -> Optional[SessionState]:
    """
    Passes the totem to the next person and returns the new state.
    """
    key = get_session_state_key(event_id)
    state_dict = cache.get(key)
    if not state_dict:
        return None

    state = SessionState(**state_dict)

    order = state.speakingOrder
    current_speaker = state.speakingNow

    if current_speaker not in order:
        next_index = 0
    else:
        current_index = order.index(current_speaker)
        next_index = (current_index + 1) % len(order)

    state.speakingNow = order[next_index]

    cache.set(key, state.dict(), timeout=3600)
    return state
