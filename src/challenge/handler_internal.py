import logging
from typing import Optional, Iterable

from config import Config

from src.db import get_db_pool

from .typing import Action


logger = logging.getLogger(__name__)


class HandlerInternal:
    def __init__(self, app_config: Config) -> None:
        self.app_config = app_config

    def get_action(self, email: str) -> Optional[Action]:
        """
        Return any action for the given challenge email
        """
        with get_db_pool(self.app_config["db"], "db").connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        action_to_take
                        FROM challenges
                        WHERE challenge=%(challenge)s AND challenge_type='E'
                    """,
                    {"challenge": email}
                )

                result = cursor.fetchone()

                if result:
                    return result[0]

        return None

    def get_patterns(self) -> Iterable[tuple[str, str]]:
        """
        Returns any pattern-type actions
        """
        with get_db_pool(self.app_config["db"], "db").connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        challenge, action_to_take
                        FROM challenges
                        WHERE challenge_type='P'
                    """
                )

                results = cursor.fetchall()

                cursor.close()

                return results
