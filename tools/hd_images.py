"""xBRZ upscale of every bitmap of the SWF (pixel-art aware, keeps edges sharp).

usage: python -I hd_images.py <images dir (JPEXS export, <id>.png)> <fills.txt> <out dir> <factor> <xbrz_cli.exe>
fills.txt (HeTool fills): "<id>\t<repeat|clip>". Edge handling before scaling (4 px pad):
  opaque + repeat -> wrap (tiles stay seamless), opaque -> replicate edge (no dark/clear fringe
  between level pieces that sit side by side), transparent -> clear.
"""
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

PAD = 4


def xbrz(exe, a, factor, mode):
    a = np.pad(a, ((PAD, PAD), (PAD, PAD), (0, 0)), mode=mode)
    h, w = a.shape[:2]
    with tempfile.TemporaryDirectory() as td:
        src, dst = os.path.join(td, 'i.raw'), os.path.join(td, 'o.raw')
        a[:, :, [2, 1, 0, 3]].copy().tofile(src)
        subprocess.run([exe, src, str(w), str(h), str(factor), dst], check=True, stdout=subprocess.DEVNULL)
        out = np.fromfile(dst, np.uint8).reshape(h * factor, w * factor, 4)[:, :, [2, 1, 0, 3]]
    p = PAD * factor
    return np.ascontiguousarray(out[p:-p, p:-p])


def main(src, fills, out, factor, exe):
    factor = int(factor)
    use = dict(line.split('\t') for line in open(fills, encoding='utf-8').read().split('\n') if line)
    os.makedirs(out, exist_ok=True)

    def one(name):
        bid = name[:-4]
        dst = os.path.join(out, name)
        if bid not in use or os.path.exists(dst):
            return
        a = np.array(Image.open(os.path.join(src, name)).convert('RGBA'))
        opaque = bool((a[:, :, 3] == 255).all())
        mode = ('wrap' if use[bid] == 'repeat' else 'edge') if opaque else 'constant'
        hd = xbrz(exe, a, factor, mode)
        if opaque:
            hd[:, :, 3] = 255
        Image.fromarray(hd, 'RGBA').save(dst, optimize=False, compress_level=9)

    names = [f for f in os.listdir(src) if f.endswith('.png')]
    with ThreadPoolExecutor(os.cpu_count()) as ex:
        list(ex.map(one, names))
    print(f'{len(names)} images -> {out} ({factor}x)')


if __name__ == '__main__':
    main(*sys.argv[1:])
