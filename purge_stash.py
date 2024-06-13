import argparse
import datetime
import logging
from os.path import basename

import config

from src.db import get_db_pool


logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        prog="purge_stash",
        description="Admin script to remove expired stash entries from the store"
    )
    parser.add_argument("-c", "--config-file", default="/etc/postconfirm.cfg", type=argparse.FileType())
    parser.add_argument("--ttl", type=int, help="Time for stash entries to live (in seconds)")
    parser.add_argument("-n", "--dry-run", action='store_true', help="Do not actually modify the data")

    args = parser.parse_args()

    # Load the configuration
    app_config = config.Config(args.config_file)

    # Set up the root logger
    logging.basicConfig(level=app_config.get('log.level', logging.WARNING))

    ttl = args.ttl or app_config.get("purge.time_to_live", 86400)

    # We need to create a connection and start a transaction
    with get_db_pool(app_config["db"], "db").connection() as connection:
        with connection.cursor() as cursor:

            ttl_interval = datetime.timedelta(seconds=ttl)

            # We start by gathering details of the expired entries.

            cursor.execute(
                """
                SELECT
                    id, sender
                FROM
                    stash
                WHERE
                    created < DATE_SUBTRACT(CURRENT_TIMESTAMP, %(interval)s)
                """,
                {"interval": ttl_interval}
            )

            ids_by_sender = {}

            for (row_id, sender) in cursor:
                if sender not in ids_by_sender:
                    ids_by_sender[sender] = [row_id]
                else:
                    ids_by_sender[sender].append(row_id)

            # We can then remove them. We do this by sender for logging purposes.

            for sender, row_ids in ids_by_sender.items():
                logger.debug("Removing %(count)d entries for %(sender)s", {"count": len(row_ids), "sender": sender})

                if not args.dry_run:
                    cursor.execute(
                        """
                        DELETE FROM
                            stash
                        WHERE
                            sender = %(sender)s
                            AND id = ANY(%(ids)s)
                        """,
                        {"sender": sender, "ids": row_ids}
                    )

            # Then we can gather a list of senders in the confirm state but 
            # who have no stashed entries.

            cursor.execute(
                """
                SELECT
                    senders.sender
                FROM
                    senders
                    LEFT JOIN stash ON (senders.sender = stash.sender)
                WHERE
                    senders.action = 'confirm'
                    AND stash.id IS NULL
                """
            )

            for (sender,) in cursor:
                logger.debug("Clearing confirmation settings for %(sender)s", {"sender": sender})

                if not args.dry_run:
                    cursor.execute(
                        """
                        UPDATE
                            senders
                        SET
                            action='expired',
                            ref=NULL
                        WHERE
                            sender=%(sender)s
                            AND action='confirm'
                        """,
                        {"sender": sender}
                    )

            connection.commit()


if __name__ == "__main__":
    main()
