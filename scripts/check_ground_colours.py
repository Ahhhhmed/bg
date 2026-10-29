"""
Validates the ground theme tints (the area lenses, C-09 / C-10) in web/layers.js.
Run after adding or recolouring a ground theme:

  python3 scripts/check_ground_colours.py      # exit 1 on failure

A tint is drawn at GROUND_OPACITY over the oat land and under the buildings,
so every check uses the colour as it appears: blended onto the land.
Checks, per theme in GROUND_THEMES:
  1. every class >= MIN_DE_YEAR (CIELAB dE76) from every construction-year
     fill (web/years.js), so a tint never reads as a building colour (15, not
     the 20 the year fills keep among themselves: a tint never touches a
     fill directly, the building's outline sits between them);
  2. every pair of classes >= MIN_DE_CLASS apart, for normal vision and under
     simulated deutan / protan / tritan vision (themes are read class by class
     from the legend);
  3. every class >= MIN_DE_LAND from the bare land, so it shows at all.
Uses the colour maths of check_year_colours.py (numpy only).
"""
import itertools
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from check_year_colours import CVD, lab, rgb, simulate, web_colours  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MIN_DE_YEAR = 15.0
MIN_DE_CLASS = 10.0
MIN_DE_LAND = 6.0


def themes():
    """(opacity, land, [(theme id, [(value, colour)])]) from web/layers.js."""
    src = (ROOT / "web" / "layers.js").read_text()
    opacity = float(re.search(r"const GROUND_OPACITY = ([0-9.]+)", src).group(1))
    land = re.search(r'land:\s*"(#[0-9a-fA-F]{6})"', src).group(1)
    block = src[src.index("const GROUND_THEMES"):src.index("const GROUND_THEMES_NEXT")]
    out = []
    for part in block.split("{ id: ")[1:]:
        tid = re.match(r'"(\w+)"', part).group(1)
        classes = [(v.strip('[]" ').replace('"', ''), c) for v, c in
                   re.findall(r'v:\s*("[^"]+"|\[[^\]]*\]),\s*color:\s*"(#[0-9a-fA-F]{6})"', part)]
        out.append((tid, classes))
    return opacity, land, out


def main():
    ok = True
    opacity, land, all_themes = themes()
    years, _ = web_colours()
    bg = rgb(land)
    print(f"ground opacity {opacity}, land {land}, year fills {years}")
    for tid, classes in all_themes:
        shown = {v: opacity * rgb(c) + (1 - opacity) * bg for v, c in classes}
        print(f"theme {tid}: " + ", ".join(f"{v} {c}" for v, c in classes))
        for v, col in shown.items():
            d_year = min(float(np.linalg.norm(lab(col) - lab(rgb(y)))) for y in years)
            d_land = float(np.linalg.norm(lab(col) - lab(bg)))
            good = d_year >= MIN_DE_YEAR and d_land >= MIN_DE_LAND
            ok &= good
            print(f"  {'ok  ' if good else 'FAIL'} {v:>4}: dE {d_year:.1f} from the nearest year fill "
                  f"(min {MIN_DE_YEAR}), {d_land:.1f} from the land (min {MIN_DE_LAND})")
        for kind in ["normal", *CVD]:
            cols = {v: (c if kind == "normal" else simulate(c, kind)) for v, c in shown.items()}
            if len(cols) < 2:
                continue
            d, a, b = min((float(np.linalg.norm(lab(x) - lab(y))), p, q)
                          for (p, x), (q, y) in itertools.combinations(cols.items(), 2))
            good = d >= MIN_DE_CLASS
            ok &= good
            print(f"  {'ok  ' if good else 'FAIL'} {kind:7s} closest classes {a} / {b}: dE {d:.1f} (min {MIN_DE_CLASS})")
    print("OK" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
