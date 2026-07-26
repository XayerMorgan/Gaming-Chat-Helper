import unittest
from types import SimpleNamespace
from unittest import mock

from gamers_chat_helper import GamersChatHelper


class _FakeTextbox:
    def __init__(self):
        self.text = ""

    def delete(self, *_args):
        self.text = ""

    def insert(self, _index, text):
        self.text = text

    def get(self, *_args):
        return self.text

    def focus_set(self):
        pass

    def see(self, _index):
        pass


class RecruitPickerTests(unittest.TestCase):
    def test_picker_is_centered_over_hyperline_parent(self):
        app = object.__new__(GamersChatHelper)
        app.root = mock.Mock()
        app.root.winfo_rootx.return_value = 100
        app.root.winfo_rooty.return_value = 50
        app.root.winfo_width.return_value = 1000
        app.root.winfo_height.return_value = 800
        app.root.winfo_screenwidth.return_value = 1920
        app.root.winfo_screenheight.return_value = 1080
        win = mock.Mock()

        with mock.patch("gamers_chat_helper._HAS_WIN32", False):
            app._position_toplevel_over_parent(win, 640, 720)

        win.geometry.assert_called_once_with("640x720+280+90")

    def test_picked_recruit_is_written_exactly_into_your_line(self):
        app = object.__new__(GamersChatHelper)
        app.gen_editor = _FakeTextbox()
        app.ai_output = app.gen_editor
        app.generator_intent = SimpleNamespace(get=lambda: "recruit")
        app.auto_copy = SimpleNamespace(get=lambda: False)
        app.root = mock.Mock()
        app._ensure_guild_brackets = lambda line: line
        app._update_quick_out_meter = mock.Mock()
        app.update_counter = mock.Mock()
        app.refresh_hud_line = mock.Mock()
        app.push_history = mock.Mock()
        app._recruit_mark_dirty = mock.Mock()
        app.show_toast = mock.Mock()
        app.set_status = mock.Mock()
        app._is_err = lambda _text: False

        app._apply_picked_recruit("[Guild] selected option")

        self.assertEqual(app.get_gen_text(), "[Guild] selected option")
        app.push_history.assert_called_once_with(
            "[Guild] selected option",
            count=False,
        )
        app.show_toast.assert_called_with(
            "In Your Line — ready to copy",
            kind="ok",
        )


if __name__ == "__main__":
    unittest.main()
