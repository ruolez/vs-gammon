import datetime
import unittest
from zoneinfo import ZoneInfo

from app import db


class LocalZone(unittest.TestCase):
    def test_a_named_zone_is_used_when_tz_is_set(self):
        self.assertEqual(db.local_zone("America/Chicago"), ZoneInfo("America/Chicago"))

    def test_without_tz_the_computers_own_zone_is_used(self):
        self.assertEqual(db.local_zone(None), None)

    def test_timestamps_without_tz_carry_the_computers_offset(self):
        stamp = datetime.datetime.fromisoformat(db.local_now(None).isoformat())
        self.assertEqual(stamp.utcoffset(), datetime.datetime.now().astimezone().utcoffset())


if __name__ == "__main__":
    unittest.main()
