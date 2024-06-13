from psycopg import Cursor


from .handler_db import HandlerDb
from .handler_db_static import HandlerDbStatic
from .sender import Sender


handlers = {"db": HandlerDb, "static": HandlerDbStatic, "_default": "db"}
instances = {}


def get_handler_instance(name: str, **kwargs) -> any:
    global instances

    if name not in instances:
        instances[name] = handlers[name](**kwargs)

    return instances[name]


def get_default_handler() -> any:
    handler_name = handlers.get("_default", "db")

    return get_handler_instance(handler_name)


def get_sender(email) -> Sender:
    return Sender(email, get_default_handler())


def get_static_sender(email, cursor: Cursor = None) -> Sender:
    return Sender(email, get_handler_instance("static", cursor=cursor))
