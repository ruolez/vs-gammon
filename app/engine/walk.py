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


def _candidates(analysis, played_move, move_text, board):
    evaluated = analysis["moves"]
    full = [m for m in evaluated if "evalcontext" not in m]
    played = next((m for m in evaluated if m["move"] == played_move), evaluated[analysis["imove"]])
    ranked = sorted(full if played in full else full + [played], key=lambda m: -m["score"])
    kept = ranked[:MAX_CANDIDATES]
    if played not in kept:
        kept.append(played)
    rows = [{"move": move_text(m["move"], board), "steps": m["move"], "equity": m["score"], "probs": m["probs"]}
            for m in kept]
    legal = sorted(
        ({"steps": m["move"], "text": move_text(m["move"], board), "equity": m["score"], "full": "evalcontext" not in m}
         for m in evaluated),
        key=lambda m: -m["equity"],
    )
    return rows, kept.index(played), len(evaluated) == 1, legal


def walk_match(match, helpers):
    info = match["match-info"]
    match_length = info.get("match-length", 0)
    games, decisions = [], []

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
            return {"nd": nd, "dt": dt, "dp": DOUBLE_PASS, "probs": analysis.get("probs")}

        for record in game["game"]:
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
                if "nd-cubeful-eq" in analysis:
                    _, base = context(player, player, record["board"])
                    cube = cube_equities(analysis, player)
                    decisions.append({
                        **base, "move_no": move_no, "kind": "cube", "dice": record.get("dice"),
                        "action": "No double", "best": best_cube_action(cube["nd"], cube["dt"], cube["dp"]),
                        "error": double_error(cube["nd"], cube["dt"], cube["dp"], doubled=False),
                        "forced": False, "cube": cube, "candidates": None,
                        "gnubg_skill": analysis.get("cube-skill"),
                    })
                if record.get("move") and analysis.get("moves"):
                    pair, base = context(player, player, record["board"])
                    rows, played_index, forced, legal = _candidates(analysis, record["move"], helpers.move_text, pair)
                    best_index = max(range(len(rows)), key=lambda i: rows[i]["equity"])
                    decisions.append({
                        **base, "move_no": move_no, "kind": "checker", "dice": record.get("dice"),
                        "action": rows[played_index]["move"], "best": rows[best_index]["move"],
                        "error": checker_error(rows, played_index), "forced": forced,
                        "candidates": rows, "played_index": played_index, "cube": None, "legal": legal,
                        "gnubg_skill": analysis.get("skill"),
                    })
            elif action == "double":
                _, base = context(player, player, record["board"])
                cube = cube_equities(analysis, player) if "nd-cubeful-eq" in analysis else None
                last_double = {"base": base, "cube": cube}
                if cube:
                    decisions.append({
                        **base, "move_no": move_no, "kind": "cube", "dice": None, "action": "Double",
                        "best": best_cube_action(cube["nd"], cube["dt"], cube["dp"]),
                        "error": double_error(cube["nd"], cube["dt"], cube["dp"], doubled=True),
                        "forced": False, "cube": cube, "candidates": None,
                        "gnubg_skill": analysis.get("skill"),
                    })
            else:
                took = action == "take"
                if last_double and last_double["cube"]:
                    cube = last_double["cube"]
                    decisions.append({
                        **last_double["base"], "player": player, "move_no": move_no, "kind": "take", "dice": None,
                        "action": "Take" if took else "Pass", "best": "Take" if cube["dt"] <= cube["dp"] else "Pass",
                        "error": take_error(cube["dt"], cube["dp"], took), "forced": False,
                        "cube": cube, "candidates": None, "gnubg_skill": analysis.get("skill"),
                    })
                if took:
                    cube_value *= 2
                    cube_owner = player
                last_double = None

    return {
        "match": {
            "match_length": match_length,
            "player1": info.get("X", {}).get("name"),
            "player2": info.get("O", {}).get("name"),
        },
        "games": games,
        "decisions": decisions,
    }
