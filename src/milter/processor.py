import logging
import random
import re
import string
from typing import Union, Optional

import chevron
from kilter.protocol import Accept, Discard, Reject
from kilter.service import Runner, Session

from src.sender import Sender, get_sender
from src.challenge import get_challenge

from src import services


logger = logging.getLogger(__name__)


LINE_SEP = "\n"


IDENTIFIER_CHARS = string.ascii_letters + string.digits + '-'


header_drop_matchers = {}


def recipient_requires_challenge(recipients: list) -> Union[False, list]:
    challenges = [get_challenge(recipient) for recipient in recipients]
    challengeable = filter(lambda challenge: challenge.get_action() == "challenge", challenges)
    to_challenge = list([challenge.get_email() for challenge in challengeable])

    logger.debug("challenges: %(challenges)s", {"challenges": to_challenge})

    if len(to_challenge):
        return to_challenge
    else:
        return False


def message_should_be_dropped(headers: list[dict]) -> bool:
    if "Precedence" not in header_drop_matchers:
        header_drop_matchers["Precedence"] = re.compile(
            services["app_config"].get("bulk_regex", r"(junk|list|bulk|auto_reply)")
        )

    if "Auto-Submitted" not in header_drop_matchers:
        header_drop_matchers["Auto-Submitted"] = re.compile(
            services["app_config"].get("auto_submitted_regex", r"^auto-")
        )

    for name, entry in headers:
        if name in header_drop_matchers:
            trimmed_entry = entry.lstrip()

            if header_drop_matchers[name].search(trimmed_entry):
                logger.debug("Dropping: header {name} matched {entry}", extra={"name": name, "entry": entry})
                return True

    return False


def subject_is_challenge_response(subject: str) -> bool:
    if not subject:
        return False

    token = get_challenge_token_from_subject(subject)

    return True if token else False


def get_challenge_subject(sender_email: str, recipients: list[str], reference: str) -> str:
    token = services["validator"].get_token(sender_email, recipients[0], reference)

    # This needs to add in the leading space.
    return f" Confirm: {token}"


def form_header(header) -> str:
    return f"{header[0]}:{header[1]}"


def reform_email_text(headers: list, body_chunks: list) -> str:
    return f"{LINE_SEP.join(form_header(header) for header in headers)}{LINE_SEP}{LINE_SEP}{''.join(body_chunks)}"


def send_challenge(sender: Sender, subject: str, recipients: list[str], reference: str) -> None:
    """
    Send the challenge email to the sender, with the reference
    and then update the sender to indicate this.
    """
    template_name = services["app_config"].get("mail_template", "/etc/postconfirm/confirm.email.mustache")
    admin_address = services["app_config"].get("admin_address")

    challenge_address = recipients[0]

    with open(template_name, "r") as template:
        message_text = chevron.render(template, {
            "subject": subject,
            "sender_address": sender.email,
            "recipient_address": ", ".join(recipients),
            "challenge_address": challenge_address,
            "admin_address": admin_address,
            "id": reference,
        })

        headers = [
            ("From", f" {challenge_address}"),
            ("To", f" {sender.email}"),
            ("Subject", get_challenge_subject(sender.email, recipients, reference)),
        ]

        challenge_message = reform_email_text(headers, [message_text])

        with services["remailer"] as mailer:
            # This should probably have a sender
            mailer.sendmail([sender.email], challenge_message)


def get_challenge_token_from_subject(subject: str) -> str:
    """
    Extracts the challenge token from the subject
    """
    match = re.match(r"Confirm: (?P<token>(?P<recipient>.*?):(?P<messageref>.*?):(?P<hash>.*?))\s*$", subject, re.IGNORECASE)
    return match["token"] if match else None


def cleanup_mail(email) -> str:
    matches = re.match(r'^(.*<)?([^>]*)(>.*)?$', email.strip())

    if matches:
        return matches[2]
    else:
        return email


async def extract_headers(session: Session) -> tuple[Optional[str], list]:
    """
    Extracts the headers from the message/session.

    The subject is explicitly returned as the first parameter, if found.
    All of the headers are then returned as a list.
    """

    mail_headers = []
    mail_subject = None

    async with session.headers as headers:
        async for header in headers:
            value = header.value.tobytes().decode()

            if header.name.lower() == "subject":
                mail_subject = value.lstrip()

            mail_headers.append((header.name, value))

    return (mail_subject, mail_headers)


async def extract_body(session: Session) -> list:
    """
    Extracts the body from the message/session.

    This can appear in multiple chunks so this is returned as a list.
    """

    mail_body = []
    async with session.body as body:
        async for chunk in body:
            mail_body.append(chunk.tobytes().decode())

    return mail_body


def extract_reference(mail_headers: list[dict]) -> str:
    message_id = next((header[1] for header in mail_headers if header[0].lower() == "message-id"), None)

    if message_id:
        matches = re.match(r" <?(.*?)@", message_id)
        if matches:
            return matches[1].replace(":", "")

    logging.warning("Message is missing a Message ID. Generating a reference code")

    return ''.join(random.choice(IDENTIFIER_CHARS, 10))


def release_messages(sender: Sender) -> None:
    """
    Releases the stashed messages relating to the sender.
    """

    with services["remailer"] as mailer:
        for (recipients, message) in sender.unstash_messages():
            logging.debug("Releasing message from %(sender)s to %(recipients)s", {
                "sender": sender.get_email(),
                "recipients": ', '.join(recipients)
            })
            # Not sure if we should be including the sender here.
            mailer.sendmail(recipients, message, sender.get_email())


@Runner
async def handle(session: Session) -> Union[Accept, Reject, Discard]:
    """
    The milter processor for postconfirm.

    Decisions are made on the basis of where the message is going to and
    then who the sender is, since not all messages will be covered by the
    challenge system. Bulk messages that would otherwise be challenged are
    dropped. Once we know that at least one destination requires a
    challenge the sender is examined. In the simple cases the action will
    be either "accept", "reject", or "discard" and the appropriate
    response can be sent immediately.

    If the sender is "unknown" then we start the challenge process, which
    includes stashing the mail and indicating that the original should be
    discarded. The sender will be marked as "confirm" and the challenge
    sent. If the sender is "confirm" then we do not need to resend the
    challenge and proceed with just stashing the mail and discarding the
    original.

    The other case is that this is a challenge response. If the sender is
    "confirm" and the response is correct then the stashed mails are
    resent. The challenge response is then discarded. If the challenge
    response fails then the mail is rejected. If the sender is in any
    other state then the response is simply discarded.
    """

    # First we set up our Sender
    mail_from = cleanup_mail(await session.envelope_from())
    sender = get_sender(mail_from)

    # Then we can gather the recipients. The order is determined by the
    # SMTP protocol.
    mail_recipients = [
        cleanup_mail(recipient) async for recipient in session.envelope_recipients()
    ]

    challenge_recipients = recipient_requires_challenge(mail_recipients)

    # In order to tell if this is a challenge response we need the
    # subject, which means collecting all the headers.

    (mail_subject, mail_headers) = await extract_headers(session)

    is_challenge_response = subject_is_challenge_response(mail_subject)

    should_drop = message_should_be_dropped(mail_headers)

    # Now we can determine the course of action
    if challenge_recipients and should_drop:
        logger.debug("Message flagged for challenge but also matched drop conditions")
        return Discard()

    elif challenge_recipients and not is_challenge_response:
        # Process the sender
        action = sender.get_action()

        if action == "accept":
            logger.debug(
                "Message flagged for challenge and sender -- %(sender)s -- marked for acceptance",
                {"sender": mail_from}
            )
            return Accept()
        elif action == "reject":
            logger.debug("Message flagged for challenge and sender marked for rejecting")
            return Reject()
        elif action == "discard":
            logger.debug("Message flagged for challenge and sender marked for discarding")
            return Discard()

        # The remaining options are "unknown" or "confirm". In both cases
        # we need to stash the mail. That means completing the collection.

        mail_body = await extract_body(session)

        mail_as_text = reform_email_text(mail_headers, mail_body)

        challenge_reference = extract_reference(mail_headers)

        sender.stash_message(mail_as_text, mail_recipients, challenge_reference)

        actions_to_challenge = ["unknown", "expired"]
        if services["app_config"].get("resend_confirmation", True):
            actions_to_challenge.append("confirm")

        if action in actions_to_challenge:
            logger.debug("Message flagged for challenge and sender -- %(sender)s -- requires challenge", {"sender": mail_from})
            send_challenge(sender, mail_subject, challenge_recipients, challenge_reference)

        return Discard()

    elif is_challenge_response:
        # Process the response
        action = sender.get_action()

        if action == "confirm":
            token = get_challenge_token_from_subject(mail_subject)

            if not services["validator"].validate_token(sender.email, token, sender.get_refs()):
                # Reject the message
                logger.debug("Message is a response but is not valid")
                return Reject()

            logger.debug("Message is a valid confirmation response")

            # Mark the sender as valid
            sender.clear_references()
            sender.set_action("accept")

            # Release the messages
            release_messages(sender)

        else:
            logger.debug("Message is a response but we are not confirming the sender")

        # Always discard the message at this stage
        return Discard()

    # Anything else is just accepted
    return Accept()
