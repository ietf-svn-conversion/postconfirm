import logging
from typing import Optional

import psycopg
from psycopg_pool import ConnectionPool


logger = logging.getLogger(__name__)


pool_cache: dict[str, ConnectionPool] = {}


def get_db_pool(config_fragment: dict, cache_key: Optional[str] = None) -> ConnectionPool:
    global pool_cache

    if not cache_key or cache_key not in pool_cache:
        try:
            pool = ConnectionPool(kwargs={
                    "dbname": config_fragment.get("name", "postconfirm"),
                    "user": config_fragment.get("user", "postconfirm"),
                    "password": config_fragment.get("password", None),
                    "host": config_fragment.get("host", "localhost"),
                    "port": config_fragment.get("port", 5432)
            })
        except psycopg.OperationalError as e:
            print(f"The error '{e}' occurred")
            raise e

        pool.open(wait=True)

        if cache_key:
            pool_cache[cache_key] = pool

        return pool
    else:
        return pool_cache[cache_key]
