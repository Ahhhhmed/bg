---
name: backlog
description: The project backlog in backlog/ (one Markdown file per item) and how to work an item into a polished, verified PR when the owner asks. Use when the owner says what to work on (an item id, "the commute item", "take the next one"), when addressing feedback on a backlog PR, when adding, editing, splitting or reprioritising backlog items, or when asked how the backlog works.
---

# Backlog

The owner curates `backlog/` and tells Claude what to focus on, typically one
item per day. Claude then works that item **thoroughly**, to a polished,
verified state on a branch, and opens a PR the owner can review in one sitting
(PR text + Vercel preview). The owner merges, comments, or re-scopes. Nothing
here runs on its own: no schedules, no automatic picking.

## Item format

One file per item: `backlog/NNN-short-slug.md`. `NNN` is a 3-digit id, never
reused. Copy `backlog/_TEMPLATE.md`. Frontmatter:

| Field | Values | Meaning |
|---|---|---|
| `id` | `"004"` | Same as the filename prefix (quoted string). |
| `title` | text | Short, imperative. |
| `status` | `draft` `ready` `in-progress` `review` `blocked` `done` | See lifecycle below. |
| `priority` | `P1` `P2` `P3` | P1 = next up. Order within a priority is by id. |
| `size` | `S` `M` `L` | S: a few hours. M: about a working day. L: more; split into S/M items before starting. |
| `city` | `all` `zurich` `belgrade` | Which city the item is about. |
| `area` | `map` `data` `infra` `docs` | For grouping only. |
| `depends_on` | `["008"]` | Ids that must be `done` first. |
| `hosts` | `["data.gov.rs"]` | Network hosts needed beyond the default allowlist. |
| `blocked_on` | text | What a human must provide or decide. Required when `blocked`; also used on `draft`. |
| `pr` | URL | Set when a PR is open. |
| `updated` | `YYYY-MM-DD` | Last change to the item. |

Body sections, in this order: **Why** (value to the owner), **Scope**
(In / Out), **Acceptance criteria** (checkboxes, each provable by command
output, a URL or a screenshot), **Notes** (files, sources, gotchas),
**Log** (one dated line per working session, newest last; never rewrite old lines).

### Lifecycle

```
draft ──(specced)──▶ ready ──(owner asks)──▶ in-progress ──▶ review ──(owner merges)──▶ done
                              ▲                            │
                              └──(owner unblocks)── blocked ◀┘
```

- `draft`: idea, not specified enough to start. If the owner asks to work on one, first turn it into `ready` (Scope + Acceptance criteria) and confirm the plan with them.
- `ready`: fully specified; can be worked as soon as the owner asks for it.
- `in-progress` / `review`: set **on the work branch**, so they become visible on `main` when the PR merges. 
- `blocked`: needs something from a human or the environment; `blocked_on` says exactly what.
- `done`: merged. Move the file to `backlog/done/` (`git mv`) the next time you work on the backlog after the merge.

`python3 scripts/backlog.py list` shows the queue in pick order,
`next` suggests the top item (the owner decides), `check` validates every file.

## Working an item (when the owner asks)

The owner's instruction defines the job: usually "work on NNN", sometimes
with extra direction ("only the night-noise part", "use source X"). Their
words override the item file; record any change of scope in the item.

### 1. Orient
- `git fetch origin`; branch `claude/backlog-NNN-slug` from `origin/main` (or continue the item's existing branch/PR if one exists).
- Read `CLAUDE.md` (gotchas, the public-repo rules), `docs/decisions.md` (what the owner already decided; don't undo it silently) and the whole item file. Load the area's skill if there is one: `map-style` (web/), `city-data` (a city's pipeline), `verify-site`, `steward`. Read the code and data it points to before deciding anything.
- If the item is `draft`, `blocked`, or its `depends_on` aren't done: say so and propose how to proceed (spec it now, do the dependency first, ...) before building.
- Check every host in `hosts:` is reachable (`curl -sS -o /dev/null -w '%{http_code}' https://HOST/`). If one is blocked, tell the owner which host to allow; carry on with whatever doesn't depend on it.

### 2. Plan
- Turn the acceptance criteria into a task list (TaskCreate) and keep it updated as you go.
- First commit on the branch: item `status: in-progress`, `updated:`, a Log line.
- If the item is `L` or turns out bigger than a day once you look: tell the owner, deliver the most useful coherent slice, and split the rest into new items in the same PR.

### 3. Work, extensively
- This is a full working session on one item: go deep. Iterate until every acceptance criterion holds, look at the result (render it, query it, count it), and fix what you find, rather than stopping at a first pass that merely builds.
- Stay inside the item's Scope. Things noticed outside it become new backlog items in the same PR (`draft` or `ready`), not extra changes.
- Decisions the item doesn't cover: take the conservative, reversible option, note it under **Decisions for review** in the PR, and keep going. Ask the owner only when a wrong guess would waste the day.
- Commit in logical steps with clear messages. Push to the item branch only; never push to `main` or merge unless the owner says so for this change.

### 4. Verify (definition of done)
Every acceptance criterion is shown to hold with real output in the PR, not
asserted. Plus, for every item:

- **Public repo:** nothing private goes in: no personal data, no secrets, no
  file the build's privacy guard refuses; `bash scripts/build.sh` still copies
  only its listed files.
- **Preview works:** `bash scripts/preview_url.sh` gives the branch preview; after the push, wait until it serves the new commit (grep a changed string from a served JS file; see the `steward` skill), and check a city's `data/layers/cadastre.pmtiles` answers a Range request with 206.
- **Site works:** `node scripts/check.cjs <preview>` passes for the start page and both cities (see the `verify-site` skill). If `web/` or the tiles changed, also a screenshot of the changed area in each city it touches (`map.jumpTo(...)`), described in the PR.
- **Data changes:** the city's pipeline re-run as `docs/development.md` says, tiles rebuilt; before/after counts printed; the city's notes in `CLAUDE.md` and `NOTICE.md` updated if a source or script changed.
- **Both cities:** a new lens, place layer or card block exists in every city; where a city has no source, its `CITY.coverage` marks it (C-01), and the PR says so.
- **Code:** `node -e "new Function(require('fs').readFileSync(F,'utf8'))"` for changed JS; `python3 -m py_compile` for changed Python; the colour checks (`scripts/check_*_colours.py`) after any colour change.
- **Docs:** `CLAUDE.md`, `README.md` (what users can do, its screenshots), `docs/development.md`, `NOTICE.md` updated when behaviour, data or sources changed. A key decision by the owner gets an entry in `docs/decisions.md`. A skill whose instructions no longer match the code gets fixed in the same PR.
- **Backlog:** item `status: review`, `pr:` set, Log line with what was done and what's left; `python3 scripts/backlog.py check` passes.

If an acceptance criterion can't be met, don't fake it: leave it unchecked,
explain why in the PR and the Log, and still open the PR with what was done.

### 5. Hand over: the PR
Open the PR against `main` with this body (fill every section; "none" is fine):

```markdown
## Backlog NNN: <title>
<one paragraph: what changed, in the owner's terms>

**Preview:** <branch preview URL>/<city>/ (say where to look: place name or coordinates)

## Acceptance criteria
- [x] <criterion> — <evidence: command + key output, or what was checked>
- [ ] <criterion not met> — <why>

## Decisions for review
- <decision taken without asking the owner, and the alternative>

## Not done / follow-ups
- <new backlog items created, with ids>

## Checks
- Nothing private, build's privacy guard passes: yes
- Preview serves this commit: yes (<how verified>)
- Console errors in headless render: none / n.a.
```

Then report back to the owner in a few lines: item, PR link, preview link (to the changed spot), what to look at, decisions made, anything blocked or left over.

## Feedback on a backlog PR

When the owner comments on the PR or relays feedback in chat: check out the
same branch, address every point (change, answer, or explain why not), re-run
the relevant checks from the definition of done, push, reply on each review
thread, update the PR description and add a Log line. Out-of-scope requests
become new items unless the owner explicitly wants them in this PR.

## Adding and editing items

- New item: next free id (`ls backlog backlog/done`), copy the template, start as `draft` unless Scope and Acceptance criteria are complete; then `ready`.
- Good acceptance criteria are **observable**: a count, an exit code, an HTTP status, a screenshot of a named place. "Looks good" isn't checkable.
- Keep items `S` or `M`. If the acceptance criteria don't fit a working day, it's two items with `depends_on`.
- Put everything a fresh session needs into **Notes**: file paths, data sources, hosts, previous attempts. Each session starts with no memory of past conversations.
- Anything needing secrets or personal data: say where the owner will put it (environment secret, private gitignored file); never put the values in an item.
- Validate with `python3 scripts/backlog.py check`.

## Best practices

- **One item, one branch, one PR.** Small, focused PRs get reviewed; big ones rot.
- **Thorough beats fast.** The owner reviews once a day, so the PR should be finished work: criteria met and shown, edge cases looked at, docs updated.
- **Evidence over claims.** Paste the command and its output. A build that succeeds isn't a feature that works.
- **Optimise for the review.** Lead with the preview link and what to look at; keep the diff focused; explain decisions once, in the PR.
- **Fail early and cheaply.** Check hosts, dependencies and data availability before building on them.
- **The backlog is the memory.** Anything learned (sources that didn't work, numbers, decisions) goes into the item's Notes/Log or `CLAUDE.md`, because the next session starts fresh.
- **Public is part of done,** every time: the repo and the map are public; only open data and code go in.
- **Never** skip or weaken a check to get green, delete backlog files, or widen scope silently.
