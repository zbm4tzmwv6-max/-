---
name: 语音转文字
description: Convert any FFmpeg-decodable audio or video file into timestamped text using a self-service ASR pipeline. Trigger for audio-to-text, video-to-text, transcript, interview/meeting/podcast/course/voice-note transcription, or sales Call analysis. Common inputs include m4a, aac, mp3, wav, flac, ogg, opus, webm, amr, mp4, mov, and mkv. The original media is sufficient input: do not ask the user to create a transcript.
---

# 语音转文字

## Purpose

Make speech-to-text a reliable internal preprocessing step for any uploaded audio/video, and a mandatory preprocessing step for content-level Call analysis.

**Invariant:** if the user has supplied the original audio/video recording, the user has supplied enough material. Never hand transcript creation back to the user merely because the current runtime lacks a ready-made ASR command.

The expected pipeline is:

`recording → normalize audio → full timestamped ASR → transcript QA → key-segment precision pass → transcript/index cache → semantic Call analysis`

Do not substitute speaking-time ratios, turn counts, voice activity, or generic sales experience for transcript evidence when the user asked for content-level Call analysis.

## Trigger behavior

Use this skill automatically for any audio/video-to-text request, and especially when any of the following are true:

- any audio/video file is uploaded and the user asks to transcribe, summarize, extract quotes, create notes, or analyze its spoken content;
- an audio/video Call is uploaded and the user asks why it did/did not close;
- the user asks for lost-sale nodes, customer psychology, original quotes, timestamps, missed opportunities, reconstructed talk tracks, qualification audit, emotional analysis, or an HTML/PDF report;
- the user asks to compare a new Call with previous closed/lost Calls;
- the user asks for a transcript, subtitle, or timestamped text from a Call.

Do **not** ask “请提供逐字稿” when the original media exists.

## Non-negotiable evidence rule

For current-Call conclusions, require semantic transcript evidence. A report-ready claim should be traceable to one or more of:

1. timestamped customer quote;
2. timestamped salesperson quote;
3. immediately adjacent conversational response;
4. audio-confirmed prosodic/acoustic change when emotion is explicitly being analyzed.

Never fabricate missing words, speaker identity, timestamps, or customer psychology.

If transcription quality is uncertain at a decisive node, re-transcribe that slice with a stronger model before drawing the conclusion.

## ASR runtime resolution: keep going through fallbacks

Resolve transcription capability in this order. Failure at one layer is **not** a reason to stop or ask the user to solve it.

### Layer A — Existing local engine

1. If a reachable Yaps CLI exists, it may be used.
2. Otherwise check for `whisper-cli`, `whisper.cpp`, `main`, or a packaged whisper.cpp binary.
3. Check for cached multilingual Whisper models.

If the local engine is available, use it and continue.

### Layer B — Existing session artifacts/cache

Look for previously bootstrapped assets, especially:

- `whisper-bin-ubuntu-x64*.zip` / extracted `whisper-cli`
- `ggml-base-q5_1.bin`
- `ggml-small-q5_1.bin`
- model archives in `/mnt/data`, the skill runtime directory, or another known cache.

Reuse them. Do not redownload or rebuild if a working copy exists.

### Layer C — Self-bootstrap whisper.cpp

If no engine is available, the assistant must attempt to establish one itself. Preferred pattern for a Linux x64 cloud runtime:

1. obtain a prebuilt whisper.cpp Ubuntu x64 binary artifact (tested with whisper.cpp 1.9.2);
2. obtain a multilingual model;
3. extract to a session cache;
4. run `whisper-cli --help` as a smoke test;
5. continue transcription.

Known-good model sources used in this project:

- base q5_1: `https://raw.githubusercontent.com/bnosac/audio.whisper/master/inst/repo/ggml-base-q5_1.bin`
- small q5_1: `https://raw.githubusercontent.com/bnosac/audio.whisper/master/inst/repo/ggml-small-q5_1.bin`
- tiny q5_1 emergency fallback: `https://raw.githubusercontent.com/bnosac/audio.whisper/master/inst/repo/ggml-tiny-q5_1.bin`

If direct binary/model download is unavailable but a connected GitHub tool is available, use GitHub Actions as a bridge: create/trigger a temporary workflow in an authorized repository that downloads the public asset and uploads it as a short-lived workflow artifact; download the artifact into the current runtime; then remove the temporary workflow. Do not ask the user to perform these steps.

If prebuilt binaries are unavailable but build tools and network access exist, clone whisper.cpp and build `whisper-cli` locally.

Only after all runtime self-service paths genuinely fail may the assistant explain the limitation. Even then, do not falsely claim that the user failed to provide required input.

## Audio normalization

Treat **any FFmpeg-decodable audio or video format** as supported input. Normalize every non-canonical source to a stable 16 kHz mono WAV before ASR:

```bash
ffmpeg -y -i INPUT -vn -ac 1 -ar 16000 -c:a pcm_s16le OUTPUT.wav
```

Keep the original recording unchanged.

If the source is stereo, inspect channel correlation before assuming left/right are separate speakers. If channels are effectively duplicates, do not use stereo diarization as speaker truth.

## Model policy for long recordings

Use a two-pass policy rather than a single weak transcript:

### Full-call pass

For recordings roughly >30 minutes, default to multilingual **base q5_1** for the full time axis. Generate at least TXT + SRT + JSON.

Recommended settings:

```bash
whisper-cli \
  -m ggml-base-q5_1.bin \
  -l zh \
  -t <reasonable CPU threads> \
  -osrt -otxt -oj \
  -of OUTPUT_PREFIX \
  NORMALIZED.wav
```

Use language `zh` for predominantly Mandarin Calls; use `auto` only when code-switching is extensive.

### Precision verification pass

Use multilingual **small q5_1** on decisive slices. For sales Calls, especially:

- pricing / budget;
- installment / down payment / loan concerns;
- “考虑一下” / “对比一下” / “问家人”;
- competitor comparison;
- commitment / persistence;
- schedule / course duration;
- refund / 14-day mechanism;
- explicit interest or explicit exit;
- the 3–8 minutes before the Call ends;
- any passage that determines a lost-sale or close causal chain.

Extract the slice with ffmpeg and re-run ASR. Prefer the precision-pass wording for quoted evidence when it is clearer and still consistent with the audio.

## Transcript QA

A transcript is not “complete” merely because a process exited successfully.

Before downstream analysis:

1. confirm duration coverage reaches the end of the Call;
2. verify the first and last meaningful spoken segments;
3. inspect obvious hallucination loops/repeated phrases;
4. inspect decisive commercial keywords;
5. verify high-stakes quotations with the precision model;
6. preserve uncertainty if audio is genuinely unclear.

For Chinese ASR, lightly normalize punctuation and obvious homophones only when context is unambiguous. Never rewrite a customer quote into a cleaner sentence and then present it as verbatim.

## Speaker attribution

Whisper text segmentation is not reliable speaker diarization by itself.

For key evidence:

- infer salesperson/customer only from surrounding semantic context when role is clear;
- if ambiguous, label as `说话人A/B` or “角色不确定” rather than inventing a role;
- never infer speaker identity from duplicated stereo channels;
- keep the quote and nearby turn together when assigning role.

For dialogue analysis, role attribution at the **key nodes** matters more than pretending every line of a 70-minute transcript has perfect diarization.

## Outputs and cache

For each media file, create a reusable transcription bundle beside the working output directory:

- `<stem>.transcript.txt` — readable timestamped transcript;
- `<stem>.srt` — timestamp ground truth;
- `<stem>.json` — segment-level machine-readable output;
- `<stem>.asr-manifest.json` — source fingerprint, duration, engine, model, language, settings, output files;
- optional `<stem>.key-segments.json` — precision-verified decisive passages.

The manifest should include a source hash so a later analysis can reuse the transcript instead of running ASR again.

If a verified transcript already exists for the same source hash, use it as the default evidence base and only reopen audio for quote verification or new acoustic analysis.

## Downstream handoff

Do not begin evidence-level semantic analysis until the timestamped transcript exists. For sales Calls, do not begin lost-sale analysis until that transcript exists.

Once it exists, downstream analysis may build:

- one-sentence diagnosis;
- customer profile / decision type;
- customer psychology path;
- full key timeline;
- true lost-sale/close nodes;
- before/after customer quote;
- salesperson response quote;
- action → psychology → result causal chain;
- qualification audit;
- drift from previously successful close actions;
- missed advancement opportunities;
- improved talk tracks;
- next-day follow-up;
- acoustic emotion overlay when requested.

Every important current-Call claim should point back to timestamped language.

## Emotion/acoustic add-on

When the user asks for emotion analysis, keep semantic and acoustic evidence separate but aligned on the same timeline.

Acoustic features may include:

- voiced-time density;
- pause duration/density;
- RMS/loudness;
- F0/pitch and pitch variance;
- speech-rate proxy;
- turn-taking / interruption patterns.

Do not equate high pitch or loudness with a specific emotion mechanically. Interpret acoustic change only together with transcript content and interaction context.

## Failure handling

Forbidden failure pattern:

> “我这里没有语音识别引擎，你先给我逐字稿/换设备/自己转一下。”

Required behavior:

1. verify the original media exists;
2. inspect local runtime;
3. reuse cached ASR assets;
4. bootstrap whisper.cpp/model if needed;
5. run transcription;
6. only report a hard blocker after self-service routes are exhausted.

The user should not have to repeatedly negotiate for transcription when the original Call recording has already been supplied.

## General media use

This Skill also supports meetings, interviews, courses, podcasts, voice notes, and video dialogue. For non-sales media, stop after the requested transcript/summary/notes rather than forcing a sales framework.

## Completion standard

A successful run means:

- the original audio was processed without user-side preprocessing;
- a timestamped transcript covers the Call;
- decisive nodes were precision-verified where needed;
- the transcript bundle was cached for reuse;
- downstream analysis can cite actual dialogue rather than proxy metrics.
