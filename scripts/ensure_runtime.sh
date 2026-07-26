#!/usr/bin/env bash
set -euo pipefail

runtime_dir="${TRANSCRIBE_RUNTIME_DIR:-/tmp/transcribe-venv}"
runtime_python="$runtime_dir/bin/python"

if [[ ! -x "$runtime_python" ]]; then
  python3 -m venv "$runtime_dir"
fi

if ! "$runtime_python" -c "import faster_whisper" >/dev/null 2>&1; then
  "$runtime_python" -m pip install --disable-pip-version-check \
    "faster-whisper==1.2.1" >&2
fi

"$runtime_python" -c "import faster_whisper" >/dev/null
printf '%s\n' "$runtime_python"
