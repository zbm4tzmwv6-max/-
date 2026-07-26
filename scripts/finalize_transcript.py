#!/usr/bin/env python3

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


def stamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def normalize(text: str) -> str:
    return re.sub(r"[\s，。！？；：、,.!?;:'\"“”‘’\-—…]+", "", text).lower()


def join_parts(parts: list[str]) -> str:
    result = ""
    for part in parts:
        part = re.sub(r"\s+", " ", part.strip())
        if not part:
            continue
        if (
            result
            and re.search(r"[A-Za-z0-9]$", result)
            and re.match(r"^[A-Za-z0-9]", part)
        ):
            result += " "
        result += part
    return result


def load_segments(path: Path) -> list[dict]:
    segments = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Invalid JSON in {path} line {line_number}"
                ) from exc
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            item["text"] = text
            item["start"] = float(item["start"])
            item["end"] = float(item["end"])
            segments.append(item)
    if not segments:
        raise RuntimeError("No non-empty transcript segments found")
    return segments


def build_groups(
    segments: list[dict],
    max_gap: float,
    max_span: float,
    max_characters: int,
) -> list[dict]:
    groups = []
    current = None
    for item in segments:
        speaker = item.get("speaker")
        if current is None:
            current = {
                "start": item["start"],
                "end": item["end"],
                "speaker": speaker,
                "parts": [item["text"]],
            }
            continue
        gap = item["start"] - current["end"]
        text_length = sum(len(part) for part in current["parts"])
        should_continue = (
            gap <= max_gap
            and item["end"] - current["start"] <= max_span
            and text_length + len(item["text"]) <= max_characters
            and speaker == current["speaker"]
        )
        if should_continue:
            current["end"] = item["end"]
            current["parts"].append(item["text"])
        else:
            groups.append(current)
            current = {
                "start": item["start"],
                "end": item["end"],
                "speaker": speaker,
                "parts": [item["text"]],
            }
    if current is not None:
        groups.append(current)
    return groups


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("segments", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--qa", required=True, type=Path)
    parser.add_argument("--title")
    parser.add_argument(
        "--speaker-note",
        default=(
            "正文未强行标注说话人；只有独立声道或可靠证据时才应添加角色，"
            "以免把快速接话或重叠语音归错人。"
        ),
    )
    parser.add_argument("--max-gap", type=float, default=1.5)
    parser.add_argument("--max-span", type=float, default=24.0)
    parser.add_argument("--max-characters", type=int, default=210)
    args = parser.parse_args()

    segments = load_segments(args.segments)
    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    if not metadata.get("completed"):
        raise RuntimeError("Metadata does not mark the transcription complete")

    duration = float(metadata.get("duration_seconds") or segments[-1]["end"])
    title = args.title or Path(metadata.get("media", args.segments.stem)).stem
    warnings = []
    timestamp_violations = []
    overlaps = []
    suspicious_segments = []
    low_confidence_words = []
    total_word_count = 0
    normalized_counts = Counter()
    recent_normalized = []

    previous = None
    for index, item in enumerate(segments):
        if item["end"] < item["start"]:
            timestamp_violations.append(
                {"index": index, "start": item["start"], "end": item["end"]}
            )
        if previous is not None:
            if item["start"] < previous["start"]:
                timestamp_violations.append(
                    {
                        "index": index,
                        "previous_start": previous["start"],
                        "start": item["start"],
                    }
                )
            if item["start"] < previous["end"] - 0.25:
                overlaps.append(
                    {
                        "index": index,
                        "start": item["start"],
                        "previous_end": previous["end"],
                    }
                )
        normalized_text = normalize(item["text"])
        if len(normalized_text) >= 8:
            normalized_counts[normalized_text] += 1
            for prior_index, prior_end, prior_text in recent_normalized:
                if normalized_text == prior_text:
                    suspicious_segments.append(
                        {
                            "reason": "nearby exact repetition",
                            "first_index": prior_index,
                            "second_index": index,
                            "timestamp": stamp(item["start"]),
                            "text": item["text"][:160],
                        }
                    )
            recent_normalized.append((index, item["end"], normalized_text))
            recent_normalized = [
                prior
                for prior in recent_normalized
                if item["start"] - prior[1] <= 45
            ]
        if float(item.get("compression_ratio", 0.0)) >= 2.4:
            suspicious_segments.append(
                {
                    "reason": "high compression ratio",
                    "index": index,
                    "timestamp": stamp(item["start"]),
                    "value": item.get("compression_ratio"),
                    "text": item["text"][:160],
                }
            )
        for word in item.get("words", []):
            token = str(word.get("word", "")).strip()
            probability = word.get("probability")
            if not token or probability is None:
                continue
            total_word_count += 1
            probability = float(probability)
            if probability < 0.25 and normalize(token):
                low_confidence_words.append(
                    {
                        "timestamp": stamp(
                            float(
                                word.get("start")
                                if word.get("start") is not None
                                else item["start"]
                            )
                        ),
                        "word": token,
                        "probability": probability,
                        "segment_index": index,
                    }
                )
        previous = item

    repeated_phrases = [
        {"normalized_text": text[:160], "count": count}
        for text, count in normalized_counts.most_common()
        if count >= 3
    ][:30]
    initial_gap = max(0.0, segments[0]["start"])
    trailing_gap = max(0.0, duration - segments[-1]["end"])
    if timestamp_violations:
        warnings.append("timestamp order or segment bounds require repair")
    if overlaps:
        warnings.append("overlapping ASR segments require spot-checking")
    if suspicious_segments:
        warnings.append("possible repeated or compressed ASR output requires review")
    if repeated_phrases:
        warnings.append("phrases repeated three or more times require contextual review")
    if initial_gap > 30:
        warnings.append("more than 30 seconds precede the first recognized speech")
    if trailing_gap > max(30.0, duration * 0.05):
        warnings.append("substantial audio remains after the last recognized speech")
    if segments[-1]["end"] > duration + 2:
        warnings.append("recognized timestamp extends beyond probed media duration")

    qa = {
        "status": "review_required" if warnings else "pass",
        "media_duration_seconds": duration,
        "media_duration": stamp(duration),
        "first_speech_second": segments[0]["start"],
        "first_speech": stamp(segments[0]["start"]),
        "last_speech_second": segments[-1]["end"],
        "last_speech": stamp(segments[-1]["end"]),
        "initial_gap_seconds": initial_gap,
        "trailing_gap_seconds": trailing_gap,
        "segment_count": len(segments),
        "transcript_characters": sum(len(item["text"]) for item in segments),
        "timestamp_violations": timestamp_violations,
        "overlaps": overlaps[:100],
        "suspicious_segments": suspicious_segments[:100],
        "repeated_phrases": repeated_phrases,
        "total_word_count": total_word_count,
        "low_confidence_word_count": len(low_confidence_words),
        "low_confidence_words": low_confidence_words[:200],
        "warnings": warnings,
    }
    args.qa.parent.mkdir(parents=True, exist_ok=True)
    args.qa.write_text(
        json.dumps(qa, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if timestamp_violations:
        raise RuntimeError(
            f"QA failed: timestamp violations were written to {args.qa}"
        )

    groups = build_groups(
        segments,
        max_gap=args.max_gap,
        max_span=args.max_span,
        max_characters=args.max_characters,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as out:
        out.write(f"《{title}》逐字稿\n")
        out.write(f"录音时长：{stamp(duration)}\n")
        out.write(
            f"正文覆盖：{stamp(segments[0]['start'])}–"
            f"{stamp(segments[-1]['end'])}"
        )
        if trailing_gap > 0.5:
            out.write(f"（末尾约 {round(trailing_gap)} 秒无可识别语音）")
        out.write("\n")
        out.write(
            "说明：本稿按原始语序保留口头语、重复、停顿式表达和中英文混用，"
            "不做总结或语义改写。"
        )
        out.write(args.speaker_note)
        out.write(
            "专有名词、重叠说话及音质不清处可能存在少量听辨误差；"
            "正式引用原话时请按时间戳回听。\n\n"
        )
        for group in groups:
            text = join_parts(group["parts"])
            speaker = f" {group['speaker']}：" if group.get("speaker") else " "
            out.write(
                f"[{stamp(group['start'])}–{stamp(group['end'])}]"
                f"{speaker}{text}\n\n"
            )

    print(json.dumps(qa, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
