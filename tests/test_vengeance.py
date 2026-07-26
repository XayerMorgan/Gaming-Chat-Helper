import unittest

from hyperline_vengeance import (
    extract_combat_targets,
    make_vengeance_entry,
    sanitize_vengeance_entries,
)


class CombatTargetParsingTests(unittest.TestCase):
    def test_extracts_killer_and_bracketed_guild(self):
        text = "[21:44] You were killed by [Night Owls] Rook-Prime with a longsword"
        self.assertEqual(
            extract_combat_targets(text),
            [{"name": "Rook-Prime", "guild": "Night Owls"}],
        )

    def test_handles_multiple_common_combat_log_formats(self):
        text = "\n".join(
            (
                "Kael defeated you for 1,240 damage",
                "Killer: Lady Vex",
                "[Raiders] Grim Jack killed you",
                "You have been slain by Thorn",
            )
        )
        self.assertEqual(
            extract_combat_targets(text),
            [
                {"name": "Kael", "guild": ""},
                {"name": "Lady Vex", "guild": ""},
                {"name": "Grim Jack", "guild": "Raiders"},
                {"name": "Thorn", "guild": ""},
            ],
        )

    def test_ignores_unrelated_lines_and_deduplicates(self):
        text = "\n".join(
            (
                "You dealt 500 damage to a wolf",
                "You were killed by Rook",
                "You were killed by Rook",
            )
        )
        self.assertEqual(
            extract_combat_targets(text),
            [{"name": "Rook", "guild": ""}],
        )


class VengeanceEntryTests(unittest.TestCase):
    def test_builds_json_ready_player_entry(self):
        entry = make_vengeance_entry(
            name="  Rook-Prime ",
            target_type="Player",
            reason="Camped me",
            details="  Kept camping   the respawn. ",
            guild="Night Owls",
            game="The Quinfall",
            source="combat log",
            now=123.0,
        )
        self.assertEqual(entry["name"], "Rook-Prime")
        self.assertEqual(entry["details"], "Kept camping the respawn.")
        self.assertEqual(entry["source"], "combat log")
        self.assertFalse(entry["settled"])

    def test_supports_guild_target_and_rejects_blank_name(self):
        guild = make_vengeance_entry(
            name="Night Owls",
            target_type="Guild",
            reason="Guild feud",
        )
        self.assertEqual(guild["target_type"], "Guild")
        with self.assertRaises(ValueError):
            make_vengeance_entry(name=" ", target_type="Player", reason="Other")

    def test_sanitizes_persisted_rows_and_preserves_settled_state(self):
        rows = [
            {
                "id": "abc123",
                "name": "Rook",
                "target_type": "Player",
                "reason": "Killed me",
                "created_at": 100,
                "settled": True,
            },
            {"name": ""},
            "invalid",
        ]
        cleaned = sanitize_vengeance_entries(rows)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0]["id"], "abc123")
        self.assertTrue(cleaned[0]["settled"])


if __name__ == "__main__":
    unittest.main()
