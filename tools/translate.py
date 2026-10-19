"""Hebrew translation of Ultimate Flash Sonic.

Writes, from the JPEXS dumps in work/:
  work/he/fonts.txt          fonts that get Hebrew glyphs (read by HeTool)
  work/he/texts/<id>.txt     new formatted text for each text tag (read by HeTool)
  work/he/scripts/...        patched copies of the ActionScript files (for ffdec -importScript)

Flash (classic text) has no bidi, so every Hebrew string is stored in visual order (see vis()).
Run: python -I tools/translate.py <project dir>
"""
import os
import re
import shutil
import sys

from PIL import ImageFont

ROOT = sys.argv[1]
W = os.path.join(ROOT, 'work')
OUT = os.path.join(W, 'he')
FONTS = os.path.join(ROOT, 'tools', 'fonts')

HEB_FONT = {37: 'SecularOne.ttf', 136: 'SecularOne.ttf', 2512: 'Rubik.ttf'}
# FFF Harmony is a DefineFont 1 tag (JPEXS can't add glyphs to it): its texts move to font 2512
REPLACE_FONT = {2463: 2512}
ORIG_FONT = {37: '37_Vipnagorgialla.ttf', 136: '136_Trebuchet MS.ttf', 2463: '2463_FFF Harmony.ttf',
             2512: '2512_Times New Roman.ttf'}
EXTRA_CHARS = '\'"-:.,!?()/0123456789 '


# ---------------------------------------------------------------- bidi
def is_hebrew(c):
    return '\u0590' <= c <= '\u05FF'


LTR_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._@/:'_-]*[A-Za-z0-9])?")
MIRROR = str.maketrans('()[]<>', ')(][><')


def vis(s):
    """Logical Hebrew (RTL paragraph) -> visual order for left-to-right rendering."""
    out = []
    for line in s.split('\n'):
        parts, pos = [], 0
        for m in LTR_RE.finditer(line):
            if m.start() > pos:
                parts.append(('n', line[pos:m.start()]))
            parts.append(('l', m.group()))
            pos = m.end()
        if pos < len(line):
            parts.append(('n', line[pos:]))
        res = []
        for kind, txt in reversed(parts):
            res.append(txt if kind == 'l' else txt[::-1].translate(MIRROR))
        out.append(''.join(res))
    return '\n'.join(out)


# ---------------------------------------------------------------- static / edit texts
# id -> (anchor, [lines]) ; anchor: c = keep each line's centre, R = right edge of the block,
#                          r = keep each line's right edge, l = keep left edge.
TEXTS = {
    77: ('c', ['המשחק נגמר']),
    91: ('c', ['תודה ששיחקתם']),
    150: ('l', ['יער העלים']),
    151: ('l', ['מערכה: גני הצינה']),
    2433: ('c', ['דניס גיד']), 2434: ('c', ['דניס גיד']), 2435: ('c', ['דניס גיד']),
    2436: ('c', ['דניס גיד']), 2437: ('c', ['דניס גיד']),
    2443: ('c', ['סוניק פלאש האולטימטיבי']),
    2444: ('R', ['המשחק נשמר באמצעות סיסמה. כדי לקבל או להזין',
                 'סיסמה, בחרו "סיסמה" בתפריט הראשי.']),
    2446: ('c', ['שמירה בסיסמה']),
    2447: ('R', ['תזוזה: חץ ימינה / שמאלה',
                 'קפיצה: רווח',
                 'ספין-דאש: החזיקו למטה, לחצו רווח ואז שחררו',
                 'השהיה: אנטר']),
    2449: ('c', ['מקשים']),
    2452: ('r', ['טוען:']),
    2457: ('c', ['התחל']), 2458: ('c', ['התחל']),
    2464: ('l', ['דוא"ל: dennis_g@bluemail.ch']),
    2469: ('c', ['המשחק המקורי מאת']),
    2470: ('c', ['זה אינו משחק סוניק רשמי.',
                 'המשחק אינו ממומן על ידי סגה או סוניק טים',
                 'בכל מקרה, סוניק טים הכי טובים!',
                 'מחיאות כפיים לסוניק טים',
                 'לכו לקנות את סוניק אדוונס 2 עכשיו!',
                 'המשחק הכי טוב שנוצר אי פעם']),
    2472: ('c', ['גרסת הפלאש נוצרה על ידי']),
    2513: ('c', ['אפקטים קוליים']),
    2516: ('c', ['מוזיקה']),
    2528: ('c', ['מערכה']), 2529: ('c', ['מערכה']), 2530: ('c', ['מערכה']),
    2532: ('c', ['זמן שיא']), 2533: ('c', ['זמן שיא']), 2534: ('c', ['זמן שיא']),
    2605: ('c', ['השהיה']), 2606: ('c', ['השהיה']),
    2607: ('c', ['המשך']),
    2608: ('c', ['יציאה']),
    2623: ('c', ['תיבת נגינה']), 2624: ('c', ['תיבת נגינה']),
    2626: ('l', ['יער העלים']),
    2627: ('l', ['גן עדן קפוא']),
    2628: ('l', ['צוות רוז']),
    2629: ('l', ['מוזיקת תפריט']),
    2630: ('l', ['בחירת שלב']),
    2631: ('l', ['קרדיטים']),
    2632: ('l', ['בוס']),
    2633: ('l', ['בוס - קרב מכריע']),
    2647: ('c', ['התחל משחק']),
    2648: ('c', ['אפשרויות']),
}
# dynamic (DefineEditText) initial texts; most are overwritten by the scripts at run time
EDITS = {
    38: 'סוניק עבר את מערכה 1', 39: 'סוניק עבר את מערכה 1',
    48: 'בונוס טבעות: 2000', 49: 'בונוס טבעות: 2000',
    57: 'אזור 1', 59: 'שם האזור', 69: 'מערכה 1', 71: 'פארק הדולפינים',
    82: 'דניס גיד', 83: 'מתכנת',
    137: 'נאקלס סיים את המשחק',
    2487: 'סוניק', 2496: 'יער העלים', 2508: 'סוניק הקיפוד', 2526: 'סוניק',
}

# ---------------------------------------------------------------- script strings
NAMES = {'sonic': 'סוניק', 'tails': 'טיילס', 'knuckles': 'נאקלס', 'cream': 'קרים', 'amy': 'איימי',
         'shadow': 'שאדו'}
FEMALE = {'cream', 'amy', 'peach'}
# new characters (tools/make_chars.py): id, Hebrew name, base character (abilities + animation labels)
_roster = os.path.join(W, 'chars', 'roster.json')
ROSTER = [dict(id=k, he=n, base=k) for k, n in NAMES.items()]
if os.path.exists(_roster):
    import json
    ROSTER += json.load(open(_roster, encoding='utf-8'))
    NAMES.update({c['id']: c['he'] for c in ROSTER})
GOT = {k: f'{n} {"עברה" if k in FEMALE else "עבר"} את מערכה' for k, n in NAMES.items()}
CLEAR = {k: f'{n} {"סיימה" if k in FEMALE else "סיים"} את המשחק!' for k, n in NAMES.items()}


def q(s):
    """AS string literal of the visual form of s."""
    return '"' + vis(s).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def obj(name, d):
    return ''.join(f'{name}.{k} = {q(v)};\n' for k, v in d.items())


S = 'DefineSprite_113_credits/frame_1/PlaceObject2_84_2/CLIPACTIONRECORD onClipEvent(load).as'
MENU = 'frame_291/PlaceObject2_2497_4/CLIPACTIONRECORD onClipEvent(load).as'
MENU2 = 'frame_291/PlaceObject2_2497_4/CLIPACTIONRECORD onClipEvent(load)_2.as'
MENU3 = 'frame_291/PlaceObject2_2497_4/CLIPACTIONRECORD onClipEvent(load)_3.as'
REC = 'frame_309/PlaceObject2_2523_15/CLIPACTIONRECORD onClipEvent(load).as'
INIT = 'frame_290/DoAction.as'


def lit(old, new):
    """Replace the string literal "old" by the visual Hebrew literal of new."""
    return ('"' + old + '"', q(new))


# Fullscreen / maximized window: keep the 350x250 stage centred and paint everything outside it
# black (the player otherwise shows off-stage objects in the letterbox area).
CURTAIN = '''Stage.scaleMode = "showAll";
Stage.align = "";
var cur = _root.createEmptyMovieClip("he_curtain", 1048000);
var box = [[-9000, -9000, 9350, 0], [-9000, 250, 9350, 9250], [-9000, 0, 0, 250], [350, 0, 9350, 250]];
for(var i = 0; i < 4; i++)
{
   var b = box[i];
   cur.beginFill(0, 100);
   cur.moveTo(b[0], b[1]); cur.lineTo(b[2], b[1]); cur.lineTo(b[2], b[3]); cur.lineTo(b[0], b[3]); cur.lineTo(b[0], b[1]);
   cur.endFill();
}
stop();'''

SCRIPTS = {
    'frame_1/DoAction.as': [('stop();', CURTAIN)],
    INIT: [
        lit('sonic-run 2', 'ריצת סוניק 2'), lit('tails follow', 'טיילס עוקב'), lit('behind', 'מאחור'),
        lit('big-cheese', 'צ\'יז ענק'), lit('moon', 'ירח'),
        lit('spinning egg', 'הביצה המסתובבת'), lit('egg bomber', 'מפציץ הביצה'),
        lit('LEAF FOREST', 'יער העלים'), lit('chill gardens', 'גני הצינה'), lit('emerald forest', 'יער האזמרגד'),
        lit('ICE PARADISE', 'גן עדן קפוא'), lit('snowy mountain', 'הר מושלג'), lit('frosty island', 'אי הכפור'),
        lit('emerald coast', 'חוף האזמרגד'), lit('green hill', 'הגבעה הירוקה'),
        lit('ENERGY PLANT', 'תחנת הכוח'), lit('powersource', 'מקור הכוח'), lit('omega station', 'תחנת אומגה'),
        lit('thunderstorm', 'סופת רעמים'), lit('ultimate showdown', 'העימות האחרון'),
        lit('RED MOUNTAIN', 'ההר האדום'), lit('windy valley', 'עמק הרוחות'), lit('mystic cave', 'המערה המסתורית'),
        ('_root.zones = 2;',
         '_root.zones = 2;\n_root.hename = new Array();\n' + obj('_root.hename', NAMES)
         + '_root.hegot = new Array();\n' + obj('_root.hegot', GOT)
         + '_root.heclear = new Array();\n' + obj('_root.heclear', CLEAR)),
        # roster: menu order, names, base character; every character starts with its own save slot
        ('_root.save.shadow = "01";',
         '_root.save.shadow = "01";\n_root.roster = new Array();\n_root.rname = new Array();\n_root.cbase = new Array();\n'
         + ''.join(f'_root.roster.push("{c["id"]}");\n_root.rname.{c["id"]} = {q(c["he"])};\n'
                   f'_root.cbase.{c["id"]} = "{c["base"]}";\n' for c in ROSTER)
         + ''.join(f'_root.save.{c["id"]} = "01";\n' for c in ROSTER[6:])),
    ],
    # the player clip: art of the chosen character, abilities of its base character
    'frame_327/PlaceObject2_2556_25/CLIPACTIONRECORD onClipEvent(load).as': [
        ('chara = _root.chara;\n   this.attachMovie(chara,"sonic",1);',
         'chara = _root.cbase[_root.chara];\n   this.attachMovie(_root.chara,"sonic",1);')],
    'frame_291/PlaceObject2_2500_41/CLIPACTIONRECORD onClipEvent(enterFrame).as': [
        ('_root.balken.chara = this[_root.chara];',
         '_root.balken.chara = this[_root.chara] == undefined ? _root.rname[_root.chara] : this[_root.chara];')],
    MENU: [
        lit('start game', 'התחל משחק'), lit('options', 'אפשרויות'), lit('password', 'סיסמה'),
        lit('cheats', 'צ\'יטים'), lit('main', 'תפריט ראשי'),
        lit('FX Volume', 'עוצמת אפקטים'), lit('Music Volume', 'עוצמת מוזיקה'), lit('back', 'חזרה'),
        lit('main game', 'משחק רגיל'), lit('time trial', 'נגד השעון'), lit('play', 'שחק'),
        lit('view records', 'צפייה בשיאים'), lit('character select', 'בחירת דמות'),
        # character select = "previous / <name> / next" (the roster is longer than the menu)
        ('chara[1] = "Sonic";\n   chara[2] = "Tails";\n   chara[3] = "Knuckles";\n   chara[4] = "Cream";\n'
         '   chara[5] = "Amy";\n   chara[6] = "Shadow";',
         f'chara[1] = {q("דמות קודמת")};\n   chara[2] = " ";\n   chara[3] = {q("דמות הבאה")};\n'
         '   chara[4] = "";\n   chara[5] = "";\n   chara[6] = "";'),
        lit('Start Game', 'התחל משחק'),
        lit('enter password', 'הזנת סיסמה'), lit('get password', 'קבלת סיסמה'),
        lit('get password:', 'קבלת סיסמה:'), lit('your password:', 'הסיסמה שלך:'), lit('empty', 'ריק'),
        lit('enter password:', 'הזנת סיסמה:'), lit('enter passwd:', 'הזינו סיסמה:'),
        lit('type here', 'הקלידו כאן'), lit('enter', 'אישור'),
    ],
    MENU2: [lit('BACK', 'חזרה'), lit('no cheats', 'אין צ\'יטים'),
            ('               if(a == 5)\n',
             '               if(a == 2)\n               {\n                  this["b" add a].t = _root.rname[_root.chara];\n'
             '               }\n               else if(a == 5)\n')],
    MENU3: [
        # previous / next walk through _root.roster (one step per press), start + back as before
        (re.compile(r'function charaf\(\)\s*\{.*?\n   \}\n(?=   function optionsf)', re.S),
         'function charaf()\n   {\n      var on = 0;\n'
         '      if(this.b1.d == "on")\n      {\n         on = -1;\n      }\n'
         '      else if(this.b2.d == "on" || this.b3.d == "on")\n      {\n         on = 1;\n      }\n'
         '      if(on != 0 && pick != "held" && _root.character.character._currentframe == 1)\n      {\n'
         '         pick = "held";\n         var n = _root.roster.length;\n         var i = 0;\n'
         '         while(i < n && _root.roster[i] != _root.chara)\n         {\n            i++;\n         }\n'
         '         i = (i + n + on) % n;\n         _root.chara = _root.roster[i];\n'
         '         this.b2.t = _root.rname[_root.chara];\n      }\n'
         '      if(on == 0)\n      {\n         pick = "off";\n      }\n'
         '      if(this.b7.d == "on")\n      {\n         _root.character.character.play();\n      }\n'
         '      else if(this.b8.d == "on")\n      {\n         back(8);\n      }\n   }\n'),
        lit('invalid passwd', 'סיסמה שגויה'), lit('accepted', 'הסיסמה התקבלה'),
        ('this["b" add a].t = (this["b" add a].t add ": off").toUpperCase();',
         f'this["b" add a].t = {q("כבוי")} add ": " add this["b" add a].t;'),
        ('this["b" add a].t = (this["b" add a].t add ": on").toUpperCase();',
         f'this["b" add a].t = {q("פעיל")} add ": " add this["b" add a].t;'),
    ],
    'frame_291/PlaceObject2_2500_41/CLIPACTIONRECORD onClipEvent(load).as': [
        lit('SONIC THE HEDGEHOG', 'סוניק הקיפוד'), lit("MILES \\'tails\\' PROWER", 'מיילס "טיילס" פראואר'),
        lit('AMY ROSE', 'איימי רוז'), lit('CREAM THE RABBIT', 'קרים הארנבת'),
        lit('KNUCKLES THE ECHIDNA', 'נאקלס האכידנה'), lit('SHADOW THE HEDGEHOG', 'שאדו הקיפוד'),
    ],
    REC: [
        lit('back', 'חזרה'), lit('BACK', 'חזרה'),
        ('"best time: " add _root.record[currentzone add "-" add currentact];',
         f'_root.record[currentzone add "-" add currentact] add " :" add {q("זמן שיא")};'),
        ('"character: " add _root.record[currentzone add "-" add currentact add "-char"];',
         f'_root.hename[_root.record[currentzone add "-" add currentact add "-char"]] add " :" add {q("דמות")};'),
    ],
    'frame_314/PlaceObject2_2537_15/CLIPACTIONRECORD onClipEvent(load).as': [lit('BACK', 'חזרה')],
    'frame_309/PlaceObject2_2536_59/CLIPACTIONRECORD onClipEvent(enterFrame).as': [lit('RECORDS', 'שיאים')],
    'frame_314/PlaceObject2_2538_59/CLIPACTIONRECORD onClipEvent(enterFrame).as': [lit('LEVEL SELECT', 'בחירת שלב')],
    'DefineSprite_40/frame_1/DoAction.as': [
        ('_root.chara.toUpperCase() add " GOT TROUGH ACT " add _root.cact;',
         '_root.cact add " " add _root.hegot[_root.chara];')],
    'DefineSprite_58/frame_1/DoAction.as': [('"ZONE " add _root.czone;', f'_root.czone add " " add {q("אזור")};')],
    'DefineSprite_70/frame_1/DoAction.as': [lit('BOSS', 'בוס'),
                                            ('"ACT " add _root.cact;', f'_root.cact add " " add {q("מערכה")};')],
    'DefineSprite_138/frame_1/DoAction.as': [
        ('t = _root.chara.toUpperCase();', 't = _root.heclear[_root.chara];'),
        ('t = t add "\\\'s";', ''),
        ('t = t add " GAME CLEARED";', ''),
    ],
    'DefineSprite_55_leveloutro/frame_26/PlaceObject2_50_3/CLIPACTIONRECORD onClipEvent(enterFrame).as': [
        ('t = s add " : " add _root.leveloutro[this.s];',
         f'lbl = {q("ניקוד")};\n   if(s == "ringbonus")\n   {{\n      lbl = {q("בונוס טבעות")};\n   }}\n'
         f'   if(s == "timebonus")\n   {{\n      lbl = {q("בונוס זמן")};\n   }}\n'
         '   t = _root.leveloutro[this.s] add " : " add lbl;')],
    'DefineSprite_146_End/frame_1/DoAction.as': [
        lit('works only with sonic', 'עובד רק עם סוניק'), lit("doesn\\'t work with tails", 'לא עובד עם טיילס'),
        lit('works only with cream', 'עובד רק עם קרים'),
        lit('NEW CHARACTER: Amy Rose\\n', 'דמות חדשה: איימי רוז\n'),
        lit('NEW CHARACTER: Shadow\\n', 'דמות חדשה: שאדו\n'),
        lit('JUKEBOX unlocked:\\n', 'תיבת הנגינה נפתחה:\n'),
        lit('select your favorite\\ntrack while pause', 'בחרו את השיר האהוב עליכם\nבזמן השהיה'),
        lit("CONGRATULATIONS\\nYou\\'ve completed the\\nwhole game!!", 'כל הכבוד!\nסיימתם את\nכל המשחק!!'),
        ('"NEW CHEAT: " add _root.cheat[num add "-name"] add "\\n" add message[num];',
         '_root.cheat[num add "-name"] add " :" add ' + q("צ'יט חדש") + ' add "\\n" add message[num];'),
    ],
    S: [
        lit('ultimate flash sonic', 'סוניק פלאש האולטימטיבי'), lit('created by', 'נוצר על ידי'),
        lit('original game by', 'המשחק המקורי מאת'), lit('SONIC-TEAM', 'סוניק טים'), lit('Sonic-Team', 'סוניק טים'),
        lit('programmer', 'תכנות'), lit('DENNIS_GID', 'דניס גיד'), lit('CHARACTER SPRITES', 'ציורי הדמויות'),
        lit('ripped by', 'חולצו על ידי'), lit('DanielSidney', 'דניאל סידני'), lit('ENDING SPRITES', 'ציורי הסיום'),
        lit('Dioxas', 'דיוקסס'), lit('music / sound FX', 'מוזיקה / אפקטים'), lit('leveldesign', 'עיצוב שלבים'),
        lit('Sonic-Team rules!', 'סוניק טים הכי טובים!'), lit('NOW GO AND BUY', 'עכשיו לכו לקנות את'),
        lit('SONIC ADVANCE 2!!!', 'סוניק אדוונס 2!!!'), lit('THE BEST GAME EVER', 'המשחק הכי טוב אי פעם'),
    ],
}


# ---------------------------------------------------------------- formatted text helpers
def parse(fmt):
    """-> header params (str), [(params str, text)]"""
    blocks = re.findall(r'\[([^\]]*)\]([^\[]*)', fmt)
    return blocks[0][0], blocks[1:] if not blocks[0][1] else [('', blocks[0][1])] + blocks[1:]


def kv(params):
    d = {}
    for line in params.strip().split('\n'):
        p = line.strip().split(' ', 1)
        if p[0]:
            d.setdefault(p[0], p[1] if len(p) > 1 else '')
    return d


_fcache = {}


def font(path, size):
    k = (path, size)
    if k not in _fcache:
        _fcache[k] = ImageFont.truetype(path, size)
    return _fcache[k]


def width(text, fid, h, heb):
    """Advance width in twips. Hebrew letters come from the Hebrew font, everything else
    (spaces, digits, punctuation) keeps the original font's glyphs."""
    orig = font(os.path.join(W, 'ex', 'fonts', ORIG_FONT[fid]), 1024)
    hf = font(os.path.join(FONTS, HEB_FONT[fid]), 1024) if heb else orig
    return sum((hf if is_hebrew(c) else orig).getlength(c) for c in text) * h / 1024


def static_text(fid_default, fmt, anchor, lines):
    header, segs = parse(fmt)
    hd = kv(header)
    state = {'x': 0, 'font': fid_default, 'height': 240}
    olds = []
    for params, text in segs:
        d = kv(params)
        for k in ('x', 'font', 'height'):
            if k in d:
                state[k] = int(d[k])
        w = width(text.rstrip('\n'), state['font'], state['height'], False)
        olds.append((dict(state), d, w))
    assert len(olds) == len(lines), (len(olds), len(lines), fmt)
    # 'R': right edge of the block, pulled in by the original left margin (mirrored layout)
    block_r = max(s['x'] + w for s, d, w in olds) - 200
    out, xs = [], []
    for (st, d, w), line in zip(olds, lines):
        nf = REPLACE_FONT.get(st['font'], st['font'])
        if 'font' in d:
            d['font'] = str(nf)
        nw = width(line, nf, st['height'], True)
        x = {'c': st['x'] + w / 2 - nw / 2, 'R': block_r - nw, 'r': st['x'] + w - nw, 'l': st['x']}[anchor]
        x = int(round(x))
        xs.append((x, x + nw))
        keep = [f'{k} {v}' for k, v in d.items() if k in ('font', 'height', 'color', 'y', 'letterspacing')]
        out.append('[\n' + '\n'.join(keep + [f'x {x}']) + '\n]' + vis(line))
    hd['xmin'] = str(min(int(hd.get('xmin', 0)), int(min(a for a, b in xs))))
    hd['xmax'] = str(max(int(hd.get('xmax', 0)), int(max(b for a, b in xs))))
    return '[\n' + '\n'.join(f'{k} {v}' for k, v in hd.items()) + '\n]' + ''.join(out)


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, 'texts'))
    with open(os.path.join(OUT, 'fonts.txt'), 'w', encoding='utf-8') as f:
        for fid, ttf in HEB_FONT.items():
            f.write(f'{fid}\t{os.path.join(FONTS, ttf)}\t{EXTRA_CHARS}\n')
    for tid, (anchor, lines) in TEXTS.items():
        fmt = open(os.path.join(W, 'fmt', f'{tid}.txt'), encoding='utf-8').read()
        new = static_text(37, fmt, anchor, lines)
        open(os.path.join(OUT, 'texts', f'{tid}.txt'), 'w', encoding='utf-8').write(new)
    for tid, text in EDITS.items():
        fmt = open(os.path.join(W, 'fmt', f'{tid}.txt'), encoding='utf-8').read()
        new = fmt[:fmt.index(']') + 1] + vis(text)
        open(os.path.join(OUT, 'texts', f'{tid}.txt'), 'w', encoding='utf-8').write(new)
    src = os.path.join(W, 'ex', 'scripts')
    for rel, subs in SCRIPTS.items():
        code = open(os.path.join(src, rel), encoding='utf-8').read()
        for old, new in subs:
            if isinstance(old, re.Pattern):
                code, n = old.subn(lambda m: new, code)
            else:
                n = code.count(old)
                code = code.replace(old, new)
            if n == 0:
                sys.exit(f'not found in {rel}: {old}')
        dst = os.path.join(OUT, 'scripts', rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'w', encoding='utf-8').write(code)
    print(f'{len(TEXTS)} static, {len(EDITS)} edit texts, {len(SCRIPTS)} scripts')


if __name__ == '__main__':
    main()
