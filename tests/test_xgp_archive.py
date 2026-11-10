import os
import unittest

from app.xgp.archive import build_rich_header, pack_archive, read_xg_file

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load_sample():
    with open(os.path.join(FIXTURES, "sample_cube.xgp"), "rb") as f:
        return f.read()


class ReadXgFile(unittest.TestCase):
    def test_reads_sample_header_and_members(self):
        parsed = read_xg_file(load_sample())
        self.assertEqual(
            (parsed["save_name"], [(n, len(d)) for n, d in parsed["files"]]),
            ("Position: 3 point match 0-0", [("temp.xg", 7680), ("temp.xgi", 5120)]),
        )

    def test_rejects_corrupt_archive(self):
        data = bytearray(load_sample())
        data[-100] ^= 0xFF
        with self.assertRaises(ValueError):
            read_xg_file(bytes(data))


class RebuildXgFile(unittest.TestCase):
    def test_rebuild_of_sample_is_byte_identical(self):
        original = load_sample()
        parsed = read_xg_file(original)
        rebuilt = build_rich_header(
            parsed["guid"], parsed["save_name"], parsed["thumbnail"]
        ) + pack_archive(parsed["files"])
        self.assertEqual(rebuilt, original)

    def test_round_trip_of_new_content(self):
        files = [("temp.xg", bytes(range(256)) * 10), ("temp.xgi", b"\x01" * 5120)]
        data = build_rich_header(b"G" * 16, "Position: 7 point match 2-4", b"\xff\xd8thumb") + pack_archive(files)
        parsed = read_xg_file(data)
        self.assertEqual(
            (parsed["guid"], parsed["save_name"], parsed["thumbnail"], parsed["files"]),
            (b"G" * 16, "Position: 7 point match 2-4", b"\xff\xd8thumb", files),
        )


if __name__ == "__main__":
    unittest.main()
