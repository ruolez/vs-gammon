import os
import random
import unittest

from app.live.reader import read_board
from app.live.replay import START, screens
from app.live.transcript import parse_mat
from tests.board_image import draw_board
from tests.test_live_tracker import reading_for

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "galaxy_3pt.mat")
FIELDS = ("dark", "light", "capped", "bar_dark", "bar_light", "off_dark", "off_light", "dice")


def comparable(reading):
    return {k: reading.get(k) for k in FIELDS}


def sample_screens(count, seed=11):
    with open(FIXTURE) as f:
        header, games = parse_mat(f.read())
    shown = screens(games, header["match_length"])
    return random.Random(seed).sample(shown, count)


class ReadBoard(unittest.TestCase):
    def test_reads_back_screens_of_a_real_match(self):
        wrong = []
        for screen in sample_screens(40):
            image = draw_board(screen["frame"], dice=screen["dice"])
            if comparable(read_board(image)) != comparable(reading_for(screen["frame"], screen["dice"])):
                wrong.append(screen)
        self.assertEqual(len(wrong), 0)

    def test_light_checkers_at_the_bottom_and_dark_dice(self):
        screen = next(s for s in sample_screens(80, seed=4) if s["dice"])
        image = draw_board(screen["frame"], bottom="light", dice=screen["dice"], dice_body="dark")
        self.assertEqual(comparable(read_board(image)), comparable(reading_for(screen["frame"], screen["dice"], bottom="light")))

    def test_a_smaller_board_reads_the_same(self):
        screen = next(s for s in sample_screens(80, seed=5) if s["dice"])
        image = draw_board(screen["frame"], dice=screen["dice"], pw=22, page=(1000, 640), origin=(500, 120))
        self.assertEqual(comparable(read_board(image)), comparable(reading_for(screen["frame"], screen["dice"])))

    def test_a_page_without_a_board(self):
        from PIL import Image
        self.assertEqual(read_board(Image.new("RGB", (800, 500), (250, 250, 250))), {"found": False, "why": "no board"})

    def test_starting_position(self):
        self.assertEqual(comparable(read_board(draw_board(START))), comparable(reading_for(START)))
