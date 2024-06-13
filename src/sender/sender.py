import logging
import re
from typing import Iterable, Optional

from .typing import Action


logger = logging.getLogger(__name__)


class Sender:
    """
    Senders are the heart of postconfirm and control the actions to be taken.

    In general, a sender starts as `unknown`. When they try to contact a protected
    address they would move to `confirm`. This email would be moved into the stash.
    At this point they should be sent an email explaining how to confirm their
    address. Until they do so all their emails are moved into the stash. Once they
    confirm their address the stashed emails would be released (resent) and they
    move to the `accept` status. It is also possible for a sender to be in the
    `reject` status (emails are flagged as rejections by the MTA) or the `discard`
    status (emails are accepted and then silently dropped by the MTA.)

    As well as the specific sender entries the database can also contain RegExp
    entries. If no specific entry is found for the sender and one of these matches
    then it will be used as the status. In general these would be `accept`,
    `reject` or `discard` but a value of `confirm` is possible and effectively
    allows a matching email address to confirm with a specific email, rather than
    waiting for a confirmation request first.
    """

    def __init__(self, email: str, handler: any) -> None:
        self.email = email
        self.references = None
        self.action = None

        self.handler = handler

    def get_email(self) -> str:
        """
        Return the sender email address.
        """
        return self.email

    def get_action(self) -> Action:
        """
        Return the action which should be applied to emails from this sender
        """

        if self.action:
            logger.debug("action for %(email)s already defined: %(action)s", {
                "email": self.email,
                "action": self.action,
            })
            return self.action

        action_data = self.handler.get_action_for_sender(self.email)

        logger.debug("Action record for %(email)s: %(action)s", {"email": self.email, "action": action_data})

        if not action_data:
            patterns = self.handler.get_patterns()

            for pattern, action, ref in patterns:
                if re.fullmatch(pattern, self.email, re.IGNORECASE) is not None:
                    action_data = (action, ref)
                    logger.debug("Matched pattern for %(email)s: %(action)s", {"email": self.email, "action": action_data})
                    break

        if action_data:
            self.action = action_data[0]
            if self.references is None:
                self.references = action_data[1]
            elif action_data[1] is not None:
                self.references = list(set(self.references).union(action_data[1]))
            # Existing references are assumed to be good.
        else:
            self.action = "unknown"
            self.references = []

        logger.debug("Final action for %(email)s determined: %(action)s", {
            "email": self.email,
            "action": self.action,
        })

        return self.action

    def set_action(self, action: Action) -> Optional[str]:
        """
        Update the action which should be applied to emails from this sender

        Returns the reference used for confirmation
        """
        refs = self.get_refs()

        logger.debug("Setting action for %(email)s to be: %(action)s", {
            "email": self.email,
            "action": action,
        })

        self.handler.set_action_for_sender(self.email, action, refs)
        self.action = action

        return refs

    def get_refs(self) -> str:
        """
        Returns the references used for confirmation
        """
        if not self.action:
            # Check the DB for the references first
            self.get_action()

        return self.references

    def add_reference(self, reference: str) -> None:
        """
        Add the reference to the set of references for the sender.

        A given reference will only be added to the sender once.
        """
        if self.references is None:
            logger.debug("Setting reference %(reference)s for %(email)s", {
                "email": self.email,
                "reference": reference
            })
            self.references = [reference]
        elif reference not in self.references:
            logger.debug("Adding reference %(reference)s for %(email)s", {
                "email": self.email,
                "reference": reference
            })
            self.references.append(reference)
        else:
            logger.debug("Skipped existing reference %(reference)s for %(email)s", {
                "email": self.email,
                "reference": reference
            })

    def remove_reference(self, reference: str) -> None:
        """
        Remove the reference from the set of references for the sender.

        If the reference does not exist it is ignored.
        """
        if self.references is None:
            logger.debug("Ignoring reference %(reference)s removal for %(email)s", {
                "email": self.email,
                "reference": reference
            })
        elif reference in self.references:
            logger.debug("Removing reference %(reference)s for %(email)s", {
                "email": self.email,
                "reference": reference
            })
            self.references.remove(reference)
        else:
            logger.debug("Skipped removal of missing reference %(reference)s for %(email)s", {
                "email": self.email,
                "reference": reference
            })

    def clear_references(self) -> list[str]:
        """
        Remove all the references for a sender.

        Typically this would happen when the sender moves from the
        `confirm` action to the `accept` one.
        """
        old_refs = self.references
        self.references = None

        return old_refs

    def stash_message(self, msg: str, recipients: list[str], reference: str = None) -> str:
        """
        Stashes the email message so that it can be released after confirmation.

        Returns the reference to be used for the confirmation
        """
        logger.debug("Stashing message for %(email)s", {"email": self.email})

        self.handler.stash_message_for_sender(self.email, msg, recipients)

        if reference:
            self.add_reference(reference)

        if self.action != "confirm":
            return self.set_action("confirm")
        else:
            return self.get_refs()

    def unstash_messages(self) -> Iterable[tuple[str, str]]:
        """
        Iterates over the stashed email messages, yielding a tuple
        of the message and the recipients.

        After each message has been returned it will be removed from the stash.
        """
        for stash in self.handler.unstash_messages_for_sender(self.email):
            logger.debug("Unstashing message for %(email)s", {"email": self.email})

            yield stash

    def validate_ref(self, ref: str) -> bool:
        """
        Determine if this is a valid reference for this sender

        Returns a boolean, true if this is a valid reference.
        """
        return ref in self.references
