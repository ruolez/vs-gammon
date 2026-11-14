"""What a viewer sees while a stored match is played: one screen after another, in player 1's frame
(player 1 sits at the bottom). Used by the Replay page and to test the board reader and move tracker."""
from app.live.legal import apply_step
from app.position import flip_frame

START = [0, -2, 0, 0, 0, 0, 5, 0, 3, 0, 0, 0, -5, 5, 0, 0, 0, -3, 0, -5, 0, 0, 0, 0, 2, 0]
SIDE = {1: "bottom", 2: "top"}


def play_steps(frame, player, steps):
    """Each position while `player` moves its checkers one by one, ending with the finished move."""
    onroll = frame if player == 1 else flip_frame(frame)
    seen = []
    for step in steps:
        onroll = apply_step(onroll, step)
        seen.append(onroll if player == 1 else flip_frame(onroll))
    return seen


def screens(games, match_length):
    """[{game_no, score, frame, dice: {side, values} | None, cube, action_index}] for every screen of the match.
    action_index points into the game's actions: the action this screen belongs to."""
    out = []
    for game_no, game in enumerate(games, start=1):
        frame, cube = list(START), 1

        def show(frame, dice, index):
            out.append({"game_no": game_no, "score": list(game["score"]), "match_length": match_length, "frame": list(frame),
                        "dice": dice, "cube": cube, "action_index": index})

        show(frame, None, -1)
        for index, action in enumerate(game["actions"]):
            if action["kind"] == "move":
                dice = {"side": SIDE[action["player"]], "values": list(action["dice"])}
                show(frame, dice, index)
                for position in play_steps(frame, action["player"], action["steps"]):
                    frame = position
                    show(frame, dice, index)
                show(frame, None, index)
            elif action["kind"] == "take":
                cube *= 2
                show(frame, None, index)
    return out
