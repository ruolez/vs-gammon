import os
import unittest

from app.live.replay import START, screens
from app.live.tracker import Tracker, winner
from app.live.transcript import parse_mat

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "galaxy_3pt.mat")
VISIBLE = 5


def reading_for(frame, dice=None, bottom="dark", visible=VISIBLE):
    top = "light" if bottom == "dark" else "dark"
    counts = {bottom: [0] * 25, top: [0] * 25}
    capped = [False] * 25
    for point in range(1, 25):
        count = abs(frame[point])
        colour = bottom if frame[point] > 0 else top
        counts[colour][point] = min(count, visible)
        capped[point] = count >= visible
    return {"found": True, "dark": counts["dark"], "light": counts["light"], "capped": capped,
            f"bar_{bottom}": frame[25], f"bar_{top}": -frame[0], "dice": dice,
            f"off_{bottom}": 15 - sum(c for c in frame if c > 0), f"off_{top}": 15 + sum(c for c in frame if c < 0)}


def watch(tracker, readings, repeats=2):
    actions = []
    for reading in readings:
        for _ in range(repeats):
            actions += tracker.feed(reading)
    return actions


def as_play(action):
    """(player, dice high-low, the points each checker left and reached) with hops merged: 3/1 1/0 and 3/0 1/1 are
    the same play."""
    leaving, reaching = [], []
    for start, end in action["steps"]:
        leaving.append(start)
        reaching.append(end)
    for point in set(leaving) & set(reaching):
        while point in leaving and point in reaching:
            leaving.remove(point)
            reaching.remove(point)
    return action["player"], tuple(sorted(action["dice"], reverse=True)), tuple(sorted(leaving)), tuple(sorted(reaching))


def played(actions):
    """The plays per game as the tracker reports them, amendments applied."""
    games = []
    for action in actions:
        if action["kind"] == "game":
            games.append([])
        elif action["kind"] == "move":
            games[-1].append(as_play(action))
        elif action["kind"] == "amend":
            games[-1][-1] = as_play(action["move"])
        elif action["kind"] == "undo":
            games[-1].pop()
    return games


def fixture_games():
    with open(FIXTURE) as f:
        return parse_mat(f.read())


class TrackStoredMatch(unittest.TestCase):
    def test_every_checker_play_of_a_real_match_is_recovered_from_the_screens(self):
        header, games = fixture_games()
        shown = screens(games, header["match_length"])
        actions = watch(Tracker(), [reading_for(s["frame"], s["dice"]) for s in shown])
        self.assertEqual(played(actions), [[as_play(a) for a in g["actions"] if a["kind"] == "move"] for g in games])

    def test_light_checkers_at_the_bottom_work_the_same(self):
        header, games = fixture_games()
        shown = screens(games[:1], header["match_length"])[:30]
        dark = watch(Tracker(), [reading_for(s["frame"], s["dice"], "dark") for s in shown])
        light = watch(Tracker(), [reading_for(s["frame"], s["dice"], "light") for s in shown])
        self.assertEqual(light, dark)

    def test_a_single_reading_is_not_trusted(self):
        tracker = Tracker()
        self.assertEqual(watch(tracker, [reading_for(START)], repeats=1), [])

    def test_taking_back_a_move_undoes_it(self):
        moved = list(START)
        dice = {"side": "bottom", "values": [5, 2]}
        moved[13], moved[8], moved[11] = 3, 4, 1
        actions = watch(Tracker(), [reading_for(START, dice), reading_for(moved, dice), reading_for(START, dice)])
        self.assertEqual([a["kind"] for a in actions], ["game", "move", "undo"])


    def test_a_move_that_does_not_fit_the_dice_read_is_still_found(self):
        """Dice misread on screen (here 6-6 for a 5-2) must not freeze the tracker: the play is matched to the roll
        that does fit."""
        header, games = fixture_games()
        shown = screens(games[:1], header["match_length"])
        misread = [reading_for(s["frame"], s["dice"] and {**s["dice"], "values": [6, 6]}) for s in shown]
        without_dice = lambda play: (play[0], play[2], play[3])
        self.assertEqual([without_dice(p) for p in played(watch(Tracker(), misread))[0]],
                         [without_dice(as_play(a)) for a in games[0]["actions"] if a["kind"] == "move"])

    def test_plays_are_recovered_when_the_opponents_finished_move_is_never_seen(self):
        """Galaxy's AI moves at once and the player rolls and plays right after: the screen with the AI's finished
        move may never be read twice in a row. The next stable board is two plays on, and both must be found."""
        header, games = fixture_games()
        shown = screens(games, header["match_length"])
        hidden = []
        for game_no, game in enumerate(games, start=1):
            moves = game["actions"]
            for index in range(len(moves) - 1):
                if moves[index]["kind"] == "move" and moves[index]["player"] == 2 and moves[index + 1]["kind"] == "move" \
                        and moves[index]["steps"] and moves[index + 1]["steps"]:
                    hidden.append((game_no, index))
        finished = {}
        for s in shown:
            finished[(s["game_no"], s["action_index"])] = s["frame"]
        skipped = [s for s in shown
                   if not any(s["game_no"] == g and s["action_index"] in (i, i + 1) and s["frame"] == finished[(g, i)]
                              for g, i in hidden)]
        self.assertEqual(len(hidden) > 10, True)
        actions = watch(Tracker(), [reading_for(s["frame"], s["dice"]) for s in skipped])
        self.assertEqual(played(actions), [[as_play(a) for a in g["actions"] if a["kind"] == "move"] for g in games])

    def test_a_position_no_move_explains_is_counted_once(self):
        jumped = list(START)
        jumped[6], jumped[1] = 0, 5
        moved = list(START)
        moved[13], moved[8], moved[11] = 3, 4, 1
        dice = {"side": "bottom", "values": [5, 2]}
        tracker = Tracker()
        counts = []
        for reading in (reading_for(START, dice), reading_for(moved, dice), reading_for(jumped, dice)):
            watch(tracker, [reading], repeats=3)
            counts.append(tracker.unexplained)
        self.assertEqual(counts, [0, 0, 1])


class Winner(unittest.TestCase):
    def test_single_gammon_and_backgammon(self):
        single = [0] * 26
        single[3] = -14
        gammon = [0] * 26
        gammon[12] = -15
        backgammon = [0] * 26
        backgammon[5] = -15
        self.assertEqual([winner(single), winner(gammon), winner(backgammon), winner(START)],
                         [(1, 1), (1, 2), (1, 3), None])
