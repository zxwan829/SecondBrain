#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
NAS_HOST="${NAS_HOST:-joe@192.168.3.27}"
NAS_KEY="${NAS_KEY:-$HOME/.ssh/id_ed25519_secondbrain_nas}"
NAS_DIR="${NAS_DIR:-/volume1/docker/secondbrain/hermes/data/plugins/secondbrain-fe-test/dashboard}"
BASE_URL="${BASE_URL:-http://192.168.3.27:9119}"
ASSET_BASE="$BASE_URL/dashboard-plugins/secondbrain-fe-test"
SSH=(ssh -i "$NAS_KEY" -o IdentitiesOnly=yes -o BatchMode=yes)

npm run typecheck
npm run package:test-plugin
npm run validate:manifest
npm run verify:bundle
npm run verify:fe25

PACKAGE_DIR="dist-hermes-test/dashboard"
node - "$PACKAGE_DIR/manifest.json" <<'NODE'
const fs = require('node:fs');
const manifest = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
if (manifest.name !== 'secondbrain-fe-test' || manifest.version !== '0.8.0-fe-dev' || manifest.entry !== 'index-fe-test.js' || manifest.css !== 'style-fe-test.css') {
  throw new Error('fixed test manifest identity/entry/version mismatch');
}
for (const name of [manifest.entry, manifest.css]) {
  if (!fs.statSync(`${process.argv[2].slice(0, -'manifest.json'.length)}${name}`).size) throw new Error(`empty asset: ${name}`);
}
console.log(`Fixed test manifest PASS ${manifest.version} ${manifest.entry} ${manifest.css}`);
NODE

TMP_MANIFEST="$(mktemp)"
TMP_JS="$(mktemp)"
TMP_CSS="$(mktemp)"
TMP_HTTP_HEADERS="$(mktemp)"
TMP_IMAGE="$(mktemp)"
cleanup() { rm -f "$TMP_MANIFEST" "$TMP_JS" "$TMP_CSS" "$TMP_HTTP_HEADERS" "$TMP_IMAGE"; }
trap cleanup EXIT

# Read and validate the live manifest, but never replace it during daily asset deploys.
"${SSH[@]}" "$NAS_HOST" "cat '$NAS_DIR/manifest.json'" > "$TMP_MANIFEST"
node - "$TMP_MANIFEST" <<'NODE'
const fs = require('node:fs');
const manifest = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
if (manifest.name !== 'secondbrain-fe-test' || manifest.version !== '0.8.0-fe-dev' || manifest.entry !== 'index-fe-test.js' || manifest.css !== 'style-fe-test.css') {
  throw new Error('NAS test manifest differs from the initialized fixed-entry manifest; refusing deployment');
}
console.log('NAS manifest is valid and fixed-entry; unchanged');
NODE

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$NAS_DIR/backup-$STAMP"
"${SSH[@]}" "$NAS_HOST" "mkdir -p '$BACKUP' && { test ! -e '$NAS_DIR/index-fe-test.js' || cp -a '$NAS_DIR/index-fe-test.js' '$BACKUP/'; } && { test ! -e '$NAS_DIR/style-fe-test.css' || cp -a '$NAS_DIR/style-fe-test.css' '$BACKUP/'; }"
"${SSH[@]}" "$NAS_HOST" "mkdir -p '$NAS_DIR/assets'"
for asset in index-fe-test.js style-fe-test.css; do
  "${SSH[@]}" "$NAS_HOST" "cat > '$NAS_DIR/$asset'" < "$PACKAGE_DIR/$asset"
done
for image in "$PACKAGE_DIR"/assets/*.png; do
  [[ -f "$image" ]] || continue
  image_name="$(basename "$image")"
  "${SSH[@]}" "$NAS_HOST" "cat > '$NAS_DIR/assets/$image_name'" < "$image"
  local_hash="$(shasum -a 256 "$image" | awk '{print $1}')"
  remote_hash="$("${SSH[@]}" "$NAS_HOST" "sha256sum '$NAS_DIR/assets/$image_name'" | awk '{print $1}')"
  [[ "$local_hash" == "$remote_hash" ]] || { echo "PNG SHA256 mismatch ($image_name); backup: $BACKUP" >&2; exit 1; }
  echo "PNG SHA256 verified: $image_name $remote_hash"
done

LOCAL_JS="$(shasum -a 256 "$PACKAGE_DIR/index-fe-test.js" | awk '{print $1}')"
LOCAL_CSS="$(shasum -a 256 "$PACKAGE_DIR/style-fe-test.css" | awk '{print $1}')"
REMOTE_JS="$("${SSH[@]}" "$NAS_HOST" "sha256sum '$NAS_DIR/index-fe-test.js'" | awk '{print $1}')"
REMOTE_CSS="$("${SSH[@]}" "$NAS_HOST" "sha256sum '$NAS_DIR/style-fe-test.css'" | awk '{print $1}')"
[[ "$LOCAL_JS" == "$REMOTE_JS" ]] || { echo "JS SHA256 mismatch; backup: $BACKUP" >&2; exit 1; }
[[ "$LOCAL_CSS" == "$REMOTE_CSS" ]] || { echo "CSS SHA256 mismatch; backup: $BACKUP" >&2; exit 1; }

fetch_asset() {
  local url="$1" output="$2" status
  status="$(curl --silent --show-error -D "$TMP_HTTP_HEADERS" -o "$output" -w '%{http_code}' "$url")"
  if [[ "$status" != "200" ]]; then
    if [[ "$status" =~ ^3[0-9][0-9]$ ]] && grep -Eiq '^location:[[:space:]]*/login([?[:space:]]|$)' "$TMP_HTTP_HEADERS"; then
      echo "HTTP asset check BLOCKED_BY_AUTH (HTTP $status; server redirected to login). NAS file hashes are verified; no credential was supplied or bypassed." >&2
      echo "Backup: $BACKUP" >&2
      exit 2
    fi
    echo "HTTP asset check failed (HTTP $status): $url; backup: $BACKUP" >&2
    exit 1
  fi
}
fetch_asset "$ASSET_BASE/index-fe-test.js" "$TMP_JS"
fetch_asset "$ASSET_BASE/style-fe-test.css" "$TMP_CSS"
HTTP_JS="$(shasum -a 256 "$TMP_JS" | awk '{print $1}')"
HTTP_CSS="$(shasum -a 256 "$TMP_CSS" | awk '{print $1}')"
[[ "$LOCAL_JS" == "$HTTP_JS" ]] || { echo "HTTP JS asset differs; backup: $BACKUP" >&2; exit 1; }
[[ "$LOCAL_CSS" == "$HTTP_CSS" ]] || { echo "HTTP CSS asset differs; backup: $BACKUP" >&2; exit 1; }

BUILD_ID="$(shasum -a 256 "$PACKAGE_DIR/index-fe-test.js" | awk '{print substr($1,1,12)}')"
echo "Fixed-entry deployment PASS"
echo "Build: $BUILD_ID"
echo "Manifest: unchanged (0.8.0-fe-dev)"
echo "Runtime URLs: $ASSET_BASE/index-fe-test.js ; $ASSET_BASE/style-fe-test.css"
echo "NAS SHA256: JS=$REMOTE_JS CSS=$REMOTE_CSS"
echo "HTTP SHA256: JS=$HTTP_JS CSS=$HTTP_CSS"
echo "Backup: $BACKUP"
echo "No rescan or Hermes restart was run. Open /secondbrain-fe-test for browser acceptance."
