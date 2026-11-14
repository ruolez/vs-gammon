from app.analysis import checker_error, double_error, take_error
from app.position import player1_frame

PLAYER_NUMBER = {"X": 1, "O": 2}
GNUBG_INDEX = {1: 0, 2: 1}
GNUBG_OWNER = {0: -1, 1: 0, 2: 1}
DOUBLE_PASS = 1.0
MAX_CANDIDATES = 10


class LineCounter:
    def __init__(self):
        self.line = 1
        self.filled = set()

    def place(self, player):
        if player in self.filled or (player == 1 and 2 in self.filled):
            self.line += 1
            self.filled = set()
        self.filled.add(player)
        return self.line


def best_cube_action(nd, dt, dp):
    if min(dt, dp) > nd:
        return "Double, take" if dt <= dp else "Double, pass"
    if dt > dp:
        return "Too good to double, pass"
    return "No double, take"


def rollout_equity(m, to_emg):
    """A rolled-out move's equity and standard error, as gnubg scores it: cubeful results are match winning
    chances turned into equity, cubeless ones are already an equity."""
    if m.get("cubeful", True):
        value = to_emg(m["cubeful-eq"])
        return value, abs(to_emg(m["cubeful-eq"] + m["cubeful-eq-std"]) - value)
    return m["match-eq"], m["match-eq-std"]


def _depth(m, base_plies):
    context = m.get("evalcontext") or {}
    return context.get("plies", base_plies)


def _row(m, move_text, board, to_emg, base_plies):
    row = {"move": move_text(m["move"], board), "steps": m["move"], "probs": m["probs"]}
    if m.get("type") == "rollout":
        row["equity"], std = rollout_equity(m, to_emg)
        row["rollout"] = {"trials": m["trials"], "std": std, "probs_std": m.get("probs-std")}
    else:
        row["equity"] = m["score"]
        if base_plies is not None:
            row["plies"] = _depth(m, base_plies)
    return row


def _full(m, base_plies):
    if base_plies is None or m.get("type") == "rollout":
        return "evalcontext" not in m
    return _depth(m, base_plies) >= base_plies


def _candidates(analysis, played_move, move_text, board, to_emg=lambda v: v, base_plies=None):
    evaluated = [_row(m, move_text, board, to_emg, base_plies) | {"_full": _full(m, base_plies), "_move": m["move"]}
                 for m in analysis["moves"]]
    full = [m for m in evaluated if m["_full"]]
    played = next((m for m in evaluated if m["_move"] == played_move), evaluated[analysis["imove"]])
    ranked = sorted(full if played in full else full + [played], key=lambda m: -m["equity"])
    kept = ranked if base_plies is not None else ranked[:MAX_CANDIDATES]
    if played not in kept:
        kept.append(played)
    rows = [{k: v for k, v in m.items() if not k.startswith("_")} for m in kept]
    legal = sorted(
        ({"steps": m["steps"], "text": m["move"], "equity": m["equity"], "full": m["_full"]} for m in evaluated),
        key=lambda m: -m["equity"],
    )
    return rows, kept.index(played), len(evaluated) == 1, legal


def walk_match(match, helpers, with_records=False, base_plies=None):
    """base_plies: the depth the match was analysed at. When given, every candidate is kept and labelled with the
    depth it was evaluated at (used after a deeper analysis of one decision)."""
    info = match["match-info"]
    match_length = info.get("match-length", 0)
    games, decisions, luck = [], [], []

    for game_no, game in enumerate(match["games"], start=1):
        ginfo = game["info"]
        score1, score2 = ginfo.get("score-X", 0), ginfo.get("score-O", 0)
        crawford = bool(ginfo.get("crawford", False))
        games.append({
            "game_no": game_no, "score1": score1, "score2": score2, "crawford": crawford,
            "winner": PLAYER_NUMBER.get(ginfo.get("winner")), "points": ginfo.get("points-won"),
        })
        cube_value, cube_owner = 1, 0
        last_double = None
        lines = LineCounter()

        def context(player, on_roll, position_id):
            pair = helpers.board_pair(position_id)
            return pair, {
                "game_no": game_no, "player": player, "on_roll": on_roll, "position_id": position_id,
                "board": player1_frame(pair, on_roll), "cube_value": cube_value, "cube_owner": cube_owner,
                "score1": score1, "score2": score2, "match_length": match_length, "crawford_game": crawford,
            }

        def to_emg(value, on_roll):
            if not match_length:
                return value
            return helpers.mwc_to_emg(value, cube_value, GNUBG_OWNER[cube_owner], GNUBG_INDEX[on_roll],
                                      match_length, (score1, score2), crawford)

        def cube_equities(analysis, on_roll):
            nd = to_emg(analysis["nd-cubeful-eq"], on_roll)
            dt = to_emg(analysis["dt-cubeful-eq"], on_roll)
            cube = {"nd": nd, "dt": dt, "dp": DOUBLE_PASS, "probs": analysis.get("probs", analysis.get("nd-probs"))}
            if base_plies is not None and analysis.get("type") != "rollout":
                cube["plies"] = (analysis.get("eval-context") or {}).get("plies", base_plies)
            if analysis.get("type") == "rollout":
                cube["rollout"] = {
                    "trials": analysis["trials"],
                    "nd_std": abs(to_emg(analysis["nd-cubeful-eq"] + analysis["nd-cubeful-eq-std"], on_roll) - nd),
                    "dt_std": abs(to_emg(analysis["dt-cubeful-eq"] + analysis["dt-cubeful-eq-std"], on_roll) - dt),
                }
            return cube

        def found(decision, record_index):
            if with_records:
                decision["record_index"] = record_index
            decisions.append(decision)

        for record_index, record in enumerate(game["game"]):
            action = record.get("action")
            if action == "set":
                cube_value = record.get("cube", cube_value)
                if "cube-owner" in record:
                    cube_owner = {"centered": 0, "X": 1, "O": 2}[record["cube-owner"]]
                continue
            if action not in ("move", "double", "take", "drop"):
                continue
            player = PLAYER_NUMBER[record["player"]]
            move_no = lines.place(player)
            analysis = record.get("analysis") or {}

            if action == "move":
                if "luck-value" in analysis:
                    luck.append({"game_no": game_no, "move_no": move_no, "player": player, "dice": record.get("dice"),
                                 "luck": analysis["luck-value"], **({"record_index": record_index} if with_records else {})})
                if "nd-cubeful-eq" in analysis:
                    _, base = context(player, player, record["board"])
                    cube = cube_equities(analysis, player)
                    found({
                        **base, "move_no": move_no, "kind": "cube", "dice": record.get("dice"),
                        "action": "No double", "best": best_cube_action(cube["nd"], cube["dt"], cube["dp"]),
                        "error": double_error(cube["nd"], cube["dt"], cube["dp"], doubled=False),
                        "forced": False, "cube": cube, "candidates": None,
                        "gnubg_skill": analysis.get("cube-skill"),
                    }, record_index)
                if record.get("move") and analysis.get("moves"):
                    pair, base = context(player, player, record["board"])
                    rows, played_index, forced, legal = _candidates(
                        analysis, record["move"], helpers.move_text, pair, lambda v: to_emg(v, player), base_plies)
                    best_index = max(range(len(rows)), key=lambda i: rows[i]["equity"])
                    found({
                        **base, "move_no": move_no, "kind": "checker", "dice": record.get("dice"),
                        "action": rows[played_index]["move"], "best": rows[best_index]["move"],
                        "error": checker_error(rows, played_index), "forced": forced,
                        "candidates": rows, "played_index": played_index, "cube": None, "legal": legal,
                        "gnubg_skill": analysis.get("skill"),
                    }, record_index)
            elif action == "double":
                _, base = context(player, player, record["board"])
                cube = cube_equities(analysis, player) if "nd-cubeful-eq" in analysis else None
                last_double = {"base": base, "cube": cube, "record_index": record_index}
                if cube:
                    found({
                        **base, "move_no": move_no, "kind": "cube", "dice": None, "action": "Double",
                        "best": best_cube_action(cube["nd"], cube["dt"], cube["dp"]),
                        "error": double_error(cube["nd"], cube["dt"], cube["dp"], doubled=True),
                        "forced": False, "cube": cube, "candidates": None,
                        "gnubg_skill": analysis.get("skill"),
                    }, record_index)
            else:
                took = action == "take"
                if last_double and last_double["cube"]:
                    cube = last_double["cube"]
                    found({
                        **last_double["base"], "player": player, "move_no": move_no, "kind": "take", "dice": None,
                        "action": "Take" if took else "Pass", "best": "Take" if cube["dt"] <= cube["dp"] else "Pass",
                        "error": take_error(cube["dt"], cube["dp"], took), "forced": False,
                        "cube": cube, "candidates": None, "gnubg_skill": analysis.get("skill"),
                    }, last_double["record_index"])
                if took:
                    cube_value *= 2
                    cube_owner = player
                last_double = None

    result = {
        "match": {
            "match_length": match_length,
            "player1": info.get("X", {}).get("name"),
            "player2": info.get("O", {}).get("name"),
        },
        "games": games,
        "decisions": decisions,
    }
    if luck:
        result["luck"] = luck
    return result
