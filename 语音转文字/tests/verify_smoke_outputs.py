#!/usr/bin/env python3
"""Validate real whisper.cpp smoke outputs; empty placeholder files must fail."""
import hashlib
import json
import re
import sys
import wave
from pathlib import Path


def check(condition, message):
    if not condition:
        raise ValueError(message)


def validate(source, outdir, cli, model):
    stem = source.stem
    expected = {
        'transcript': outdir / f'{stem}.transcript.txt',
        'raw_txt': outdir / f'{stem}.asr-base.txt',
        'srt': outdir / f'{stem}.asr-base.srt',
        'json': outdir / f'{stem}.asr-base.json',
        'wav': outdir / f'{stem}.normalized-16k.wav',
    }
    manifest_path = outdir / f'{stem}.asr-manifest.json'
    for path in [*expected.values(), manifest_path]:
        check(path.is_file() and path.stat().st_size > 0, f'Missing/empty output: {path}')
    manifest = json.loads(manifest_path.read_text())
    check(manifest['source_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest(), 'Source hash mismatch')
    check(manifest['source_size'] == source.stat().st_size, 'Source size mismatch')
    for key, value in {'source': source, 'cli': cli, 'model': model}.items():
        check(Path(manifest[key]).resolve() == value.resolve(), f'Manifest {key} mismatch')
    for key, value in {'engine': 'whisper.cpp', 'strength': 'base', 'language': 'en'}.items():
        check(manifest[key] == value, f'Manifest {key} mismatch')
    for key, path in expected.items():
        check(Path(manifest['outputs'][key]).resolve() == path.resolve(), f'Wrong output path: {key}')
    with wave.open(str(expected['wav'])) as wav:
        check((wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2), 'WAV must be 16 kHz mono PCM16')
        duration = wav.getnframes() / wav.getframerate()
    check(3 <= duration <= 30, f'Unexpected fixture duration: {duration}')

    srt = expected['srt'].read_text().strip()
    blocks = re.split(r'\n\s*\n', srt)
    text_lines = []
    timestamped = []
    previous_end = 0
    for index, block in enumerate(blocks, 1):
        lines = block.splitlines()
        check(len(lines) >= 3 and lines[0].strip() == str(index), 'Invalid SRT block/index')
        match = re.fullmatch(r'(\d{2,}):([0-5]\d):([0-5]\d),(\d{3}) --> (\d{2,}):([0-5]\d):([0-5]\d),(\d{3})', lines[1].strip())
        check(match is not None, 'Invalid SRT timestamp')
        h, m, s, ms, eh, em, es, ems = map(int, match.groups())
        start, end = h*3600+m*60+s+ms/1000, eh*3600+em*60+es+ems/1000
        check(previous_end <= start < end <= duration + 1, 'Nonmonotonic/out-of-range SRT timestamps')
        previous_end = end
        content = ' '.join(line.strip() for line in lines[2:]).strip()
        check(bool(content), 'Empty SRT text')
        text_lines.append(content)
        timestamped.append(f'[{lines[1].strip().replace(",", ".")}] {content}')
    check(expected['transcript'].read_text().strip() == '\n'.join(timestamped), 'Transcript/SRT mismatch')
    result = json.loads(expected['json'].read_text())
    segments = result['transcription']
    check(isinstance(segments, list) and len(segments) > 0, 'Empty JSON transcription')
    json_text = ' '.join(segment['text'] for segment in segments)
    normalize = lambda text: ' '.join(re.findall(r'[a-z]+', text.lower()))
    raw = normalize(expected['raw_txt'].read_text())
    check(bool(raw) and raw == normalize(' '.join(text_lines)) == normalize(json_text), 'TXT/SRT/JSON text mismatch')
    # Tolerate ASR punctuation and minor wording differences, reject unrelated hallucinations.
    words = set(raw.split())
    hits = words & {'hello', 'world', 'speech', 'test', 'audio', 'listening'}
    check(len(hits) >= 3, f'Fixture speech not recognized: {raw}')
    return {'status': 'passed', 'duration_seconds': duration, 'segments': len(segments), 'keyword_hits': sorted(hits)}


if __name__ == '__main__':
    source, outdir, cli, model = (Path(arg).resolve() for arg in sys.argv[1:])
    report = outdir.parent / 'validation.json'
    try:
        summary = validate(source, outdir, cli, model)
    except Exception as exc:
        report.write_text(json.dumps({'status': 'failed', 'error': str(exc)}, indent=2) + '\n')
        raise
    report.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary))
