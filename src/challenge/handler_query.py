import logging
from typing import Optional, Iterable

from config import Config

from src.db import get_db_pool

from .typing import Action


logger = logging.getLogger(__name__)


class HandlerQuery:
    def __init__(self, handler_config: Config) -> None:
        self.handler_config = handler_config

    def _get_db_config(self):
        return self.handler_config["db"]
    
    def _get_name(self):
        return self.handler_config["name"]

    def _split_email(self, email: str) -> tuple[str, str]:
        """
        Splits the email address into a local part and a domain.
        """
        return email.split('@', maxsplit=1)
    
    def get_action(self, email: str) -> Optional[Action]:
        """
        Return any action for the given challenge email
        """

        if "action_query" not in self.handler_config:
            logger.debug("Skipping non-existent action query for %(name)s", {"name": self._get_name()})
            return None

        (local_part, domain) = self._split_email(email)

        try:
            with get_db_pool(self._get_db_config(), self._get_name()).connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        self.handler_config["action_query"],
                        {
                            "local_part": local_part,
                            "domain": domain,
                        }
                    )

                    result = cursor.fetchone()

                    if result:
                        return result[0]

        except Exception as e:
            logger.error("Failed to execute action query for %(name)s with local part %(local_part)s and domain %(domain)s: %(reason)s", {
                "name": self._get_name(),
                "local_part": local_part,
                "domain": domain,
                "reason": str(e)
            })

        return None

    def get_patterns(self) -> Iterable[tuple[str, str]]:
        """
        Returns any pattern-type actions
        """

        if "pattern_query" not in self.handler_config:
            logger.debug("Skipping non-existent pattern query for %(name)s", {"name": self._get_name()})
            return []

        try:
            with get_db_pool(self._get_db_config(), self._get_name()).connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        self.handler_config["pattern_query"],
                    )

                    results = cursor.fetchall()

                    cursor.close()

                    return results

        except Exception as e:
            logger.error("Failed to execute pattern query for %(name)s: %(reason)s", {
                "name": self._get_name(),
                "reason": str(e)
            })
