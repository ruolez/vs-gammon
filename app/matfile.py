import hashlib
import json
import re

TAG = re.compile(r'^\s*;\s*\[(?P<key>[^"\]]+?)\s+"(?P<value>[^"]*)"\]')
MATCH_LENGTH = re.compile(r"^\s*(\d+)\s+point match", re.IGNORECASE | re.MULTILINE)
SCORE_LINE = re.compile(r"^\s*(?P<p1>\S.*?)\s*:\s*\d+\s{2,}(?P<p2>\S.*?)\s*:\s*\d+\s*$")


def _elo(value):
    if not value:
        return None
    return value.split("/")[0].replace(",", ".").strip()


def parse_mat_header(text):
    length = MATCH_LENGTH.search(text)
    if not length:
        raise ValueError("not a match file: no 'N point match' line")
    tags = {}
    for line in text.splitlines():
        found = TAG.match(line)
        if found:
            tags[found["key"].strip()] = found["value"].strip()
    player1, player2 = tags.get("Player 1"), tags.get("Player 2")
    if not (player1 and player2):
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.match(r"^\s*Game\s+1\s*$", line) and i + 1 < len(lines):
                score = SCORE_LINE.match(lines[i + 1])
                if score:
                    player1, player2 = score["p1"], score["p2"]
                break
    date = tags.get("EventDate")
    time = tags.get("EventTime")
    return {
        "site": tags.get("Site"),
        "external_id": tags.get("Match ID"),
        "player1": player1,
        "player2": player2,
        "elo1": _elo(tags.get("Player 1 Elo")),
        "elo2": _elo(tags.get("Player 2 Elo")),
        "event_date": date.replace(".", "-") if date else None,
        "event_time": time.replace(".", ":") if time else None,
        "match_length": int(length.group(1)),
    }


GAME_LINE = re.compile(r"^\s*Game\s+\d+\s*$")
MOVE_NUMBER = re.compile(r"^\s*\d+\)")
REPEATED = re.compile(r"^(?P<move>\S+?)\((?P<times>\d)\)$")


def _normal_action(text):
    text = " ".join(text.replace("*", "").split()).lower()
    dice, colon, moves = text.partition(":")
    if not (colon and dice.isdigit()):
        return text
    steps = []
    for step in moves.split():
        repeated = REPEATED.match(step)
        steps += [repeated["move"]] * int(repeated["times"]) if repeated else [step]
    return f"{dice}: {' '.join(sorted(steps))}"


def match_fingerprint(text):
    """Same value for the same match whatever the headers say or which player's column is on the left:
    every action is recorded with its player's name, in the order played."""
    length = int(MATCH_LENGTH.search(text).group(1)) if MATCH_LENGTH.search(text) else None
    lines = text.splitlines()
    games, actions, names, column = [], None, None, None
    for i, line in enumerate(lines):
        if GAME_LINE.match(line):
            score = SCORE_LINE.match(lines[i + 1]) if i + 1 < len(lines) else None
            if not score:
                return None
            names = (score["p1"].strip().lower(), score["p2"].strip().lower())
            column = score.start("p2")
            actions = []
            games.append(actions)
            continue
        if actions is None or not line.strip() or SCORE_LINE.match(line) or line.lstrip().startswith(";"):
            continue
        for name, part in ((names[0], MOVE_NUMBER.sub("", line[:column], count=1)), (names[1], line[column:])):
            action = _normal_action(part)
            if action:
                actions.append([name, action])
    if length is None or not any(games):
        return None
    payload = json.dumps({"length": length, "games": games}, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
