import io
import unittest

from PIL import Image

from app.xgp.thumbnail import HEIGHT, WIDTH, render_thumbnail
from tests.test_position import START_FRAME

CROWDED = [-2, 0, 0, 0, 0, 0, 9, 0, 0, 0, 0, 0, -11, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3]


class RenderThumbnail(unittest.TestCase):
    def test_produces_a_jpeg_of_the_xg_thumbnail_size(self):
        for board in (START_FRAME, CROWDED):
            image = Image.open(io.BytesIO(render_thumbnail(board)))
            self.assertEqual((image.format, image.size), ("JPEG", (WIDTH, HEIGHT)))


if __name__ == "__main__":
    unittest.main()
