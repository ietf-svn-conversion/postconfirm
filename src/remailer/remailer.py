import logging
from smtplib import SMTP, SMTPServerDisconnected

from config import Config


logger = logging.getLogger(__name__)


class Remailer:
    """
    Provides a simple wrapper around the python mail code that is context
    aware, allows for re-use and will default the envelope sender.

    Configuration is via the following keys:
    * `smtp_host` (defaults to "localhost") as the host to send via
    * `smtp_port` (defaults to 25) as the port to connect to on the `smtp_host`
    * `remailer_sender` (defaults to "<>") as the default envelope sender
    """

    def __init__(self, app_config: Config):
        self.host = app_config.get("smtp_host", "localhost")
        self.port = app_config.get("smtp_port", 25)
        self.sender_from = app_config.get("remail_sender", "<>")

        self.smtp = None

    def get_connection(self) -> SMTP:
        if not self._check_smtp_connection():
            self._init_smtp_connection()

        return self.smtp

    def sendmail(self, recipients: list[str], message: str, sender: str = None) -> any:
        connection = self.get_connection()

        try:
            return connection.sendmail(sender or self.sender_from, recipients, message)
        except Exception as e:
            logger.error("Exception in SMTP: %(reason)s", {"reason": str(e)})

    def __enter__(self) -> any:
        return self

    def __exit__(self, type, value, traceback) -> bool:
        if self.smtp:
            try:
                self.smtp.quit()
            except SMTPServerDisconnected:
                pass

            self.smtp = None

        return True

    def _check_smtp_connection(self) -> bool:
        if not self.smtp:
            return False

        try:
            self.smtp.docmd("NOOP")
            return True

        except SMTPServerDisconnected:
            self.smtp = None
            return False

    def _init_smtp_connection(self) -> None:
        self.smtp = SMTP(host=self.host, port=self.port)
