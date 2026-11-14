"""Reads a backgammon board from a screenshot (BackgammonGalaxy's default look).

Finds the two playing fields by the felt colour, derives the point width from them, then counts checkers outward from
each point's edge, on the bar and in the trays, and finds dice by shape. Returns a reading as described in
app/live/tracker.py, or {"found": False, "why": ...}."""
from PIL import Image

MAX_WIDTH = 1800
SLOTS = 5
FELT = (74, 100, 57)
FRAME = (66, 49, 34)
TOLERANCE = 24


def _near(c, ref, tol=TOLERANCE):
    return abs(c[0] - ref[0]) <= tol and abs(c[1] - ref[1]) <= tol and abs(c[2] - ref[2]) <= tol


def _shade(c):
    """'dark' or 'light' for checker colours, None for anything else."""
    low, high = min(c), max(c)
    if high < 38:
        return "dark"
    if low > 215 and high - low < 30:
        return "light"
    return None


def _runs(values, threshold):
    runs, start = [], None
    for i, v in enumerate(values + [0]):
        if v > threshold and start is None:
            start = i
        elif v <= threshold and start is not None:
            runs.append((start, i - 1))
            start = None
    return runs


class Board:
    def __init__(self, image):
        self.image = image
        self.px = image.load()
        self.w, self.h = image.size

    def find_fields(self):
        """The two playing fields: rough columns of felt first, then their exact edges along the rows through the
        middle of the board, where the felt runs from edge to edge (stacks of checkers hide it nearer the frame)."""
        px, w, h = self.px, self.w, self.h
        step = 2
        columns = [sum(1 for y in range(0, h, step) if _near(px[x, y], FELT)) for x in range(w)]
        rough = sorted(_runs(columns, h / step * 0.04), key=lambda r: r[0] - r[1])[:2]
        if len(rough) < 2:
            return None
        middle_x = sum(sorted(rough)[0]) // 2
        felt_rows = [y for y in range(h) if _near(px[middle_x, y], FELT)]
        if not felt_rows:
            return None
        mid = (felt_rows[0] + felt_rows[-1]) // 2
        span = max(4, (felt_rows[-1] - felt_rows[0]) // 12)
        edges = {}
        for y in range(mid - span, mid + span + 1, 2):
            runs = [r for r in _runs([1 if _near(px[x, y], FELT) else 0 for x in range(w)], 0) if r[1] - r[0] > w * 0.03]
            for run in runs:
                field = min(range(2), key=lambda i: abs((run[0] + run[1]) / 2 - sum(sorted(rough)[i]) / 2))
                low, high = edges.get(field, (run[0], run[1]))
                edges[field] = (min(low, run[0]), max(high, run[1]))
        if len(edges) < 2:
            return None
        left, right = edges[0], edges[1]
        widths = (left[1] - left[0] + 1, right[1] - right[0] + 1)
        gap = right[0] - left[1]
        if not (0.85 < widths[0] / widths[1] < 1.18 and 0.08 * widths[0] < gap < 0.5 * widths[0]):
            return None
        middle_x = (left[0] + left[1]) // 2
        top = mid
        while top > 0 and not _near(px[middle_x, top - 1], FRAME, 12):
            top -= 1
        bottom = mid
        while bottom < h - 1 and not _near(px[middle_x, bottom + 1], FRAME, 12):
            bottom += 1
        self.left, self.right, self.top, self.bottom = left, right, top, bottom
        self.pw = (widths[0] + widths[1]) / 12
        return True

    def disc(self, cx, cy, radius):
        """The shade every sample of a small disc agrees on, or None."""
        r = radius * 0.55
        points = [(0, 0), (r, 0), (-r, 0), (0, r), (0, -r), (r * 0.7, r * 0.7), (-r * 0.7, r * 0.7), (r * 0.7, -r * 0.7), (-r * 0.7, -r * 0.7)]
        shades = set()
        for dx, dy in points:
            x, y = int(round(cx + dx)), int(round(cy + dy))
            if not (0 <= x < self.w and 0 <= y < self.h):
                return None
            shades.add(_shade(self.px[x, y]))
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
        """Borne-off checkers as slabs in the trays right of the board (bottom player's lower, top player's upper)."""
        x = self.right[1] + self.pw * 0.75
        if x >= self.w:
            return None
        pitch = self.pw * 0.3
        half = (self.top + self.bottom) / 2
        upper = self.slabs(x, self.top, half, pitch)
        lower = self.slabs(x, half, self.bottom, pitch)
        return upper, lower

    def slabs(self, x, y0, y1, pitch):
        counts = {"dark": 0, "light": 0}
        y, run_shade, run = int(y0), None, 0
        while y <= y1:
            shade = _shade(self.px[int(x), y])
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
        return {"side": sides.pop(), "values": values[:2] if len(values) >= 2 else None} if len(values) >= 2 else None

    def blobs(self, x0, x1, y0, y1, shade):
        """Square, nearly filled blobs of one shade about a die's size: (left, top, right, bottom)."""
        seen = set()
        boxes = []
        px = self.px
        for y in range(y0, y1, 2):
            for x in range(x0, x1, 2):
                if (x, y) in seen or _shade(px[x, y]) != shade:
                    continue
                stack, pixels = [(x, y)], 0
                seen.add((x, y))
                left, top, right, bottom = x, y, x, y
                while stack:
                    cx, cy = stack.pop()
                    pixels += 1
                    left, right, top, bottom = min(left, cx), max(right, cx), min(top, cy), max(bottom, cy)
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if x0 <= nx <= x1 and y0 - self.pw <= ny <= y1 + self.pw and (nx, ny) not in seen and _shade(px[nx, ny]) == shade:
                            seen.add((nx, ny))
                            stack.append((nx, ny))
                width, height = right - left + 1, bottom - top + 1
                if 0.5 * self.pw < width < 1.1 * self.pw and 0.8 < width / height < 1.25 \
                        and self.square_corners((left, top, right, bottom), shade):
                    boxes.append((left, top, right, bottom))
        return boxes

    def square_corners(self, box, shade):
        """Dice have filled corners; checkers (circles) don't."""
        left, top, right, bottom = box
        dx, dy = (right - left) * 0.12, (bottom - top) * 0.12
        corners = ((left + dx, top + dy), (right - dx, top + dy), (left + dx, bottom - dy), (right - dx, bottom - dy))
        return all(_shade(self.px[int(round(x)), int(round(y))]) == shade for x, y in corners)

    def die_value(self, box, body):
        """Pips are spots of the other shade inside the die (blurred edges, neither shade, are ignored)."""
        left, top, right, bottom = box
        pip = "light" if body == "dark" else "dark"
        inset = max(1, (right - left + 1) // 12)
        x0, x1, y0, y1 = left + inset, right - inset, top + inset, bottom - inset
        spots, seen = 0, set()
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if (x, y) in seen or _shade(self.px[x, y]) != pip:
                    continue
                spots += 1
                stack = [(x, y)]
                seen.add((x, y))
                while stack:
                    cx, cy = stack.pop()
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if x0 <= nx <= x1 and y0 <= ny <= y1 and (nx, ny) not in seen and _shade(self.px[nx, ny]) == pip:
                            seen.add((nx, ny))
                            stack.append((nx, ny))
        return spots if 1 <= spots <= 6 else None


def read_board(image):
    image = image.convert("RGB")
    if image.width > MAX_WIDTH:
        image = image.resize((MAX_WIDTH, round(image.height * MAX_WIDTH / image.width)), Image.BILINEAR)
    board = Board(image)
    if not board.find_fields():
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
        reading[f"off_{shade}"] = sum(tray[shade] for tray in trays) if trays else None
    reading["dice"] = board.dice()
    reading["geometry"] = {"left": board.left, "right": board.right, "top": board.top, "bottom": board.bottom,
                           "point": round(board.pw, 2), "width": board.w, "height": board.h}
    return reading
