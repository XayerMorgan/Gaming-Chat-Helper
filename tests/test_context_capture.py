import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from gamers_chat_helper import GamersChatHelper


class ContextCaptureTests(unittest.TestCase):
    def test_capture_creates_timestamped_local_png_and_restores_window(self):
        app = object.__new__(GamersChatHelper)
        root = mock.Mock()
        root.after.side_effect = lambda _delay, callback: callback()
        app.root = root
        app.always_on_top = SimpleNamespace(get=lambda: True)
        app.game_var = SimpleNamespace(get=lambda: "The Quinfall")
        app._app_hwnd = 1
        app._foreground_hwnd = lambda: None
        app.set_status = mock.Mock()
        app.show_toast = mock.Mock()
        image = mock.Mock()

        with tempfile.TemporaryDirectory() as capture_dir:
            with (
                mock.patch("gamers_chat_helper.CONTEXT_CAPTURE_DIR", capture_dir),
                mock.patch("gamers_chat_helper._HAS_PIL", True),
                mock.patch("gamers_chat_helper._HAS_WIN32", False),
                mock.patch("gamers_chat_helper.ImageGrab.grab", return_value=image),
            ):
                app.capture_game_context()

        saved_path = image.save.call_args.args[0]
        self.assertEqual(image.save.call_args.kwargs["format"], "PNG")
        self.assertEqual(os.path.dirname(saved_path), capture_dir)
        self.assertRegex(
            os.path.basename(saved_path),
            r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_\d{3}_The-Quinfall\.png$",
        )
        root.iconify.assert_called_once()
        root.deiconify.assert_called_once()
        app.show_toast.assert_called_once()


if __name__ == "__main__":
    unittest.main()
