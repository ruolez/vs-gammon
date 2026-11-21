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


def mover_fits(frame, reading, bottom, player):
    """Whether the player's checkers in a known position are where the reading shows them, allowing for blots the
    other side may have hit since (those sit on the player's bar now; the hitting checker may have moved on)."""
    top = "light" if bottom == "dark" else "dark"
    own_colour = bottom if player == 1 else top
    sign = 1 if player == 1 else -1
    hits = 0
    for point in range(1, 25):
        own = max(sign * frame[point], 0)
        seen_own = reading[own_colour][point]
        if own == seen_own or (reading["capped"][point] and seen_own and own > seen_own):
            continue
        if own == 1 and not seen_own:
            hits += 1
            continue
        return False
    bar = sign * frame[25 if player == 1 else 0]
    if reading[f"bar_{own_colour}"] != bar + hits:
        return False
    off = reading.get(f"off_{own_colour}")
    return off is None or off == 15 - sum(max(sign * c, 0) for c in frame)


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
        self.unexplained = 0

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
        # One side moving twice running needs the other to have danced, which shows as dice changing sides: when two
        # plays, one each, fit as well (the other side entered and was hit straight back), they are what happened.
        last = self.history[-1]["action"]["player"] if self.history else None
        if move and move["player"] != last:
            moves = [move]
        else:
            moves = list(self._find_pair(reading) or ([move] if move else []))
        if not moves:
            self.unexplained += 1
        for move in moves:
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

    def _rolls(self, player, shown):
        """The rolls that may explain the player's next play. While the player's dice are still on screen only those
        dice count (a half-played move must not pass for another roll's whole play); once they are gone or replaced
        the move is over, and a roll the screen didn't show counts too, so a misread die never stops the game being
        followed."""
        known = self.dice.get(player)
        if not known:
            return ROLLS
        if self._still_shown(player, shown):
            return [known]
        return [known] + [r for r in ROLLS if r != tuple(sorted(known))]

    def _still_shown(self, player, shown):
        known = self.dice.get(player)
        return bool(known and shown and PLAYER[shown["side"]] == player and sorted(shown["values"]) == sorted(known))

    def _plays(self, frame, player, rolls):
        onroll = frame if player == 1 else flip_frame(frame)
        for roll in rolls:
            for end, steps in final_positions(onroll, roll).items():
                if steps:
                    after = list(end) if player == 1 else flip_frame(list(end))
                    yield {"player": player, "kind": "move", "dice": tuple(roll), "steps": steps, "after": after}

    def _rank(self, move):
        known = self.dice.get(move["player"])
        if not known:
            return 2
        return 0 if sorted(known) == sorted(move["dice"]) else 1

    def _find_move(self, reading):
        """The play that turns the position into the reading. A play with the dice seen wins, then one by the side
        that had dice."""
        shown = reading.get("dice")
        fitting = [move for player in (1, 2) for move in self._plays(self.frame, player, self._rolls(player, shown))
                   if fits(move["after"], reading, self.bottom)]
        return min(fitting, key=self._rank) if fitting else None

    def _find_pair(self, reading):
        """Two plays, one by each side, that turn the position into the reading: the screen after the first was
        never read twice in a row (Galaxy's AI moves at once and the player can roll and play straight after), and
        without this the game would no longer be followed at all. The first play's side must match the reading's
        checkers but for blots the second play hit, which leaves few candidates for the second play's search. While
        the first side's dice are still on screen it is still moving; while the second side's are, only they count
        (that play may be half done)."""
        shown = reading.get("dice")
        last = self.history[-1]["action"]["player"] if self.history else None
        firsts = (3 - last,) if last else (1, 2)
        fitting = []
        for first in firsts:
            second = 3 - first
            if self._still_shown(first, shown):
                continue
            for move in self._plays(self.frame, first, self._rolls(first, None)):
                if not mover_fits(move["after"], reading, self.bottom, first):
                    continue
                rolls = [tuple(sorted(shown["values"]))] if shown and PLAYER[shown["side"]] == second else ROLLS
                for reply in self._plays(move["after"], second, rolls):
                    if fits(reply["after"], reading, self.bottom):
                        fitting.append((move, reply))
                        break
        if not fitting:
            return None
        return min(fitting, key=lambda pair: self._rank(pair[0]))
