import logging
import re

from .typing import Action


logger = logging.getLogger(__name__)


class Challenge:
    """
    Challenges are analogous to Senders, but control whether an address should be challenged.

    In general an address starts as `unknown`. A specific challenge entry can modify this to
    be either `challenge` or `ignore`. If there is no specific entry then a pattern entry
    will be looked up instead.

    Unlike Sender, Challenge uses an array of handlers, with an `ignore` response having
    higher precedence than a `challenge`. (This is because static overrides are more likely)
    """

    def __init__(self, email: str, handlers: list) -> None:
        self.handlers = handlers
        self.hydrated = False
        self.email = email
        self.action = "unknown"

    def _update_action(self, new_action: str) -> bool:
        """
        Updates the action based on the precedence rule:
        ignore > challenge > unknown

        Returns a boolean indicating if the value was actually changed.
        """
        replace_action = False

        if self.action == "unknown" or new_action == "ignore":
            replace_action = True

        if self.action == new_action:
            replace_action = False

        if replace_action:
            self.action = new_action

        return replace_action

    def get_email(self) -> str:
        """
        Return the challenge email address.
        """
        return self.email

    def get_action(self) -> Action:
        if not self.hydrated:
            self._look_up_action()

        return self.action

    def _look_up_action(self) -> None:
        for handler in self.handlers:
            action = handler.get_action(self.email)

            if not action:
                for (pattern, pattern_action) in handler.get_patterns():
                    logger.debug("Handling pattern %(pattern)s which would result in %(pattern_action)s", {
                        "pattern": pattern,
                        "pattern_action": pattern_action
                    })
                    if re.fullmatch(pattern, self.email, re.IGNORECASE) is not None:
                        action = pattern_action
                        break

            if action:
                self._update_action(action)
