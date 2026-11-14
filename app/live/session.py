"""A live match read from the screen: board readings go through the tracker into a transcript, a background thread
has gnubg analyse each new move, and view() builds what the Play online sidebar shows.

Against a person, nothing the engine says about the game in progress is shown (fair play): moves, pips and dice
are, the analysis of a game appears once that game is over."""
import threading
import time

from app.analysis import classify, summarize
from app.live.legal import move_text
from app.live.tracker import Tracker
from app.live.transcript import render_mat

OPPONENTS = ("person", "ai")


def luck_level(luck):
    if luck >= 0.6:
        return "very_lucky"
    if luck >= 0.3:
        return "lucky"
    if luck <= -0.6:
        return "very_unlucky"
    if luck <= -0.3:
        return "unlucky"
    return None


def pips(frame):
    bottom = sum(i * c for i, c in enumerate(frame) if c > 0)
    top = sum((25 if i == 0 else 25 - i) * -c for i, c in enumerate(frame) if c < 0)
    return [bottom, top]


def win_chances(decision):
    """Player 1's chances after a checker play, from the played move's evaluation (mover's view)."""
    probs = decision["candidates"][decision["played_index"]]["probs"]
    if decision["player"] == 1:
        return {"win": probs[0], "gammon": probs[1], "lose_gammon": probs[3]}
    return {"win": 1 - probs[0], "gammon": probs[3], "lose_gammon": probs[1]}


def clean_settings(raw, current=None):
    settings = dict(current or {"match_length": 7, "opponent": "person", "player1": "You", "player2": "Opponent",
                                "score": [0, 0]})
    if "match_length" in raw:
        length = int(raw["match_length"])
        if not 0 <= length <= 63:
            raise ValueError("match length must be between 0 (money game) and 63")
        settings["match_length"] = length
    if "opponent" in raw:
        if raw["opponent"] not in OPPONENTS:
            raise ValueError("opponent must be 'person' or 'ai'")
        settings["opponent"] = raw["opponent"]
    for key in ("player1", "player2"):
        if key in raw:
            name = " ".join(str(raw[key]).split())[:40]
            if not name:
                raise ValueError("player names can't be empty")
            settings[key] = name
    if "score" in raw:
        score = [int(v) for v in raw["score"]]
        if len(score) != 2 or min(score) < 0:
            raise ValueError("score must be two numbers")
        settings["score"] = score
    return settings


class LiveSession:
    def __init__(self, settings, engine, plies=2, threads=2):
        self.settings = clean_settings(settings)
        self.engine = engine
        self.plies, self.threads = plies, threads
        self.tracker = Tracker()
        self.games = []
        self.decisions = {}
        self.luck = {}
        self.analysed = {}
        self.generation = {}
        self.version = 0
        self.reading = {"found": False, "why": "no screenshot yet", "at": None}
        self.engine_state = {"busy": False, "error": None}
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.running = True
        self.worker = threading.Thread(target=self._work, daemon=True)
        self.worker.start()

    # ---- readings and actions ----

    def feed(self, reading):
        with self.lock:
            self.reading = {"found": bool(reading.get("found")), "why": reading.get("why"), "at": time.time()}
            actions = self.tracker.feed(reading)
            for action in actions:
                self._apply(action)
            if actions:
                self.version += 1
                self.wake.set()
            return actions

    def _game_no(self):
        return len(self.games)

    def _forget(self, game_no, index):
        for key in [k for k in self.decisions if k[0] == game_no and k[1] >= index]:
            del self.decisions[key]
        for key in [k for k in self.luck if k[0] == game_no and k[1] >= index]:
            del self.luck[key]
        self.analysed[game_no] = min(self.analysed.get(game_no, 0), index)
        self.generation[game_no] = self.generation.get(game_no, 0) + 1

    def _apply(self, action):
        kind = action["kind"]
        if kind == "game":
            if self.games and action.get("result") and not self.games[-1]["result"]:
                winner, points = action["result"]
                self.games[-1]["result"] = {"winner": winner, "points": points}
                self.settings["score"][winner - 1] += points
            self.games.append({"score": tuple(self.settings["score"]), "actions": [], "result": None})
            return
        if not self.games:
            return
        actions = self.games[-1]["actions"]
        if kind == "move":
            actions.append(action)
        elif kind == "undo" and actions:
            actions.pop()
            self._forget(self._game_no(), len(actions))
        elif kind == "amend" and actions:
            actions[-1] = action["move"]
            self._forget(self._game_no(), len(actions) - 1)

    def update(self, raw):
        with self.lock:
            before = dict(self.settings)
            self.settings = clean_settings(raw, self.settings)
            if self.games and not self.games[-1]["actions"] and self.settings["score"] != before["score"]:
                self.games[-1]["score"] = tuple(self.settings["score"])
            if self.settings["match_length"] != before["match_length"] and self.games:
                for game_no in range(1, len(self.games) + 1):
                    self._forget(game_no, 0)
                self.wake.set()
            self.version += 1

    def header(self):
        return {"match_length": self.settings["match_length"], "player1": self.settings["player1"],
                "player2": self.settings["player2"], "site": "VS Gammon live"}

    def transcript(self):
        with self.lock:
            return render_mat(self.header(), self.games)

    # ---- analysis ----

    def _next_job(self):
        for game_no, game in enumerate(self.games, start=1):
            done = self.analysed.get(game_no, 0)
            if done < len(game["actions"]):
                upto = self.games[:game_no]
                upto = upto[:-1] + [{**upto[-1], "result": None}]
                return game_no, max(0, done - 1), render_mat(self.header(), upto), self.generation.get(game_no, 0)
        return None

    def _work(self):
        while self.running:
            self.wake.wait(timeout=1)
            self.wake.clear()
            while self.running:
                with self.lock:
                    job = self._next_job()
                    if not job:
                        break
                    self.engine_state["busy"] = True
                game_no, start, text, generation = job
                try:
                    result = self.engine.analyse(text, start, plies=self.plies, threads=self.threads)
                    error = None
                except Exception as exc:  # the engine failing must not stop the session
                    result, error = None, str(exc)
                with self.lock:
                    self.engine_state = {"busy": False, "error": error}
                    if error:
                        self.version += 1
                        break
                    if self.generation.get(game_no, 0) != generation:
                        continue
                    for key in [k for k in self.decisions if k[0] == game_no and k[1] >= start]:
                        del self.decisions[key]
                    for d in result["decisions"]:
                        self.decisions[(game_no, d["record_index"], d["kind"])] = d
                    for luck in result["luck"]:
                        self.luck[(game_no, luck["record_index"])] = luck
                    self.analysed[game_no] = max(self.analysed.get(game_no, 0), min(result["records"], len(self.games[game_no - 1]["actions"])))
                    self.version += 1

    def stop(self):
        self.running = False
        self.wake.set()

    # ---- what the sidebar shows ----

    def _finished(self, game_no):
        return game_no < len(self.games) or bool(self.games[game_no - 1]["result"])

    def _visible(self, game_no):
        return self.settings["opponent"] == "ai" or self._finished(game_no)

    def _plain(self, game_no, action):
        game = self.games[game_no - 1]
        return {"kind": "checker", "board": list(action["before"]), "on_roll": action["player"], "player": action["player"],
                "dice": list(action["dice"]), "cube_value": 1, "cube_owner": 0, "score1": game["score"][0],
                "score2": game["score"][1], "match_length": self.settings["match_length"], "crawford_game": False,
                "player1": self.settings["player1"], "player2": self.settings["player2"],
                "played_steps": [list(s) for s in action["steps"]]}

    def move(self, game_no, index):
        """One move for the mini board: the engine's decision when it may be shown, else the plain move."""
        with self.lock:
            if not 1 <= game_no <= len(self.games) or not 0 <= index < len(self.games[game_no - 1]["actions"]):
                return None
            action = self.games[game_no - 1]["actions"][index]
            decision = self.decisions.get((game_no, index, "checker")) if self._visible(game_no) else None
            shown = {**decision, "player1": self.settings["player1"], "player2": self.settings["player2"]} if decision \
                else self._plain(game_no, action)
            shown["played_steps"] = [list(s) for s in action["steps"]]
            return {"game_no": game_no, "index": index, "engine": bool(decision), "decision": shown}

    def view(self, thresholds):
        with self.lock:
            moves, graph, rated, luck_by_player = [], [], [], {1: [], 2: []}
            for game_no, game in enumerate(self.games, start=1):
                visible = self._visible(game_no)
                for index, action in enumerate(game["actions"]):
                    row = {"game_no": game_no, "index": index, "player": action["player"], "dice": list(action["dice"]),
                           "move": move_text(action["steps"]), "held": not visible}
                    checker = self.decisions.get((game_no, index, "checker"))
                    luck = self.luck.get((game_no, index))
                    if visible:
                        row["pending"] = index >= self.analysed.get(game_no, 0)
                        if checker:
                            row.update({"error": checker["error"], "class": classify(checker["error"], thresholds),
                                        "best": checker["best"], "forced": checker["forced"]})
                            graph.append({"game_no": game_no, "index": index, "player": action["player"], **win_chances(checker)})
                        if luck:
                            row["luck"] = luck["luck"]
                            row["luck_level"] = luck_level(luck["luck"])
                            luck_by_player[action["player"]].append(luck["luck"])
                        rated += [d for (g, i, _), d in self.decisions.items() if g == game_no and i == index]
                    moves.append(row)
            summary = summarize(rated, thresholds)
            frame = self.tracker.frame
            stats = {}
            for player in (1, 2):
                values = luck_by_player[player]
                stats[player] = {
                    **summary.get(player, {"pr": None}),
                    "luck": round(sum(values), 4) if values else None,
                    "rolls": len(values),
                    "lucky": sum(1 for v in values if v >= 0.3),
                    "unlucky": sum(1 for v in values if v <= -0.3),
                    "pips": pips(frame)[player - 1] if frame else None,
                }
            last = None
            for game_no in range(len(self.games), 0, -1):
                if self.games[game_no - 1]["actions"]:
                    last = self.move(game_no, len(self.games[game_no - 1]["actions"]) - 1)
                    break
            current = len(self.games)
            return {
                "active": True,
                "version": self.version,
                "thresholds": thresholds,
                "settings": self.settings,
                "reading": self.reading,
                "engine": self.engine_state,
                "held": bool(current) and not self._visible(current),
                "games": [{"game_no": n, "score": list(g["score"]), "result": g["result"], "moves": len(g["actions"])}
                          for n, g in enumerate(self.games, start=1)],
                "position": {"frame": frame, "bottom": self.tracker.bottom,
                             "pips": pips(frame) if frame else None},
                "moves": moves,
                "last": last,
                "stats": stats,
                "graph": graph,
            }
