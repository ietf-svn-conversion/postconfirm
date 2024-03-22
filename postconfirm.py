import argparse
import logging

from anyio import create_tcp_listener, run
import config

from src.milter import Processor
from src.remailer import Remailer

services = {}


async def main():
    parser = argparse.ArgumentParser(
        prog="postconfirm",
        description="Milter handler for confirming that emails come from valid email addresses"
    )
    parser.add_argument("-c", "--config-file", default="/etc/postconfirm.cfg", type=argparse.FileType())
    parser.add_argument("-p", "--port")

    args = parser.parse_args()

    # Load the configuration
    app_config = config.Config(args.config_file)

    # Set up the root logger
    logging.basicConfig(level=app_config.get('log.level', logging.WARNING))

    # Set up a services registry
    services["app_config"] = app_config
    services["remailer"] = Remailer(app_config)

    # Start the listener
    listen_port = args.port or app_config.get("milter_port", 1999)
    listener = await create_tcp_listener(local_port=listen_port)
    await listener.serve(Processor.handle)


if __name__ == "__main__":
    run(main)