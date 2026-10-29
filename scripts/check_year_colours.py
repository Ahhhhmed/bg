"""
Validates the construction-year group colours (docs/decisions.md C-07). Run
after touching web/years.js or the base palette in web/layers.js:

  python3 scripts/check_year_colours.py            # offline checks, exit 1 on failure
  python3 scripts/check_year_colours.py --relief   # + contrast on swisstopo's relief tiles (network)

Checks (one hue in four shades, C-07):
  1. (the first check, web vs print groups, belongs to the project the map came from)
  2. every group's OUTLINE >= MIN_CONTRAST against the map background (WCAG
     ratio). Pastel fills are too light to carry a 2:1 contrast themselves; the
     deeper same-hue outline carries the shape instead;
  3. every pair of FILLS >= MIN_DE apart (CIELAB dE76) for normal vision and
     under simulated deutan / protan / tritan vision (Machado et al. 2009,
     severity 1.0) -- so the groups stay tellable apart for colour-blind viewers;
  4. the newest group >= MIN_DE_BASE from the forest and park fills, and every
     other group >= MIN_DE_BASE_OTHER, read from web/layers.js;
  5. the fills get darker with year (CIELAB L* strictly decreasing): newer = darker;
  6. --relief: median contrast of the weakest outline on swisstopo's relief
     tiles (as web/relief.js draws them) at a flat and a steep spot.
Needs numpy (and Pillow for --relief).
"""
import io
import itertools
import math
import re
import sys
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MIN_CONTRAST = 3.0
MIN_DE = 20.0
MIN_DE_BASE = 20.0
MIN_DE_BASE_OTHER = 12.0
RELIEF_URL = ("https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissalti3d-reliefschattierung/"
              "default/current/3857/{z}/{x}/{y}.png")
RELIEF_SPOTS = {"flat (Bahnhofstrasse)": (8.539, 47.372), "steep (Uetliberg flank)": (8.495, 47.352)}

CVD = {
    "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "tritan": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]],
}


def rgb(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)]) / 255


def lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def luminance(c):
    return lin(c) @ np.array([0.2126, 0.7152, 0.0722])


def contrast(l1, l2):
    hi, lo = np.maximum(l1, l2), np.minimum(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def lab(c):
    xyz = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]) @ lin(c)
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def simulate(c, kind):
    l = np.clip(np.array(CVD[kind]) @ lin(c), 0, 1)
    return np.where(l <= 0.0031308, 12.92 * l, 1.055 * l ** (1 / 2.4) - 0.055)


def web_colours():
    """(fills, outlines) from web/years.js."""
    src = (ROOT / "web" / "years.js").read_text()
    block = src[src.index("const YEAR_GROUPS"):src.index("];", src.index("const YEAR_GROUPS"))]
    return (re.findall(r'color:\s*"(#[0-9a-fA-F]{6})"', block),
            re.findall(r'outline:\s*"(#[0-9a-fA-F]{6})"', block))


def base_colours():
    """Map background, forest, park fills and relief opacity from web/layers.js / relief.js."""
    src = (ROOT / "web" / "layers.js").read_text()
    pick = lambda k: re.search(k + r':\s*"(#[0-9a-fA-F]{6})"', src).group(1)
    rel = (ROOT / "web" / "relief.js").read_text()
    opacity = float(re.search(r'"raster-opacity":\s*([0-9.]+)', rel).group(1))
    return pick("land"), pick("forest"), pick("park"), opacity


def web_starts():
    """First year of each group in web/years.js (None = open start)."""
    src = (ROOT / "web" / "years.js").read_text()
    block = src[src.index("const YEAR_GROUPS"):src.index("];", src.index("const YEAR_GROUPS"))]
    return [None if f == "null" else int(f) for f in re.findall(r"from:\s*(null|\d+)", block)]


def relief_check(weakest, background, opacity):
    from PIL import Image
    bg, lw = rgb(background), luminance(rgb(weakest))
    for z in (14, 16):
        for name, (lon, lat) in RELIEF_SPOTS.items():
            n = 2 ** z
            x = int((lon + 180) / 360 * n)
            y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
            req = urllib.request.Request(RELIEF_URL.format(z=z, x=x, y=y), headers={"User-Agent": "bg-check"})
            im = np.asarray(Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=30).read())).convert("RGBA"))
            im = im.astype(float) / 255
            a = im[..., 3:] * opacity
            ground = bg * (1 - a) + im[..., :3] * a
            r = contrast(luminance(ground), lw)
            print(f"  relief z{z} {name:24s} median {np.median(r):.2f}:1, 5th pct {np.percentile(r, 5):.2f}:1")


def main():
    ok = True
    web, outlines = web_colours()
    starts_web = web_starts()
    background, forest, park, opacity = base_colours()
    print(f"web/years.js fills:    {web}")
    print(f"web/years.js outlines: {outlines}")
    print(f"group starts {starts_web}")
    print(f"background {background}, forest {forest}, park {park}, relief opacity {opacity}")
    if len(outlines) != len(web):
        print("FAIL every group in web/years.js needs an outline colour")
        ok = False

    bg = luminance(rgb(background))
    ratios = {c: float(contrast(luminance(rgb(c)), bg)) for c in outlines}
    for c, r in ratios.items():
        flag = "ok  " if r >= MIN_CONTRAST else "FAIL"
        ok &= r >= MIN_CONTRAST
        print(f"{flag} outline {c} contrast on {background}: {r:.2f}:1 (min {MIN_CONTRAST})")

    for kind in ["normal", *CVD]:
        cols = [rgb(c) if kind == "normal" else simulate(rgb(c), kind) for c in web]
        pairs = [(float(np.linalg.norm(lab(a) - lab(b))), web[i], web[j])
                 for (i, a), (j, b) in itertools.combinations(enumerate(cols), 2)]
        d, a, b = min(pairs)
        flag = "ok  " if d >= MIN_DE else "FAIL"
        ok &= d >= MIN_DE
        print(f"{flag} {kind:7s} closest fills {a} / {b}: dE {d:.1f} (min {MIN_DE})")

    for name, base in (("forest", forest), ("park", park)):
        for i, c in enumerate(web):
            d = float(np.linalg.norm(lab(rgb(c)) - lab(rgb(base))))
            need = MIN_DE_BASE if i == len(web) - 1 else MIN_DE_BASE_OTHER
            flag = "ok  " if d >= need else "FAIL"
            ok &= d >= need
            print(f"{flag} fill {c} vs {name} {base}: dE {d:.1f} (min {need})")

    lightness = [float(lab(rgb(c))[0]) for c in web]
    darker = all(a > b for a, b in zip(lightness, lightness[1:]))
    ok &= darker
    print(f"{'ok  ' if darker else 'FAIL'} fills get darker with year: L* {' > '.join(f'{v:.0f}' for v in lightness)}")

    if "--relief" in sys.argv:
        weakest = min(ratios, key=ratios.get)
        print(f"weakest outline {weakest} on swisstopo relief at {opacity:.0%} opacity:")
        relief_check(weakest, background, opacity)

    print("OK" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
