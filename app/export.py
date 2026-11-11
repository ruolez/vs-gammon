import csv
import io
import re
import uuid
import zipfile

from app.analysis import classify
from app.position import seat_decider
from app.xgp.thumbnail import render_thumbnail
from app.xgp.writer import build_xgp

XGP_DECISION = {"checker": "checker", "cube": "double", "take": "take"}


def _safe(text):
    return re.sub(r"[^A-Za-z0-9.-]+", "_", str(text)).strip("_") or "x"


def export_filename(decision, error_class):
    player_name = decision["player1"] if decision["player"] == 1 else decision["player2"]
    parts = [
        f"{_safe(decision['player1'])}-vs-{_safe(decision['player2'])}",
        _safe(decision.get("event_date") or "undated"),
        f"g{decision['game_no']}",
        f"m{decision['move_no']}",
        _safe(player_name),
        decision["kind"],
        error_class or "ok",
    ]
    return "_".join(parts) + ".xgp"


def spot_from_decision(decision, saved_at, guid, thumbnail):
    return {
        "player1": decision["player1"],
        "player2": decision["player2"],
        "match_length": decision["match_length"],
        "score1": decision["score1"],
        "score2": decision["score2"],
        "crawford_game": bool(decision["crawford_game"]),
        "on_roll": decision["on_roll"],
        "board": decision["board"],
        "cube_value": decision["cube_value"],
        "cube_owner": decision["cube_owner"],
        "decision": XGP_DECISION[decision["kind"]],
        "dice": tuple(decision["dice"]) if decision["dice"] else None,
        "guid": guid,
        "saved_at": saved_at,
        "thumbnail": thumbnail,
    }


def _unique(name, used):
    candidate, n = name, 1
    while candidate in used:
        n += 1
        candidate = f"{name[:-4]}-{n}.xgp"
    used.add(candidate)
    return candidate


def build_export_zip(decisions, thresholds, saved_at):
    buffer = io.BytesIO()
    index = io.StringIO()
    writer = csv.writer(index)
    writer.writerow(["file", "match", "game", "move", "player", "kind", "played", "best", "error", "class", "xgid"])
    used = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for decision in decisions:
            error_class = classify(decision["error"], thresholds)
            name = _unique(export_filename(decision, error_class), used)
            seated = seat_decider(decision)
            spot = spot_from_decision(seated, saved_at, uuid.uuid4().bytes_le, render_thumbnail(seated["board"]))
            archive.writestr(name, build_xgp(spot))
            player_name = decision["player1"] if decision["player"] == 1 else decision["player2"]
            writer.writerow([
                name, f"{decision['player1']} vs {decision['player2']}", decision["game_no"], decision["move_no"],
                player_name, decision["kind"], decision["action"], decision["best"], f"{decision['error']:.3f}",
                error_class or "", decision.get("xgid", ""),
            ])
        archive.writestr("index.csv", index.getvalue())
    return buffer.getvalue()
