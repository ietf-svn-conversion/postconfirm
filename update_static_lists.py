import argparse
import logging
from os.path import basename
from pathlib import Path
import re
from typing import Union

import config
import psycopg

from src import services
from src.db import get_db_pool
from src.sender import get_static_sender


logger = logging.getLogger(__name__)


dry_run = False


def process_senders(cursor: psycopg.Cursor, app_config: config.Config) -> None:
    logger.debug("Clearing down old static sender data")

    if not dry_run:
        cursor.execute(
            """
            TRUNCATE
                senders_static
            RESTART IDENTITY
            """
        )

    email_lists = [
        ("confirmlist", "accept"),
        ("allowlists", "accept"),
        ("whitelists", "accept"),
        ("rejectlists", "reject"),
        ("blacklists", "reject"),
        ("discardlists", "discard"),
    ]

    for config_name, action in email_lists:
        config_lists = app_config.get(config_name, [])

        if isinstance(config_lists, str):
            config_lists = [config_lists]

        for list_name in config_lists:
            logger.info("Processing list (type: %(type)s; file: %(file_name)s)", {
                "type": action,
                "file_name": list_name
            })
            source_name = basename(list_name)

            add_email_sender_entries(cursor, list_name, action, source_name)

    regex_lists = [
        ("allowregex", "accept"),
        ("whiteregex", "accept"),
        ("rejectregex", "reject"),
        ("blackregex", "reject"),
        ("discardregex", "discard"),
    ]

    for config_name, action in regex_lists:
        for list_name in app_config.get(config_name, []):
            logger.info("Processing regex list (type: %(type)s; file: %(file_name)s)", {
                "type": action,
                "file_name": list_name
            })

            source_name = basename(list_name)

            add_pattern_sender_entries(cursor, list_name, action, source_name)


def add_email_sender_entries(cursor, list_name: str, action: str, source_name: str) -> None:
    try:
        with open(list_name, "r") as f:
            for entry in f:
                add_sender_entry(cursor, entry.strip(), action, source_name)
    except (FileNotFoundError, PermissionError) as e:
        logger.warning("Skipping invalid email list %(filename)s (%(source)s): %(reason)s", {
            "source": source_name,
            "filename": list_name,
            "reason": str(e)
        })


def add_pattern_sender_entries(cursor, list_name: str, action: str, source_name: str) -> None:
    try:
        with open(list_name, "r") as f:
            line_counter = 0
            for entry in f:
                line_counter += 1

                try:
                    stripped_entry = entry.strip()
                    re.compile(stripped_entry)

                    add_sender_entry(cursor, stripped_entry, action, source_name, "P")
                except re.error as e:
                    logger.warning("Skipping invalid entry on %(line_counter)d of %(filename)s (%(source)s): %(entry)s -- %(reason)s", {
                                        "line_counter": line_counter,
                                        "filename": list_name,
                                        "source": source_name,
                                        "entry": stripped_entry,
                                        "reason": e.msg
                                    })
    except (FileNotFoundError, PermissionError) as e:
        logger.error("Skipping invalid pattern list %(filename)s (%(source)s): %(reason)s", {
            "source": source_name,
            "filename": list_name,
            "reason": str(e)
        })


def add_sender_entry(cursor, sender: str, action: str, source_name: str, sender_type: str = "E", reference: str = None) -> None:
    values = {
        "sender": sender,
        "action": action,
        "source_name": source_name,
        "type": sender_type,
        "reference": reference,
    }

    logger.debug("Adding %(type)s entry for %(sender)s from %(source_name)s as %(action)s with %(reference)s", values)

    if not dry_run:
        cursor.execute(
            """
            INSERT INTO senders_static
                (sender, action, source, ref, type)
                VALUES
                    (%(sender)s, %(action)s, %(source_name)s, %(reference)s, %(type)s)
                ON CONFLICT (sender)
                    DO UPDATE SET action=%(action)s, source=%(source_name)s, ref=%(reference)s, type=%(type)s
            """,
            values
        )


def process_in_progress(cursor: psycopg.Cursor, app_config: config.Config) -> None:
    logger.debug("Clearing down old static stash data")

    if not dry_run:
        cursor.execute(
            """
            TRUNCATE
                stash_static
            RESTART IDENTITY
            """
        )

    mail_cache_dir = app_config.get("mail_cache_dir", None)

    if mail_cache_dir:
        logger.info("Processing in-progress confirmations by scanning cache: %(cache_dir)s", {"cache_dir": mail_cache_dir})

        process_cache_directory(cursor, mail_cache_dir)


def process_cache_directory(cursor: psycopg.Cursor, cache_dir: str) -> None:
    senders = {}

    cache_path = Path(cache_dir)
    for entry in cache_path.iterdir():
        if not entry.is_file():
            continue

        result = process_cache_file(str(entry))
        if not result:
            logger.warning("Could not process %(filename)s. Skipping", {"filename": str(entry)})
            continue

        (from_email, recipients, message) = result
        reference = entry.name

        if "@" not in from_email:
            logger.warning("%(filename)s has no valid FROM. Probably an autogenerated message. Skipping", {"filename": str(entry)})
            continue

        if from_email not in senders:
            this_sender = get_static_sender(from_email, cursor)
            senders[from_email] = this_sender
        else:
            this_sender = senders[from_email]

        if not dry_run:
            this_sender.stash_message(message, recipients, reference)


def process_cache_file(filename: str) -> Union[False, tuple[str, list[str], str]]:
    try:
        with open(filename) as f:
            message = f.read()

            (headers, body) = message.split("\n\n", maxsplit=1)

            sender_match = re.match(r"From ([^ ]+)", headers)
            recipient_match = re.search(r"^X-Original-To: (.+)$", headers, re.MULTILINE | re.IGNORECASE)

            if not sender_match or not recipient_match:
                return False

            return (sender_match[1], [recipient_match[1]], message)

    except (FileNotFoundError, PermissionError):
        return False


def process_challenges(cursor: psycopg.Cursor, app_config: config.Config) -> None:
    logger.debug("Clearing down old challenge data")

    if not dry_run:
        cursor.execute(
            """
            TRUNCATE
                challenges
            RESTART IDENTITY
            """
        ) 

    challenge_lists = [
        ("challengelists", "challenge"),
        ("nochallengelists", "ignore"),
    ]

    for config_name, action in challenge_lists:
        config_lists = app_config.get(config_name, [])

        if isinstance(config_lists, str):
            config_lists = [config_lists]

        for list_name in config_lists:
            logger.info("Processing challenge list (type: %(type)s; file: %(file_name)s)", {
                "type": action,
                "file_name": list_name
            })
            source_name = basename(list_name)

            add_email_challenge_entries(cursor, list_name, action, source_name)

    regex_lists = [
        ("challengeregex", "challenge"),
        ("nochallengeregex", "ignore"),
    ]

    for config_name, action in regex_lists:
        for list_name in app_config.get(config_name, []):
            logger.info("Processing challenge regex list (type: %(type)s; file: %(file_name)s)", {
                "type": action,
                "file_name": list_name
            })

            source_name = basename(list_name)

            add_pattern_challenge_entries(cursor, list_name, action, source_name)


def add_email_challenge_entries(cursor, list_name: str, action: str, source_name: str) -> None:
    try:
        with open(list_name, "r") as f:
            for entry in f:
                add_challenge_entry(cursor, entry.strip(), action, source_name)
    except (FileNotFoundError, PermissionError) as e:
        logger.warning("Skipping invalid email challenge list %(filename)s (%(source)s): %(reason)s", {
            "source": source_name,
            "filename": list_name,
            "reason": str(e)
        })


def add_pattern_challenge_entries(cursor, list_name: str, action: str, source_name: str) -> None:
    try:
        with open(list_name, "r") as f:
            line_counter = 0
            for entry in f:
                line_counter += 1

                try:
                    stripped_entry = entry.strip()
                    re.compile(stripped_entry)

                    add_challenge_entry(cursor, stripped_entry, action, source_name, "P")
                except re.error as e:
                    logger.warning("Skipping invalid entry on %(line_counter)d of %(filename)s (%(source)s): %(entry)s -- %(reason)s", {
                                        "line_counter": line_counter,
                                        "filename": list_name,
                                        "source": source_name,
                                        "entry": stripped_entry,
                                        "reason": e.msg
                                    })
    except (FileNotFoundError, PermissionError) as e:
        logger.error("Skipping invalid pattern challenge list %(filename)s (%(source)s): %(reason)s", {
            "source": source_name,
            "filename": list_name,
            "reason": str(e)
        })


def add_challenge_entry(cursor, challenge: str, action: str, source_name: str, challenge_type: str = "E") -> None:
    values = {
        "challenge": challenge,
        "action_to_take": action,
        "source_name": source_name,
        "challenge_type": challenge_type,
    }

    logger.debug("Adding %(challenge_type)s entry for %(challenge)s from %(source_name)s as challenge %(action_to_take)s", values)

    if not dry_run:
        cursor.execute(
            """
            INSERT INTO challenges
                (challenge, action_to_take, source, challenge_type)
                VALUES
                    (%(challenge)s, %(action_to_take)s, %(source_name)s, %(challenge_type)s)
                ON CONFLICT (challenge)
                    DO UPDATE SET action_to_take=%(action_to_take)s, source=%(source_name)s, challenge_type=%(challenge_type)s
            """,
            values
        )


def main():
    global dry_run

    parser = argparse.ArgumentParser(
        prog="update_static_lists",
        description="Admin script to convert the file-based lists into the database"
    )
    parser.add_argument("-c", "--config-file", default="/etc/postconfirm.cfg", type=argparse.FileType())
    parser.add_argument("-n", "--dry-run", action='store_true', help="Do not actually modify the data")
    parser.add_argument("--skip-senders")
    parser.add_argument("--skip-in-progress")
    parser.add_argument("--skip-challenges")

    args = parser.parse_args()

    # Load the configuration
    app_config = config.Config(args.config_file)

    services["app_config"] = app_config

    # Set up the root logger
    logging.basicConfig(level=app_config.get('log.level', logging.WARNING))

    dry_run = args.dry_run

    with get_db_pool(app_config["db"], "db").connection() as connection:
        with connection.cursor() as cursor:

            if not args.skip_senders:
                process_senders(cursor, app_config)

            if not args.skip_in_progress:
                process_in_progress(cursor, app_config)

            if not args.skip_challenges:
                process_challenges(cursor, app_config)

            connection.commit()


if __name__ == "__main__":
    main()
