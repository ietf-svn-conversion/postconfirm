from .handler_internal import HandlerInternal
from .handler_query import HandlerQuery

handlers = []


def init_handlers(services) -> None:
    app_config = services["app_config"]

    for challenge_config in app_config.get("challenges", [{}]):
        if "type" not in challenge_config or challenge_config["type"] == "internal":
            handlers.append(HandlerInternal(app_config))
        elif challenge_config["type"] == "query":
            handlers.append(HandlerQuery(challenge_config))

    services["challenge_handlers"] = handlers
