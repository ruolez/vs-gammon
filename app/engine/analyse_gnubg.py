import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.environ.get("GA_APP_ROOT", "/srv"))

import gnubg  # noqa: E402  (only importable inside gnubg -p)

from app.engine.walk import walk_match  # noqa: E402


class GnubgHelpers:
    def board_pair(self, position_id):
        return gnubg.positionfromid(position_id)

    def move_text(self, move, board_pair):
        return gnubg.movetupletostring(tuple(tuple(step) for step in move), board_pair)

    def mwc_to_emg(self, mwc, cube, owner, on_roll, match_length, score, crawford):
        info = gnubg.cubeinfo(cube, owner, on_roll, match_length, tuple(score), 1 if crawford else 0, 0)
        return gnubg.mwc2eq(mwc, info)


def analyse(path, plies, threads):
    for command in (
        "set confirm new off",
        f"set threads {threads}",
        f"set analysis chequerplay evaluation plies {plies}",
        f"set analysis cubedecision evaluation plies {plies}",
        "set analysis chequerplay evaluation cubeful on",
        "set analysis cubedecision evaluation cubeful on",
        "set analysis luck off",
        f'import mat "{path}"',
    ):
        gnubg.command(command)
    match = gnubg.match(analysis=0, boards=0, statistics=0, verbose=0)
    if not match or not match.get("games"):
        raise ValueError("gnubg could not import any games from this file")
    started = time.time()
    gnubg.command("analyse match")
    seconds = time.time() - started
    match = gnubg.match(analysis=1, boards=1, statistics=0, verbose=1)
    result = walk_match(match, GnubgHelpers())
    result["engine"] = {"plies": plies, "threads": threads, "seconds": round(seconds, 2)}
    return result


def main():
    output = os.environ["GA_OUTPUT"]
    try:
        result = analyse(os.environ["GA_INPUT"], int(os.environ.get("GA_PLIES", "2")), int(os.environ.get("GA_THREADS", "4")))
    except Exception as exc:
        result = {"error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()}
    with open(output + ".tmp", "w") as f:
        json.dump(result, f)
    os.replace(output + ".tmp", output)


main()
