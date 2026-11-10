import struct

RECORD_SIZE = 2560

HEADER_MATCH = 0
HEADER_GAME = 1
CUBE = 2
MOVE = 3
FOOTER_GAME = 4
FOOTER_MATCH = 5

NOT_ANALYSED = -1000.0

FIELDS = {
    HEADER_MATCH: {
        "s_player1": (9, "short41"),
        "s_player2": (50, "short41"),
        "match_length": (92, "<i"),
        "crawford": (100, "?"),
        "jacoby": (101, "?"),
        "beaver": (102, "?"),
        "date": (128, "<d"),
        "game_id": (268, "<i"),
        "version": (552, "<i"),
        "cube_limit": (612, "<i"),
        "player1": (880, "wide129"),
        "player2": (1138, "wide129"),
    },
    HEADER_GAME: {
        "score1": (12, "<i"),
        "score2": (16, "<i"),
        "crawford_apply": (20, "?"),
        "game_number": (48, "<i"),
        "in_progress": (52, "?"),
    },
    CUBE: {
        "active": (12, "<i"),
        "double": (16, "<i"),
        "take": (20, "<i"),
        "beaver_r": (24, "<i"),
        "raccoon_r": (28, "<i"),
        "cube_b": (32, "<i"),
        "position": (36, "board"),
        "an_pos": (64, "board"),
        "an_level": (92, "<i"),
        "an_score": (96, "<2i"),
        "an_cube": (104, "<i"),
        "an_cube_pos": (108, "<i"),
        "an_crawford": (116, "<h"),
        "an_flag_double": (120, "<h"),
        "an_is_beaver": (122, "<h"),
        "an_eval": (124, "<7f"),
        "an_equ_no_double": (152, "<f"),
        "an_equ_double": (156, "<f"),
        "an_equ_drop": (160, "<f"),
        "an_level_request": (164, "<h"),
        "an_double_choice3": (166, "<h"),
        "an_eval_double": (168, "<7f"),
        "err_cube": (200, "<d"),
        "dice_rolled": (208, "short3"),
        "err_take": (216, "<d"),
        "rollout_index_d": (224, "<i"),
        "comp_choice_d": (228, "<i"),
        "analyze_c": (232, "<i"),
        "err_beaver": (240, "<d"),
        "err_raccoon": (248, "<d"),
        "analyze_cr": (256, "<i"),
        "is_valid": (260, "<i"),
        "tutor_cube": (264, "<b"),
        "tutor_take": (265, "<b"),
        "err_tutor_cube": (272, "<d"),
        "err_tutor_take": (280, "<d"),
        "flagged": (288, "?"),
        "comment_cube": (292, "<i"),
    },
    MOVE: {
        "position_i": (9, "board"),
        "position_end": (35, "board"),
        "active": (64, "<i"),
        "moves": (68, "<8i"),
        "dice": (100, "<2i"),
        "cube_a": (108, "<i"),
        "n_move_eval": (120, "<i"),
        "an_pos": (124, "board"),
        "an_dice": (152, "<2i"),
        "an_level": (160, "<i"),
        "an_score": (164, "<2i"),
        "an_cube": (172, "<i"),
        "an_cube_pos": (176, "<i"),
        "an_crawford": (180, "<i"),
        "an_jacoby": (184, "<i"),
        "an_n_moves": (188, "<i"),
        "played": (2308, "?"),
        "err_move": (2312, "<d"),
        "err_luck": (2320, "<d"),
        "comp_choice": (2328, "<i"),
        "init_eq": (2336, "<d"),
        "analyze_m": (2472, "<i"),
        "analyze_l": (2476, "<i"),
        "invalid_m": (2480, "<i"),
        "err_tutor_move": (2512, "<d"),
        "flagged": (2520, "?"),
        "comment_move": (2524, "<i"),
    },
}


def record_type(record):
    return record[8]


def split_records(data):
    if len(data) % RECORD_SIZE:
        raise ValueError("XG game file length is not a multiple of the record size")
    return [bytearray(data[i : i + RECORD_SIZE]) for i in range(0, len(data), RECORD_SIZE)]


def _field(record, name):
    try:
        return FIELDS[record_type(record)][name]
    except KeyError:
        raise KeyError(f"record type {record_type(record)} has no field {name}") from None


def get_field(record, name):
    offset, kind = _field(record, name)
    if kind == "board":
        return list(struct.unpack_from("<26b", record, offset))
    if kind.startswith("short"):
        length = record[offset]
        return bytes(record[offset + 1 : offset + 1 + length]).decode("latin-1")
    if kind.startswith("wide"):
        chars = int(kind[4:])
        raw = bytes(record[offset : offset + chars * 2]).decode("utf-16-le")
        return raw.split("\x00", 1)[0]
    values = struct.unpack_from(kind, record, offset)
    return list(values) if len(values) > 1 else values[0]


def set_field(record, name, value):
    offset, kind = _field(record, name)
    if kind == "board":
        struct.pack_into("<26b", record, offset, *value)
    elif kind.startswith("short"):
        capacity = int(kind[5:]) - 1
        encoded = value.encode("latin-1", "replace")[:capacity]
        record[offset] = len(encoded)
        record[offset + 1 : offset + 1 + capacity] = encoded + bytes(capacity - len(encoded))
    elif kind.startswith("wide"):
        chars = int(kind[4:])
        encoded = value.encode("utf-16-le")[: (chars - 1) * 2]
        record[offset : offset + chars * 2] = encoded + bytes(chars * 2 - len(encoded))
    elif isinstance(value, (list, tuple)):
        struct.pack_into(kind, record, offset, *value)
    else:
        struct.pack_into(kind, record, offset, value)
