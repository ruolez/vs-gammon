"""Draws a board in one of BackgammonGalaxy's looks, for testing the board reader."""
from PIL import Image, ImageDraw

THEMES = {
    "green": {"page": (3, 7, 18), "felt": (74, 100, 57), "frame": (66, 49, 34), "tray": (56, 41, 29),
              "points": ((255, 68, 34), (201, 183, 151)),
              "shades": {"dark": ((13, 13, 20), (245, 245, 245)), "light": ((255, 255, 255), (20, 20, 24))}},
    "blue": {"page": (3, 5, 19), "felt": (104, 142, 221), "frame": (5, 3, 44), "tray": (25, 32, 83),
             "points": ((134, 163, 228), (93, 125, 211)),
             "shades": {"dark": ((57, 82, 177), (237, 239, 252)), "light": ((237, 239, 252), (57, 82, 177))}},
}
BUTTON = (42, 53, 72)
PIPS = {1: [(0.5, 0.5)], 2: [(0.27, 0.27), (0.73, 0.73)], 3: [(0.25, 0.25), (0.5, 0.5), (0.75, 0.75)],
        4: [(0.27, 0.27), (0.73, 0.27), (0.27, 0.73), (0.73, 0.73)],
        5: [(0.25, 0.25), (0.75, 0.25), (0.5, 0.5), (0.25, 0.75), (0.75, 0.75)],
        6: [(0.27, 0.22), (0.73, 0.22), (0.27, 0.5), (0.73, 0.5), (0.27, 0.78), (0.73, 0.78)]}


def draw_board(frame, bottom="dark", dice=None, pw=32, page=(1660, 955), origin=(980, 220), dice_body=None,
               theme="green", buttons=False):
    """frame: player 1 (bottom) frame. dice: {"side", "values"}. dice_body: the dice colour, else the roller's.
    buttons: icon buttons between the trays, as the blue game page has them."""
    colours = THEMES[theme]
    FELT, FRAME, TRAY, POINTS, SHADES = (colours[k] for k in ("felt", "frame", "tray", "points", "shades"))
    top_shade = "light" if bottom == "dark" else "dark"
    image = Image.new("RGB", page, colours["page"])
    d = ImageDraw.Draw(image)
    ox, oy = origin
    field_w, bar_w, margin, tray_w = 6 * pw, int(pw * 1.3), int(pw * 2), int(pw * 1.1)
    height = 11 * pw
    left_x = ox + margin
    right_x = left_x + field_w + bar_w
    top_y, bottom_y = oy + int(pw * 0.9), oy + int(pw * 0.9) + height
    d.rounded_rectangle((ox, oy, right_x + field_w + tray_w + margin // 2, bottom_y + int(pw * 0.9)), radius=20, fill=FRAME)
    for fx in (left_x, right_x):
        d.rectangle((fx, top_y, fx + field_w - 1, bottom_y - 1), fill=FELT)
    tray_x = right_x + field_w + pw // 4
    tray_gap = int(pw * 1.8) if buttons else pw // 2
    d.rectangle((tray_x, top_y + pw, tray_x + tray_w - pw // 4, (top_y + bottom_y) // 2 - tray_gap), fill=TRAY)
    d.rectangle((tray_x, (top_y + bottom_y) // 2 + tray_gap, tray_x + tray_w - pw // 4, bottom_y - pw), fill=TRAY)
    if buttons:
        for i in range(3):
            y = (top_y + bottom_y) // 2 - int(pw * 1.6) + i * int(pw * 1.1)
            d.rounded_rectangle((tray_x, y, tray_x + tray_w - pw // 4, y + int(pw * 0.9)), radius=4, fill=BUTTON)
            d.rectangle((tray_x + pw // 4, y + pw // 4, tray_x + pw // 2, y + int(pw * 0.65)), fill=(232, 234, 240))

    def column(point):
        if point <= 6:
            return right_x + (6 - point) * pw
        if point <= 12:
            return left_x + (12 - point) * pw
        if point <= 18:
            return left_x + (point - 13) * pw
        return right_x + (point - 19) * pw

    point_h = int(height * 0.37)
    for point in range(1, 25):
        x = column(point)
        colour = POINTS[point % 2]
        if point > 12:
            d.polygon([(x, top_y), (x + pw - 1, top_y), (x + pw / 2, top_y + point_h)], fill=colour)
        else:
            d.polygon([(x, bottom_y - 1), (x + pw - 1, bottom_y - 1), (x + pw / 2, bottom_y - point_h)], fill=colour)

    def checker(cx, cy, shade):
        r = pw / 2 - 0.5
        fill = SHADES[shade][0]
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill, outline=tuple(max(0, c - 25) for c in fill))

    for point in range(1, 25):
        count = frame[point]
        if not count:
            continue
        shade = bottom if count > 0 else top_shade
        for slot in range(min(abs(count), 5)):
            cy = top_y + (slot + 0.5) * pw if point > 12 else bottom_y - (slot + 0.5) * pw
            checker(column(point) + pw / 2, cy, shade)
    bar_x = left_x + field_w + bar_w / 2
    middle = (top_y + bottom_y) / 2
    for slot in range(frame[25]):
        checker(bar_x, middle + pw * 1.2 + slot * pw, bottom)
    for slot in range(-frame[0]):
        checker(bar_x, middle - pw * 1.2 - slot * pw, top_shade)

    off_bottom = 15 - sum(c for c in frame if c > 0)
    off_top = 15 + sum(c for c in frame if c < 0)
    pitch = min(pw * 0.25, ((bottom_y - top_y) // 2 - tray_gap - pw - 4) / 15)
    slab_x0, slab_x1 = tray_x + 2, tray_x + tray_w - pw // 4 - 2
    for i in range(off_bottom):
        y = bottom_y - pw - 2 - (i + 1) * pitch
        d.rectangle((slab_x0, y + 1, slab_x1, y + pitch - 1), fill=SHADES[bottom][0])
    for i in range(off_top):
        y = top_y + pw + 2 + i * pitch
        d.rectangle((slab_x0, y + 1, slab_x1, y + pitch - 1), fill=SHADES[top_shade][0])

    if dice:
        roller = bottom if dice["side"] == "bottom" else top_shade
        body, pip = SHADES[dice_body or roller]
        field = right_x if dice["side"] == "bottom" else left_x
        size = pw * 0.85
        for i, value in enumerate(dice["values"]):
            x = field + field_w / 2 - size * 1.15 + i * size * 1.3
            y = middle - size / 2
            d.rounded_rectangle((x, y, x + size, y + size), radius=size * 0.15, fill=body)
            for px, py in PIPS[value]:
                r = size * 0.09
                d.ellipse((x + px * size - r, y + py * size - r, x + px * size + r, y + py * size + r), fill=pip)
    return image
