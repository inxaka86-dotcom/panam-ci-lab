"""Authorization-gate tests: valid owner, impostor, spoofed login and malformed tasks."""
import unittest

from agent_mvp.issue_task import validate, REPOSITORY, OWNER_ID, OWNER_LOGIN


def valid_issue():
    return {
        "action": "opened",
        "issue": {
            "number": 70,
            "state": "open",
            "title": "[PANAM-AUTOCODER] Test trusted task",
            "body": "PANAM_AUTOCODER_V1\nСоздай модуль в изолированной песочнице.",
            "user": {"login": OWNER_LOGIN, "id": OWNER_ID},
        },
    }


class AuthorizationTests(unittest.TestCase):
    def assert_rejected(self, data, repo=REPOSITORY):
        with self.assertRaises(ValueError):
            validate(data, repo)

    def test_owner_allowed(self):
        number, task = validate(valid_issue(), REPOSITORY)
        self.assertEqual(number, 70)
        self.assertIn("Создай модуль", task)

    def test_impostor_denied(self):
        data = valid_issue()
        data["issue"]["user"]["login"] = "random-outsider"
        data["issue"]["user"]["id"] = 12345
        self.assert_rejected(data)

    def test_spoofed_login_denied(self):
        data = valid_issue()
        data["issue"]["user"]["id"] = 12345
        self.assert_rejected(data)

    def test_spoofed_id_denied(self):
        data = valid_issue()
        data["issue"]["user"]["login"] = "lookalike"
        self.assert_rejected(data)

    def test_repository_denied(self):
        self.assert_rejected(valid_issue(), "attacker/repo")

    def test_edited_event_denied(self):
        data = valid_issue()
        data["action"] = "edited"
        self.assert_rejected(data)

    def test_pull_request_denied(self):
        data = valid_issue()
        data["issue"]["pull_request"] = {"url": "https://example.com"}
        self.assert_rejected(data)

    def test_marker_denied(self):
        data = valid_issue()
        data["issue"]["body"] = "Just run the AI!"
        self.assert_rejected(data)

    def test_title_denied(self):
        data = valid_issue()
        data["issue"]["title"] = "Please run the AI"
        self.assert_rejected(data)

    def test_empty_body_denied(self):
        data = valid_issue()
        data["issue"]["body"] = "PANAM_AUTOCODER_V1\n "
        self.assert_rejected(data)

    def test_oversized_body_denied(self):
        data = valid_issue()
        data["issue"]["body"] = "PANAM_AUTOCODER_V1\n" + "д" * 3000
        self.assert_rejected(data)

    def test_nonprintable_denied(self):
        data = valid_issue()
        data["issue"]["body"] += "\x00"
        self.assert_rejected(data)

    def test_noninteger_issue_denied(self):
        data = valid_issue()
        data["issue"]["number"] = "70"
        self.assert_rejected(data)


if __name__ == "__main__":
    unittest.main()
