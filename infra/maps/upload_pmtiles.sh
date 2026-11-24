#!/usr/bin/env bash
set -euo pipefail

: "${PMTILES_FILE:?Set PMTILES_FILE to the local .pmtiles file}"
: "${R2_BUCKET:?Set R2_BUCKET to the destination bucket}"
: "${R2_OBJECT_KEY:?Set R2_OBJECT_KEY to the destination object key}"

WRANGLER_BIN="${WRANGLER_BIN:-wrangler}"
if ! command -v "$WRANGLER_BIN" >/dev/null 2>&1; then
  echo "Wrangler is required. Install it or set WRANGLER_BIN." >&2
  exit 1
fi

if [[ ! -f "$PMTILES_FILE" ]]; then
  echo "PMTiles file not found: $PMTILES_FILE" >&2
  exit 1
fi

"$WRANGLER_BIN" r2 object put "$R2_BUCKET/$R2_OBJECT_KEY" \
  --file "$PMTILES_FILE" \
  --content-type application/vnd.pmtiles \
  --remote
