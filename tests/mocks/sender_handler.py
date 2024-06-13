defined_sender = "specific@example.com"


class MockHandler:
    def __init__(self):
        self.actions = {defined_sender: ("accept", None)}

        self.stash = {
            defined_sender: [
                ("a message", ["a@b.c", "d@e.f"]),
                ("a message", ["a@b.c", "d@e.f"]),
            ]
        }

    def get_action_for_sender(self, sender: str):
        if sender in self.actions:
            return self.actions[sender]
        else:
            return None

    def get_patterns(self):
        return iter(
            [
                (r".*@example\.com", "confirm", "foo"),
                (r".*@nowhere\.example\.com", "reject", None),
            ]
        )

    def set_action_for_sender(self, sender: str, action: str, ref: str):
        self.actions[sender] = (action, ref)

    def stash_message_for_sender(self, sender: str, msg: str, recipients: list[str]):
        data = (msg, recipients)

        if sender in self.stash:
            self.stash[sender].append(data)
        else:
            self.stash[sender] = [data]

    def unstash_messages_for_sender(self, sender: str):
        if sender in self.stash:
            emails = self.stash[sender]
            del self.stash[sender]
        else:
            emails = []

        for index, data in enumerate(emails):
            yield (index, *data)
