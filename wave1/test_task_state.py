import copy
import unittest
from datetime import datetime, timedelta, timezone

from wave1.task_state import TaskStateError, is_due, new_task, transition, validate


class TaskStateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    def test_queue_wait_resume_complete(self):
        state = new_task("synthetic-task-001", now=self.now)
        self.assertTrue(is_due(state, now=self.now))
        running = transition(state, "running", now=self.now)
        self.assertFalse(is_due(running, now=self.now))
        wake = self.now + timedelta(minutes=10)
        waiting = transition(running, "waiting", now=self.now, next_wake_at=wake)
        self.assertFalse(is_due(waiting, now=self.now))
        self.assertTrue(is_due(waiting, now=wake))
        resumed = transition(waiting, "running", now=wake)
        done = transition(resumed, "succeeded", now=wake + timedelta(seconds=1))
        self.assertEqual(done["status"], "succeeded")
        self.assertFalse(is_due(done, now=wake + timedelta(hours=1)))

    def test_invalid_transition_fails_closed(self):
        state = new_task("synthetic-task-002", now=self.now)
        with self.assertRaises(TaskStateError):
            transition(state, "succeeded", now=self.now)

    def test_integrity_detects_tamper(self):
        state = new_task("synthetic-task-003", now=self.now)
        tampered = copy.deepcopy(state)
        tampered["status"] = "cancelled"
        with self.assertRaises(TaskStateError):
            validate(tampered)


if __name__ == "__main__":
    unittest.main()
