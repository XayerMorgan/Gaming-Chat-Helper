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
    procedural_noise_line,
    procedural_recruit_line,
    random_seed,
    recruit_creative_plan,
    retry_threshold,
    select_diverse_lines,
    semantic_diversity_threshold,
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

    def test_recruit_plans_do_not_repeat_across_a_long_session(self):
        recent = []
        prompts = []
        for _ in range(100):
            plan_id, prompt = recruit_creative_plan(recent)
            recent.append(plan_id)
            prompts.append(prompt)

        self.assertEqual(len(set(recent)), 100)
        self.assertTrue(all("underlying idea" in prompt for prompt in prompts))

    def test_noise_plans_and_offline_lines_have_broad_cardinality(self):
        recent = []
        lines = []
        for _ in range(100):
            plan_id, line = procedural_noise_line(3, recent)
            recent.append(plan_id)
            lines.append(line)

        self.assertEqual(len(set(recent)), 100)
        self.assertGreaterEqual(len(set(lines)), 95)

    def test_procedural_recruit_fallback_varies_content(self):
        recent = []
        lines = []
        for _ in range(50):
            plan_id, line = procedural_recruit_line("[Defiants]", recent)
            recent.append(plan_id)
            lines.append(line)

        self.assertEqual(len(set(recent)), 50)
        self.assertGreaterEqual(len(set(lines)), 45)
        self.assertTrue(all("[Defiants]" in line for line in lines))


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
        self.assertLess(
            semantic_diversity_threshold("Varied", "recruit"),
            retry_threshold("Varied"),
        )

    def test_diverse_selection_compares_candidates_to_each_other(self):
        candidates = [
            "Need healer for Foaming Catacombs chill run",
            "Need a healer for Foaming Catacombs — chill run",
            "Social guild seeking returning players, PST for details",
        ]

        selected = select_diverse_lines(candidates, [], threshold=0.78)

        self.assertEqual(
            selected,
            [
                candidates[0],
                candidates[2],
            ],
        )


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

    def test_multi_recruit_semantic_duplicates_trigger_new_content_plans(self):
        app = object.__new__(GamersChatHelper)
        app.api_url = "http://127.0.0.1:1234/v1/chat/completions"
        app.lm_host = "127.0.0.1:1234"
        app.history = []
        app.variety_var = SimpleNamespace(get=lambda: "Varied")
        app.limit = lambda: 180
        app._selected_lm_model = lambda: "test-model"
        app._llm_headers = lambda: {}
        app.system_prompt = lambda job="recruit_fresh": "system"

        responses = [
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "1. Chill guild looking for active players, PST\n"
                                    "2. Active players wanted for our chill guild, PST\n"
                                    "3. Join our chill guild, active players PST"
                                )
                            }
                        }
                    ]
                },
            ),
            SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "1. New here? Find your regular crew with [Guild]\n"
                                    "2. Done with random groups? [Guild] is building a core\n"
                                    "3. Good people over roster size — ask about [Guild]"
                                )
                            }
                        }
                    ]
                },
            ),
        ]
        with mock.patch(
            "gamers_chat_helper.requests.post",
            side_effect=responses,
        ) as post:
            result = app.call_local_llm(
                "Write three recruit lines",
                n=3,
                job="recruit_fresh",
            )

        self.assertEqual(post.call_count, 2)
        self.assertEqual(len(result), 3)
        retry_prompt = post.call_args_list[1].kwargs["json"]["messages"][1]["content"]
        self.assertIn("SEMANTIC RESET", retry_prompt)
        self.assertIn("DISTINCT CONTENT PLANS", retry_prompt)


if __name__ == "__main__":
    unittest.main()
