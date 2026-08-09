#!/usr/bin/env python3
"""Reliable media transcription wrapper for whisper.cpp.

Normalizes media to 16 kHz mono WAV, runs whisper-cli, emits txt/srt/json,
and writes an ASR manifest. Designed for Mandarin audio/video, including long sales Calls, meetings, interviews, courses, podcasts, and voice notes.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, time
from pathlib import Path


def sha256(path: Path, chunk=1024*1024) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def run(cmd, env=None):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    if p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(map(str,cmd))}\n{p.stdout[-5000:]}")
    return p.stdout


def srt_to_timestamped_txt(srt_path: Path, out_path: Path):
    raw = srt_path.read_text('utf-8', errors='replace').replace('\r\n','\n')
    blocks = re.split(r'\n\s*\n', raw.strip())
    lines = []
    for b in blocks:
        parts = [x.strip() for x in b.split('\n') if x.strip()]
        if len(parts) < 3 or '-->' not in parts[1]:
            continue
        ts = parts[1].replace(',', '.')
        content = ' '.join(parts[2:])
        lines.append(f'[{ts}] {content}')
    out_path.write_text('\n'.join(lines)+'\n','utf-8')


def resolve_cli(explicit: str|None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    for n in ('whisper-cli','whisper.cpp','main'):
        q = shutil.which(n)
        if q:
            candidates.append(Path(q))
    candidates += [
        Path('/mnt/data/_whisper_bin/pkg/whisper-bin-ubuntu-x64/whisper-cli'),
        Path(__file__).resolve().parents[1]/'runtime'/'whisper-bin-ubuntu-x64'/'whisper-cli',
    ]
    for p in candidates:
        if p.exists() and os.access(p, os.X_OK):
            return p.resolve()
    raise FileNotFoundError('whisper-cli not found; bootstrap runtime before retrying')


def resolve_model(explicit: str|None, strength: str) -> Path:
    if explicit and Path(explicit).exists():
        return Path(explicit).resolve()
    names = ['ggml-small-q5_1.bin'] if strength == 'small' else ['ggml-base-q5_1.bin']
    roots = [Path('/mnt/data'), Path(__file__).resolve().parents[1]/'runtime', Path.home()/'.cache'/'speech-to-text-asr']
    for root in roots:
        for name in names:
            for p in [root/name, root/'models'/name]:
                if p.exists():
                    return p.resolve()
    raise FileNotFoundError(f"{names[0]} not found; bootstrap model before retrying")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('--output-dir', default=None)
    ap.add_argument('--cli', default=None)
    ap.add_argument('--model', default=None)
    ap.add_argument('--strength', choices=['base','small'], default='base')
    ap.add_argument('--language', default='zh')
    ap.add_argument('--threads', type=int, default=max(2, min(8, os.cpu_count() or 4)))
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    src = Path(args.input).resolve()
    if not src.exists():
        raise SystemExit(f'input not found: {src}')
    outdir = Path(args.output_dir).resolve() if args.output_dir else src.parent
    outdir.mkdir(parents=True, exist_ok=True)
    stem = src.stem
    prefix = outdir/f'{stem}.asr-{args.strength}'
    wav = outdir/f'{stem}.normalized-16k.wav'
    manifest = outdir/f'{stem}.asr-manifest.json'
    digest = sha256(src)

    if manifest.exists() and not args.force:
        try:
            m = json.loads(manifest.read_text('utf-8'))
            if m.get('source_sha256') == digest and Path(m.get('outputs',{}).get('srt','')).exists():
                print(json.dumps({'status':'reused','manifest':str(manifest),'outputs':m['outputs']}, ensure_ascii=False))
                return
        except Exception:
            pass

    try:
        cli = resolve_cli(args.cli)
        model = resolve_model(args.model,args.strength)
    except FileNotFoundError:
        bootstrap = Path(__file__).resolve().parent/'bootstrap_from_session_assets.sh'
        runtime = Path(__file__).resolve().parents[1]/'runtime'
        if bootstrap.exists():
            subprocess.run([str(bootstrap), str(runtime)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        cli = resolve_cli(args.cli)
        model = resolve_model(args.model,args.strength)

    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise SystemExit('ffmpeg not found')

    run([ffmpeg,'-y','-i',str(src),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(wav)])
    env = os.environ.copy()
    env['LD_LIBRARY_PATH'] = str(cli.parent)+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    t0 = time.time()
    log = run([str(cli),'-m',str(model),'-l',args.language,'-t',str(args.threads),'-osrt','-otxt','-oj','-of',str(prefix),str(wav)], env=env)
    elapsed = round(time.time()-t0,2)
    timestamped = outdir/f'{stem}.transcript.txt'
    srt_path = Path(str(prefix)+'.srt')
    srt_to_timestamped_txt(srt_path, timestamped)
    outputs = {
        'transcript':str(timestamped),
        'raw_txt':str(prefix)+'.txt',
        'srt':str(prefix)+'.srt',
        'json':str(prefix)+'.json',
        'wav':str(wav)
    }
    for k,p in outputs.items():
        if k != 'wav' and not Path(p).exists():
            raise RuntimeError(f'missing expected output: {p}')
    m = {
        'source':str(src),'source_sha256':digest,'source_size':src.stat().st_size,
        'engine':'whisper.cpp','cli':str(cli),'model':str(model),'strength':args.strength,
        'language':args.language,'threads':args.threads,'elapsed_seconds':elapsed,
        'outputs':outputs,'log_tail':log[-1200:]
    }
    manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2),'utf-8')
    print(json.dumps({'status':'ok','manifest':str(manifest),'outputs':outputs,'elapsed_seconds':elapsed}, ensure_ascii=False))


if __name__ == '__main__':
    main()
