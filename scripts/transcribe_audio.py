#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from faster_whisper import WhisperModel


DEFAULT_PROMPT = (
    "以下是一段中文对话。请忠实逐字转写，保留口头语、重复、停顿式表达、"
    "中英文混用、专有名词和数字，不要总结或改写。"
)


def timestamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def output_paths(prefix: Path) -> dict[str, Path]:
    base = str(prefix)
    return {
        "raw": Path(base + ".raw.txt"),
        "segments": Path(base + ".segments.jsonl"),
        "metadata": Path(base + ".metadata.json"),
        "progress": Path(base + ".progress.json"),
    }


def atomic_json(path: Path, payload: dict) -> None:
    temporary = Path(str(path) + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def read_existing(segments_path: Path) -> tuple[int, int, float, str]:
    count = 0
    characters = 0
    last_end = 0.0
    tail = ""
    with segments_path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid checkpoint JSON on line {line_number}; "
                    "preserve the file and repair it before resuming"
                ) from exc
            count += 1
            text = str(item.get("text", ""))
            characters += len(text)
            last_end = max(last_end, float(item["end"]))
            tail = (tail + text)[-400:]
    return count, characters, last_end, tail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("media", type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--title")
    parser.add_argument("--model", default="large-v3-turbo")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--hotwords")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--cpu-threads", type=int, default=8)
    parser.add_argument(
        "--model-cache",
        type=Path,
        default=Path(
            os.environ.get(
                "TRANSCRIBE_MODEL_CACHE",
                "/tmp/hf-transcript-cache/hub",
            )
        ),
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.media.is_file():
        raise FileNotFoundError(args.media)
    if args.resume and args.force:
        raise ValueError("--resume and --force cannot be combined")

    paths = output_paths(args.output_prefix)
    args.output_prefix.parent.mkdir(parents=True, exist_ok=True)
    existing = [path for path in paths.values() if path.exists()]
    if args.force:
        for path in existing:
            path.unlink()
        existing = []
    if existing and not args.resume:
        rendered = ", ".join(str(path) for path in existing)
        raise FileExistsError(
            f"Refusing to overwrite existing output: {rendered}. "
            "Use --resume for a partial job or --force for an intentional rerun."
        )

    title = args.title or args.media.stem
    prompt = args.prompt
    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    language = None if args.language.lower() == "auto" else args.language

    segment_count = 0
    characters = 0
    resume_end = 0.0
    context_tail = ""
    file_mode = "w"
    if args.resume:
        if paths["metadata"].exists():
            metadata = json.loads(paths["metadata"].read_text(encoding="utf-8"))
            if metadata.get("completed"):
                print(json.dumps(metadata, ensure_ascii=False), flush=True)
                return 0
        if not paths["segments"].exists() or not paths["raw"].exists():
            raise FileNotFoundError(
                "Resume requires both the .segments.jsonl and .raw.txt checkpoints"
            )
        segment_count, characters, resume_end, context_tail = read_existing(
            paths["segments"]
        )
        file_mode = "a"

    started = time.monotonic()
    print(
        f"Loading model={args.model} device={args.device} "
        f"compute_type={args.compute_type} cache={args.model_cache}",
        flush=True,
    )
    args.model_cache.mkdir(parents=True, exist_ok=True)
    model = WhisperModel(
        args.model,
        device=args.device,
        compute_type=args.compute_type,
        cpu_threads=args.cpu_threads,
        num_workers=1,
        download_root=str(args.model_cache),
    )
    print(f"Model ready after {time.monotonic() - started:.1f}s", flush=True)

    effective_prompt = prompt
    if context_tail:
        effective_prompt = f"{prompt}\n前文末尾供衔接：{context_tail}"
    transcription_options = {
        "language": language,
        "task": "transcribe",
        "beam_size": 5,
        "best_of": 5,
        "patience": 1.0,
        "temperature": 0.0,
        "condition_on_previous_text": True,
        "initial_prompt": effective_prompt,
        "vad_filter": True,
        "vad_parameters": {
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 250,
        },
        "word_timestamps": True,
        "hallucination_silence_threshold": 2.0,
    }
    if args.hotwords:
        transcription_options["hotwords"] = args.hotwords
    if resume_end > 0:
        transcription_options["clip_timestamps"] = [resume_end]

    segments, info = model.transcribe(str(args.media), **transcription_options)
    progress = {
        "state": "transcribing",
        "media": str(args.media.resolve()),
        "title": title,
        "model": args.model,
        "language": info.language,
        "duration_seconds": info.duration,
        "segment_count": segment_count,
        "transcript_characters": characters,
        "last_audio_second": resume_end,
        "last_audio_timestamp": timestamp(resume_end),
        "resumed": bool(resume_end),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(paths["progress"], progress)

    with paths["raw"].open(file_mode, encoding="utf-8") as text_file, paths[
        "segments"
    ].open(file_mode, encoding="utf-8") as jsonl_file:
        if file_mode == "w":
            text_file.write(f"《{title}》原始自动转写\n")
            text_file.write("说明：保留原始分段时间戳；此文件未经最终质检。\n\n")
        last_reported_audio = resume_end
        for segment in segments:
            text = segment.text.strip()
            if not text or float(segment.end) <= resume_end + 0.05:
                continue
            segment_count += 1
            characters += len(text)
            payload = {
                "id": segment_count,
                "start": float(segment.start),
                "end": float(segment.end),
                "text": text,
                "avg_logprob": float(segment.avg_logprob),
                "no_speech_prob": float(segment.no_speech_prob),
                "compression_ratio": float(segment.compression_ratio),
                "words": [
                    {
                        "start": word.start,
                        "end": word.end,
                        "word": word.word,
                        "probability": word.probability,
                    }
                    for word in (segment.words or [])
                ],
            }
            text_file.write(
                f"[{timestamp(segment.start)}–{timestamp(segment.end)}] {text}\n"
            )
            jsonl_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
            text_file.flush()
            jsonl_file.flush()

            should_report = (
                segment_count == 1
                or float(segment.end) - last_reported_audio >= 300
            )
            if should_report:
                progress.update(
                    {
                        "segment_count": segment_count,
                        "transcript_characters": characters,
                        "last_audio_second": float(segment.end),
                        "last_audio_timestamp": timestamp(segment.end),
                        "elapsed_seconds": time.monotonic() - started,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                atomic_json(paths["progress"], progress)
                print(
                    f"progress segment={segment_count} "
                    f"audio={timestamp(segment.end)} "
                    f"elapsed={(time.monotonic() - started) / 60:.1f}m",
                    flush=True,
                )
                last_reported_audio = float(segment.end)

    elapsed = time.monotonic() - started
    last_end = 0.0
    if paths["segments"].exists():
        _, _, last_end, _ = read_existing(paths["segments"])
    metadata = {
        "completed": True,
        "engine": "faster-whisper",
        "model": args.model,
        "device": args.device,
        "compute_type": args.compute_type,
        "model_cache": str(args.model_cache.resolve()),
        "language": info.language,
        "language_probability": info.language_probability,
        "duration_seconds": info.duration,
        "duration_after_vad_seconds": info.duration_after_vad,
        "segment_count": segment_count,
        "transcript_characters": characters,
        "last_audio_second": last_end,
        "elapsed_seconds_this_run": elapsed,
        "media": str(args.media.resolve()),
        "raw_transcript": str(paths["raw"].resolve()),
        "segments_jsonl": str(paths["segments"].resolve()),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(paths["metadata"], metadata)
    progress.update(
        {
            "state": "completed",
            "segment_count": segment_count,
            "transcript_characters": characters,
            "last_audio_second": last_end,
            "last_audio_timestamp": timestamp(last_end),
            "elapsed_seconds": elapsed,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    atomic_json(paths["progress"], progress)
    print(json.dumps(metadata, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
