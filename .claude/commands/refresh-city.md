Refresh a city's data and rebuild its map (argument: the city id, e.g. `zurich` or `belgrade`):

1. Follow the `city-data` skill for that city's run order (Zürich: `bash cities/zurich/pipeline/refresh.sh`; Belgrade: the steps in `CLAUDE.md`).
2. Print before/after counts (buildings, addresses, places per layer, stops) and the tiles' size.
3. `bash scripts/build.sh`, serve `dist/` and run `node scripts/check.cjs` locally; fix what fails.
4. Commit the tiles and tables (not `data/src/`, not `data/work/`) on a branch and open a PR with the counts.
