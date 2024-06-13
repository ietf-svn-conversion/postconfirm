import argparse
import logging

import config

from src.db import get_db_pool


logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        prog="extract_confirmed_accounts",
        description="Admin script to generate a list of the confirmed accounts"
    )
    parser.add_argument("-c", "--config-file", default="/etc/postconfirm.cfg", type=argparse.FileType())

    args = parser.parse_args()

    # Load the configuration
    app_config = config.Config(args.config_file)

    # Set up the root logger
    logging.basicConfig(level=app_config.get('log.level', logging.WARNING))

    # We need to create a connection and start a transaction
    with get_db_pool(app_config["db"], "db").connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    sender
                FROM
                    senders
                WHERE
                    source='postconfirm'
                    AND action='accept'
                    AND type='E'
                """
            )

            for (sender,) in cursor:
                print(sender)


if __name__ == "__main__":
    main()
