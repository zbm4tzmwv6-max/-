#!/usr/bin/env bash
# Run after runtime preparation; generate speech locally, never download a recording.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACTS="${1:-$ROOT/../../smoke-artifacts}"
mkdir -p "$ARTIFACTS"
WORK="$(mktemp -d "$ARTIFACTS/e2e.XXXXXX")"
WORK="$(cd "$WORK" && pwd)"
on_exit() {
  local status=$?
  if (( status != 0 )); then
    echo "FAIL: exit=$status evidence=$WORK" >&2
    find "$WORK" -type f -printf '%p %s bytes\n' >&2
  fi
  exit "$status"
}
trap on_exit EXIT

for dependency in python3 ffmpeg espeak-ng; do command -v "$dependency" >/dev/null; done
CLI="$ROOT/runtime/whisper-bin-ubuntu-x64/whisper-cli"
MODEL="$ROOT/runtime/ggml-base-q5_1.bin"
test -x "$CLI"
test -s "$MODEL"
bash "$ROOT/scripts/bootstrap_from_session_assets.sh" "$ROOT/runtime"

# English is intentional: a small, deterministic CI fixture, not a Mandarin accuracy test.
printf '%s\n' 'Hello world. This is a short speech recognition test. The audio contains spoken words. Thank you for listening.' > "$WORK/expected.txt"
espeak-ng -v en-us -s 140 -f "$WORK/expected.txt" -w "$WORK/speech.wav"
# Exercise generic media decoding and resampling, not only already-normalized WAV input.
ffmpeg -hide_banner -loglevel error -y -i "$WORK/speech.wav" -ar 44100 -ac 2 -c:a flac "$WORK/smoke.flac"
python3 "$ROOT/scripts/transcribe_media.py" "$WORK/smoke.flac" \
  --output-dir "$WORK/output" --cli "$CLI" --model "$MODEL" \
  --strength base --language en --threads 2 --force
python3 "$ROOT/tests/verify_smoke_outputs.py" "$WORK/smoke.flac" "$WORK/output" "$CLI" "$MODEL"
echo "PASS: end-to-end smoke; evidence=$WORK"
