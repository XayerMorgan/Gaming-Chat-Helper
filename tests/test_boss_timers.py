import json
import os
import tempfile
import unittest

from hyperline_boss_timers import (
    load_boss_timer_defaults,
    merge_boss_timer_sites,
    normalize_timer_url,
    parse_event_cards,
    sanitize_boss_timer_sites,
)


class BossTimerConfigTests(unittest.TestCase):
    def test_extracts_native_event_cards_from_server_rendered_html(self):
        html = """
        <article><h3 title="Titanseal">Titanseal</h3>
        <p>Next spawn in</p><p>9m 37s</p><span>Daily at 22:00 UTC</span></article>
        <article><h3 title="Capture the Flag">Capture the Flag</h3>
        <p>Next session in <span>1h 09m 37s</span></p></article>
        """
        self.assertEqual(
            parse_event_cards(html),
            [
                {"name": "Titanseal", "countdown": "9m 37s", "detail": "Daily at 22:00 UTC"},
                {"name": "Capture the Flag", "countdown": "1h 09m 37s", "detail": ""},
            ],
        )

    def test_only_http_and_https_timer_urls_are_accepted(self):
        self.assertEqual(
            normalize_timer_url("https://thequinfall-codex.com/events"),
            "https://thequinfall-codex.com/events",
        )
        self.assertEqual(normalize_timer_url("javascript:alert(1)"), "")
        self.assertEqual(normalize_timer_url("not a url"), "")

    def test_shipped_defaults_and_private_overrides_merge_by_game(self):
        defaults = {
            "The Quinfall": "https://thequinfall-codex.com/events",
            "Other Game": "https://example.com/default",
        }
        overrides = {"Other Game": "https://example.com/custom"}

        self.assertEqual(
            merge_boss_timer_sites(defaults, overrides),
            {
                "The Quinfall": "https://thequinfall-codex.com/events",
                "Other Game": "https://example.com/custom",
            },
        )

    def test_defaults_file_supports_versioned_games_object(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "boss_timer_sites.defaults.json")
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(
                    {
                        "version": 1,
                        "games": {
                            "The Quinfall": "https://thequinfall-codex.com/events",
                            "Bad": "file:///private",
                        },
                    },
                    stream,
                )

            self.assertEqual(
                load_boss_timer_defaults(path),
                {"The Quinfall": "https://thequinfall-codex.com/events"},
            )

    def test_malformed_mapping_is_discarded(self):
        self.assertEqual(sanitize_boss_timer_sites(["not", "a", "mapping"]), {})


if __name__ == "__main__":
    unittest.main()
