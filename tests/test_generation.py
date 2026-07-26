import unittest
from types import SimpleNamespace
from unittest import mock

from gamers_chat_helper import GamersChatHelper
from hyperline_generation import (
    VARIETY_OPTIONS,
    apply_variety,
    closest_recent_line,
    line_similarity,
    normalize_variety,
    random_seed,
    retry_threshold,
    structure_direction,
)


BASE_SAMPLING = {
    "temperature": 0.60,
    "top_p": 0.88,
    "top_k": 40,
    "min_p": 0.05,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.10,
    "max_tokens": 90,
    "stream": False,
}


class VarietyTests(unittest.TestCase):
    def test_options_and_invalid_value_fall_back_to_recommended(self):
        self.assertEqual(VARIETY_OPTIONS, ("Stable", "Varied", "Wild"))
        self.assertEqual(normalize_variety("unknown"), "Varied")

    def test_stable_preserves_existing_chat_sampling(self):
        self.assertEqual(
            apply_variety(BASE_SAMPLING, "recruit", "Stable"),
            BASE_SAMPLING,
        )

    def test_varied_and_wild_increase_chat_novelty(self):
        varied = apply_variety(BASE_SAMPLING, "recruit", "Varied")
        wild = apply_variety(BASE_SAMPLING, "recruit", "Wild")

        self.assertGreater(varied["temperature"], BASE_SAMPLING["temperature"])
        self.assertGreater(wild["temperature"], varied["temperature"])
        self.assertGreaterEqual(varied["presence_penalty"], 0.15)
        self.assertGreaterEqual(wild["presence_penalty"], 0.28)

    def test_accuracy_jobs_are_never_changed(self):
        for job in ("ocr", "economy"):
            for mode in VARIETY_OPTIONS:
                self.assertEqual(apply_variety(BASE_SAMPLING, job, mode), BASE_SAMPLING)

    def test_noise_remains_owned_by_chaos_control(self):
        self.assertEqual(
            apply_variety(BASE_SAMPLING, "noise", "Wild"),
            BASE_SAMPLING,
        )

    def test_structure_nudge_is_only_added_to_varied_chat(self):
        self.assertEqual(structure_direction("lfg", "Stable"), "")
        self.assertEqual(structure_direction("economy", "Wild"), "")
        self.assertIn("constraints unchanged", structure_direction("lfg", "Varied"))

    def test_random_seed_is_in_lm_studio_supported_range(self):
        seeds = {random_seed() for _ in range(12)}
        self.assertGreater(len(seeds), 1)
        self.assertTrue(all(1 <= seed <= 2_147_483_647 for seed in seeds))


class SimilarityTests(unittest.TestCase):
    def test_near_paraphrase_scores_higher_than_unrelated_line(self):
        source = "LFG Foaming Catacombs need healer chill run"
        similar = "LFG Foaming Catacombs, need a healer for a chill run"
        unrelated = "Anyone else reorganize inventory instead of questing?"

        self.assertGreater(
            line_similarity(source, similar),
            line_similarity(source, unrelated),
        )

    def test_closest_recent_line_and_thresholds(self):
        recent = [
            "Need one healer for Foaming Catacombs, chill run",
            "Guild recruiting social players, PST if interested",
        ]
        closest, score = closest_recent_line(
            "Need a healer for Foaming Catacombs — chill run",
            recent,
        )

        self.assertEqual(closest, recent[0])
        self.assertGreaterEqual(score, retry_threshold("Varied"))
        self.assertGreater(retry_threshold("Stable"), retry_threshold("Wild"))


class LmStudioPayloadTests(unittest.TestCase):
    def test_exact_recent_output_retries_with_a_new_seed(self):
        app = object.__new__(GamersChatHelper)
        app.api_url = "http://127.0.0.1:1234/v1/chat/completions"
        app.lm_host = "127.0.0.1:1234"
        app.history = ["Need healer for DG"]
        app.variety_var = SimpleNamespace(get=lambda: "Stable")
        app.limit = lambda: 150
        app._selected_lm_model = lambda: "test-model"
        app._llm_headers = lambda: {}
        app.system_prompt = lambda job="banter": "system"

        responses = [
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "choices": [{"message": {"content": "Need healer for DG"}}]
                },
            ),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "choices": [
                        {"message": {"content": "DG group open — healer spot available"}}
                    ]
                },
            ),
        ]
        with mock.patch(
            "gamers_chat_helper.requests.post",
            side_effect=responses,
        ) as post:
            result = app.call_local_llm("Write an LFG", n=1, job="lfg")

        self.assertEqual(result, ["DG group open — healer spot available"])
        self.assertEqual(post.call_count, 2)
        first_payload = post.call_args_list[0].kwargs["json"]
        second_payload = post.call_args_list[1].kwargs["json"]
        self.assertNotEqual(first_payload["seed"], second_payload["seed"])
        self.assertIn(
            "NOVELTY RETRY",
            second_payload["messages"][1]["content"],
        )


if __name__ == "__main__":
    unittest.main()
