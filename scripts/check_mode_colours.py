"""
Validates the building colour modes (BUILDING_COLOR_MODES in web/layers.js) the way check_year_colours.py validates the year shades:

  python3 scripts/check_mode_colours.py      # exit 1 on failure

Per mode (the year mode is checked by check_year_colours.py):
  1. every pair of class fills >= MIN_DE (CIELAB dE76) apart, for normal
     vision and simulated deutan / protan / tritan vision;
  2. every class outline >= MIN_CONTRAST against the oat land (WCAG ratio);
  3. stepped modes get darker with the value (L* strictly decreasing);
  4. every fill >= MIN_DE_NODATA from the no-data greige and from the
     non-housing greige, so "no value" never reads as a class.
"""
import itertools
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from check_year_colours import CVD, contrast, lab, luminance, rgb, simulate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MIN_DE = 19.0          # the year shades keep 20; 19 lets four one-hue steps keep a usable lightest class
MIN_DE_MANY = 10.0     # modes with more than 5 classes (noise: 7 dB steps, heating: 7 sources; owner 2026-10-19)
MIN_CONTRAST = 3.0
MIN_DE_NODATA = 8.0
HEX = r'"(#[0-9a-fA-F]{6})"'


def modes():
    """[(id, stepped, [(fill, outline)])] from web/layers.js."""
    src = (ROOT / "web" / "layers.js").read_text()
    block = src[src.index("const BUILDING_COLOR_MODES = ["):src.index("const BUILDING_COLOR_MODES_NEXT")]
    land = re.search(r'land:\s*' + HEX, src).group(1)
    other = re.search(r'otherFill:\s*' + HEX, src).group(1)
    years = (ROOT / "web" / "years.js").read_text()
    nodata = re.search(r"NO_YEAR_COLOR = " + HEX, years).group(1)
    out = []
    for part in re.split(r'\n  \{ id: ', block)[1:]:
        mid = re.match(r'"(\w+)"', part).group(1)
        if mid == "year":
            continue
        if "classes:" in part:
            pairs = re.findall(r'color:\s*' + HEX + r',\s*outline:\s*' + HEX, part)
            out.append((mid, False, pairs))
        else:
            fills = re.findall(HEX, re.search(r"colors:\s*\[([^\]]*)\]", part).group(1))
            lines = re.findall(HEX, re.search(r"outlines:\s*\[([^\]]*)\]", part).group(1))
            out.append((mid, True, list(zip(fills, lines))))
    return land, nodata, other, out


def main():
    ok = True
    land, nodata, other, all_modes = modes()
    bg = luminance(rgb(land))
    for mid, stepped, pairs in all_modes:
        fills = [f for f, _ in pairs]
        print(f"mode {mid}: {fills}")
        for kind in ["normal", *CVD]:
            cols = [rgb(c) if kind == "normal" else simulate(rgb(c), kind) for c in fills]
            d, a, b = min((float(np.linalg.norm(lab(x) - lab(y))), fills[i], fills[j])
                          for (i, x), (j, y) in itertools.combinations(enumerate(cols), 2))
            need = MIN_DE if len(fills) <= 5 else MIN_DE_MANY
            good = d >= need
            ok &= good
            print(f"  {'ok  ' if good else 'FAIL'} {kind:7s} closest fills {a} / {b}: dE {d:.1f} (min {need})")
        for f, o in pairs:
            r = float(contrast(luminance(rgb(o)), bg))
            dn = min(float(np.linalg.norm(lab(rgb(f)) - lab(rgb(x)))) for x in (nodata, other))
            good = r >= MIN_CONTRAST and dn >= MIN_DE_NODATA
            ok &= good
            print(f"  {'ok  ' if good else 'FAIL'} {f} outline {o}: {r:.2f}:1 on {land} (min {MIN_CONTRAST}); "
                  f"dE {dn:.1f} from no-data / non-housing (min {MIN_DE_NODATA})")
        if stepped:
            L = [float(lab(rgb(f))[0]) for f in fills]
            good = all(a > b for a, b in zip(L, L[1:]))
            ok &= good
            print(f"  {'ok  ' if good else 'FAIL'} darker with the value: L* {' > '.join(f'{v:.0f}' for v in L)}")
    print("OK" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
