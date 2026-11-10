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
