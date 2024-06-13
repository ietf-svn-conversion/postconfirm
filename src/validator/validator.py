import base64
import hashlib
import hmac
import logging

from config import Config


logger = logging.getLogger(__name__)


class Validator:
    """
    Provides validation services for dealing with the confirmation token
    """
    def __init__(self, app_config: Config):
        self.hash_key = bytes()

        hash_key_filename = app_config.get("key_file")

        if not hash_key_filename:
            logger.error("A hash key filename must be provided as 'key_file'")
            return

        try:
            with open(hash_key_filename, "rb") as f:
                self.hash_key = f.read()
        except (FileNotFoundError, PermissionError) as e:
            logger.error("The hash key file %(filename)s could not be opened: %(reason)s", {
                "filename": hash_key_filename,
                "reason": str(e)
            })
            return

    def hash(self, message_bytes: bytes) -> str:
        digest = hmac.new(self.hash_key, message_bytes, hashlib.sha224).digest()
        return base64.urlsafe_b64encode(digest).strip(b"=").decode()

    def make_hash(self, sender: str, recipient: str, reference: str):
        hashable = f"{sender}-{recipient}-{reference}"

        return self.hash(hashable.encode())

    def validate_hash(self, sender: str, recipient: str, reference: str, hash: str) -> bool:
        return self.make_hash(sender, recipient, reference) == hash

    def validate_token(self, sender: str, token: str, references: list[str]) -> bool:
        try:
            (recipient, reference, hash) = token.strip().split(":")
        except ValueError:
            return False

        for reference_entry in references:
            if reference_entry == reference:
                return self.validate_hash(sender, recipient, reference_entry, hash)

        return False

    def get_token(self, sender: str, recipient: str, reference: str) -> str:
        hash_str = self.make_hash(sender, recipient, reference)

        return f"{recipient}:{reference}:{hash_str}"
