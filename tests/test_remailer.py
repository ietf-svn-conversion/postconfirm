from io import StringIO
from os.path import dirname
from smtplib import SMTPServerDisconnected
from unittest.mock import Mock, patch

import config
import pytest

from src.remailer.remailer import Remailer

empty_cfg = config.Config(StringIO(""))
cfg = config.Config(f"{dirname(__file__)}/fixtures/config.cfg")


class TestRemailer:
    def test_it_initialises_defaults(self):
        mailer = Remailer(empty_cfg)

        assert mailer.host == "localhost"
        assert mailer.port == 25
        assert mailer.sender_from == "<>"

    def test_it_initialises_from_config(self):
        mailer = Remailer(cfg)

        assert mailer.host == cfg["smtp_host"]
        assert mailer.port == cfg["smtp_port"]
        assert mailer.sender_from == cfg["remail_sender"]

    @patch("src.remailer.remailer.SMTP")
    def test_it_provides_a_consistent_connection(self, mock_smtp):
        mailer = Remailer(cfg)

        connection = mailer.get_connection()

        assert mailer.smtp is connection

        new_connection = mailer.get_connection()

        assert new_connection is connection

    @patch("src.remailer.remailer.SMTP")
    def test_it_handles_context(self, mock_smtp):
        with Remailer(cfg) as mailer:
            connection = mailer.get_connection()

            assert mailer.smtp is connection

    @pytest.mark.skip("Issue with the docmd mocking/connections being the same")
    @patch(
        "src.remailer.remailer.SMTP",
    )
    def test_it_handles_disconnection(self, mock_smtp):
        mock_smtp.return_value.docmd = Mock(side_effect=SMTPServerDisconnected)

        mailer = Remailer(cfg)
        mailer.get_connection()

        mock_smtp.return_value.docmd.assert_not_called()

        mailer.get_connection()

        mock_smtp.return_value.docmd.assert_called_with("NOOP")

    @patch("src.remailer.remailer.SMTP")
    def test_it_defaults_the_sender(self, mock_smtp):
        mailer = Remailer(cfg)

        recipients = ["a@example.com", "b@example.com"]
        message = "This is the dummy message"

        mailer.sendmail(recipients, message)

        mock_smtp.return_value.sendmail.assert_called_with(
            mailer.sender_from, recipients, message
        )

    def test_the_sender_can_be_overridden(self):
        with patch("src.remailer.remailer.SMTP", autospec=True) as mock_smtp:
            mailer = Remailer(cfg)

            sender = "someone@example.com"
            recipients = ["a@example.com", "b@example.com"]
            message = "This is the dummy message"

            mailer.sendmail(recipients, message, sender)

            mock_smtp.return_value.sendmail.assert_called_with(
                sender, recipients, message
            )
