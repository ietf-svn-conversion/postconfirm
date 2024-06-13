import json
import logging
from typing import Iterable, Optional, Tuple

from config import Config
from psycopg import Cursor

from .typing import Action

from src import services
from src.db import get_db_pool


logger = logging.getLogger(__name__)


class HandlerDbStatic:
    def __init__(self, app_config: Config = None, cursor: Cursor = None) -> None:
        self.app_config = app_config if app_config else services["app_config"]
        self.cursor = cursor

    def _get_cursor(self):
        if self.cursor:
            yield self.cursor
        else:
            with get_db_pool(self.app_config["db"], "db").connection() as connection:
                with connection.cursor() as cursor:
                    yield cursor

    def get_action_for_sender(self, sender: str) -> Optional[Tuple[Action, str]]:
        """
        Return any action for the given sender
        """
        for cursor in self._get_cursor():
            cursor.execute(
                """
                SELECT
                    action, ref
                    FROM senders_static
                    WHERE sender=%(sender)s AND type='E'
                """,
                {"sender": sender}
            )
            result = cursor.fetchone()

            if result:
                ref = result[1]
                if ref:
                    try:
                        ref = json.loads(ref)
                    except json.JSONDecodeError:
                        pass

                return (
                    result[0],
                    ref
                )

        return ('unknown', None)

    def get_patterns(self) -> Iterable[Tuple[str, str, str]]:
        """
        Returns any pattern-type actions
        """
        for cursor in self._get_cursor():
            cursor.execute(
                """
                SELECT
                    sender, action, ref
                    FROM senders_static
                    WHERE type='P'
                """
            )

            for row in cursor:
                yield row

    def set_action_for_sender(self, sender: str, action: Action, ref: str) -> bool:
        """
        Sets the action for the sender
        """
        for cursor in self._get_cursor():
            encoded_ref = json.dumps(ref) if ref else None

            try:
                cursor.execute(
                    """
                    INSERT INTO senders_static
                        (sender, action, ref, type, source)
                        VALUES
                            (%(sender)s, %(action)s, %(ref)s, 'E', 'static')
                        ON CONFLICT (sender)
                            DO UPDATE SET action=%(action)s
                    """,
                    {"sender": sender, "action": action, "ref": encoded_ref}
                )
                cursor.connection.commit()
                return True

            except Exception as e:
                print(f"ERROR setting sender: {e}", flush=True)
                return False

    def stash_message_for_sender(
        self, sender: str, msg: str, recipients: list[str]
    ) -> bool:
        """
        Stores the message for the sender
        """
        for cursor in self._get_cursor():
            try:
                cursor.execute(
                    """
                    INSERT INTO stash_static
                        (sender, recipients, message)
                        VALUES
                            (%(sender)s, %(recipients)s, %(message)s)
                    """,
                    {"sender": sender, "recipients": json.dumps(recipients), "message": msg}
                )
                cursor.connection.commit()
                return True

            except Exception as e:
                print(f"ERROR stashing mail: {e}")
                return False

    def unstash_messages_for_sender(
        self, sender: str
    ) -> Iterable[Tuple[str, list[str]]]:
        """
        Yields the messages for the sender
        """
        for cursor in self._get_cursor():
            try:
                cursor.execute(
                    """
                    SELECT
                        id, recipients, message
                        FROM stash_static
                        WHERE sender=%(sender)s
                    """,
                    {"sender": sender}
                )

                for (row_id, recipients, message) in cursor:
                    yield (json.loads(recipients), message)

                    # Use a different cursor to avoid clobbering the in-progress loop
                    cursor.connection.cursor().execute(
                        """
                        DELETE FROM stash_static
                            WHERE id=%(row_id)s
                        """,
                        {"row_id": row_id}
                    )
                    cursor.connection.commit()

            except Exception as e:
                print(f"ERROR unstashing mails: {e}", flush=True)
                return
