import gnubg  # only importable inside gnubg -p


class GnubgHelpers:
    def board_pair(self, position_id):
        return gnubg.positionfromid(position_id)

    def move_text(self, move, board_pair):
        return gnubg.movetupletostring(tuple(tuple(step) for step in move), board_pair)

    def mwc_to_emg(self, mwc, cube, owner, on_roll, match_length, score, crawford):
        info = gnubg.cubeinfo(cube, owner, on_roll, match_length, tuple(score), 1 if crawford else 0, 0)
        return gnubg.mwc2eq(mwc, info)
