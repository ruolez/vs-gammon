import datetime
import os
import random

from app.position import flip_frame
from app.xgp.archive import build_rich_header, pack_archive, read_xg_file
from app.xgp.records import NOT_ANALYSED, set_field, split_records

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template.xgp")
MONEY_GAME = 99999
DELPHI_EPOCH = datetime.datetime(1899, 12, 30)
DOUBLED_BLOCK = slice(64, 196)
UNANALYSED_CUBE_FLAG = -100
NO_CUBE_ACTION = -2
XG_BAR = 24
XG_OFF = -1
COMMENT_LINE = b"\x01\x02"
RTF_HEAD = (b"{\\rtf1\\ansi\\ansicpg1252\\uc1\\deff0\\deflang1033\\deflangfe1033{\\fonttbl{\\f0\\fcharset0 Arial;}}"
            + COMMENT_LINE + b"{\\colortbl;}" + COMMENT_LINE + b"\\pard\\sl-240\\slmult1 \\lang1033\\fs20\\f0 ")


def _load_template():
    with open(TEMPLATE_PATH, "rb") as f:
        files = dict(read_xg_file(f.read())["files"])
    header_match, header_game, cube = split_records(files["temp.xg"])
    _, pending_move = split_records(files["temp.xgi"])
    return header_match, header_game, cube, pending_move


def _delphi_date(moment):
    return (moment - DELPHI_EPOCH).total_seconds() / 86400


def _signed_cube_log(cube_value, cube_owner):
    log = cube_value.bit_length() - 1
    return {0: 0, 1: log, 2: -log}[cube_owner]


def _away(spot, player):
    if not spot["match_length"]:
        return 0
    score = spot["score1"] if player == 1 else spot["score2"]
    return spot["match_length"] - score


def _dice_text(dice):
    return f"{dice[0]}{dice[1]}" if dice else "11"


def _xg_moves(steps):
    """Our steps (1-24, 25 = bar, 0 = off) as XG's from/to pairs: 0-based points, 24 = bar, -1 = off."""
    pairs = [value for a, b in steps for value in (XG_BAR if a == 25 else a - 1, XG_OFF if b == 0 else b - 1)]
    return pairs + [-1] * (8 - len(pairs))


def _after_move(frame, steps):
    """The mover's frame (25 = own bar, 0 = the opponent's bar, opponent negative) after playing the steps."""
    after = list(frame)
    for a, b in steps:
        after[a] -= 1
        if b == 0:
            continue
        if after[b] == -1:
            after[b] = 0
            after[0] -= 1
        after[b] += 1
    return after


def _cube_action(spot, cube_b, active):
    if spot["decision"] == "checker":
        can_double = not spot["crawford_game"] and cube_b * active >= 0
        return (0 if can_double else NO_CUBE_ACTION), -1
    if spot["decision"] == "double":
        return (1 if spot["action"] == "Double" else 0), -1
    return 1, (1 if spot["action"] == "Take" else 0)


def _rtf_comment(text):
    escaped = bytearray()
    for byte in text.encode("cp1252", "replace"):
        if byte in b"\\{}":
            escaped += b"\\" + bytes([byte])
        elif 32 <= byte < 127:
            escaped.append(byte)
        else:
            escaped += f"\\'{byte:02x}".encode()
    return RTF_HEAD + bytes(escaped) + b"\\par" + COMMENT_LINE + b"}\r\n"


def save_name(spot):
    if not spot["match_length"]:
        return "Position: money game"
    return f"Position: {spot['match_length']} point match {spot['score1']}-{spot['score2']}"


def build_xgp(spot):
    header_match, header_game, cube, move = _load_template()
    on_roll = spot["on_roll"]
    opponent = 2 if on_roll == 1 else 1
    active = 1 if on_roll == 1 else -1
    cube_b = _signed_cube_log(spot["cube_value"], spot["cube_owner"])
    onroll_view = spot["board"] if on_roll == 1 else flip_frame(spot["board"])

    set_field(header_match, "s_player1", spot["player1"])
    set_field(header_match, "s_player2", spot["player2"])
    set_field(header_match, "player1", spot["player1"])
    set_field(header_match, "player2", spot["player2"])
    set_field(header_match, "match_length", spot["match_length"] or MONEY_GAME)
    set_field(header_match, "crawford", bool(spot["match_length"]))
    set_field(header_match, "date", _delphi_date(spot["saved_at"]))
    set_field(header_match, "game_id", random.randint(1, 2**31 - 1))

    set_field(header_game, "score1", spot["score1"])
    set_field(header_game, "score2", spot["score2"])
    set_field(header_game, "crawford_apply", spot["crawford_game"])
    set_field(header_game, "game_number", 1)
    set_field(header_game, "in_progress", True)

    double, take = _cube_action(spot, cube_b, active)
    set_field(cube, "active", active)
    for name in ("beaver_r", "raccoon_r", "rollout_index_d", "comp_choice_d", "analyze_c", "analyze_cr"):
        set_field(cube, name, -1)
    set_field(cube, "double", double)
    set_field(cube, "take", take)
    set_field(cube, "cube_b", cube_b)
    set_field(cube, "position", spot["board"])
    cube[DOUBLED_BLOCK] = bytes(DOUBLED_BLOCK.stop - DOUBLED_BLOCK.start)
    set_field(cube, "an_pos", onroll_view)
    set_field(cube, "an_score", [_away(spot, on_roll), _away(spot, opponent)])
    set_field(cube, "an_cube", spot["cube_value"])
    set_field(cube, "an_cube_pos", 0 if cube_b == 0 else (1 if cube_b * active > 0 else -1))
    set_field(cube, "an_crawford", 1 if spot["crawford_game"] else 0)
    set_field(cube, "an_flag_double", UNANALYSED_CUBE_FLAG)
    for name in ("err_cube", "err_take", "err_beaver", "err_raccoon", "err_tutor_cube", "err_tutor_take"):
        set_field(cube, name, NOT_ANALYSED)
    set_field(cube, "dice_rolled", _dice_text(spot["dice"]))
    set_field(cube, "flagged", False)
    set_field(cube, "comment_cube", -1)

    set_field(move, "active", active)
    set_field(move, "position_i", spot["board"])
    set_field(move, "dice", list(spot["dice"] or (1, 1)))
    set_field(move, "cube_a", cube_b)

    game_records = [header_match, header_game, cube]
    if spot["decision"] == "checker":
        set_field(move, "moves", _xg_moves(spot["played_steps"]))
        set_field(move, "position_end", _after_move(onroll_view, spot["played_steps"]))
        set_field(move, "played", True)
        game_records.append(move)
    if spot["comment"] and spot["decision"] == "checker":
        set_field(move, "comment_move", 0)
    elif spot["comment"]:
        set_field(cube, "comment_cube", 0)
    files = [
        ("temp.xg", b"".join(bytes(r) for r in game_records)),
        ("temp.xgi", bytes(header_match) + bytes(move)),
    ]
    if spot["comment"]:
        files.append(("temp.xgc", _rtf_comment(spot["comment"])))
    header = build_rich_header(spot["guid"], save_name(spot), spot["thumbnail"])
    return header + pack_archive(files)
