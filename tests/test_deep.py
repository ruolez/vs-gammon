import unittest

from app.engine import deep


class EvalSettings(unittest.TestCase):
    def test_defaults_are_three_ply_with_five_moves(self):
        self.assertEqual(deep.eval_settings({}), {"checker": {"plies": 3, "prune": True}, "cube": {"plies": 3, "prune": True},
                                                  "moves": {"count": 5, "within": 0.16}})

    def test_plies_above_four_are_refused(self):
        with self.assertRaisesRegex(ValueError, "checker play plies must be between 0 and 4"):
            deep.eval_settings({"checker": {"plies": 5}})

    def test_four_ply_widens_the_last_filter_stage_and_skips_the_three_ply_stage(self):
        commands = deep.evaluation_commands(deep.eval_settings({"checker": {"plies": 4}, "moves": {"count": 3, "within": 0.1}}))
        self.assertEqual([c for c in commands if "movefilter" in c],
                         ["set analysis movefilter 4 2 0 3 0.1", "set analysis movefilter 4 0 0 8 0.16",
                          "set analysis movefilter 4 3 -1 0 0"])


class RolloutSettings(unittest.TestCase):
    def test_unknown_keys_are_ignored_and_nested_values_merge(self):
        settings = deep.rollout_settings({"trials": "2592", "truncation": {"enabled": True}, "bogus": 1})
        self.assertEqual((settings["trials"], settings["truncation"], "bogus" in settings),
                         (2592, {"enabled": True, "after": 11, "checker": {"plies": 1, "prune": True},
                                 "cube": {"plies": 1, "prune": True}}, False))

    def test_bad_values_are_refused(self):
        cases = [({"trials": 0}, "games must be between 1"), ({"trials": "many"}, "games must be a whole number"),
                 ({"seed": -1}, "seed must be between 0"), ({"stop_on_jsd": {"limit": 0}}, "JSD limit must be between")]
        for changes, message in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, message):
                deep.rollout_settings(changes)

    def test_commands_cover_every_option(self):
        settings = deep.rollout_settings({
            "trials": 648, "cubeful": False, "variance_reduction": False, "quasi_random": False, "seed": 42,
            "checker": {"plies": 2, "prune": False}, "cube": {"plies": 1},
            "later": {"enabled": True, "after": 5, "checker": {"plies": 0}},
            "truncation": {"enabled": True, "after": 9}, "bearoff": {"exact": False, "one_sided": False},
            "stop_on_error": {"enabled": True, "min_games": 144, "max_error": 0.01},
            "stop_on_jsd": {"enabled": True, "min_games": 216, "limit": 3},
        })
        commands = deep.rollout_commands(settings)
        for expected in ("set rollout trials 648", "set rollout cubeful off", "set rollout varredn off",
                         "set rollout quasirandom off", "set rollout seed 42", "set rollout chequerplay plies 2",
                         "set rollout chequerplay prune off", "set rollout cubedecision plies 1",
                         "set rollout later enable on", "set rollout later plies 5",
                         "set rollout later chequerplay plies 0", "set rollout truncation enable on",
                         "set rollout truncation plies 9", "set rollout bearofftruncation exact off",
                         "set rollout bearofftruncation onesided off", "set rollout limit enable on",
                         "set rollout limit minimumgames 144", "set rollout limit maxerror 0.01",
                         "set rollout jsd stop on", "set rollout jsd minimumgames 216", "set rollout jsd limit 3.0"):
            with self.subTest(command=expected):
                self.assertIn(expected, commands)

    def test_no_seed_command_without_a_seed(self):
        self.assertFalse(any("seed" in c for c in deep.rollout_commands(deep.rollout_settings({}))))

    def test_presets_are_valid_settings(self):
        for name, preset in deep.ROLLOUT_PRESETS.items():
            with self.subTest(preset=name):
                self.assertEqual(deep.rollout_settings(preset), preset)


class RolloutSteps(unittest.TestCase):
    def test_steps_grow_in_blocks_of_36_and_end_at_the_total(self):
        for trials in (37, 144, 1000, 1296, 5184):
            steps = deep.rollout_steps(trials)
            with self.subTest(trials=trials):
                self.assertEqual(
                    (steps[-1], steps == sorted(set(steps)), all(s % 36 == 0 for s in steps[:-1]), len(steps) <= 11),
                    (trials, True, True, True))

    def test_tiny_rollouts_run_in_one_go(self):
        self.assertEqual(deep.rollout_steps(36), [36])

    def test_progress_line_round_trip(self):
        self.assertEqual((deep.parse_progress(deep.progress_line(324, 1296)), deep.parse_progress("Rollout done.")),
                         ({"done": 324, "total": 1296}, None))


if __name__ == "__main__":
    unittest.main()
