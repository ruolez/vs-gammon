"""Legal checker plays in the on-roll frame (index 1..24 = points from the mover's side, 25 = mover's bar,
0 = opponent's bar as a negative count; mover's checkers positive). Steps are (from, to) with 25 = bar, 0 = off."""
import re
from functools import reduce

BAR = 25
OFF = 0


def apply_step(frame, step):
    start, end = step
    after = list(frame)
    after[start] -= 1
    if end != OFF:
        if after[end] == -1:
            after[end] = 0
            after[0] -= 1
        after[end] += 1
    return after


def apply_steps(frame, steps):
    return reduce(apply_step, steps, list(frame))


def _single_steps(frame, die):
    if frame[BAR] > 0:
        to = BAR - die
        return [(BAR, to)] if frame[to] >= -1 else []
    home = all(frame[p] <= 0 for p in range(7, BAR + 1))
    highest = next((p for p in range(6, 0, -1) if frame[p] > 0), 0) if home else 0
    steps = []
    for point in range(24, 0, -1):
        if frame[point] <= 0:
            continue
        to = point - die
        if to >= 1:
            if frame[to] >= -1:
                steps.append((point, to))
        elif home and (to == 0 or point == highest):
            steps.append((point, OFF))
    return steps


def _sequences(frame, dice, done, found):
    moved = False
    for i, die in enumerate(dice):
        if die in dice[:i]:
            continue
        rest = dice[:i] + dice[i + 1:]
        for step in _single_steps(frame, die):
            moved = True
            _sequences(apply_step(frame, step), rest, done + [(step, die)], found)
    if not moved:
        found.append((done, frame))


def final_positions(frame, dice):
    """{final frame (tuple): steps} for every distinct legal play, applying the rules on how many dice must be used."""
    high, low = max(dice), min(dice)
    found = []
    _sequences(list(frame), [high] * 4 if high == low else [high, low], [], found)
    longest = max(len(done) for done, _ in found)
    kept = [(done, end) for done, end in found if len(done) == longest]
    if longest == 1 and high != low and any(die == high for (_, die), in (d for d, _ in kept)):
        kept = [(done, end) for done, end in kept if done[0][1] == high]
    finals = {}
    for done, end in kept:
        finals.setdefault(tuple(end), tuple(step for step, _ in done))
    return finals


def legal_moves(frame, dice):
    return list(final_positions(frame, dice).values())


def move_text(steps):
    return " ".join(f"{a}/{b}" for a, b in sorted(steps, reverse=True))


STEP = re.compile(r"^(bar|\d+)/(off|\d+)\*?(?:\((\d)\))?$", re.IGNORECASE)


def parse_move_text(text):
    steps = []
    for token in text.replace("*", "").split():
        found = STEP.match(token)
        if not found:
            raise ValueError(f"not a move: {token}")
        start = BAR if found[1].lower() == "bar" else int(found[1])
        end = OFF if found[2].lower() == "off" else int(found[2])
        steps += [(start, end)] * int(found[3] or 1)
    return tuple(sorted(steps, reverse=True))
