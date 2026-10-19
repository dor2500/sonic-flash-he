"""Hebrew title logo (replaces shape 105 "ULTIMATE FLASH / SONIC", 143x47 px) at 4x resolution.
Run: python -I tools/make_logo.py <project dir>"""
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = sys.argv[1]
S = 4
W, H = 143 * S, 47 * S
FONT = os.path.join(ROOT, 'tools', 'fonts', 'SecularOne.ttf')
OUTLINE = (24, 28, 72, 255)


def metal(size, top, bottom, band):
    """vertical silver gradient with a darker band in the middle (like the original chrome letters)"""
    w, h = size
    g = Image.new('RGBA', size)
    px = g.load()
    for y in range(h):
        t = y / max(1, h - 1)
        c = [int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)]
        if band[0] < t < band[1]:
            c = [int(v * 0.72) for v in c]
        for x in range(w):
            px[x, y] = (*c, 255)
    return g


def text_layer(text, size, box, stroke):
    # PIL draws left to right: feed the visual (reversed) string
    vis = text[::-1]
    while True:  # shrink until it fits the box
        f = ImageFont.truetype(FONT, size)
        l, t, r, b = f.getbbox(vis, stroke_width=stroke)
        if (r - l) <= box[2] and (b - t) <= box[3]:
            break
        size -= 2
    x = box[0] + (box[2] - (r - l)) / 2 - l
    y = box[1] + (box[3] - (b - t)) / 2 - t
    m_fill = Image.new('L', (W, H))
    m_line = Image.new('L', (W, H))
    ImageDraw.Draw(m_fill).text((x, y), vis, font=f, fill=255)
    ImageDraw.Draw(m_line).text((x, y), vis, font=f, fill=255, stroke_width=stroke, stroke_fill=255)
    return m_fill, m_line, (int(y + t), int(y + b))


def main():
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    for text, size, box, stroke, band in (('סוניק', 60 * S, (2 * S, 13 * S, W - 4 * S, 34 * S - S), 3 * S, (0.5, 0.6)),
                                          ('פלאש האולטימטיבי', 14 * S, (8 * S, S, W - 16 * S, 12 * S), int(1.5 * S), (0.5, 0.58))):
        fill, line, (y0, y1) = text_layer(text, size, box, stroke)
        shadow = line.filter(ImageFilter.GaussianBlur(S)).point(lambda v: v * 0.6)
        out.alpha_composite(Image.merge('RGBA', [Image.new('L', (W, H), 0)] * 3 + [ImageChops.offset(shadow, S, S)]))
        out.alpha_composite(Image.composite(Image.new('RGBA', (W, H), OUTLINE), Image.new('RGBA', (W, H), (0, 0, 0, 0)), line))
        grad = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        grad.paste(metal((W, max(1, y1 - y0)), (255, 255, 255), (150, 150, 165), band), (0, y0))
        out.alpha_composite(Image.composite(grad, Image.new('RGBA', (W, H), (0, 0, 0, 0)), fill))
    dst = os.path.join(ROOT, 'work', 'he', 'logo.png')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    out.save(dst)
    print('saved', dst)


if __name__ == '__main__':
    main()
