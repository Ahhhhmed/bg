#!/usr/bin/env bash
# Installs what the pipelines and the build need on Linux (a cloud sandbox,
# CI): tippecanoe (built from source, no apt package), GDAL, and the Python
# packages of requirements.txt in .venv/. Headless checks need Node and
# Playwright with Chromium (`npm i playwright && npx playwright install chromium`).
# Usage: bash setup.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
SUDO=$(command -v sudo || true)

echo "== System packages =="
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq build-essential libsqlite3-dev zlib1g-dev gdal-bin libgdal-dev python3-venv python3-pip git

echo "== tippecanoe (>= 2.17, built from source) =="
if ! command -v tippecanoe >/dev/null 2>&1; then
  tmp=$(mktemp -d)
  git clone --depth 1 https://github.com/felt/tippecanoe.git "$tmp/tippecanoe"
  make -C "$tmp/tippecanoe" -j"$(nproc)"
  $SUDO make -C "$tmp/tippecanoe" install
  rm -rf "$tmp"
fi

echo "== Python packages (.venv) =="
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "Done. Activate with: source .venv/bin/activate; then see README.md."
