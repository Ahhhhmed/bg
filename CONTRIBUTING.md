# Contributing to bg

bg is built by people working with [Claude Code](https://claude.com/claude-code):
you decide what to build and review the result; Claude writes the code, runs
the data pipelines and proves the map works. This guide is the human side.
Claude's side is in [`CLAUDE.md`](CLAUDE.md) and the skills in `.claude/`,
which every session reads by itself.

## The loop

1. **Pick an item** in [`backlog/`](backlog/) (one file per item;
   `python3 scripts/backlog.py list` shows them in order). Or write a new one:
   copy `backlog/_TEMPLATE.md`, or ask Claude to write it from your idea.
2. **Start a Claude Code session** on the repo (on the web at
   [claude.ai/code](https://claude.ai/code), in the desktop app, or `claude` in a
   terminal) and say what you want: *"work on 005"*, optionally with direction
   (*"only pharmacies and doctors for now"*).
3. **Claude works on a branch** (`claude/backlog-NNN-...`), checks its work
   headlessly, and opens a pull request with what it did, the evidence, and the
   decisions it took without asking you.
4. **Review the PR.** Open its Vercel preview (Claude gives you the link) and look
   at the place it names. Then merge it, comment on it (Claude can address
   comments in the same session), or close it.
5. **Merging deploys.** `main` goes live on Vercel within minutes.

One item per session and PR keeps the reviews small. Each session starts with
no memory of the last one: what matters goes into the backlog item's Log, the
docs or [`docs/decisions.md`](docs/decisions.md), and Claude does that in the PR.

## What to tell Claude, and what Claude asks you

- **Decisions are yours.** When something needs a choice (a source, a colour,
  what to leave out), Claude asks, or takes the safe option and lists it under
  "Decisions for review". A decision you want kept goes into
  `docs/decisions.md`; say so ("make that a decision").
- **Be concrete about what you see**: a place, a zoom, a screenshot. "The card at
  Slavija shows no stop" is quicker to act on than "the cards are off".
- **Belgrade first.** Zürich is the reference (C-23): the same app with fuller
  data, to show what a feature looks like where a source exists. Change it only
  when the shared app needs it.
- **Ask for the why.** Claude can explain any part of the map, the data or a
  decision; `docs/decisions.md` has the history.

## The rules Claude follows (so you know what to expect)

- **Public repo, public map.** Only open data and code. No personal data, no
  secrets, no data whose licence doesn't allow publishing.
- **Only what a source states.** No guessed values; estimates are marked "≈".
  Where Belgrade has no data, the map says so (greyed, "nije dostupno") instead
  of hiding the feature or making something up.
- **Every source credited**, with its licence ([`NOTICE.md`](NOTICE.md)) and its
  date on the card.
- **Serbian and English** for every new label.
- **Proof, not claims.** A PR shows the counts, screenshots and check output.

## Setting up the cloud environment (claude.ai/code)

Cloud sessions run in a container with an allow-list of hosts. Add these under
the environment's **Network access → Allowed domains** (keep "allow package
managers" ticked):

| Needed for | Hosts |
|---|---|
| the map's libraries, fonts, relief (headless checks) | `unpkg.com`, `fonts.googleapis.com`, `fonts.gstatic.com`, `wmts.geo.admin.ch` |
| Belgrade data | `data.gov.rs`, `opendata.kosava.cloud`, `overturemaps-us-west-2.s3.us-west-2.amazonaws.com`, `copernicus-dem-30m.s3.amazonaws.com` |
| Zürich data (only for a refresh) | `data.geo.admin.ch`, `api3.geo.admin.ch`, `geodienste.ch`, `maps.zh.ch`, `www.zh.ch`, `www.ogd.stadt-zuerich.ch`, `data.stadt-zuerich.ch`, `overpass.osm.ch`, `gtfs.geops.ch`, `www.housing-stat.ch` |
| setup (tippecanoe from source) | `github.com` |

A backlog item lists any further hosts it needs under `hosts:`. If one is
missing, Claude names it and carries on with what doesn't need it.

The container is set up by `bash setup.sh` (tippecanoe, GDAL, Python packages);
Claude runs it when a pipeline needs it. Building and checking the site needs
only Python and Node.

## Working locally (optional)

```bash
git clone https://github.com/Ahhhhmed/bg && cd bg
bash setup.sh                          # Linux; on macOS: brew install tippecanoe gdal, then pip install -r requirements.txt
bash scripts/build.sh                  # the site -> dist/, from the committed tiles and tables
python3 scripts/serve.py 8750 dist     # open http://localhost:8750/
```

Then run `claude` in the folder and work as above. The committed tiles are
enough to build and run the site; the pipelines in `cities/*/pipeline/` are
only needed to refresh a city's data (see [`README.md`](README.md)).

## Deployment

Vercel builds every push (`vercel.json` runs `bash scripts/build.sh`, output
`dist/`): `main` is production, every branch gets a preview.
`bash scripts/preview_url.sh` prints a branch's preview link. GitHub Actions
(`.github/workflows/check.yml`) runs the privacy guard, the build and the
headless check on every push.

## Licence

Code: MIT ([`LICENSE`](LICENSE)). Data: each source's own licence
([`NOTICE.md`](NOTICE.md)). By contributing you agree your code is published
under MIT.
