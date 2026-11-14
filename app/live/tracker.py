"""Turns board readings (what the screen shows) into match actions.

A reading counts the checkers of each colour on every point, numbered from the bottom player's side (1 = bottom
right), the bar, the checkers borne off and the dice: {"found", "dark": [25], "light": [25], "capped": [25],
"bar_dark", "bar_light", "off_dark", "off_light" (None when not read), "dice": {"side": "bottom"|"top",
"values": [a, b]} | None}. "capped" marks stacks drawn at the most a point can show, so there may be more; the
borne-off counts then still tell a bear-off from that stack apart. Player 1 is the bottom player, frames are in
player 1's frame."""
from app.live.legal import final_positions
from app.live.replay import START
from app.position import flip_frame

ROLLS = [(a, b) for a in range(1, 7) for b in range(a, 7)]
STABLE_READINGS = 2
PLAYER = {"bottom": 1, "top": 2}
COLORS = ("dark", "light")


def reading_frame(reading, bottom):
    top = "light" if bottom == "dark" else "dark"
    frame = [0] * 26
    for point in range(1, 25):
        frame[point] = reading[bottom][point] - reading[top][point]
    frame[25] = reading[f"bar_{bottom}"]
    frame[0] = -reading[f"bar_{top}"]
    return frame


def fits(frame, reading, bottom):
    """Whether a known position could be what the reading shows (capped stacks may hold more)."""
    top = "light" if bottom == "dark" else "dark"
    if frame[25] != reading[f"bar_{bottom}"] or -frame[0] != reading[f"bar_{top}"]:
        return False
    off = (15 - sum(c for c in frame if c > 0), 15 + sum(c for c in frame if c < 0))
    for seen, count in ((reading.get(f"off_{bottom}"), off[0]), (reading.get(f"off_{top}"), off[1])):
        if seen is not None and seen != count:
            return False
    for point in range(1, 25):
        own, other = max(frame[point], 0), max(-frame[point], 0)
        seen_own, seen_other = reading[bottom][point], reading[top][point]
        if reading["capped"][point]:
            if own < seen_own or other < seen_other or (seen_own and other) or (seen_other and own):
                return False
        elif (own, other) != (seen_own, seen_other):
            return False
    return True


def winner(frame):
    """(player, points) when one side has borne every checker off, else None. No cube is read yet: points are 1-3."""
    mine, theirs = sum(c for c in frame if c > 0), -sum(c for c in frame if c < 0)
    if mine and theirs:
        return None
    won, lost_frame = (1, frame) if not mine else (2, flip_frame(frame))
    loser_left = -sum(c for c in lost_frame if c < 0)
    if loser_left < 15:
        return won, 1
    in_home = any(lost_frame[p] < 0 for p in range(0, 7))
    return won, 3 if in_home else 2


class Tracker:
    def __init__(self):
        self.bottom = None
        self.frame = None
        self.history = []
        self.last_key = None
        self.repeats = 0
        self.handled_key = None
        self.dice = {}
        self.dice_order = []

    def _key(self, reading):
        dice = reading.get("dice")
        return (tuple(reading["dark"]), tuple(reading["light"]), tuple(reading["capped"]), reading["bar_dark"],
                reading["bar_light"], reading.get("off_dark"), reading.get("off_light"),
                (dice["side"], tuple(dice["values"])) if dice else None)

    def feed(self, reading):
        """Returns the actions this reading completes: moves, {"kind": "game"} for a new game, {"kind": "undo"} when the
        last move was taken back, {"kind": "amend", "move"} when it turned out to be a different play (a half-played
        move can look like another whole play; the move is final once the other side acts)."""
        if not reading or not reading.get("found"):
            return []
        key = self._key(reading)
        self.repeats = self.repeats + 1 if key == self.last_key else 1
        self.last_key = key
        if self.repeats < STABLE_READINGS or key == self.handled_key:
            return []
        self.handled_key = key
        return self._stable(reading)

    def _start_colour(self, reading):
        return next((c for c in COLORS if fits(START, reading, c)), None)

    def _stable(self, reading):
        actions = []
        starting = self._start_colour(reading)
        taken_back = self.history and self.history[-1]["before"] == START and not self.history[-1].get("closed")
        if starting and self.frame != START and not taken_back:
            self.bottom = starting
            if self.frame is not None:
                actions.append({"kind": "game", "result": winner(self.frame)})
            else:
                actions.append({"kind": "game", "result": None})
            self.frame, self.history, self.dice, self.dice_order = list(START), [], {}, []
        if self.bottom is None or self.frame is None:
            return actions
        dice = reading.get("dice")
        if fits(self.frame, reading, self.bottom):
            if dice:
                actions += self._dice_seen(PLAYER[dice["side"]], tuple(dice["values"]))
            return actions
        if self.history and fits(self.history[-1]["before"], reading, self.bottom):
            undone = self.history.pop()
            self.frame = undone["before"]
            self.dice[undone["action"]["player"]] = undone["action"]["dice"]
            return actions + [{"kind": "undo"}]
        amended = self._amend(reading)
        if amended:
            return actions + [amended]
        move = self._find_move(reading)
        if move:
            self._close()
            self.history.append({"before": self.frame, "action": move})
            move["before"] = self.frame
            self.frame = move.pop("after")
            self.dice.pop(move["player"], None)
            actions.append(move)
        return actions

    def _amend(self, reading):
        last = self.history[-1] if self.history else None
        if not last or last.get("closed") or not last["action"]["steps"]:
            return None
        action = last["action"]
        before = last["before"]
        onroll = before if action["player"] == 1 else flip_frame(before)
        for end, steps in final_positions(onroll, action["dice"]).items():
            after = list(end) if action["player"] == 1 else flip_frame(list(end))
            if fits(after, reading, self.bottom):
                last["action"] = {**action, "steps": steps}
                self.frame = after
                return {"kind": "amend", "move": {**last["action"], "before": before}}
        return None

    def _close(self):
        if self.history:
            self.history[-1]["closed"] = True

    def _dice_seen(self, player, values):
        """New dice for one side while the position stands still: if the other side had dice it never used, it danced."""
        if self.dice.get(player) == values:
            return []
        actions = []
        other = 3 - player
        if self.history and self.history[-1]["action"]["player"] != player:
            self._close()
        if other in self.dice:
            actions.append({"player": other, "kind": "move", "dice": self.dice.pop(other), "steps": (), "before": self.frame})
            self._close()
            self.history.append({"before": self.frame, "action": actions[-1], "closed": True})
        self.dice[player] = values
        return actions

    def _find_move(self, reading):
        fitting = []
        for player in (1, 2):
            onroll = self.frame if player == 1 else flip_frame(self.frame)
            known = self.dice.get(player)
            rolls = [known] if known else ROLLS
            for roll in rolls:
                for end, steps in final_positions(onroll, roll).items():
                    after = list(end) if player == 1 else flip_frame(list(end))
                    if steps and fits(after, reading, self.bottom):
                        fitting.append({"player": player, "kind": "move", "dice": tuple(roll), "steps": steps, "after": after})
        if not fitting:
            return None
        with_dice = [m for m in fitting if self.dice.get(m["player"])]
        return (with_dice or fitting)[0]
