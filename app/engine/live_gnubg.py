"""Runs inside gnubg (-p) for as long as live analysis is on. Reads one JSON request per line on stdin:
{"mat": path, "from_record": n, "plies": p, "threads": t}; imports the transcript so far, analyses the records of the
last game from `from_record` on, and prints one line "VSG-LIVE <json>" with that game's new decisions and luck."""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.environ.get("GA_APP_ROOT", "/srv"))

import gnubg  # noqa: E402  (only importable inside gnubg -p)

from app.engine.gnubg_helpers import GnubgHelpers  # noqa: E402
from app.engine.walk import walk_match  # noqa: E402

ANALYSED = ("move", "double")
PREFIX = "VSG-LIVE "


def configure(plies, threads):
    for command in (
        "set confirm new off",
        f"set threads {threads}",
        f"set analysis chequerplay evaluation plies {plies}",
        f"set analysis cubedecision evaluation plies {plies}",
        "set analysis chequerplay evaluation cubeful on",
        "set analysis cubedecision evaluation cubeful on",
        "set analysis luck on",
        "set analysis luckanalysis plies 0",
    ):
        gnubg.command(command)


def go_to(game_no, record_index):
    gnubg.command("first game")
    for _ in range(game_no - 1):
        gnubg.command("next game")
    gnubg.navigate(next=record_index)


def analyse(request):
    started = time.time()
    gnubg.command(f'import mat "{request["mat"]}"')
    games = gnubg.match(analysis=0, boards=0, statistics=0, verbose=0)["games"]
    game_no = len(games)
    records = games[-1]["game"]
    start = max(0, request["from_record"])
    for index in range(start, len(records)):
        if records[index].get("action") in ANALYSED:
            go_to(game_no, index)
            gnubg.command("analyse move")
    walked = walk_match(gnubg.match(analysis=1, boards=1, statistics=0, verbose=1), GnubgHelpers(), with_records=True)
    mine = lambda items: [i for i in items if i["game_no"] == game_no and i["record_index"] >= start]
    return {"game_no": game_no, "records": len(records), "actions": [r.get("action") for r in records],
            "decisions": mine(walked["decisions"]), "luck": mine(walked.get("luck", [])),
            "seconds": round(time.time() - started, 3)}


def main():
    configured = None
    for line in sys.stdin:
        try:
            request = json.loads(line)
            wanted = (request.get("plies", 2), request.get("threads", 2))
            if wanted != configured:
                configure(*wanted)
                configured = wanted
            result = analyse(request)
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()}
        print(PREFIX + json.dumps(result), flush=True)


main()
