from src.sender import Sender
from tests.mocks.sender_handler import MockHandler, defined_sender


class TestSender:
    def test_it_initializes(self):
        sender = Sender(defined_sender, MockHandler())
        assert sender

    def test_it_tracks_the_sender_email(self):
        sender = Sender(defined_sender, MockHandler())
        assert sender.get_email() == defined_sender

    def test_it_gets_action_based_on_match(self):
        sender = Sender(defined_sender, MockHandler())
        action = sender.get_action()
        assert action == "accept"

    def test_it_gets_action_based_on_pattern(self):
        sender = Sender("noone@example.com", MockHandler())
        action = sender.get_action()
        assert action == "confirm"

        sender = Sender("anyone@nowhere.example.com", MockHandler())
        action = sender.get_action()
        assert action == "reject"

    def test_the_action_can_be_changed(self):
        sender = Sender(defined_sender, MockHandler())
        action = sender.get_action()
        assert action == "accept"

        sender.set_action("reject")
        action = sender.get_action()
        assert action == "reject"

    def test_setting_action_overrides_pattern(self):
        sender = Sender("anyone@nowhere.example.com", MockHandler())
        action = sender.get_action()
        assert action == "reject"

        sender.set_action("accept")
        action = sender.get_action()
        assert action == "accept"

    def test_emails_can_be_unstashed(self):
        sender = Sender(defined_sender, MockHandler())
        email_data = list(sender.unstash_messages())
        assert len(email_data) == 2

    def test_emails_can_be_stashed(self):
        sender = Sender(defined_sender, MockHandler())
        ref = sender.stash_message("foo", ["e@f.g"])
        email_data = list(sender.unstash_messages())
        assert len(email_data) == 3
        assert ref is None

    def test_emails_can_be_stashed_with_ref(self):
        sender = Sender(defined_sender, MockHandler())
        test_ref = "a-reference"
        ref = sender.stash_message("foo", ["e@f.g"], test_ref)
        email_data = list(sender.unstash_messages())
        assert len(email_data) == 3
        assert ref == [test_ref]
