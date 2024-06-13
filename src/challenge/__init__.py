from .challenge import Challenge
from .handlers import handlers, init_handlers
from .typing import Action

__all__ = [
    "get_challenge",
    "Challenge",
    "init_handlers",
    "Action"
]


def get_challenge(email: str) -> Challenge:
    return Challenge(email, handlers)
