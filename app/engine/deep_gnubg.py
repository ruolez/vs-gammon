"""Runs inside gnubg (-p): analyses one decision of a match more deeply, either with a deeper evaluation or a
rollout, and writes the decision in the app's format. Progress lines from gnubg's rollout go to stdout."""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.environ.get("GA_APP_ROOT", "/srv"))

import gnubg  # noqa: E402  (only importable inside gnubg -p)

from app.engine.gnubg_helpers import GnubgHelpers  # noqa: E402
from app.engine.deep import evaluation_commands, progress_line, rollout_commands, rollout_steps, stops_early  # noqa: E402
from app.engine.walk import walk_match  # noqa: E402

IDENTITY = ("game_no", "move_no", "kind", "player")


def find(walked, job):
    return next((d for d in walked["decisions"] if all(d[k] == job["decision"][k] for k in IDENTITY)), None)


def go_to(game_no, record_index):
    gnubg.command("first game")
    for _ in range(game_no - 1):
        gnubg.command("next game")
    gnubg.navigate(next=record_index)


def run(job):
    for command in (
        "set confirm new off",
        f"set threads {job['threads']}",
        f"set analysis chequerplay evaluation plies {job['base_plies']}",
        f"set analysis cubedecision evaluation plies {job['base_plies']}",
        "set analysis chequerplay evaluation cubeful on",
        "set analysis cubedecision evaluation cubeful on",
        "set analysis luck off",
        f'import mat "{job["mat"]}"',
        "analyse match",
    ):
        gnubg.command(command)
    helpers = GnubgHelpers()
    target = find(walk_match(gnubg.match(analysis=1, boards=1, statistics=0, verbose=1), helpers, with_records=True), job)
    if not target:
        raise ValueError("this decision is not in the match any more; re-analyse the match")
    go_to(job["decision"]["game_no"], target["record_index"])
    settings = job["settings"]
    started = time.time()
    if job["mode"] == "eval":
        for command in evaluation_commands(settings):
            gnubg.command(command)
        gnubg.command("analyse move")
    else:
        for command in rollout_commands(settings):
            gnubg.command(command)
        checker = job["decision"]["kind"] == "checker"
        totals = [settings["trials"]] if stops_early(settings) else rollout_steps(settings["trials"])
        for total in totals:
            gnubg.command(f"set rollout trials {total}")
            if checker:
                mark_moves(job, target["record_index"])
                gnubg.command("analyse rollout move")
            else:
                gnubg.command("cmark cube set rollout")
                gnubg.command("analyse rollout cube")
            print(progress_line(total, settings["trials"]), flush=True)
    seconds = time.time() - started
    match = gnubg.match(analysis=1, boards=1, statistics=0, verbose=1)
    if job["mode"] == "rollout":
        mark_cubeful(match, settings["cubeful"])
    result = find(walk_match(match, helpers, base_plies=job["base_plies"]), job)
    if not result:
        raise ValueError("gnubg lost track of this decision")
    return {"decision": result, "seconds": round(seconds, 2)}


def mark_moves(job, record_index):
    """Marks the chosen moves for rollout. gnubg clears the marks after each rollout and re-sorts the move list,
    so the numbers are looked up again every time."""
    game = gnubg.match(analysis=1, boards=0, statistics=0, verbose=0)["games"][job["decision"]["game_no"] - 1]
    moves = [same_move(m["move"]) for m in game["game"][record_index]["analysis"]["moves"]]
    wanted = sorted({moves.index(same_move(steps)) + 1 for steps in job["moves"] if same_move(steps) in moves})
    if not wanted:
        raise ValueError("none of the chosen moves is in gnubg's move list")
    gnubg.command("cmark move clear")
    gnubg.command("cmark move set rollout " + " ".join(map(str, wanted)))


def same_move(steps):
    return tuple(sorted(tuple(step) for step in steps))


def mark_cubeful(match, cubeful):
    for game in match["games"]:
        for record in game["game"]:
            for move in (record.get("analysis") or {}).get("moves", []):
                if move.get("type") == "rollout":
                    move["cubeful"] = cubeful


def main():
    output = os.environ["GA_OUTPUT"]
    try:
        with open(os.environ["GA_JOB"]) as f:
            result = run(json.load(f))
    except Exception as exc:
        result = {"error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()}
    with open(output + ".tmp", "w") as f:
        json.dump(result, f)
    os.replace(output + ".tmp", output)


main()
