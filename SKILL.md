---
name: transcribe-long-recording
description: Convert uploaded audio or video recordings into complete timestamped verbatim transcripts with durable progress, an offline faster-whisper fallback, and explicit coverage and hallucination checks. Use when the user asks for a 逐字稿, 录音转文字, 音频转写, call transcript, interview transcript, meeting transcript, or transcription of .m4a, .mp3, .wav, .aac, .flac, .mp4, .mov, or similar media—especially for long recordings, Chinese or mixed Chinese-English speech, sales calls, or when direct/native transcription is unavailable or has failed.
---

# Transcribe long recordings

Produce a faithful transcript, not a summary. Preserve the original order, fillers,
repetition, false starts, numbers, and mixed-language wording. Keep intermediate
files in scratch and save the final user-facing transcript durably.

## Workflow

1. Locate the uploaded media locally before asking the user to upload again.
   If several files are plausible and the target is not clear, ask which one.
2. Inspect the media:

   ```bash
   python3 scripts/inspect_media.py INPUT --output MEDIA_INFO.json
   ```

   Record the file size, duration, audio codec, channel count, and whether stereo
   channels carry effectively identical content.
3. Use an already callable transcription engine when it can produce a complete
   timestamped transcript. If it is absent or fails, continue with the bundled
   offline fallback instead of stopping at engine discovery.
4. Prepare the fallback runtime:

   ```bash
   bash scripts/ensure_runtime.sh
   ```

   Capture the printed Python path. Invoke the script through `bash` so it also
   works on no-exec skill mounts. The script reuses a working environment and
   installs `faster-whisper` only when missing.
5. Build a short domain hint from facts the user supplied. Do not invent names,
   products, or topics. For a Chinese sales call, a suitable hint is:

   > 以下是一通中文销售通话。请忠实逐字转写，保留口头语、重复、
   > 停顿式表达、中英文混用、专有名词和数字，不要总结或改写。

6. Transcribe with a unique output prefix. Default to `large-v3-turbo`, Chinese,
   CPU, and int8 unless the runtime has a verified better configuration:

   ```bash
   RUNTIME_PYTHON scripts/transcribe_audio.py INPUT \
     --output-prefix OUTPUT_PREFIX \
     --title "录音标题" \
     --language zh \
     --prompt "DOMAIN_HINT"
   ```

   Replace `RUNTIME_PYTHON` with the path printed by `ensure_runtime.sh`. Run long
   jobs in a resumable command session. Poll actual output and tell the user what
   audio timestamp has been reached. If interrupted, rerun with `--resume`; never
   call partial output complete.
7. Read [quality-standard.md](references/quality-standard.md) completely, then
   generate the final transcript and QA report:

   ```bash
   python3 scripts/finalize_transcript.py \
     OUTPUT_PREFIX.segments.jsonl \
     OUTPUT_PREFIX.metadata.json \
     --output FINAL.txt \
     --qa QA.json \
     --title "录音标题"
   ```

8. Review every QA warning and inspect at least the opening, middle, and ending
   sections. Confirm that the final audio duration and last recognized speech are
   consistent. State trailing silence explicitly rather than treating it as lost
   content.
9. Save only the final transcript as the reusable deliverable unless the user asks
   for diagnostics. Report duration, approximate character count, coverage, and
   speaker-label policy with the file link.

## Speaker labels

- If stereo channels are effectively identical, do not infer two speakers from
  channel count.
- If the recording is mixed mono, do not force `销售/客户` labels from conversational
  semantics alone. Short acknowledgements and overlapping turns are easy to
  misattribute.
- Add labels only from independent channels, a reliable diarization tool, or
  evidence that survives spot-checking. Mark ambiguous turns as `说话人不确定`.
- Accuracy outranks cosmetic completeness. An unlabeled accurate transcript is
  preferable to a confidently mislabeled one.

## Guardrails

- Never summarize, rewrite, or silently repair meaning in a verbatim transcript.
  Correct only unmistakable recognition or punctuation errors, and keep the raw
  ASR artifacts for comparison.
- Never claim completeness from file size or context-window assumptions. Verify
  coverage from timestamps and media duration.
- Never fabricate a transcript when no engine can decode the media. Explain the
  exact blocker and preserve any verified partial output.
- Do not overwrite prior outputs by default. Use `--force` only when replacing
  those exact generated files is intended.
