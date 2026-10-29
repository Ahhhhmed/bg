---
name: verify-site
description: Prove the city maps actually work -- the start page (Belgrade), each city's map with its controls, building / stop / place cards, search, languages, the commute lens and the air stations -- with a headless browser, locally, on a branch preview or in production. Use after any change to web/, a city's data or tiles, or the build, before handing a preview link to the owner, and after a merge.
---

# Verify the site

A cloud session has no browser of its own: the headless check is how you see the map.

## Locally
```bash
bash scripts/build.sh                      # -> dist/ (privacy guard included)
python3 scripts/serve.py 8750 dist &       # HTTP Range: PMTiles needs it
node scripts/check.cjs http://localhost:8750 /tmp/check
```
`scripts/build.sh` deletes and rebuilds `dist/`: restart the server after it (a server
whose root was deleted answers with empty responses).

## On a preview or production
```bash
bash scripts/preview_url.sh                # the branch's URLs
node scripts/check.cjs <url> /tmp/check    # <url> = the site root
```

## What `check.cjs` proves (exit 1 on any failure, JSON report)
- the start page is Belgrade's map, draws buildings and links the reference (`/zurich/`);
- per city: the map loads, buildings render at z17, a click opens the building card, the
  address search finds its test address, the commute lens colours buildings and a stop card
  opens, `?lang=en` switches the language; Belgrade's air stations render;
- no console errors and no 4xx / 5xx from the site's own host.

Screenshots go to the out dir (`<city>_start`, `_z17`, `_card`, `_search`, `_commute`,
`_stop`, `_<lang>`): read the ones of the area you changed.

## Gotchas
- SwiftShader (no GPU) is slow: waits are generous. A blank map above an open bottom sheet
  on a phone viewport is a SwiftShader artifact.
- `map` is a top-level `const` in `map.js`: in `page.evaluate` it's `map`, not `window.map`.
- Jumping Zürich's map outside Switzerland makes swisstopo's relief answer 400: not a bug.
- Playwright: `npm i playwright && npx playwright install chromium` if it isn't there.
