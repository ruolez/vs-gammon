import os
import random
import unittest

from app.live.reader import read_board
from app.live.replay import START, screens
from app.live.transcript import parse_mat
from tests.board_image import draw_board
from app.live.tracker import Tracker
from tests.test_live_tracker import as_play, fixture_games, played, reading_for, watch

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

    def test_reads_the_blue_theme(self):
        wrong = []
        for screen in sample_screens(20, seed=7):
            image = draw_board(screen["frame"], dice=screen["dice"], theme="blue")
            if comparable(read_board(image)) != comparable(reading_for(screen["frame"], screen["dice"])):
                wrong.append(screen)
        self.assertEqual(len(wrong), 0)

    def test_a_game_on_the_blue_board_is_followed_move_by_move(self):
        header, games = fixture_games()
        shown = screens(games[:1], header["match_length"])
        readings, known = [], {}
        for screen in shown:
            readings.append(read_board(draw_board(screen["frame"], dice=screen["dice"], theme="blue", buttons=True), known))
            known.update(readings[-1].get("checkers") or {})
        actions = watch(Tracker(), readings)
        self.assertEqual(played(actions), [[as_play(a) for a in games[0]["actions"] if a["kind"] == "move"]])

    def test_a_busy_middle_and_deep_stacks_by_the_bar_keep_the_fields_in_place(self):
        """The game page from a real match: buttons and a watermark across the middle, five-checker stacks on both
        points next to the bar on the right, so the felt hardly ever runs from edge to edge there."""
        frame = [0, 0, 0, 0, -2, 0, 5, 0, 3, 0, 1, 0, -4, 4, 0, 0, -1, -2, -1, -5, 0, 0, 0, 0, 1, 1]
        image = draw_board(frame, bottom="light", theme="blue", buttons=True, busy_middle=True)
        self.assertEqual(comparable(read_board(image)), comparable(reading_for(frame, None, bottom="light")))

    def test_buttons_between_the_trays_are_not_borne_off_checkers(self):
        screen = next(s for s in sample_screens(80, seed=6) if s["dice"])
        image = draw_board(screen["frame"], dice=screen["dice"], theme="blue", buttons=True)
        self.assertEqual(comparable(read_board(image)), comparable(reading_for(screen["frame"], screen["dice"])))

    def test_blue_light_checkers_at_the_bottom_with_light_dice(self):
        screen = next(s for s in sample_screens(80, seed=8) if s["dice"])
        image = draw_board(screen["frame"], bottom="light", dice=screen["dice"], dice_body="light", theme="blue")
        self.assertEqual(comparable(read_board(image)), comparable(reading_for(screen["frame"], screen["dice"], bottom="light")))

    def test_a_page_without_a_board(self):
        from PIL import Image
        self.assertEqual(read_board(Image.new("RGB", (800, 500), (250, 250, 250))), {"found": False, "why": "no board"})

    def test_starting_position(self):
        for theme in ("green", "blue"):
            with self.subTest(theme=theme):
                self.assertEqual(comparable(read_board(draw_board(START, theme=theme))), comparable(reading_for(START)))
