"""New playable characters, drawn by code in every pose of the original character sprites.

usage: python -I make_chars.py <root> [--sheet]
reads  work/swf.xml (JPEXS swf2xml of the original), work/ex/images (original bitmaps)
writes work/chars/<id>/*.png, work/chars/spec.txt (for CharTool), work/chars/roster.json (for translate.py)
       --sheet: work/chars/sheet_<id>.png contact sheets for checking the art

Each character is a skeleton (hip, knees, ankles, shoulders, elbows, hands, head) posed per animation frame,
painted at 4x with outlined parts and reduced to pixel art; the result is placed where the original frame's
figure stood (feet on the same line, balls on the same centre), so the game's physics stay untouched.
"""
import colorsys
import json
import math
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw

ROOT = sys.argv[1] if len(sys.argv) > 1 else '.'
W = os.path.join(ROOT, 'work')
IMG = os.path.join(W, 'ex', 'images')
OUT = os.path.join(W, 'chars')
SS = 4                      # supersampling
OL = (16, 16, 40)           # outline colour
BASE_SPRITE = {'sonic': 1691, 'tails': 512, 'knuckles': 1289, 'cream': 829, 'amy': 1041, 'shadow': 1477}
SELECT = {'sonic': 2075, 'tails': 2086, 'amy': 2099, 'cream': 2125, 'knuckles': 2175, 'shadow': 2255}
ART_SPRITE, ICON_SPRITE = 104, 2598
COLOUR_SPRITES = [47, 66, 109, 112, 120, 127, 130, 142, 2507]   # per-character frames copied from a look-alike
PIVOT = (46.5, 48.5)        # pole of the "swing" frames


# ------------------------------------------------------------------ geometry helpers
def rot(v, a):
    """rotate (x, y) by a radians, clockwise on screen (y down)."""
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def add(p, q, k=1.0):
    return (p[0] + q[0] * k, p[1] + q[1] * k)


def down(a_deg, length):
    """vector of a limb pointing down, swung forward (+x) by a_deg."""
    a = math.radians(a_deg)
    return (math.sin(a) * length, math.cos(a) * length)


def dark(c, k=0.72):
    return tuple(int(v * k) for v in c[:3])


def light(c, k=0.35):
    return tuple(int(v + (255 - v) * k) for v in c[:3])


class Pen:
    """draws primitives given in 1x figure coordinates onto a SS canvas (offset + global rotation)."""

    def __init__(self, w, h, origin, scale=1.0, angle=0.0, pivot=(0, 0)):
        self.im = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)
        self.o, self.k, self.a, self.pv = origin, scale, angle, pivot
        self.prio = {OL: 6}

    def T(self, p):
        q = rot((p[0] - self.pv[0], p[1] - self.pv[1]), self.a)
        x, y = q[0] + self.pv[0], q[1] + self.pv[1]
        return ((self.o[0] + x * self.k) * SS, (self.o[1] + y * self.k) * SS)

    def ow(self):
        return SS * 1.0

    def ell(self, c, rx, ry, col, ang=0.0, ol=True, n=28):
        pts = [add(c, rot((rx * math.cos(t), ry * math.sin(t)), ang)) for t in (2 * math.pi * i / n for i in range(n))]
        self.poly(pts, col, ol)

    def poly(self, pts, col, ol=True):
        """filled polygon; ol = a thin darker rim of the part's own colour (the silhouette outline comes later)."""
        tp = [self.T(p) for p in pts]
        if ol:
            rim = dark(col, .55)
            r = SS * .6
            self.d.line(tp + [tp[0]], fill=rim, width=int(r * 2), joint='curve')
            for p in tp:
                self.d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=rim)
            self.prio.setdefault(rim, 7)
        self.d.polygon(tp, fill=col)

    def limb(self, p, q, w, col, ol=True, square=False):
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dy) or 1e-6
        nx, ny = -dy / L * w / 2, dx / L * w / 2
        if square:
            pts = [(p[0] + nx, p[1] + ny), (q[0] + nx, q[1] + ny), (q[0] - nx, q[1] - ny), (p[0] - nx, p[1] - ny)]
        else:
            n = 8
            a0 = math.atan2(ny, nx)
            pts = [add(q, (math.cos(a0 - math.pi * i / n) * w / 2, math.sin(a0 - math.pi * i / n) * w / 2)) for i in range(n + 1)]
            pts += [add(p, (math.cos(a0 + math.pi - math.pi * i / n) * w / 2, math.sin(a0 + math.pi - math.pi * i / n) * w / 2)) for i in range(n + 1)]
        self.poly(pts, col, ol)

    def dot(self, c, r, col, prio=None):
        self.ell(c, r, r, col, ol=False, n=12)
        if prio:
            self.prio[tuple(col[:3])] = prio

    def mark(self, col, thr):
        self.prio[tuple(col[:3])] = thr

    def reduce(self):
        """SS -> 1x: outline / marked details win at low coverage, otherwise the majority colour."""
        a = np.array(self.im)
        h, w = a.shape[0] // SS, a.shape[1] // SS
        rgb = a[:, :, :3].astype(np.int32)
        key = (rgb[:, :, 0] << 16) | (rgb[:, :, 1] << 8) | rgb[:, :, 2]
        key[a[:, :, 3] == 0] = -1
        cols, inv = np.unique(key, return_inverse=True)
        inv = inv.reshape(key.shape)
        K = len(cols)
        blocks = inv.reshape(h, SS, w, SS).transpose(0, 2, 1, 3).reshape(h, w, SS * SS)
        cnt = np.zeros((h, w, K), np.int32)
        for i in range(SS * SS):
            np.add.at(cnt, (np.arange(h)[:, None], np.arange(w)[None, :], blocks[:, :, i]), 1)
        tr = np.where(cols == -1)[0]
        opaque = SS * SS - (cnt[:, :, tr[0]] if len(tr) else 0)
        score = cnt.astype(np.float32).copy()
        if len(tr):
            score[:, :, tr[0]] = -1
        for col, thr in self.prio.items():
            kk = (col[0] << 16) | (col[1] << 8) | col[2]
            j = np.where(cols == kk)[0]
            if len(j):
                win = cnt[:, :, j[0]] >= thr
                score[:, :, j[0]] = np.where(win, 999 + cnt[:, :, j[0]], score[:, :, j[0]])
        best = score.argmax(axis=2)
        out = np.zeros((h, w, 4), np.uint8)
        kb = cols[best]
        out[:, :, 0], out[:, :, 1], out[:, :, 2] = (kb >> 16) & 255, (kb >> 8) & 255, kb & 255
        out[:, :, 3] = np.where((opaque >= 7) | (score.max(axis=2) >= 999), 255, 0)
        # 1 px outline around the silhouette (grow the canvas by 1 px so it always fits)
        out = np.pad(out, ((1, 1), (1, 1), (0, 0)))
        al = out[:, :, 3] > 0
        nb = np.zeros_like(al)
        nb[1:, :] |= al[:-1, :]; nb[:-1, :] |= al[1:, :]; nb[:, 1:] |= al[:, :-1]; nb[:, :-1] |= al[:, 1:]
        edge = nb & ~al
        out[edge] = OL + (255,)
        return Image.fromarray(out, 'RGBA')


# ------------------------------------------------------------------ characters
SKIN = (255, 196, 148)
WHITE = (248, 248, 248)
BLACK = (24, 24, 32)
BROWN = (120, 66, 28)
DBROWN = (70, 38, 16)


def ch(**k):
    base = dict(rig='biped', R=7.2, T=7.0, TW=6.6, thigh=4.2, shin=4.2, arm1=3.5, arm2=3.5, lw=2.4, aw=2.2,
                shoe=(6.2, 3.2), glove=WHITE, hand_r=1.6, head_up=0.72, square=False, arms=True)
    base.update(k)
    return base


def eye(p, c, rx, ry, iris=BLACK, mood=None, look=0.35):
    if mood == 'hurt':
        p.limb(add(c, (-rx, -ry * .6)), add(c, (rx, ry * .6)), 0.7, BLACK, ol=False)
        p.limb(add(c, (-rx, ry * .6)), add(c, (rx, -ry * .6)), 0.7, BLACK, ol=False)
        p.mark(BLACK, 3)
        return
    p.ell(c, rx, ry, WHITE, ol=False)
    p.mark(WHITE, 5)
    p.ell(add(c, (rx * look, ry * .15)), rx * .55, ry * .62, iris, ol=False)
    p.mark(iris, 3)


class Head:
    """head painters: H(p, c, R, ang, ch, mood) with features in units of R, facing right."""

    @staticmethod
    def place(c, R, ang):
        return lambda x, y: add(c, rot((x * R, y * R), ang))

    @staticmethod
    def plumber(p, c, R, ang, k, mood):
        P = Head.place(c, R, ang)
        cap, hair, mus = k['cap'], k.get('hair', BROWN), k.get('mus', DBROWN)
        p.ell(P(0, .05), R * k.get('face', 1.0), R * k.get('face', 1.0), SKIN, ang)
        p.ell(P(-.52, .12), .42 * R, .5 * R, hair, ang)
        p.ell(P(-.3, .22), .18 * R, .24 * R, SKIN, ang)
        dome = [P(-.08 + 1.0 * math.cos(t), -.32 + .66 * math.sin(t)) for t in np.linspace(math.pi, 2 * math.pi, 16)]
        p.poly(dome, cap)
        p.ell(P(.7, -.32), .5 * R, .15 * R, cap, ang)
        p.ell(P(.1, -.66), .26 * R, .22 * R, WHITE, ang, ol=False)
        p.ell(P(.1, -.66), .1 * R, .1 * R, k.get('letter', cap), ang, ol=False)
        eye(p, P(.45, -.02), .2 * R, .3 * R, k.get('iris', (40, 80, 200)), mood)
        nose = k.get('nose', SKIN)
        p.ell(P(.92, .2), k.get('nose_r', .3) * R, .26 * R, nose, ang)
        if k.get('zigzag'):
            p.poly([P(.25, .5), P(.55, .42), P(.75, .62), P(.98, .45), P(1.08, .62), P(.72, .78), P(.38, .72)], mus, ol=False)
        else:
            p.ell(P(.6, .5), .44 * R, .16 * R, mus, ang, ol=False)
        p.mark(mus, 4)

    @staticmethod
    def toad(p, c, R, ang, k, mood):
        P = Head.place(c, R, ang)
        p.ell(P(.05, .3), .85 * R, .78 * R, SKIN, ang)
        p.ell(P(0, -.42), 1.38 * R, .92 * R, WHITE, ang)
        for x, y, r in ((.62, -.55, .3), (-.55, -.62, .32), (.02, -1.02, .26)):
            p.ell(P(x, y), r * R, r * R * .9, (226, 34, 40), ang, ol=False)
        p.ell(P(.45, .3), .11 * R, .24 * R, BLACK, ang, ol=False)
        p.mark(BLACK, 3)
        if mood == 'hurt':
            p.ell(P(.65, .72), .12 * R, .08 * R, BLACK, ang, ol=False)

    @staticmethod
    def peach(p, c, R, ang, k, mood):
        P = Head.place(c, R, ang)
        gold = (255, 210, 60)
        p.ell(P(-.42, .62), .7 * R, 1.15 * R, gold, ang)
        p.ell(P(0, 0), .95 * R, .95 * R, SKIN, ang)
        p.ell(P(.05, -.55), .9 * R, .42 * R, gold, ang)
        p.poly([P(-.3, -.88), P(-.26, -1.3), P(-.08, -1.02), P(.08, -1.36), P(.24, -1.02), P(.42, -1.28), P(.42, -.86)], (255, 196, 30))
        p.dot(P(.08, -1.05), .1 * R, (60, 120, 255), 2)
        eye(p, P(.45, .02), .17 * R, .3 * R, (40, 110, 230), mood)
        p.dot(P(.78, .5), .1 * R, (230, 70, 110), 2)
        p.dot(P(-.15, .45), .1 * R, (60, 120, 255), 2)

    @staticmethod
    def yoshi(p, c, R, ang, k, mood):
        P = Head.place(c, R, ang)
        g = (60, 190, 60)
        for y in (-.15, .3):
            p.poly([P(-.75, y - .25), P(-1.15, y), P(-.75, y + .25)], (226, 40, 40))
        p.ell(P(-.1, -.05), .8 * R, .85 * R, g, ang)
        p.ell(P(.68, .2), .78 * R, .6 * R, g, ang)
        p.ell(P(.42, .5), .55 * R, .3 * R, WHITE, ang, ol=False)
        p.dot(P(1.0, .02), .07 * R, (20, 80, 20), 2)
        for x, s in ((.02, .9), (.38, 1.0)):
            p.ell(P(x, -.72), .27 * R * s, .42 * R * s, WHITE, ang)
            p.ell(P(x + .1, -.66), .12 * R, .22 * R, BLACK, ang, ol=False)
        p.mark(BLACK, 3)

    @staticmethod
    def kirby(p, c, R, ang, k, mood):
        P = Head.place(c, R, ang)
        p.ell(P(0, 0), R, R, (255, 160, 190), ang)
        for x in (.2, .52):
            if mood == 'hurt':
                p.limb(P(x - .1, -.25), P(x + .1, -.1), .6, BLACK, ol=False)
            else:
                p.ell(P(x, -.2), .1 * R, .25 * R, BLACK, ang, ol=False)
                p.dot(P(x, -.32), .05 * R, WHITE, 2)
        p.mark(BLACK, 3)
        p.ell(P(.7, .12), .14 * R, .07 * R, (240, 90, 130), ang, ol=False)
        p.ell(P(.42, .2), .08 * R, .06 * R, (150, 30, 50), ang, ol=False)

    @staticmethod
    def megaman(p, c, R, ang, k, mood):
        P = Head.place(c, R, ang)
        blue, cyan = (30, 90, 230), (90, 200, 255)
        p.ell(P(0, -.05), R, R, blue, ang)
        p.ell(P(.38, .25), .6 * R, .62 * R, SKIN, ang)
        p.ell(P(-.1, -.7), .45 * R, .16 * R, cyan, ang, ol=False)
        p.ell(P(-.3, .05), .26 * R, .26 * R, cyan, ang)
        eye(p, P(.5, .12), .18 * R, .28 * R, (40, 90, 220), mood)

    @staticmethod
    def link(p, c, R, ang, k, mood):
        P = Head.place(c, R, ang)
        green, blond = (40, 150, 50), (250, 210, 80)
        p.poly([P(-.2, -.75), P(-1.0, -.35), P(-1.75, .95), P(-.55, .15)], green)
        p.ell(P(-.3, .05), .72 * R, .85 * R, blond, ang)
        p.ell(P(.12, .12), .85 * R, .85 * R, SKIN, ang)
        p.poly([P(-.15, .05), P(-.85, -.3), P(-.2, .35)], SKIN)
        p.poly([P(-.75, -.2), P(-.1, -1.0), P(.85, -.55), P(.55, -.3), P(-.4, .05)], green)
        p.ell(P(.5, -.4), .42 * R, .2 * R, blond, ang, ol=False)
        eye(p, P(.5, .08), .16 * R, .27 * R, (40, 110, 230), mood)

    @staticmethod
    def steve(p, c, R, ang, k, mood):
        P = Head.place(c, R, ang)
        hair, sk = (70, 45, 25), (198, 140, 100)
        p.poly([P(-.9, -.9), P(.9, -.9), P(.9, .9), P(-.9, .9)], sk)
        p.poly([P(-.9, -.9), P(.9, -.9), P(.9, -.5), P(-.4, -.5), P(-.4, .3), P(-.9, .3)], hair, ol=False)
        if mood == 'hurt':
            p.poly([P(.45, -.1), P(.9, -.1), P(.9, .1), P(.45, .1)], BLACK, ol=False)
        else:
            p.poly([P(.3, -.15), P(.6, -.15), P(.6, .15), P(.3, .15)], WHITE, ol=False)
            p.poly([P(.6, -.15), P(.9, -.15), P(.9, .15), P(.6, .15)], (60, 60, 160), ol=False)
            p.mark(WHITE, 4)
            p.mark((60, 60, 160), 3)
        p.poly([P(.45, .45), P(.9, .45), P(.9, .62), P(.45, .62)], (110, 60, 40), ol=False)

    @staticmethod
    def pikachu(p, c, R, ang, k, mood):
        P = Head.place(c, R, ang)
        y = (255, 220, 40)
        p.poly([P(-.25, -.65), P(-.55, -2.0), P(.1, -.8)], y)
        p.poly([P(-.4, -1.55), P(-.55, -2.0), P(-.2, -1.6)], BLACK, ol=False)
        p.ell(P(0, 0), R, .92 * R, y, ang)
        p.poly([P(.25, -.7), P(1.0, -1.75), P(.62, -.55)], y)
        p.poly([P(.82, -1.5), P(1.0, -1.75), P(.9, -1.35)], BLACK, ol=False)
        p.ell(P(.55, .38), .22 * R, .2 * R, (230, 40, 30), ang, ol=False)
        if mood == 'hurt':
            p.limb(P(.3, -.15), P(.55, -.05), .7, BLACK, ol=False)
        else:
            p.ell(P(.42, -.08), .17 * R, .2 * R, BLACK, ang, ol=False)
            p.dot(P(.46, -.14), .07 * R, WHITE, 2)
        p.mark(BLACK, 3)
        p.dot(P(.96, .06), .06 * R, BLACK, 2)

    @staticmethod
    def none(p, c, R, ang, k, mood):
        pass


def H_goat_head(p, c, s, ang, mood, tongue=True):
    """goat head, c = skull centre, s = scale (1 = sprite size)."""
    P = lambda x, y: add(c, rot((x * s, y * s), ang))
    grey, horn = (200, 200, 205), (110, 100, 90)
    p.limb(P(-1.2, -1.8), P(-4.6, -2.4), 1.8 * s, horn)
    p.limb(P(-4.6, -2.4), P(-5.6, -.5), 1.5 * s, horn)
    p.ell(P(0, 0), 3.4 * s, 2.7 * s, grey, ang)
    p.ell(P(2.9, 1.0), 2.6 * s, 1.7 * s, grey, ang + .25)
    p.ell(P(-1.9, .1), 1.6 * s, .8 * s, (170, 170, 175), ang + .6)
    if tongue:
        p.limb(P(3.6, 2.4), P(4.4, 5.4), 1.2 * s, (240, 110, 140))
    p.poly([P(1.6, 2.4), P(2.4, 2.4), P(1.7, 4.4)], (235, 235, 238))
    if mood == 'hurt':
        p.limb(P(.6, -.6), P(1.6, .2), .6, BLACK, ol=False)
    else:
        p.ell(P(1.0, -.5), .75 * s, .65 * s, (250, 220, 120), ol=False)
        p.ell(P(1.15, -.5), .5 * s, .2 * s, BLACK, ol=False)
    p.mark(BLACK, 3)
    p.dot(P(5.2, .6), .35 * s, (60, 50, 50), 2)


def torso_paint(p, k, hip, up, lean, T, TW):
    a = math.radians(lean)
    mid = add(hip, up, T * .5)
    style = k.get('torso', 'plain')
    c1, c2 = k['c1'], k.get('c2', k['c1'])
    if style == 'overalls':
        p.ell(add(hip, up, T * .62), TW * .5, T * .42, c1, a)
        p.ell(add(hip, up, T * .32), TW * .52, T * .42, c2, a)
        for s in (-.22, .22):
            p.limb(add(add(hip, up, T * .45), rot((s * TW, 0), a)), add(add(hip, up, T * .85), rot((s * TW * 1.1, 0), a)), 1.0, c2, ol=False)
        p.dot(add(add(hip, up, T * .55), rot((TW * .25, 0), a)), .5, (255, 220, 60), 2)
    elif style == 'rect':
        hw, hh = TW / 2, T / 2
        pts = [add(mid, rot(v, a)) for v in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
        p.poly(pts, c1)
    elif style == 'bean':
        hw, hh = TW / 2, T / 2
        pts = []
        for i in range(32):
            t = 2 * math.pi * i / 32
            x, y = math.cos(t), math.sin(t)
            sx, sy = math.copysign(abs(x) ** .5, x), math.copysign(abs(y) ** .5, y)
            pts.append(add(mid, rot((sx * hw, sy * hh), a)))
        p.poly([add(add(mid, rot((-hw - 1.6, -1.2), a)), (0, 0))] + [add(mid, rot(v, a)) for v in ((-hw - 2.6, -3), (-hw - 2.6, 3.5), (-hw + 1, 3.5))], dark(c1, .8))
        p.poly(pts, c1)
        p.ell(add(mid, rot((hw * .45, -hh * .35), a)), hw * .62, hh * .26, (150, 220, 250), a)
        p.ell(add(mid, rot((hw * .6, -hh * .45), a)), hw * .25, hh * .08, WHITE, a, ol=False)
    elif style == 'sponge':
        hw, hh = TW / 2, T / 2
        box = lambda y0, y1, col, ol=True: p.poly([add(mid, rot(v, a)) for v in ((-hw, y0), (hw, y0), (hw, y1), (-hw, y1))], col, ol)
        box(-hh, hh, (255, 236, 80))
        box(hh * .45, hh * .62, WHITE, False)
        box(hh * .62, hh, (150, 90, 40), False)
        for x, y in ((-.55, -.7), (-.7, .1), (-.2, .25)):
            p.dot(add(mid, rot((x * hw, y * hh), a)), .7, (190, 200, 40), 2)
        for x in (.15, .62):
            if k.get('_mood') == 'hurt':
                p.limb(add(mid, rot((x * hw - 1, -hh * .45), a)), add(mid, rot((x * hw + 1, -hh * .25), a)), .7, BLACK, ol=False)
                continue
            p.ell(add(mid, rot((x * hw, -hh * .35), a)), 2.0, 2.2, WHITE)
            p.dot(add(mid, rot((x * hw + .6, -hh * .32), a)), .9, (60, 140, 230), 3)
            p.dot(add(mid, rot((x * hw + .7, -hh * .32), a)), .45, BLACK, 2)
        p.limb(add(mid, rot((hw * .05, hh * .15), a)), add(mid, rot((hw * .7, hh * .1), a)), .8, (160, 40, 40), ol=False)
        p.dot(add(mid, rot((hw * .5, -hh * .05), a)), .9, (255, 236, 80))
        p.limb(add(mid, rot((hw * .25, hh * .53), a)), add(mid, rot((hw * .25, hh * .85), a)), 1.0, (210, 40, 40), ol=False)
    else:
        p.ell(mid, TW * .5, T * .6, c1, a)
        if k.get('belly'):
            p.ell(add(mid, rot((TW * .2, T * .05), a)), TW * .3, T * .42, k['belly'], a, ol=False)
        if k.get('belt'):
            p.limb(add(add(hip, up, T * .25), rot((-TW * .45, 0), a)), add(add(hip, up, T * .25), rot((TW * .45, 0), a)), 1.1, k['belt'], ol=False)
        if k.get('saddle'):
            p.ell(add(mid, rot((-TW * .45, -T * .05), a)), TW * .28, T * .42, k['saddle'], a)


def biped(p, k, pose):
    """paint a biped; pose angles in degrees (limbs measured from straight down, + = forward)."""
    g = lambda n, d=0.0: pose.get(n, d)
    lean = g('lean')
    a = math.radians(lean)
    up = (math.sin(a), -math.cos(a))
    hip = (0.0, -(k['thigh'] + k['shin']) - k['shoe'][1] * .45 + g('by'))
    T, TW, R = k['T'], k['TW'], k['R']
    mood = pose.get('mood')
    k['_mood'] = mood

    def leg(side, shade):
        h, kn = g('hip' + side), g('knee' + side)
        knee = add(hip, down(h, k['thigh']))
        ank = add(knee, down(h - kn, k['shin']))
        col = k['legs'] if not shade else dark(k['legs'])
        if k['thigh'] + k['shin'] > 1.5:
            p.limb(hip, knee, k['lw'], col, square=k['square'])
            p.limb(knee, ank, k['lw'], col, square=k['square'])
        sa = math.radians(-(h - kn) + g('toe' + side))
        sl, sh = k['shoe']
        shoe = k['shoes'] if not shade else dark(k['shoes'])
        if k['square']:
            c = add(ank, rot((sl * .25, sh * .2), sa))
            p.poly([add(c, rot(v, sa)) for v in ((-sl * .45, -sh * .45), (sl * .55, -sh * .45), (sl * .55, sh * .5), (-sl * .45, sh * .5))], shoe)
        else:
            p.ell(add(ank, rot((sl * .25, sh * .15), sa)), sl * .5, sh * .5, shoe, sa)
            if k.get('shoe_band'):
                p.ell(add(ank, rot((-sl * .05, -sh * .1), sa)), sl * .2, sh * .45, k['shoe_band'] if not shade else dark(k['shoe_band']), sa, ol=False)

    def arm(side, shade):
        if not k['arms']:
            return
        s, e = g('sh' + side) + lean * .5, g('el' + side)
        sho = add(add(hip, up, T * .82), rot(((-1.0 if shade else .4), 0), a))
        elb = add(sho, down(s, k['arm1']))
        hand = add(elb, down(s + e, k['arm2']))
        c1, c2 = k.get('sleeve', k['c1']), k.get('fore', k.get('sleeve', k['c1']))
        if shade:
            c1, c2 = dark(c1), dark(c2)
        p.limb(sho, elb, k['aw'], c1, square=k['square'])
        p.limb(elb, hand, k['aw'] * .9, c2, square=k['square'])
        gl = k['glove'] or c2
        p.ell(hand, k['hand_r'], k['hand_r'], gl if not shade else dark(gl))

    if k.get('tail'):
        k['tail'](p, k, hip, up, a, pose)
    arm('B', True)
    leg('B', True)
    if k.get('torso') == 'dress':
        pass
    else:
        torso_paint(p, k, hip, up, lean, T, TW)
    leg('F', False)
    if k.get('torso') == 'dress':
        fy = max(add(add(hip, down(g('hipF'), k['thigh'])), down(g('hipF') - g('kneeF'), k['shin']))[1],
                 add(add(hip, down(g('hipB'), k['thigh'])), down(g('hipB') - g('kneeB'), k['shin']))[1]) - 2.2
        top = add(hip, up, 2.0)
        sw = 5.5 + abs(g('hipF') - g('hipB')) * .03
        p.poly([add(top, (-2.4, 0)), add(top, (2.4, 0)), (top[0] + sw + 1.5, fy), (top[0] - sw, fy)], k['c1'])
        p.ell(add(hip, up, T * .6), TW * .45, T * .5, k['c1'], a)
        p.ell(add(hip, up, 1.6), TW * .5, 1.0, light(k['c1']), a)
    if R > 0:
        hc = add(hip, up, T + R * k['head_up'])
        k['head'](p, hc, R, math.radians(g('head') + lean * .4), k, mood)
    arm('F', False)


def tail_pika(p, k, hip, up, a, pose):
    b = add(hip, up, 1.5)
    pts = [(0, 0), (-3, -1.5), (-2.2, -4), (-6, -5.5), (-5, -8.5), (-10, -10), (-8.5, -6.5), (-4.6, -6), (-5.5, -3.3), (-1.4, -2.2)]
    p.poly([add(b, rot(v, a * .5)) for v in pts], (255, 220, 40))
    p.poly([add(b, rot(v, a * .5)) for v in pts[:3] + [pts[-1]]], (150, 90, 40), ol=False)


def tail_yoshi(p, k, hip, up, a, pose):
    b = add(hip, up, 2.0)
    p.limb(b, add(b, rot((-5, 1.5), a)), 3.2, (60, 190, 60))


# quadruped (the goat) ------------------------------------------------------
def goat(p, k, pose):
    g = lambda n, d=0.0: pose.get(n, d)
    lean = math.radians(g('lean'))
    body = (0.0, -11.0 + g('by'))
    grey, dgrey, hoof = (220, 220, 225), (160, 160, 168), (70, 60, 60)
    hips = [(5.5, 'F'), (-5.5, 'B')]

    def leg(x, sid, shade):
        h, kn = g('hip' + sid), g('knee' + sid)
        top = add(body, rot((x, 2.0), lean))
        knee = add(top, down(h, 4.2))
        foot = add(knee, down(h - kn, 4.2))
        col = dgrey if shade else grey
        p.limb(top, knee, 2.4, col)
        p.limb(knee, foot, 2.0, col)
        p.ell(add(foot, (.4, .3)), 1.3, .9, hoof)

    leg(4.3, 'F2', True)
    leg(-6.5, 'B2', True)
    p.limb(add(body, rot((-8.5, -1.5), lean)), add(body, rot((-10.5, -4.5 + g('tail')), lean)), 1.8, grey)
    p.ell(body, 9.0, 5.2, grey, lean)
    p.ell(add(body, rot((-3, -1.5), lean)), 3.5, 1.8, (200, 200, 208), lean, ol=False)
    leg(5.8, 'F', False)
    leg(-5.0, 'B', False)
    neck0 = add(body, rot((6.5, -1.5), lean))
    ha = math.radians(g('head')) + lean
    hc = add(neck0, rot((3.0, -5.0), ha))
    p.limb(neck0, hc, 4.2, grey)
    H_goat_head(p, add(hc, rot((1.0, -.5), ha)), 1.0, ha, pose.get('mood'), tongue=not pose.get('notongue'))


CHARS = [
    ch(id='mario', he='מריו', base='sonic', head=Head.plumber, cap=(222, 34, 30), letter=(222, 34, 30), c1=(222, 34, 30),
       c2=(56, 100, 240), torso='overalls', legs=(56, 100, 240), shoes=(110, 60, 25), sleeve=(222, 34, 30), ball=((222, 34, 30), (56, 100, 240))),
    ch(id='luigi', he="לואיג'י", base='sonic', head=Head.plumber, cap=(40, 170, 60), letter=(40, 170, 60), c1=(40, 170, 60),
       c2=(36, 60, 190), torso='overalls', legs=(36, 60, 190), shoes=(110, 60, 25), sleeve=(40, 170, 60), thigh=4.8, shin=4.8, T=7.6, TW=6.0,
       ball=((40, 170, 60), (36, 60, 190))),
    ch(id='wario', he='וואריו', base='knuckles', head=Head.plumber, cap=(250, 210, 30), letter=(30, 60, 200), c1=(250, 210, 30),
       c2=(120, 40, 150), torso='overalls', legs=(120, 40, 150), shoes=(40, 140, 60), sleeve=(250, 210, 30), nose=(250, 140, 160),
       nose_r=.38, mus=BLACK, zigzag=True, face=1.06, TW=9.0, thigh=3.6, shin=3.6, ball=((250, 210, 30), (120, 40, 150))),
    ch(id='waluigi', he="וואלואיג'י", base='shadow', head=Head.plumber, cap=(110, 40, 160), letter=(250, 210, 30), c1=(110, 40, 160),
       c2=(30, 30, 50), torso='overalls', legs=(30, 30, 50), shoes=(240, 140, 30), sleeve=(110, 40, 160), nose=(250, 150, 170), mus=BLACK,
       thigh=5.6, shin=5.6, T=8.0, TW=5.4, arm1=4.4, arm2=4.4, ball=((110, 40, 160), (30, 30, 50))),
    ch(id='toad', he='טואד', base='cream', head=Head.toad, c1=(40, 70, 200), legs=WHITE, shoes=(120, 70, 30), sleeve=(40, 70, 200),
       fore=SKIN, glove=SKIN, R=6.6, thigh=3.4, shin=3.4, T=6.0, belly=(250, 200, 60), ball=(WHITE, (226, 34, 40))),
    ch(id='peach', he="הנסיכה פיץ'", base='amy', head=Head.peach, c1=(255, 120, 180), torso='dress', legs=SKIN, shoes=(230, 40, 80),
       sleeve=(255, 150, 200), fore=SKIN, R=6.8, thigh=4.6, shin=4.6, TW=5.6, ball=((255, 120, 180), (255, 210, 60))),
    ch(id='yoshi', he='יושי', base='sonic', head=Head.yoshi, c1=(60, 190, 60), belly=WHITE, saddle=(226, 40, 40), legs=(60, 190, 60),
       shoes=(240, 120, 30), sleeve=(60, 190, 60), glove=None, tail=tail_yoshi, R=6.8, ball=((60, 190, 60), WHITE)),
    ch(id='kirby', he='קירבי', base='tails', head=Head.kirby, c1=(255, 160, 190), legs=(255, 160, 190), shoes=(226, 30, 60),
       sleeve=(255, 160, 190), glove=None, R=10.0, T=0.0, TW=0.1, thigh=1.2, shin=1.2, arm1=2.6, arm2=1.6, aw=3.2, hand_r=1.9,
       shoe=(8.0, 4.4), head_up=0.95, lw=3.0, torso='none', ball=((255, 160, 190), (226, 30, 60))),
    ch(id='megaman', he='מגה מן', base='sonic', head=Head.megaman, c1=(90, 200, 255), legs=(90, 200, 255), shoes=(30, 90, 230),
       sleeve=(30, 90, 230), glove=(30, 90, 230), shoe_band=(90, 200, 255), hand_r=1.9, ball=((30, 90, 230), (90, 200, 255))),
    ch(id='link', he='לינק', base='sonic', head=Head.link, c1=(40, 150, 50), belt=(110, 60, 25), legs=(240, 230, 200), shoes=(110, 60, 25),
       sleeve=(40, 150, 50), fore=SKIN, glove=(150, 90, 40), ball=((40, 150, 50), (250, 210, 80))),
    ch(id='steve', he='סטיב', base='knuckles', head=Head.steve, c1=(40, 180, 190), torso='rect', legs=(50, 60, 150), shoes=(90, 90, 100),
       sleeve=(40, 180, 190), fore=(198, 140, 100), glove=(198, 140, 100), square=True, R=6.4, T=8.0, TW=6.0, thigh=4.4, shin=4.4,
       lw=3.0, aw=2.8, hand_r=1.4, shoe=(4.6, 2.2), ball=((40, 180, 190), (50, 60, 150))),
    ch(id='pikachu', he="פיקאצ'ו", base='tails', head=Head.pikachu, c1=(255, 220, 40), legs=(255, 220, 40), shoes=(255, 220, 40),
       sleeve=(255, 220, 40), glove=None, tail=tail_pika, R=7.4, T=6.0, TW=7.6, thigh=2.6, shin=2.6, arm1=2.6, arm2=2.4,
       shoe=(5.0, 2.8), ball=((255, 220, 40), (230, 40, 30))),
    ch(id='crewmate', he='אמונג אס', base='sonic', head=Head.none, c1=(214, 30, 40), torso='bean', legs=(214, 30, 40), shoes=(180, 22, 34),
       R=0, T=13.0, TW=12.0, thigh=2.6, shin=2.6, lw=4.2, shoe=(5.4, 3.2), arms=False, ball=((214, 30, 40), (150, 220, 250))),
    ch(id='sponge', he='בובספוג', base='sonic', head=Head.none, c1=(255, 236, 80), torso='sponge', legs=(255, 236, 80), shoes=BLACK,
       sleeve=WHITE, fore=(255, 236, 80), glove=(255, 236, 80), R=0, T=12.0, TW=13.0, thigh=3.6, shin=3.6, lw=1.4, aw=1.4,
       arm1=3.6, arm2=3.6, hand_r=1.2, shoe=(5.0, 2.6), ball=((255, 236, 80), (150, 90, 40))),
    dict(id='goat', he='העז', base='sonic', rig='goat', ball=((220, 220, 225), (110, 100, 90))),
    dict(id='supersonic', he='סופר סוניק', base='sonic', rig='recolor', recolor='gold'),
    dict(id='scourge', he="סקורג'", base='sonic', rig='recolor', recolor='green'),
    dict(id='silver', he='סילבר', base='shadow', rig='recolor', recolor='silver'),
]
# original look-alike for the per-character colour frames (bars, circles) of the game
TWIN = dict(mario='knuckles', luigi='sonic', wario='tails', waluigi='shadow', toad='cream', peach='amy', yoshi='sonic',
            kirby='amy', megaman='sonic', link='tails', steve='sonic', pikachu='tails', crewmate='knuckles', sponge='tails',
            goat='shadow', supersonic='tails', scourge='sonic', silver='shadow')


# ------------------------------------------------------------------ poses
def cyc(i, n):
    return 2 * math.pi * i / max(n, 1)


def run_pose(i, n, amp, lean, knee, arm_amp, el, by=1.0):
    t = cyc(i, n)
    s, c = math.sin(t), math.cos(t)
    return dict(lean=lean, by=-abs(c) * by, hipF=amp * s, hipB=-amp * s,
                kneeF=knee * max(0, -c) + 10, kneeB=knee * max(0, c) + 10,
                shF=-arm_amp * s, shB=arm_amp * s, elF=el, elB=el)


def pose_for(state, i, n):
    """pose dict, or ('ball'|'swirl'|'dash'|'wheel', info) for the special frames."""
    if state == 'stand':
        b = [0, 0, .5, .5, 1][min(i, 4)]
        return dict(hipF=8, hipB=-6, kneeF=6, kneeB=4, shF=10 + 6 * b, elF=25, shB=-8, elB=20, by=b * .5, head=-3 * b)
    if state == 'walk':
        return run_pose(i, n, 26, 4, 35, 22, 25, .6)
    if state == 'runslow':
        return run_pose(i, n, 36, 9, 50, 35, 60)
    if state == 'run':
        return run_pose(i, n, 48, 15, 70, 50, 85)
    if state == 'runfast':
        p = run_pose(i, n, 58, 22, 80, 15, 30)
        p.update(shF=-55, shB=-70, elF=25, elB=15)
        return p
    if state == 'runfast2':
        return ('wheel', i)
    if state in ('roll', 'jump'):
        return ('ball', i)
    if state == 'break':
        return dict(lean=-18, hipF=45, kneeF=0, hipB=-5, kneeB=45, shF=-35, elF=40, shB=-60, elB=30, head=-6)
    if state == 'push':
        t = cyc(i, n)
        return dict(lean=30, hipF=-5 + 10 * math.sin(t), kneeF=35, hipB=-35 - 10 * math.sin(t), kneeB=15,
                    shF=80, elF=10, shB=75, elB=15)
    if state == 'duck':
        f = (i + 1) / n
        return dict(lean=12 * f, by=0, hipF=55 * f + 10, kneeF=110 * f, hipB=35 * f, kneeB=100 * f,
                    shF=40 + 20 * f, elF=40, shB=30, elB=40, head=8 * f)
    if state == 'look':
        f = min(1, (i + 1) / max(1, n - 1))
        return dict(hipF=8, hipB=-6, kneeF=6, kneeB=4, head=-28 * f, lean=-6 * f, shF=60 + 90 * f, elF=90 * f, shB=-10, elB=20)
    if state == 'jumphigh':
        if i < 4:
            return dict(hipF=4, hipB=-4, kneeF=4, kneeB=10, shF=8, elF=6, shB=-6, elB=6, toeF=-30, toeB=-30)
        t = cyc(i, 4)
        return dict(hipF=25, kneeF=60, hipB=-12, kneeB=30, shF=165 + 12 * math.sin(t), elF=15, shB=150 - 12 * math.sin(t), elB=25)
    if state == 'grind':
        return dict(lean=6, hipF=24, kneeF=18, hipB=-24, kneeB=18, shF=85, elF=0, shB=100, elB=5, toeF=-10, toeB=10)
    if state == 'hit':
        return dict(lean=-20 - 6 * i, hipF=40, kneeF=40, hipB=20, kneeB=55, shF=125, elF=40, shB=145, elB=30, head=-8, mood='hurt',
                    rot=-12 * i)
    if state == 'balance':
        t = cyc(i, n)
        return dict(lean=32, head=22, hipF=8, kneeF=6, hipB=-40, kneeB=65, shF=95 + 65 * math.sin(t), elF=10,
                    shB=95 - 65 * math.sin(t), elB=10)
    if state == 'twistl':
        p = run_pose(i, n, 40, 10, 55, 40, 70)
        if i < n - 2:
            p['rot'] = 360.0 * i / (n - 2)
        return p
    if state == 'swing':
        return dict(hipF=10, kneeF=20, hipB=-5, kneeB=10, shF=180, elF=0, shB=175, elB=0, swing=True)
    if state == 'dead':
        return dict(hipF=25, kneeF=10, hipB=-20, kneeB=10, shF=150, elF=10, shB=-150, elB=-10, head=-10, mood='hurt')
    if state == 'fly':
        p = run_pose(i, n, 20, 6, 30, 0, 0)
        p.update(shF=160, shB=170, elF=10, elB=10)
        return p
    return dict()


def goat_pose(state, i, n):
    if state in ('walk', 'runslow', 'run', 'runfast', 'runfast2', 'twistl'):
        amp = dict(walk=25, runslow=35, run=45, runfast=55, runfast2=60, twistl=45)[state]
        t = cyc(i, n)
        s = math.sin(t)
        p = dict(hipF=amp * s, kneeF=-30 * max(0, s), hipF2=amp * math.sin(t + .6), kneeF2=-30 * max(0, math.sin(t + .6)),
                 hipB=-amp * s, kneeB=30 * max(0, -s), hipB2=-amp * math.sin(t + .6), kneeB2=30 * max(0, -math.sin(t + .6)),
                 by=-abs(math.cos(t)) * 1.5, head=-5 + 6 * s, tail=2 * s)
        if state == 'twistl' and i < n - 2:
            p['rot'] = 360.0 * i / (n - 2)
        return p
    base = dict(hipF=5, hipF2=-3, hipB=-5, hipB2=3)
    if state == 'stand':
        base.update(head=[0, 0, -6, -6, 8][min(i, 4)], tail=[0, 2, 0, 2, 0][min(i, 4)])
    elif state == 'break':
        base.update(lean=-14, hipF=45, hipF2=40, hipB=10, hipB2=5, kneeB=20, head=-10)
    elif state == 'push':
        base.update(lean=12, head=45, hipB=-35, hipB2=-30, notongue=True)
    elif state == 'duck':
        f = (i + 1) / n
        base.update(by=4 * f, kneeF=-120 * f, kneeF2=-120 * f, kneeB=120 * f, kneeB2=120 * f, hipF=-60 * f, hipF2=-60 * f,
                    hipB=60 * f, hipB2=60 * f, head=15 * f)
    elif state == 'look':
        base.update(head=-35, lean=-10)
    elif state == 'jumphigh':
        base.update(hipF=50, hipF2=45, hipB=-50, hipB2=-45, head=-20, lean=-15 if i < 4 else 10 * math.sin(cyc(i, 4)))
    elif state == 'hit':
        base.update(lean=-25, hipF=60, hipF2=30, hipB=40, hipB2=10, kneeF=-40, mood='hurt', rot=-15 * i)
    elif state == 'balance':
        base.update(lean=25, head=35, hipB=-50, hipB2=-30, kneeB=50, tail=4 * math.sin(cyc(i, n)))
    elif state == 'swing':
        base.update(hipF=-30, hipF2=-40, hipB=30, hipB2=40, swing=True)
    elif state == 'dead':
        base.update(rot=180, hipF=20, hipF2=-20, hipB=25, hipB2=-25, mood='hurt')
    return base


# ------------------------------------------------------------------ rendering
def render_figure(k, pose, scale=1.0):
    """figure on a big canvas, cropped; returns (img, anchor) where anchor = feet point (x, y) inside img."""
    S = int(140 * max(1.0, scale))
    o = (S / 2, S * .72)
    rot_deg = pose.get('rot', 0.0)
    p = Pen(S, S, o, scale, math.radians(rot_deg), pivot=(0, -14))
    (goat if k['rig'] == 'goat' else biped)(p, k, pose)
    im = p.reduce()
    bb = im.getbbox()
    return im.crop(bb), (o[0] - bb[0], o[1] - bb[1])


def render_ball(k, i, r, kind='ball', squash=1.0):
    S = int(r * 2 + 8)
    p = Pen(S, S, (S / 2, S / 2))
    c1, c2 = k['ball']
    a = i * math.pi / 2 + .4
    p.ell((0, 0), r * squash, r, c1)
    p.ell((r * .2, r * .25), r * .78 * squash, r * .72, dark(c1, .82), ol=False)
    p.ell((-r * .05, -r * .05), r * .8 * squash, r * .78, c1, ol=False)
    if kind == 'swirl':
        for j in range(3):
            pts = [rot((math.cos(t) * r * t / 6.5, math.sin(t) * r * t / 6.5), a + j * 2.1) for t in np.linspace(.3, 5.8, 16)]
            for q0, q1 in zip(pts, pts[1:]):
                p.limb(q0, q1, 1.6, c2 if j != 1 else light(c1, .5), ol=False)
    else:
        q = rot((r * .62, 0), a)
        p.ell(q, r * .32, r * .32, c2, ol=False)
        p.ell(rot((r * .62, 0), a + math.pi), r * .22, r * .22, c2, ol=False)
        p.limb(rot((-r * .9, 0), a + .5), rot((r * .9, 0), a + .5), 1.1, dark(c1, .6), ol=False)
    p.ell((-r * .38, -r * .42), r * .2, r * .16, light(c1, .7), ol=False)
    p.mark(c2, 5)
    im = p.reduce()
    return im


def render_wheel(k, i):
    pose = dict(lean=22, hipF=0, kneeF=0, hipB=0, kneeB=0, shF=-60, elF=20, shB=-75, elB=10)
    k2 = dict(k, thigh=.3, shin=.3, shoe=(.1, .1))
    if k['rig'] == 'goat':
        return render_figure(k, dict(goat_pose('run', i, 4), hipF=70, hipB=-70))
    S = 140
    o = (S / 2, S * .72)
    p = Pen(S, S, o)
    c = (0, -6.0)
    for j, col in enumerate((dark(k.get('shoes', (200, 40, 40))), k.get('shoes', (200, 40, 40)))):
        pts = [add(c, rot((math.cos(t) * 6.5, math.sin(t) * 4.2), .3 + j * .5 + i * .7)) for t in np.linspace(0, 2 * math.pi, 26)]
        for q0, q1 in zip(pts, pts[1:]):
            p.limb(q0, q1, 1.8, col, ol=False)
    p.mark(k.get('shoes', (200, 40, 40)), 5)
    k2_hip_lift = dict(pose, by=-(k['thigh'] + k['shin']) + 3.5)
    biped(p, k2, k2_hip_lift)
    im = p.reduce()
    bb = im.getbbox()
    return im.crop(bb), (o[0] - bb[0], o[1] - bb[1])


def is_fur(a, base):
    """mask of the body colour of the original sprite (blue for sonic, ... ) used to find the ball."""
    r, g, b = a[:, :, 0].astype(int), a[:, :, 1].astype(int), a[:, :, 2].astype(int)
    op = a[:, :, 3] > 0
    return op & ~((r > 170) & (g > 150)) & ~((r + g + b) < 80)


def frame_image(k, state, i, n, orig, base):
    """(png Image, dx, dy) for one original bitmap."""
    a = np.array(orig)
    op = a[:, :, 3] > 0
    ys, xs = np.nonzero(op)
    if len(xs) == 0:
        return orig, 0, 0
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    rig = k['rig']
    pose = goat_pose(state, i, n) if rig == 'goat' else pose_for(state, i, n)
    if isinstance(pose, tuple) or (state == 'dash'):
        kind = 'dash' if state == 'dash' else pose[0]
        if kind == 'wheel':
            im, anc = render_wheel(k, i)
            return im, int(round((x0 + x1) / 2 - anc[0])), int(y1 - im.height)
        fur = is_fur(a, base)
        fys, fxs = np.nonzero(fur)
        if kind == 'dash':
            # the ball is the right-most blob; keep the dust to its left from the original
            bx0 = int(np.percentile(fxs, 30)) if len(fxs) else x0
            cols = fxs[fxs >= bx0]
            rows = fys[fxs >= bx0]
            if len(cols) < 20:      # no body colour found: the right half of the drawing is the ball
                cols, rows = xs[xs >= (x0 + x1) / 2], ys[xs >= (x0 + x1) / 2]
            cx, cy = (cols.min() + cols.max() + 1) / 2, (rows.min() + rows.max() + 1) / 2
            r = max(cols.max() + 1 - cols.min(), rows.max() + 1 - rows.min()) / 2
            out = orig.copy()
            px = np.array(out)
            dist = np.hypot(np.arange(px.shape[1])[None, :] - cx, np.arange(px.shape[0])[:, None] - cy)
            px[dist < r + 1.5] = 0
            out = Image.fromarray(px, 'RGBA')
            ball = render_ball(k, i, r * .92, squash=1.12)
            out.alpha_composite(ball, (int(round(cx - ball.width / 2)), int(round(cy - ball.height / 2))))
            return out, 0, 0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        r = min(x1 - x0, y1 - y0) / 2 - .5
        ball = render_ball(k, i, r, 'swirl' if (state == 'jump' and i == 1) else 'ball')
        if rig == 'goat':
            hp = Pen(ball.width + 12, ball.height + 12, ((ball.width + 12) / 2, (ball.height + 12) / 2))
            hp.im.paste(ball.resize((ball.width * SS, ball.height * SS), Image.NEAREST), (6 * SS, 6 * SS))
            H_goat_head(hp, rot((r * .55, 0), i * math.pi / 2 - .6), .8, i * math.pi / 2, None, tongue=False)
            ball = hp.reduce()
        return ball, int(round(cx - ball.width / 2)), int(round(cy - ball.height / 2))
    if pose.get('swing'):
        # hands on the pole, body pointing from the pole to where the original figure is
        cxm, cym = xs.mean(), ys.mean()
        ang = math.atan2(cxm - PIVOT[0], cym - PIVOT[1])
        im, anc = render_figure(k, dict(pose, rot=math.degrees(-ang) + 180))
        # find the hands: the figure is rotated around (0, -14); place the end nearest the pole there
        fa = np.array(im)[:, :, 3] > 0
        fy, fx = np.nonzero(fa)
        dvec = (math.sin(ang), math.cos(ang))
        proj = fx * dvec[0] + fy * dvec[1]
        j = proj.argmin()
        return im, int(round(PIVOT[0] - fx[j])), int(round(PIVOT[1] - fy[j]))
    im, anc = render_figure(k, pose)
    if pose.get('rot'):
        return im, int(round((x0 + x1) / 2 - im.width / 2)), int(round((y0 + y1) / 2 - im.height / 2))
    return im, int(round((x0 + x1) / 2 - im.width / 2 + (anc[0] - im.width / 2) * .5)), int(y1 - im.height)


# ------------------------------------------------------------------ recolours of the real sprites
def recolor(img, mode):
    a = np.array(img.convert('RGBA')).astype(np.float32)
    out = a.copy()
    r, g, b = a[:, :, 0] / 255, a[:, :, 1] / 255, a[:, :, 2] / 255
    for y in range(a.shape[0]):
        for x in range(a.shape[1]):
            if a[y, x, 3] == 0:
                continue
            h, l, s = colorsys.rgb_to_hls(r[y, x], g[y, x], b[y, x])
            hd = h * 360
            if mode in ('gold', 'green') and 195 <= hd <= 255 and s > .25:
                nh = 48 if mode == 'gold' else 115
                l2 = min(.92, l * (1.35 if mode == 'gold' else 1.05) + (.12 if mode == 'gold' else 0))
                rr, gg, bb = colorsys.hls_to_rgb(nh / 360, l2, min(1, s * 1.05))
            elif mode == 'gold' and 80 <= hd <= 170 and s > .3:
                rr, gg, bb = colorsys.hls_to_rgb(0, l, s)            # green eyes -> red
            elif mode == 'silver' and 195 <= hd <= 255 and s > .25:
                rr, gg, bb = colorsys.hls_to_rgb(.6, min(.95, .45 + l * .8), .1)  # borrowed blue frames -> silver
            elif mode == 'silver' and l < .32 and s < .5:
                rr, gg, bb = colorsys.hls_to_rgb(.6, .62 + l * .9, .08)  # black fur -> silver
            elif mode == 'silver' and (hd < 20 or hd > 340) and s > .4:
                rr, gg, bb = colorsys.hls_to_rgb(185 / 360, l, s)    # red stripes -> cyan
            elif mode == 'green' and 80 <= hd <= 170 and s > .3:
                rr, gg, bb = colorsys.hls_to_rgb(.0, l * .9, s)      # eyes -> red
            else:
                continue
            out[y, x, :3] = (rr * 255, gg * 255, bb * 255)
    return Image.fromarray(out.clip(0, 255).astype(np.uint8), 'RGBA')


# ------------------------------------------------------------------ big art (menu preview, level intro, life icon)
def art(k, size, kind):
    """kind: 'select' | 'intro' | 'icon'."""
    w, h = size
    if k['rig'] == 'goat':
        if kind == 'icon':
            p = Pen(w * 2, h * 2, (w, h))
            H_goat_head(p, (0, 0), 1.1, 0, None)
            im = p.reduce()
            return fit(im.crop(im.getbbox()), size)
        sc = (w - 6) / 32
        im, anc = render_figure(k, dict(goat_pose('stand', 0, 1), head=-8), scale=sc)
        return fit(im, size)
    if kind == 'icon':
        if k['R'] <= 0:
            im, anc = render_figure(k, pose_for('stand', 0, 1), scale=.6)
            return fit(im, size)
        sc = (h - 3) / (2.7 * k['R'])
        p = Pen(w * 2, h * 2, (w, h), sc)
        k['head'](p, (0, 0), k['R'], 0, k, None)
        im = p.reduce()
        return fit(im.crop(im.getbbox()), size)
    pose = dict(hipF=14, kneeF=10, hipB=-10, kneeB=6, shF=120, elF=70, shB=-20, elB=30, head=-6)
    if kind == 'select':
        pose = dict(hipF=10, kneeF=6, hipB=-8, kneeB=4, shF=35, elF=80, shB=-15, elB=40, head=-4)
    if k['R'] <= 0:     # face on the body: keep the arms beside it
        pose.update(shF=-35, elF=20, shB=-45, elB=10)
    im, anc = render_figure(k, pose, scale=1.0)
    sc = min((w - 4) / im.width, (h - 4) / im.height)
    im, anc = render_figure(k, pose, scale=sc)
    return fit(im, size)


def fit(im, size):
    w, h = size
    if im.width > w or im.height > h:
        im = im.copy()
        im.thumbnail((w, h), Image.NEAREST)
    out = Image.new('RGBA', size, (0, 0, 0, 0))
    out.alpha_composite(im, ((w - im.width) // 2, h - im.height - 2 if h - im.height - 2 >= 0 else 0))
    return out


# ------------------------------------------------------------------ swf structure (from swf.xml)
class Swf:
    def __init__(self, path):
        root = ET.parse(path).getroot()
        self.by = {}
        for t in root.find('tags'):
            for key in ('spriteId', 'shapeId', 'characterID'):
                if t.get(key) is not None:
                    self.by[int(t.get(key))] = t
                    break

    def frames(self, sid):
        sp = self.by[sid]
        dl, out, labels = {}, [], {}
        for s in sp.find('subTags'):
            ty = s.get('type', '')
            if ty.startswith('PlaceObject'):
                if s.get('characterId') is not None and s.get('placeFlagHasCharacter', 'true') != 'false':
                    dl[int(s.get('depth'))] = int(s.get('characterId'))
            elif ty.startswith('RemoveObject'):
                dl.pop(int(s.get('depth')), None)
            elif ty == 'FrameLabelTag':
                labels[len(out)] = s.get('name')
            elif ty == 'ShowFrameTag':
                out.append(dict(dl))
        return out, labels

    def bitmaps(self, cid, seen=None):
        """bitmap ids under a character, in display order."""
        seen = seen if seen is not None else set()
        t = self.by.get(cid)
        if t is None or cid in seen:
            return []
        seen.add(cid)
        if t.get('type', '').startswith('DefineShape'):
            return [int(e.get('bitmapId')) for e in t.iter() if e.get('bitmapId') and e.get('bitmapId') != '65535']
        if t.get('type') == 'DefineSpriteTag':
            res = []
            for f in self.frames(cid)[0]:
                for d in sorted(f):
                    for b in self.bitmaps(f[d], seen):
                        if b not in res:
                            res.append(b)
            return res
        return []

    def poses(self, sid):
        """bitmap id -> (state, index, count) for a character sprite."""
        fr, labels = self.frames(sid)
        res = {}
        starts = sorted(labels)
        for li, f in enumerate(starts):
            name = labels[f]
            end = starts[li + 1] if li + 1 < len(starts) else len(fr)
            seq = []
            for ff in range(f, end):
                for d, c in sorted(fr[ff].items()):
                    for b in self.bitmaps(c, set()):
                        if b not in seq:
                            seq.append(b)
            for i, b in enumerate(seq):
                res.setdefault(b, (name, i, len(seq)))
        return res

    def label_bitmap(self, sid, label):
        fr, labels = self.frames(sid)
        f = [k for k, v in labels.items() if v == label][0]
        for d, c in sorted(fr[f].items()):
            bs = self.bitmaps(c, set())
            if bs:
                return bs[0]


def main():
    sheet = '--sheet' in sys.argv
    only = [a for a in sys.argv[2:] if not a.startswith('--')]
    swf = Swf(os.path.join(W, 'swf.xml'))
    os.makedirs(OUT, exist_ok=True)
    spec = []
    roster = []
    for k in CHARS:
        if only and k['id'] not in only:
            continue
        cid, base = k['id'], k['base']
        d = os.path.join(OUT, cid)
        os.makedirs(d, exist_ok=True)
        poses = swf.poses(BASE_SPRITE[base])
        lines, cells = [], []
        for bid, (state, i, n) in sorted(poses.items()):
            orig = Image.open(os.path.join(IMG, f'{bid}.png')).convert('RGBA')
            if k['rig'] == 'recolor':
                im, dx, dy = recolor(orig, k['recolor']), 0, 0
            else:
                im, dx, dy = frame_image(k, state, i, n, orig, base)
            fn = os.path.join(d, f'{bid}.png')
            im.save(fn)
            lines.append(f'img\t{bid}\t{fn}\t{dx}\t{dy}')
            cells.append((state, i, orig, im, dx, dy))
        spec += [f'clone\t{BASE_SPRITE[base]}\t{cid}'] + lines + ['end']
        # menu preview (4 images of the select_ sprite)
        sel = swf.bitmaps(SELECT[base])
        lines = []
        for j, bid in enumerate(sel):
            orig = Image.open(os.path.join(IMG, f'{bid}.png')).convert('RGBA')
            im = recolor(orig, k['recolor']) if k['rig'] == 'recolor' else art(k, orig.size, 'select')
            fn = os.path.join(d, f'select_{j}.png')
            im.save(fn)
            lines.append(f'img\t{bid}\t{fn}\t0\t0')
        spec += [f'clone\t{SELECT[base]}\tselect_{cid}'] + lines + ['end']
        # level intro art + life icon: new labelled frames
        for sp, kind in ((ART_SPRITE, 'intro'), (ICON_SPRITE, 'icon')):
            bid = swf.label_bitmap(sp, base)
            orig = Image.open(os.path.join(IMG, f'{bid}.png')).convert('RGBA')
            im = recolor(orig, k['recolor']) if k['rig'] == 'recolor' else art(k, orig.size, kind)
            fn = os.path.join(d, f'{kind}.png')
            im.save(fn)
            spec += [f'frame\t{sp}\t{cid}\t{base}', f'img\t{bid}\t{fn}\t0\t0', 'end']
        twin = TWIN.get(cid, base)
        for sp in COLOUR_SPRITES:
            spec += [f'frame\t{sp}\t{cid}\t{twin}', 'end']
        roster.append(dict(id=cid, he=k['he'], base=base))
        if sheet:
            make_sheet(cells, os.path.join(OUT, f'sheet_{cid}.png'), d)
        print(cid, len(poses), 'frames')
    with open(os.path.join(OUT, 'spec.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(spec) + '\n')
    if not only:
        with open(os.path.join(OUT, 'roster.json'), 'w', encoding='utf-8') as f:
            json.dump(roster, f, ensure_ascii=False, indent=1)


def make_sheet(cells, out, d):
    """original (faint) + new frame at its placed offset, per animation row."""
    Z, cell = 3, 64
    states = []
    for c in cells:
        if c[0] not in states:
            states.append(c[0])
    rows = {s: sorted([c for c in cells if c[0] == s], key=lambda c: c[1]) for s in states}
    width = max(len(v) for v in rows.values())
    C = cell * Z
    sh = Image.new('RGBA', (60 + width * C, len(states) * C), (90, 90, 130, 255))
    dr = ImageDraw.Draw(sh)
    for r, s in enumerate(states):
        for j, (state, i, orig, im, dx, dy) in enumerate(rows[s]):
            ox, oy = min(0, dx), min(0, dy)
            cw, chh = max(orig.width, dx + im.width) - ox, max(orig.height, dy + im.height) - oy
            canvas = Image.new('RGBA', (cw, chh), (0, 0, 0, 0))
            g = orig.copy()
            g.putalpha(orig.getchannel('A').point(lambda v: v // 4))
            canvas.alpha_composite(g, (-ox, -oy))
            canvas.alpha_composite(im, (dx - ox, dy - oy))
            canvas = canvas.resize((cw * Z, chh * Z), Image.NEAREST)
            canvas.thumbnail((C - 2, C - 2), Image.NEAREST)
            sh.alpha_composite(canvas, (60 + j * C, r * C))
        dr.text((2, r * C + 2), s, fill=(255, 255, 255, 255))
    sh.save(out)


if __name__ == '__main__':
    main()
