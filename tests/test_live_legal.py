import json
import os
import random
import unittest

from app.live.legal import apply_steps, final_positions, legal_moves, move_text, parse_move_text

FIXTURE = os.path.join(os.path.dirname(__file__), "js", "fixtures", "galaxy_3pt_legal.json")
START = [0, -2, 0, 0, 0, 0, 5, 0, 3, 0, 0, 0, -5, 5, 0, 0, 0, -3, 0, -5, 0, 0, 0, 0, 2, 0]
ALL_ROLLS = [(a, b) for a in range(1, 7) for b in range(a, 7)]


def gnubg_finals(entry):
    return {tuple(apply_steps(entry["frame"], [tuple(s) for s in steps])) for steps in entry["legal"]}


class LegalMoves(unittest.TestCase):
    def test_final_positions_match_gnubg_for_every_position_of_a_real_match(self):
        with open(FIXTURE) as f:
            positions = json.load(f)
        mismatched = [p["id"] for p in positions if set(final_positions(p["frame"], p["dice"])) != gnubg_finals(p)]
        self.assertEqual(mismatched, [])

    def test_opening_31_has_the_sixteen_gnubg_plays(self):
        self.assertEqual(len(final_positions(START, (3, 1))), 16)

    def test_dancing_on_the_bar_leaves_the_position_unchanged(self):
        closed = [0] * 26
        closed[25] = 1
        for point in range(19, 25):
            closed[point] = -2
        self.assertEqual(legal_moves(closed, (6, 1)), [()])

    def test_only_the_larger_die_when_just_one_can_be_played(self):
        # a lone checker on 13 can play the 6 or the 5, but the 2 point blocks playing both
        frame = [0] * 26
        frame[13], frame[2] = 1, -2
        self.assertEqual(list(final_positions(frame, (6, 5))), [tuple(apply_steps(frame, [(13, 7)]))])

    def test_a_random_game_keeps_every_checker_accounted_for(self):
        rng = random.Random(3)
        frame = START
        for _ in range(80):
            before = (sum(c for c in frame if c > 0), -sum(c for c in frame if c < 0))
            steps = rng.choice(legal_moves(frame, rng.choice(ALL_ROLLS)))
            after = apply_steps(frame, steps)
            borne_off = sum(1 for _, to in steps if to == 0)
            self.assertEqual((sum(c for c in after if c > 0), -sum(c for c in after if c < 0)), (before[0] - borne_off, before[1]))
            frame = [-after[25 - i] for i in range(26)]
            if not any(c > 0 for c in frame) or not any(c < 0 for c in frame):
                break


class MoveText(unittest.TestCase):
    def test_round_trip_through_mat_notation(self):
        cases = [((13, 8), (13, 11)), ((25, 22), (22, 16)), ((6, 0), (6, 0), (5, 0), (5, 0)), ()]
        self.assertEqual([parse_move_text(move_text(c)) for c in cases], [tuple(sorted(c, reverse=True)) for c in cases])

    def test_parses_repeat_counts_and_hit_marks(self):
        self.assertEqual(parse_move_text("8/5(2) 6/5*"), ((8, 5), (8, 5), (6, 5)))
