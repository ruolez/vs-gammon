import unittest

from app.dashboard import game_phase, streak_days
from app.position import flip_frame
from tests.test_position import START_FRAME


def frame(points, bar=0, opp_bar=0):
    f = [0] * 26
    for p, n in points.items():
        f[p] = n
    f[25] = bar
    f[0] = -opp_bar
    return f


def checker(board, on_roll=1, move_no=10):
    return {"kind": "checker", "board": board, "on_roll": on_roll, "move_no": move_no}


RACE = frame({13: 5, 8: 5, 6: 5, 20: -5, 22: -5, 24: -5})
BEAROFF = frame({6: 5, 4: 5, 2: 5, 20: -15})
CONTACT_HOME = frame({6: 5, 5: 5, 4: 5, 3: -1, 19: -14})
MIDDLE = frame({24: 2, 13: 5, 8: 3, 6: 5, 1: -2, 12: -5, 17: -3, 19: -5})


class GamePhase(unittest.TestCase):
    def test_phases(self):
        cases = [
            ("opening", checker(START_FRAME, move_no=2)),
            ("middle", checker(MIDDLE)),
            ("race", checker(RACE)),
            ("bearoff", checker(BEAROFF)),
            ("bearoff", checker(CONTACT_HOME)),
            ("cube", {"kind": "cube", "board": MIDDLE, "on_roll": 1, "move_no": 9}),
            ("cube", {"kind": "take", "board": MIDDLE, "on_roll": 1, "move_no": 9}),
        ]
        self.assertEqual([(name, game_phase(d)) for name, d in cases], [(name, name) for name, _ in cases])

    def test_phase_is_read_from_the_player_on_roll(self):
        self.assertEqual(game_phase(checker(flip_frame(RACE), on_roll=2)), "race")

    def test_checker_on_the_bar_is_contact(self):
        self.assertEqual(game_phase(checker(frame({6: 14, 20: -15}, bar=1))), "middle")


class StreakDays(unittest.TestCase):
    def test_counts_consecutive_days_ending_today(self):
        self.assertEqual(streak_days(["2026-11-10", "2026-11-09", "2026-11-08", "2026-11-05"], "2026-11-10"), 3)

    def test_streak_still_alive_if_last_practice_was_yesterday(self):
        self.assertEqual(streak_days(["2026-11-09", "2026-11-08"], "2026-11-10"), 2)

    def test_broken_streak(self):
        self.assertEqual(streak_days(["2026-11-07"], "2026-11-10"), 0)

    def test_no_practice(self):
        self.assertEqual(streak_days([], "2026-11-10"), 0)

    def test_month_boundary_and_unsorted_input(self):
        self.assertEqual(streak_days(["2026-10-31", "2026-11-01", "2026-10-30"], "2026-11-01"), 3)


if __name__ == "__main__":
    unittest.main()
