#!/usr/bin/env bash
# Prints the Vercel preview URL of the current (or given) branch, computed from
# Vercel's branch-alias naming (lowercase, every run of other characters -> "-"),
# so it works right after a push without waiting for a bot comment.
# Usage: bash scripts/preview_url.sh [branch]   (VERCEL_PROJECT / VERCEL_SCOPE override the names)
set -euo pipefail
PROJECT=${VERCEL_PROJECT:-bg}
SCOPE=${VERCEL_SCOPE:-ahhhhmed}
branch="${1:-$(git rev-parse --abbrev-ref HEAD)}"
s=$(echo "$branch" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')
url="https://${PROJECT}-git-${s}-${SCOPE}.vercel.app"
echo "$url/            (Belgrade, the start page)"
echo "$url/zurich/"
echo "$url/belgrade/"
