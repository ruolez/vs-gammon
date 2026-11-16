"""Reads a backgammon board from a screenshot (BackgammonGalaxy, any board theme).

No colour is assumed: the playing fields are two similar rectangles of one colour (the felt), the frame is what
surrounds them, the points' colours are read at their bases and the checkers' colours from the discs on the points.
The point width follows from the fields; checkers are counted outward from each point's edge, on the bar and in the
trays, and dice are found by shape. Returns a reading as described in app/live/tracker.py, or
{"found": False, "why": ...}."""
from collections import Counter

from PIL import Image, ImageChops

MAX_WIDTH = 1800
SLOTS = 5
TOLERANCE = 24
CHECKER_TOLERANCE = 40
PIP_CONTRAST = 60
FELT_CANDIDATES = 5
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


def _distance(c, ref):
    return max(abs(c[0] - ref[0]), abs(c[1] - ref[1]), abs(c[2] - ref[2]))


def _near(c, ref, tol=TOLERANCE):
    return _distance(c, ref) <= tol


def _luminance(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _runs(values, threshold):
    runs, start = [], None
    for i, v in enumerate(list(values) + [0]):
        if v > threshold and start is None:
            start = i
        elif v <= threshold and start is not None:
            runs.append((start, i - 1))
            start = None
    return runs


def _clusters(colours, tol=TOLERANCE):
    """Colours grouped by nearness, biggest group first: [(mean colour, count)]."""
    groups = []
    for c in colours:
        group = next((g for g in groups if _near(c, g["mean"], tol)), None)
        if group is None:
            groups.append({"sum": list(c), "count": 1, "mean": tuple(c)})
            continue
        group["count"] += 1
        group["sum"] = [s + v for s, v in zip(group["sum"], c)]
        group["mean"] = tuple(round(s / group["count"]) for s in group["sum"])
    return [(g["mean"], g["count"]) for g in sorted(groups, key=lambda g: -g["count"])]


def _mask(image, colour, tol=TOLERANCE):
    """An L image, 255 where the pixel is within tol of colour on every channel."""
    diff = ImageChops.difference(image, Image.new("RGB", image.size, colour))
    r, g, b = (band.point(lambda v: 255 if v <= tol else 0) for band in diff.split())
    return ImageChops.darker(ImageChops.darker(r, g), b)


def felt_candidates(image):
    """The page's most common colours, darkest left out (no board theme has a near-black felt)."""
    small = image.resize((max(1, image.width // 6), max(1, image.height // 6)), Image.NEAREST)
    picked = []
    for _, colour in sorted(small.getcolors(small.width * small.height), reverse=True):
        if max(colour) < 50 or any(_near(colour, p) for p in picked):
            continue
        picked.append(colour)
        if len(picked) == FELT_CANDIDATES:
            break
    return picked


class Board:
    def __init__(self, image, known=None):
        self.image = image
        self.px = image.load()
        self.w, self.h = image.size
        self.known = {shade: tuple(colour) for shade, colour in (known or {}).items() if colour}
        self.dark, self.light = self.known.get("dark", BLACK), self.known.get("light", WHITE)
        self.learned = {}
        self.others = []
        self.shades = {}

    def find(self):
        return any(self.find_fields(felt) for felt in felt_candidates(self.image))

    def find_fields(self, felt):
        """The two playing fields: rough columns of felt first, then their exact edges along the rows through the
        middle of the board, where the felt runs from edge to edge (stacks of checkers hide it nearer the frame)."""
        w, h = self.w, self.h
        mask = _mask(self.image, felt)
        columns = list(mask.resize((w, 1), Image.BOX).tobytes())
        rough = sorted(_runs(columns, 255 * 0.04), key=lambda r: r[0] - r[1])[:2]
        if len(rough) < 2:
            return False
        rough.sort()
        felt_at = mask.load()
        profile = mask.crop((rough[0][0], 0, rough[0][1] + 1, h)).resize((1, h), Image.BOX).tobytes()
        felt_rows = [y for y, v in enumerate(profile) if v > 255 * 0.02]
        if not felt_rows:
            return False
        mid = (felt_rows[0] + felt_rows[-1]) // 2
        span = max(4, (felt_rows[-1] - felt_rows[0]) // 12)
        edges = {}
        for y in range(max(0, mid - span), min(h, mid + span + 1), 2):
            runs = [r for r in _runs([felt_at[x, y] for x in range(w)], 0) if r[1] - r[0] > w * 0.03]
            for run in runs:
                field = min(range(2), key=lambda i: abs((run[0] + run[1]) / 2 - sum(rough[i]) / 2))
                low, high = edges.get(field, (run[0], run[1]))
                edges[field] = (min(low, run[0]), max(high, run[1]))
        if len(edges) < 2:
            return False
        left, right = edges[0], edges[1]
        widths = (left[1] - left[0] + 1, right[1] - right[0] + 1)
        gap = right[0] - left[1]
        if not (0.85 < widths[0] / widths[1] < 1.18 and 0.08 * widths[0] < gap < 0.5 * widths[0]):
            return False
        bar_x = left[1] + max(2, int(gap * 0.15))
        frame = Counter(self.px[bar_x, y] for y in felt_rows).most_common(1)[0][0]
        tops, bottoms = [], []
        for field, width in zip((left, right), widths):
            for index in range(6):
                x = int(field[0] + (index + 0.5) * width / 6)
                top = mid
                while top > 0 and not _near(self.px[x, top - 1], frame, 12):
                    top -= 1
                bottom = mid
                while bottom < h - 1 and not _near(self.px[x, bottom + 1], frame, 12):
                    bottom += 1
                tops.append(top)
                bottoms.append(bottom)
        # Buttons and dice in the middle of a field can end a single column's walk early: take the median column.
        top, bottom = sorted(tops)[6], sorted(bottoms)[6]
        if not 1.2 < (bottom - top + 1) / widths[0] < 2.6:
            return False
        self.left, self.right, self.top, self.bottom = left, right, top, bottom
        self.felt, self.frame = felt, frame
        self.pw = (widths[0] + widths[1]) / 12
        self.learn_colours()
        return True

    def learn_colours(self):
        """Point colours from the corners of each point's base (a checker there is round and leaves them free), checker
        colours from the first disc on each point, whatever is not felt or point. Dark is the darker checker colour.
        When only one colour shows (one side has borne everything off) it is matched to the colours an earlier frame
        learned, else told apart by being darker or lighter than the felt."""
        pw = self.pw
        bases, discs = [], []
        for point in range(1, 25):
            x = self.point_center_x(point)
            base_y = self.top + pw * 0.08 if point > 12 else self.bottom - pw * 0.08
            bases += [self.px[int(x + dx * pw), int(base_y)] for dx in (-0.38, 0.38)]
            disc = self.uniform(x, self.top + pw / 2 if point > 12 else self.bottom - pw / 2, pw / 2)
            if disc:
                discs.append(disc)
        points = [colour for colour, _ in _clusters(bases)[:2]]
        self.others = [self.felt, self.frame] + points
        checkers = [c for c, _ in _clusters([d for d in discs if not any(_near(d, o, 30) for o in self.others)])[:2]]
        if len(checkers) == 2:
            self.learned = dict(zip(("dark", "light"), sorted(checkers, key=_luminance)))
        elif len(checkers) == 1:
            colour = checkers[0]
            if self.known:
                shade = min(self.known, key=lambda k: _distance(colour, self.known[k]))
            else:
                shade = "dark" if _luminance(colour) < _luminance(self.felt) else "light"
            self.learned = {shade: colour}
        self.dark = self.learned.get("dark", self.dark)
        self.light = self.learned.get("light", self.light)
        self.shades = {}

    def shade(self, c):
        """'dark' or 'light' for checker colours, None for anything else."""
        known = self.shades.get(c, False)
        if known is not False:
            return known
        best, best_distance = None, None
        for name, ref in (("dark", self.dark), ("light", self.light)) + tuple((None, o) for o in self.others):
            d = _distance(c, ref)
            if best_distance is None or d < best_distance:
                best, best_distance = name, d
        result = best if best and best_distance <= CHECKER_TOLERANCE else None
        self.shades[c] = result
        return result

    def disc_samples(self, cx, cy, radius):
        r = radius * 0.55
        points = [(0, 0), (r, 0), (-r, 0), (0, r), (0, -r), (r * 0.7, r * 0.7), (-r * 0.7, r * 0.7), (r * 0.7, -r * 0.7), (-r * 0.7, -r * 0.7)]
        samples = []
        for dx, dy in points:
            x, y = int(round(cx + dx)), int(round(cy + dy))
            if not (0 <= x < self.w and 0 <= y < self.h):
                return None
            samples.append(self.px[x, y])
        return samples

    def uniform(self, cx, cy, radius):
        """The colour of a small disc when every sample is close to it, else None."""
        samples = self.disc_samples(cx, cy, radius)
        if not samples or any(not _near(s, samples[0], 20) for s in samples):
            return None
        return samples[0]

    def disc(self, cx, cy, radius):
        """The shade every sample of a small disc agrees on, or None."""
        samples = self.disc_samples(cx, cy, radius)
        if not samples:
            return None
        shades = {self.shade(s) for s in samples}
        return shades.pop() if len(shades) == 1 else None

    def point_center_x(self, point):
        field, index = (self.right, 6 - point) if point <= 6 else (self.left, 12 - point) if point <= 12 \
            else (self.left, point - 13) if point <= 18 else (self.right, point - 19)
        return field[0] + (index + 0.5) * self.pw

    def stack(self, point):
        x = self.point_center_x(point)
        shade, count = None, 0
        for slot in range(SLOTS):
            y = self.top + (slot + 0.5) * self.pw if point > 12 else self.bottom - (slot + 0.5) * self.pw
            seen = self.disc(x, y, self.pw / 2)
            if not seen or (shade and seen != shade):
                break
            shade, count = seen, count + 1
        return shade, count

    def column_pieces(self, x, y0, y1, pitch):
        """Checkers of each shade lined up in a column. Hits a little apart belong to one group (between touching
        checkers the sample disc briefly straddles both); a group's length tells how many checkers it holds."""
        groups = {"dark": [], "light": []}
        for y in range(int(y0), int(y1) + 1):
            seen = self.disc(x, y, pitch / 2)
            if not seen:
                continue
            spans = groups[seen]
            if spans and y - spans[-1][1] <= pitch * 0.35:
                spans[-1][1] = y
            else:
                spans.append([y, y])
        return {shade: sum(max(1, int(round((end - start + pitch * 0.55) / pitch))) for start, end in spans)
                for shade, spans in groups.items()}

    def bar(self):
        x = (self.left[1] + self.right[0]) / 2
        return self.column_pieces(x, self.top, self.bottom, self.pw)

    def trays(self):
        """Borne-off checkers as slabs in the trays right of the board: the stretches of the column that are not frame
        and at least a point and a half long (buttons that some layouts put between the trays are shorter). A tray can
        be a shade off the frame, hence the tight match."""
        x = int(self.right[1] + self.pw * 0.75)
        if x >= self.w:
            return None
        counts = {"dark": 0, "light": 0}
        for start, end in _runs([0 if _near(self.px[x, y], self.frame, 4) else 1 for y in range(self.top, self.bottom + 1)], 0):
            if end - start + 1 >= self.pw * 1.5:
                for shade, count in self.slabs(x, self.top + start, self.top + end, self.pw * 0.3).items():
                    counts[shade] += count
        return counts

    def slabs(self, x, y0, y1, pitch):
        counts = {"dark": 0, "light": 0}
        y, run_shade, run = int(y0), None, 0
        while y <= y1:
            shade = self.shade(self.px[int(x), y])
            if shade == run_shade and shade:
                run += 1
            else:
                if run_shade:
                    counts[run_shade] += max(1, int(round(run / pitch)))
                run_shade, run = shade, 1
            y += 1
        if run_shade:
            counts[run_shade] += max(1, int(round(run / pitch)))
        return counts

    def dice(self):
        found = []
        band_top = int(self.top + (self.bottom - self.top) * 0.36)
        band_bottom = int(self.top + (self.bottom - self.top) * 0.64)
        for side, field in (("top", self.left), ("bottom", self.right)):
            for body in ("light", "dark"):
                for box in self.blobs(field[0], field[1], band_top, band_bottom, body):
                    value = self.die_value(box, body)
                    if value:
                        found.append((side, box[0], value))
        if not found:
            return None
        sides = {s for s, _, _ in found}
        if len(sides) != 1:
            return None
        values = [v for _, _, v in sorted(found)]
        return {"side": sides.pop(), "values": values[:2]} if len(values) >= 2 else None

    def blobs(self, x0, x1, y0, y1, shade):
        """Square, nearly filled blobs of one shade about a die's size: (left, top, right, bottom)."""
        seen = set()
        boxes = []
        px = self.px
        for y in range(y0, y1, 2):
            for x in range(x0, x1, 2):
                if (x, y) in seen or self.shade(px[x, y]) != shade:
                    continue
                stack = [(x, y)]
                seen.add((x, y))
                left, top, right, bottom = x, y, x, y
                while stack:
                    cx, cy = stack.pop()
                    left, right, top, bottom = min(left, cx), max(right, cx), min(top, cy), max(bottom, cy)
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if x0 <= nx <= x1 and y0 - self.pw <= ny <= y1 + self.pw and (nx, ny) not in seen \
                                and self.shade(px[nx, ny]) == shade:
                            seen.add((nx, ny))
                            stack.append((nx, ny))
                width, height = right - left + 1, bottom - top + 1
                if 0.5 * self.pw < width < 1.1 * self.pw and 0.8 < width / height < 1.25 \
                        and self.square((left, top, right, bottom)):
                    boxes.append((left, top, right, bottom))
        return boxes

    def square(self, box):
        """A die fills its box with body and pips; a checker (a circle) leaves felt or point in the corners, a fifth
        of the box. Pips can sit close to the corners, so single corner samples won't do."""
        left, top, right, bottom = box
        pixels = [self.px[x, y] for y in range(top, bottom + 1) for x in range(left, right + 1)]
        background = sum(1 for c in pixels if any(_near(c, o) for o in self.others))
        return background < len(pixels) * 0.08

    def die_value(self, box, body):
        """Pips are spots that stand out from the die's colour (some themes fade the pips of a die already played);
        felt showing at a rounded corner is not a pip."""
        left, top, right, bottom = box
        body_colour = self.dark if body == "dark" else self.light
        inset = max(1, (right - left + 1) // 12)
        x0, x1, y0, y1 = left + inset, right - inset, top + inset, bottom - inset

        def is_pip(c):
            return _distance(c, body_colour) > PIP_CONTRAST and not _near(c, self.felt)

        spots, seen = 0, set()
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if (x, y) in seen or not is_pip(self.px[x, y]):
                    continue
                spots += 1
                stack = [(x, y)]
                seen.add((x, y))
                while stack:
                    cx, cy = stack.pop()
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if x0 <= nx <= x1 and y0 <= ny <= y1 and (nx, ny) not in seen and is_pip(self.px[nx, ny]):
                            seen.add((nx, ny))
                            stack.append((nx, ny))
        return spots if 1 <= spots <= 6 else None


def read_board(image, known=None):
    """known: checker colours an earlier frame learned ({"dark", "light"}), for a frame that shows only one."""
    image = image.convert("RGB")
    if image.width > MAX_WIDTH:
        image = image.resize((MAX_WIDTH, round(image.height * MAX_WIDTH / image.width)), Image.BILINEAR)
    board = Board(image, known)
    if not board.find():
        return {"found": False, "why": "no board"}
    reading = {"found": True, "dark": [0] * 25, "light": [0] * 25, "capped": [False] * 25}
    for point in range(1, 25):
        shade, count = board.stack(point)
        if shade:
            reading[shade][point] = count
            reading["capped"][point] = count == SLOTS
    bar = board.bar()
    reading["bar_dark"], reading["bar_light"] = bar["dark"], bar["light"]
    trays = board.trays()
    for shade in ("dark", "light"):
        reading[f"off_{shade}"] = trays[shade] if trays else None
    reading["dice"] = board.dice()
    reading["geometry"] = {"left": board.left, "right": board.right, "top": board.top, "bottom": board.bottom,
                           "point": round(board.pw, 2), "width": board.w, "height": board.h}
    reading["checkers"] = board.learned
    return reading
