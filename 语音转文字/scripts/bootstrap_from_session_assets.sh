#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)/runtime}"
mkdir -p "$ROOT"

# Reuse the exact assets created by the proven project bootstrap when present.
if [[ -f /mnt/data/whisper-bin-ubuntu-x64-artifact.zip && ! -x "$ROOT/whisper-bin-ubuntu-x64/whisper-cli" ]]; then
  tmp=$(mktemp -d)
  unzip -q /mnt/data/whisper-bin-ubuntu-x64-artifact.zip -d "$tmp"
  mkdir -p "$ROOT"
  tar -xzf "$tmp/whisper-bin-ubuntu-x64.tar.gz" -C "$ROOT"
  rm -rf "$tmp"
fi
for size in base small tiny; do
  z="/mnt/data/whisper-${size}-q5_1.zip"
  if [[ -f "$z" ]]; then unzip -qo "$z" -d "$ROOT"; fi
done

CLI="$ROOT/whisper-bin-ubuntu-x64/whisper-cli"
if [[ -x "$CLI" ]]; then
  LD_LIBRARY_PATH="$(dirname "$CLI"):${LD_LIBRARY_PATH:-}" "$CLI" --help >/dev/null
  echo "whisper runtime ready: $CLI"
else
  echo "session assets not found or incomplete" >&2
  exit 2
fi
