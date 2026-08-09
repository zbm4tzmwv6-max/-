#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
"$ROOT/scripts/bootstrap_from_session_assets.sh" "$ROOT/runtime"
CLI="$ROOT/runtime/whisper-bin-ubuntu-x64/whisper-cli"
MODEL="$ROOT/runtime/ggml-base-q5_1.bin"
test -x "$CLI"
test -s "$MODEL"
test -f "$ROOT/scripts/transcribe_media.py"
python3 "$ROOT/scripts/transcribe_media.py" --help >/dev/null
echo "PASS: 语音转文字 runtime + generic media wrapper available"
