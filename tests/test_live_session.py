import os
import time
import unittest

from app.live.replay import screens
from app.live.session import LiveSession, clean_settings, luck_level, pips
from app.live.transcript import parse_mat
from tests.test_live_tracker import reading_for

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "galaxy_3pt.mat")
THRESHOLDS = {"doubtful": 0.03, "bad": 0.06, "very_bad": 0.12}
ERRORS = [0.0, 0.07, 0.0, 0.2, 0.01, 0.04]


class FakeEngine:
    """Grades every record of the last game in the transcript, cycling through ERRORS."""

    def __init__(self):
        self.calls = []

    def stop(self):
        pass

    def analyse(self, text, from_record, plies=2, threads=2):
        _, games = parse_mat(text)
        actions = games[-1]["actions"]
        self.calls.append((len(games), from_record, len(actions)))
        decisions, luck = [], []
        for index in range(from_record, len(actions)):
            action = actions[index]
            error = ERRORS[index % len(ERRORS)]
            decisions.append({"record_index": index, "kind": "checker", "player": action["player"], "error": error,
                              "best": "best move", "forced": False, "action": "played", "cube": None,
                              "played_index": 0, "candidates": [{"probs": [0.6, 0.2, 0.01, 0.1, 0.0], "equity": 0.1}]})
            luck.append({"record_index": index, "player": action["player"], "luck": 0.35 if index % 3 == 0 else -0.1})
        return {"game_no": len(games), "records": len(actions), "decisions": decisions, "luck": luck}


def fixture_screens():
    with open(FIXTURE) as f:
        header, games = parse_mat(f.read())
    return games, screens(games, header["match_length"])


def play(session, shown):
    for screen in shown:
        for _ in range(2):
            session.feed(reading_for(screen["frame"], screen["dice"]))


def settle(session, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with session.lock:
            if not session._next_job() and not session.engine_state["busy"]:
                return
        time.sleep(0.02)
    raise AssertionError("analysis did not catch up")


class FollowAMatch(unittest.TestCase):
    def setUp(self):
        self.games, self.shown = fixture_screens()
        self.engine = FakeEngine()

    def session(self, opponent):
        session = LiveSession({"opponent": opponent, "match_length": 3}, self.engine)
        self.addCleanup(session.stop)
        return session

    def first_moves(self, count):
        return [s for s in self.shown if s["game_no"] == 1 and s["action_index"] < count]

    def test_moves_are_followed_and_analysed_against_the_ai(self):
        session = self.session("ai")
        play(session, self.first_moves(6))
        settle(session)
        view = session.view(THRESHOLDS)
        self.assertEqual(
            [(m["player"], m["dice"], m["class"]) for m in view["moves"]],
            [(1, [3, 1], None), (2, [6, 4], "bad"), (1, [6, 4], None), (2, [4, 3], "very_bad"), (1, [4, 1], None), (2, [3, 3], "doubtful")],
        )

    def test_against_a_person_the_game_in_progress_shows_no_engine_output(self):
        session = self.session("person")
        play(session, self.first_moves(6))
        settle(session)
        view = session.view(THRESHOLDS)
        engine_keys = {"error", "class", "best", "luck", "pending"}
        self.assertEqual((view["held"], [sorted(engine_keys & set(m)) for m in view["moves"]], view["graph"],
                          view["stats"][1]["pr"], view["last"]["engine"]),
                         (True, [[]] * 6, [], None, False))

    def test_a_finished_game_is_shown_against_a_person_while_the_next_one_is_held(self):
        session = self.session("person")
        play(session, [s for s in self.shown if s["game_no"] == 1] + [s for s in self.shown if s["game_no"] == 2][:1])
        settle(session)
        view = session.view(THRESHOLDS)
        game_one = [m for m in view["moves"] if m["game_no"] == 1]
        self.assertEqual((view["held"], view["games"][0]["result"], view["settings"]["score"], all("class" in m for m in game_one)),
                         (True, {"winner": 1, "points": 1}, [1, 0], True))

    def test_only_new_records_are_sent_for_analysis(self):
        session = self.session("ai")
        for count in range(1, 5):
            play(session, [s for s in self.first_moves(count) if s["action_index"] == count - 1])
            settle(session)
        self.assertEqual(self.engine.calls, [(1, 0, 1), (1, 0, 2), (1, 1, 3), (1, 2, 4)])

    def test_luck_and_pips_reach_the_stats(self):
        session = self.session("ai")
        play(session, self.first_moves(6))
        settle(session)
        stats = session.view(THRESHOLDS)["stats"]
        self.assertEqual((stats[1]["rolls"], stats[1]["lucky"], round(stats[1]["luck"], 2), stats[1]["pips"] + stats[2]["pips"] > 0),
                         (3, 1, 0.15, True))

    def test_an_earlier_move_for_the_board_is_held_like_the_list(self):
        held, shown = self.session("person"), self.session("ai")
        for session in (held, shown):
            play(session, self.first_moves(3))
            settle(session)
        plain, analysed = held.move(1, 1), shown.move(1, 1)
        self.assertEqual((plain["engine"], "candidates" in plain["decision"], plain["decision"]["played_steps"],
                          analysed["engine"], analysed["decision"]["error"], held.move(1, 9)),
                         (False, False, [[24, 18], [18, 14]], True, 0.07, None))

    def test_a_taken_back_move_loses_its_analysis(self):
        session = self.session("ai")
        play(session, self.first_moves(2))
        settle(session)
        start = [s for s in self.shown if s["game_no"] == 1 and s["action_index"] == 1][0]
        session.feed(reading_for(start["frame"], None))
        session.feed(reading_for(start["frame"], None))
        settle(session)
        self.assertEqual([m["index"] for m in session.view(THRESHOLDS)["moves"]], [0])


class Settings(unittest.TestCase):
    def test_defaults_and_validation(self):
        self.assertEqual(clean_settings({}), {"match_length": 7, "opponent": "person", "player1": "You", "player2": "Opponent", "score": [0, 0]})
        for bad in ({"opponent": "robot"}, {"match_length": 99}, {"player1": "  "}, {"score": [1]}):
            with self.assertRaises(ValueError):
                clean_settings(bad)


class Helpers(unittest.TestCase):
    def test_luck_levels(self):
        self.assertEqual([luck_level(v) for v in (0.7, 0.3, 0.0, -0.3, -0.6)], ["very_lucky", "lucky", None, "unlucky", "very_unlucky"])

    def test_pips_of_the_starting_position(self):
        self.assertEqual(pips([0, -2, 0, 0, 0, 0, 5, 0, 3, 0, 0, 0, -5, 5, 0, 0, 0, -3, 0, -5, 0, 0, 0, 0, 2, 0]), [167, 167])
