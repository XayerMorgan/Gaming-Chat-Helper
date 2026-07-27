import queue
import unittest

from gamers_chat_helper import GamersChatHelper


class _FakeRoot:
    def __init__(self):
        self.after_calls = []

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))


class UiQueuePumpTests(unittest.TestCase):
    def test_pump_yields_after_bounded_batch(self):
        app = object.__new__(GamersChatHelper)
        app._alive = True
        app._ui_queue = queue.Queue()
        app.root = _FakeRoot()
        seen = []
        for number in range(40):
            app._ui_queue.put(lambda number=number: seen.append(number))

        app._pump_ui_queue()

        self.assertEqual(len(seen), 32)
        self.assertEqual(app._ui_queue.qsize(), 8)
        self.assertEqual(app.root.after_calls[0][0], 20)

    def test_callback_failure_does_not_stop_following_work(self):
        app = object.__new__(GamersChatHelper)
        app._alive = True
        app._ui_queue = queue.Queue()
        app.root = _FakeRoot()
        seen = []

        def fail():
            raise RuntimeError("test failure")

        app._ui_queue.put(fail)
        app._ui_queue.put(lambda: seen.append("continued"))
        app._pump_ui_queue()

        self.assertEqual(seen, ["continued"])
        self.assertEqual(app.root.after_calls[0][0], 50)
