import json
import logging
import os
import tempfile
import unittest
from unittest import mock

from hyperline_persistence import atomic_write_json, configure_diagnostics


class AtomicWriteJsonTests(unittest.TestCase):
    def test_writes_expected_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")

            atomic_write_json(path, {"seed": "two\nlines", "enabled": True})

            with open(path, "r", encoding="utf-8") as stream:
                self.assertEqual(
                    json.load(stream),
                    {"seed": "two\nlines", "enabled": True},
                )

    def test_optional_trailing_newline_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "templates.json")

            atomic_write_json(path, [], indent=2, trailing_newline=True)

            with open(path, "rb") as stream:
                self.assertTrue(stream.read().endswith(b"\n"))

    def test_failed_replace_preserves_existing_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write('{"version": "original"}')

            with mock.patch(
                "hyperline_persistence.os.replace",
                side_effect=OSError("simulated replace failure"),
            ):
                with self.assertRaises(OSError):
                    atomic_write_json(path, {"version": "new"})

            with open(path, "r", encoding="utf-8") as stream:
                self.assertEqual(json.load(stream), {"version": "original"})
            self.assertEqual(os.listdir(directory), ["config.json"])


class DiagnosticsTests(unittest.TestCase):
    def tearDown(self):
        logger = logging.getLogger("hyperline")
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)

    def test_logger_reuses_handler_for_same_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "hyperline.log")

            first = configure_diagnostics(path)
            second = configure_diagnostics(path)
            matching = [
                handler
                for handler in first.handlers
                if os.path.abspath(getattr(handler, "baseFilename", "")) == path
            ]
            try:
                first.warning("diagnostic test")
                for handler in matching:
                    handler.flush()

                self.assertIs(first, second)
                self.assertEqual(len(matching), 1)
                with open(path, "r", encoding="utf-8") as stream:
                    self.assertIn("diagnostic test", stream.read())
            finally:
                for handler in matching:
                    handler.close()
                    first.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
