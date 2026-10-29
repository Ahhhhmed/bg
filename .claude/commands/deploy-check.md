Check that the production deployment works, not just that it built:

1. `curl -sI` the start page and each city page: 200, no login redirect (Vercel's deployment protection must stay off).
2. A Range request on each city's tiles: `curl -s -o /dev/null -w '%{http_code}' -H 'Range: bytes=0-99' <url>/<city>/data/layers/cadastre.pmtiles` must answer 206 (PMTiles needs Range).
3. `node scripts/check.cjs <url>` (see the `verify-site` skill) and report its failures, or that there are none.
