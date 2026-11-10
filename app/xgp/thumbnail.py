import io

from PIL import Image, ImageDraw

WIDTH, HEIGHT = 192, 148
MARGIN = 6
BAR_WIDTH = 12
FRAME = (92, 64, 51)
FELT = (234, 221, 196)
POINT_DARK = (156, 93, 64)
POINT_LIGHT = (214, 178, 134)
PLAYER1 = (250, 250, 250)
PLAYER2 = (40, 40, 40)
MAX_STACK = 5


def _point_x(point, point_width):
    index = (point - 1) % 12
    column = 11 - index if point <= 12 else index
    x = MARGIN + column * point_width
    if column >= 6:
        x += BAR_WIDTH
    return x


def _draw_stack(draw, x_center, top, count, radius, downward, colour):
    outline = PLAYER2 if colour == PLAYER1 else PLAYER1
    shown = min(count, MAX_STACK)
    for i in range(shown):
        offset = radius + i * radius * 2
        y = top + offset if downward else top - offset
        draw.ellipse((x_center - radius, y - radius, x_center + radius, y + radius), fill=colour, outline=outline)
    if count > MAX_STACK:
        offset = radius + (shown - 1) * radius * 2
        y = top + offset if downward else top - offset
        draw.text((x_center - radius + 2, y - radius), str(count), fill=outline)


def render_thumbnail(board):
    image = Image.new("RGB", (WIDTH, HEIGHT), FRAME)
    draw = ImageDraw.Draw(image)
    inner_width = WIDTH - 2 * MARGIN - BAR_WIDTH
    point_width = inner_width / 12
    radius = point_width / 2 - 1
    top, bottom = MARGIN, HEIGHT - MARGIN
    half = (bottom - top) * 0.42

    draw.rectangle((MARGIN, top, WIDTH - MARGIN, bottom), fill=FELT)
    bar_x = MARGIN + 6 * point_width
    draw.rectangle((bar_x, top, bar_x + BAR_WIDTH, bottom), fill=FRAME)

    for point in range(1, 25):
        x = _point_x(point, point_width)
        colour = POINT_DARK if point % 2 else POINT_LIGHT
        if point <= 12:
            draw.polygon([(x, bottom), (x + point_width, bottom), (x + point_width / 2, bottom - half)], fill=colour)
        else:
            draw.polygon([(x, top), (x + point_width, top), (x + point_width / 2, top + half)], fill=colour)
        count = board[point]
        if count:
            _draw_stack(draw, x + point_width / 2, bottom if point <= 12 else top, abs(count), radius,
                        downward=point > 12, colour=PLAYER1 if count > 0 else PLAYER2)

    bar_center = bar_x + BAR_WIDTH / 2
    if board[25]:
        _draw_stack(draw, bar_center, HEIGHT / 2 + 4, board[25], BAR_WIDTH / 2 - 1, downward=True, colour=PLAYER1)
    if board[0]:
        _draw_stack(draw, bar_center, HEIGHT / 2 - 4, -board[0], BAR_WIDTH / 2 - 1, downward=False, colour=PLAYER2)

    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return out.getvalue()
