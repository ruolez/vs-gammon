"""Board readings the tracker could not explain, kept with the frame they came from so the reader can be checked
against real game pages. Only the newest few are kept."""
import datetime
import json
import os

from PIL import Image

from app.live.reader import MAX_WIDTH

FOLDER = "live-frames"
KEEP = 30


def keep_unexplained(data_dir, image, reading, keep=KEEP):
    folder = os.path.join(data_dir, FOLDER)
    os.makedirs(folder, exist_ok=True)
    picture = image.convert("RGB")
    if picture.width > MAX_WIDTH:
        picture = picture.resize((MAX_WIDTH, round(picture.height * MAX_WIDTH / picture.width)), Image.BILINEAR)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    picture.save(os.path.join(folder, stamp + ".png"))
    with open(os.path.join(folder, stamp + ".json"), "w") as f:
        json.dump(reading, f)
    stamps = sorted({os.path.splitext(name)[0] for name in os.listdir(folder)})
    for old in stamps[:-keep]:
        for ext in (".png", ".json"):
            try:
                os.remove(os.path.join(folder, old + ext))
            except FileNotFoundError:
                pass
