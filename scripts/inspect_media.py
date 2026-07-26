#!/usr/bin/env python3

import argparse
import array
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path


def run_json(command: list[str]) -> dict:
    completed = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(completed.stdout)


def parse_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def channel_similarity(
    media: Path, start_seconds: float, sample_seconds: float
) -> dict:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-ss",
        str(max(0.0, start_seconds)),
        "-i",
        str(media),
        "-map",
        "0:a:0",
        "-t",
        str(max(1.0, sample_seconds)),
        "-ac",
        "2",
        "-ar",
        "8000",
        "-f",
        "f32le",
        "pipe:1",
    ]
    completed = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    values = array.array("f")
    values.frombytes(completed.stdout)
    if sys.byteorder != "little":
        values.byteswap()
    frame_count = len(values) // 2
    if frame_count < 800:
        return {
            "sample_frames": frame_count,
            "correlation": None,
            "gain_normalized_residual": None,
            "near_identical": None,
            "reason": "insufficient decoded stereo samples",
        }

    sum_left = 0.0
    sum_right = 0.0
    sum_left_sq = 0.0
    sum_right_sq = 0.0
    sum_cross = 0.0
    for index in range(frame_count):
        left = float(values[index * 2])
        right = float(values[index * 2 + 1])
        sum_left += left
        sum_right += right
        sum_left_sq += left * left
        sum_right_sq += right * right
        sum_cross += left * right

    mean_left = sum_left / frame_count
    mean_right = sum_right / frame_count
    covariance = sum_cross - frame_count * mean_left * mean_right
    variance_left = sum_left_sq - frame_count * mean_left * mean_left
    variance_right = sum_right_sq - frame_count * mean_right * mean_right
    denominator = math.sqrt(max(variance_left * variance_right, 0.0))
    correlation = covariance / denominator if denominator > 1e-12 else None

    gain = sum_cross / sum_right_sq if sum_right_sq > 1e-12 else 0.0
    residual_sq = 0.0
    for index in range(frame_count):
        left = float(values[index * 2])
        right = float(values[index * 2 + 1])
        residual = left - gain * right
        residual_sq += residual * residual
    residual_ratio = math.sqrt(residual_sq / max(sum_left_sq, 1e-12))
    near_identical = bool(
        correlation is not None
        and correlation >= 0.999
        and residual_ratio <= 0.02
    )
    return {
        "sample_frames": frame_count,
        "correlation": correlation,
        "gain_normalized_residual": residual_ratio,
        "near_identical": near_identical,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("media", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample-start", type=float, default=0.0)
    parser.add_argument("--sample-seconds", type=float, default=120.0)
    args = parser.parse_args()

    if not args.media.is_file():
        raise FileNotFoundError(args.media)
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        raise RuntimeError("ffprobe and ffmpeg are required")

    probe = run_json(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(args.media),
        ]
    )
    audio_streams = [
        stream
        for stream in probe.get("streams", [])
        if stream.get("codec_type") == "audio"
    ]
    if not audio_streams:
        raise RuntimeError("No audio stream found")
    audio = audio_streams[0]
    duration = parse_float(probe.get("format", {}).get("duration"))
    if duration is None:
        duration = parse_float(audio.get("duration"))
    channels = int(audio.get("channels") or 0)

    result = {
        "path": str(args.media.resolve()),
        "size_bytes": args.media.stat().st_size,
        "duration_seconds": duration,
        "audio_stream_count": len(audio_streams),
        "codec": audio.get("codec_name"),
        "sample_rate": int(audio["sample_rate"]) if audio.get("sample_rate") else None,
        "channels": channels,
        "channel_layout": audio.get("channel_layout"),
        "bit_rate": parse_float(audio.get("bit_rate")),
        "stereo_similarity": None,
    }
    if channels >= 2:
        result["stereo_similarity"] = channel_similarity(
            args.media,
            args.sample_start,
            min(args.sample_seconds, duration or args.sample_seconds),
        )

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
