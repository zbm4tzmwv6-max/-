#!/usr/bin/env python3
"""Extract and re-transcribe a decisive media slice with the stronger small model."""
from __future__ import annotations
import argparse, os, shutil, subprocess, tempfile
from pathlib import Path


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('--start', required=True, help='ffmpeg timestamp, e.g. 00:49:30')
    ap.add_argument('--end', required=True, help='ffmpeg timestamp, e.g. 00:56:00')
    ap.add_argument('--cli', required=True)
    ap.add_argument('--model', required=True)
    ap.add_argument('--output-prefix', required=True)
    ap.add_argument('--language', default='zh')
    ap.add_argument('--threads', type=int, default=max(2,min(8,os.cpu_count() or 4)))
    a=ap.parse_args()
    ff=shutil.which('ffmpeg')
    if not ff: raise SystemExit('ffmpeg not found')
    with tempfile.TemporaryDirectory(prefix='speech-refine-') as td:
        wav=Path(td)/'slice.wav'
        subprocess.check_call([ff,'-y','-ss',a.start,'-to',a.end,'-i',a.input,'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(wav)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        env=os.environ.copy(); env['LD_LIBRARY_PATH']=str(Path(a.cli).resolve().parent)+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
        subprocess.check_call([a.cli,'-m',a.model,'-l',a.language,'-t',str(a.threads),'-osrt','-otxt','-oj','-of',a.output_prefix,str(wav)],env=env)

if __name__=='__main__': main()
