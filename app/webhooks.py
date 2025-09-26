from typing import Callable, List, Dict
_subscribers: list[str] = []

def subscribe(url: str):
    if url not in _subscribers:
        _subscribers.append(url)

def subscribers() -> list[str]:
    return list(_subscribers)

def emit(event: str, payload: dict):  # stub: replace with async http posts later
    # no-op for MVP to keep dependencies small
    return {"event": event, "sent": len(_subscribers)}
