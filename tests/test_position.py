import random
import unittest

from app.position import build_xgid, flip_frame, onroll_frame, player1_frame

START_SIDE = (0, 0, 0, 0, 0, 5, 0, 3, 0, 0, 0, 0, 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0)
START_FRAME = [0, -2, 0, 0, 0, 0, 5, 0, 3, 0, 0, 0, -5, 5, 0, 0, 0, -3, 0, -5, 0, 0, 0, 0, 2, 0]
START_XGID = "-b----E-C---eE---c-e----B-"

# gnubg positionfromid("2jbEGQDh3QYDQA"): X on roll with one checker on the bar
BAR_PAIR = (
    (0, 1, 2, 2, 2, 2, 0, 0, 0, 1, 0, 0, 3, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
    (1, 0, 0, 0, 4, 3, 2, 2, 0, 0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1),
)


def random_pair(rng):
    player = [0] * 25
    for _ in range(rng.randint(0, 15)):
        player[rng.randrange(25)] += 1
    free_for_opponent = [i for i in range(24) if player[23 - i] == 0] + [24]
    opponent = [0] * 25
    for _ in range(rng.randint(0, 15)):
        opponent[rng.choice(free_for_opponent)] += 1
    return tuple(opponent), tuple(player)


class OnrollFrame(unittest.TestCase):
    def test_starting_position(self):
        self.assertEqual(onroll_frame((START_SIDE, START_SIDE)), START_FRAME)

    def test_bars_and_opponent_points_are_mirrored(self):
        frame = onroll_frame(BAR_PAIR)
        self.assertEqual(
            (frame[25], frame[0], frame[1], frame[23], frame[22], frame[12], frame[5]),
            (1, 0, 1, -1, -2, -3, 4),
        )

    def test_checker_counts_are_preserved(self):
        rng = random.Random(7)
        for _ in range(200):
            pair = random_pair(rng)
            frame = onroll_frame(pair)
            self.assertEqual(
                (sum(c for c in frame if c > 0), -sum(c for c in frame if c < 0)),
                (sum(pair[1]), sum(pair[0])),
            )


class FlipFrame(unittest.TestCase):
    def test_flip_is_an_involution(self):
        rng = random.Random(11)
        for _ in range(200):
            frame = onroll_frame(random_pair(rng))
            self.assertEqual(flip_frame(flip_frame(frame)), frame)

    def test_starting_position_is_symmetric(self):
        self.assertEqual(flip_frame(START_FRAME), START_FRAME)


class Player1Frame(unittest.TestCase):
    def test_player1_on_roll_keeps_onroll_view(self):
        self.assertEqual(player1_frame(BAR_PAIR, on_roll=1), onroll_frame(BAR_PAIR))

    def test_player2_on_roll_is_seen_from_player1(self):
        frame = player1_frame(BAR_PAIR, on_roll=2)
        self.assertEqual((frame[0], frame[24], frame[2], frame[13]), (-1, -1, 1, 3))


class BuildXgid(unittest.TestCase):
    def test_opening_roll_for_player1(self):
        self.assertEqual(
            build_xgid(START_FRAME, on_roll=1, dice=(5, 2), cube_value=1, cube_owner=0,
                       score1=0, score2=0, match_length=7, crawford_game=False),
            f"XGID={START_XGID}:0:0:1:52:0:0:0:7:10",
        )

    def test_cube_decision_player2_owning_cube_in_crawford_free_game(self):
        self.assertEqual(
            build_xgid(START_FRAME, on_roll=2, dice=None, cube_value=4, cube_owner=2,
                       score1=3, score2=1, match_length=5, crawford_game=False),
            f"XGID={START_XGID}:2:-1:-1:00:3:1:0:5:10",
        )

    def test_crawford_flag(self):
        self.assertTrue(
            build_xgid(START_FRAME, on_roll=1, dice=(1, 1), cube_value=1, cube_owner=0,
                       score1=2, score2=0, match_length=3, crawford_game=True).endswith(":11:2:0:1:3:10")
        )


if __name__ == "__main__":
    unittest.main()
