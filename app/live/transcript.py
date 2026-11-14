"""Match transcripts in the .mat (Jellyfish) format that gnubg imports.

A game is {"score": (player 1, player 2), "actions": [...], "result": {"winner", "points"} or None}; an action is
{"player": 1|2, "kind": "move", "dice": (a, b), "steps": ((from, to), ...)} or {"player", "kind": "double"|"take"|"drop"}.
Player 1 is the left column. Steps use the mover's point numbers (25 = bar, 0 = off)."""
import re

from app.live.legal import move_text, parse_move_text
from app.matfile import SCORE_LINE, parse_mat_header

LEFT_WIDTH = 28
NAME_WIDTH = 33
GAME_LINE = re.compile(r"^\s*Game\s+(\d+)\s*$")
NUMBER = re.compile(r"^\s*\d+\)")
ROLL = re.compile(r"^(\d)(\d):\s*(.*)$")
WINS = re.compile(r"^Wins\s+(\d+)\s+points?", re.IGNORECASE)


def _action(text, player):
    text = text.strip()
    if not text:
        return None
    roll = ROLL.match(text)
    if roll:
        return {"player": player, "kind": "move", "dice": (int(roll[1]), int(roll[2])), "steps": parse_move_text(roll[3])}
    lowered = text.lower()
    if lowered.startswith("doubles"):
        return {"player": player, "kind": "double"}
    if lowered.startswith("takes"):
        return {"player": player, "kind": "take"}
    if lowered.startswith(("drops", "passes")):
        return {"player": player, "kind": "drop"}
    wins = WINS.match(text)
    if wins:
        return {"player": player, "kind": "wins", "points": int(wins[1])}
    raise ValueError(f"unknown action: {text}")


def parse_mat(text):
    header = parse_mat_header(text)
    lines = text.splitlines()
    games, game, column = [], None, None
    for i, line in enumerate(lines):
        if GAME_LINE.match(line):
            score = SCORE_LINE.match(lines[i + 1]) if i + 1 < len(lines) else None
            if not score:
                raise ValueError("a game without a score line")
            column = score.start("p2")
            numbers = re.findall(r":\s*(\d+)", lines[i + 1])
            game = {"score": (int(numbers[0]), int(numbers[1])), "actions": [], "result": None}
            games.append(game)
            continue
        if game is None or not line.strip() or SCORE_LINE.match(line) or line.lstrip().startswith(";"):
            continue
        body = NUMBER.sub(lambda m: " " * len(m[0]), line, count=1)
        for player, part in ((1, body[:column]), (2, body[column:])):
            action = _action(part, player)
            if action and action["kind"] == "wins":
                game["result"] = {"winner": player, "points": action["points"]}
            elif action:
                game["actions"].append(action)
    return header, games


def _text(action, cube_value):
    if action["kind"] == "move":
        high, low = max(action["dice"]), min(action["dice"])
        moves = move_text(action["steps"])
        return f"{high}{low}: {moves}" if moves else f"{high}{low}:"
    if action["kind"] == "double":
        return f" Doubles => {cube_value * 2}"
    return " Takes" if action["kind"] == "take" else " Drops"


def _line(number, left, right):
    prefix = f"{number:3d}) " if number else " " * 5
    left_part = left.ljust(LEFT_WIDTH) if right else left
    if right and len(left) >= LEFT_WIDTH:
        left_part = left + " "
    return (prefix + left_part + right).rstrip()


def render_mat(header, games):
    names = (header.get("player1") or "Player 1", header.get("player2") or "Player 2")
    out = []
    for key, tag in (("player1", "Player 1"), ("player2", "Player 2"), ("site", "Site")):
        if header.get(key):
            out.append(f'; [{tag} "{header[key]}"]')
    out += ["", f" {header['match_length']} point match", ""]
    for game_no, game in enumerate(games, start=1):
        out.append(f" Game {game_no}")
        out.append(f" {names[0]} : {game['score'][0]}".ljust(NAME_WIDTH) + f"{names[1]} : {game['score'][1]}")
        cube, number, row = 1, 0, None
        for action in game["actions"]:
            text = _text(action, cube)
            if action["kind"] == "take":
                cube *= 2
            if action["player"] == 1 or row is None:
                if row is not None:
                    out.append(_line(*row))
                number += 1
                row = [number, "", ""]
            row[action["player"]] = text
            if action["player"] == 2:
                out.append(_line(*row))
                row = None
        if row is not None:
            out.append(_line(*row))
        if game.get("result"):
            winner, points = game["result"]["winner"], game["result"]["points"]
            ends = header["match_length"] and game["score"][winner - 1] + points >= header["match_length"]
            win = f" Wins {points} point" + (" and the match" if ends else "")
            out.append(_line(0, win, "") if game["result"]["winner"] == 1 else _line(0, "", win))
        out.append("")
    return "\n".join(out) + "\n"
