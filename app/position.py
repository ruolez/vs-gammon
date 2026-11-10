BAR = 24


def onroll_frame(board_pair):
    opponent, player = board_pair
    frame = [0] * 26
    for point in range(1, 25):
        frame[point] = player[point - 1] - opponent[24 - point]
    frame[0] = -opponent[BAR]
    frame[25] = player[BAR]
    return frame


def flip_frame(frame):
    return [-frame[25 - i] for i in range(26)]


def player1_frame(board_pair, on_roll):
    frame = onroll_frame(board_pair)
    return frame if on_roll == 1 else flip_frame(frame)


def _xgid_char(count):
    if count > 0:
        return chr(ord("A") + count - 1)
    if count < 0:
        return chr(ord("a") - count - 1)
    return "-"


def build_xgid(frame, on_roll, dice, cube_value, cube_owner, score1, score2, match_length, crawford_game, max_cube_log=10):
    position = "".join(_xgid_char(c) for c in frame)
    cube_log = cube_value.bit_length() - 1
    owner = {0: 0, 1: 1, 2: -1}[cube_owner]
    turn = 1 if on_roll == 1 else -1
    dice_text = f"{dice[0]}{dice[1]}" if dice else "00"
    return (
        f"XGID={position}:{cube_log}:{owner}:{turn}:{dice_text}:{score1}:{score2}:"
        f"{1 if crawford_game else 0}:{match_length}:{max_cube_log}"
    )
