import os
import unittest

from app.engine.runner import gnubg_available
from app.live.engine import LiveEngine
from app.live.transcript import parse_mat, render_mat

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "galaxy_3pt.mat")


def transcript_until(games, game_count, action_count):
    """The match as it stood after `action_count` actions of game `game_count` (earlier games complete)."""
    shown = [dict(g) for g in games[:game_count]]
    shown[-1] = {**shown[-1], "actions": shown[-1]["actions"][:action_count], "result": None}
    return shown


@unittest.skipUnless(gnubg_available(), "gnubg is only installed in the container")
class LiveAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE) as f:
            cls.header, cls.games = parse_mat(f.read())
        cls.engine = LiveEngine()

    @classmethod
    def tearDownClass(cls):
        cls.engine.stop()

    def analyse(self, game_count, action_count, from_record):
        text = render_mat(self.header, transcript_until(self.games, game_count, action_count))
        return self.engine.analyse(text, from_record, plies=2, threads=2)

    def test_records_line_up_with_actions(self):
        result = self.analyse(1, 40, 39)
        self.assertEqual((result["game_no"], result["records"], result["actions"][28:30]), (1, 40, ["double", "take"]))

    def test_the_sixes_mistake_is_graded_as_in_the_full_analysis(self):
        # game 1 line 16: fishsoup's 66 (record 31), the move test_engine_integration checks too
        result = self.analyse(1, 32, 31)
        move = next(d for d in result["decisions"] if d["kind"] == "checker")
        self.assertEqual((move["record_index"], move["player"], move["dice"], move["gnubg_skill"], round(move["error"], 3)),
                         (31, 2, [6, 6], "bad", 0.107))

    def test_the_take_is_analysed_when_the_double_is_analysed_again(self):
        result = self.analyse(1, 30, 28)
        self.assertEqual(sorted(d["kind"] for d in result["decisions"] if d["record_index"] == 28), ["cube", "take"])

    def test_every_move_gets_its_luck(self):
        result = self.analyse(2, 6, 0)
        self.assertEqual([(l["record_index"], l["player"]) for l in result["luck"]],
                         [(i, a["player"]) for i, a in enumerate(self.games[1]["actions"][:6])])

    def test_one_process_answers_many_requests(self):
        pids = set()
        for count in (3, 4, 5):
            self.analyse(1, count, count - 1)
            pids.add(self.engine.proc.pid)
        self.assertEqual(len(pids), 1)
