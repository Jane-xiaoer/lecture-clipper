#!/usr/bin/env python3
"""
Step 0: 视频转文字 → 生成 SRT 字幕

用法：
  python step0_transcribe.py --video input.mp4 --out input.srt
  python step0_transcribe.py --video input.mp4 --out input.srt --provider groq
  python step0_transcribe.py --video input.mp4 --out input.srt --provider openai

支持的转写服务：
  groq   - 免费 Whisper API，速度快（推荐，需 GROQ_API_KEY）
  openai - OpenAI Whisper API（需 OPENAI_API_KEY，$0.006/分钟）
  local  - 本地 faster-whisper（免费，需 pip install faster-whisper，慢）

Groq 免费申请：https://console.groq.com
"""
import argparse, os, subprocess, sys, tempfile
from pathlib import Path

# ── 音频提取 ──────────────────────────────────────────────────────
def extract_audio(video_path: str, tmp_dir: str) -> str:
    """把视频里的音频提取出来（小文件，方便上传 API）"""
    audio_path = str(Path(tmp_dir) / "audio.mp3")
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn",                    # 不要视频
        "-ar", "16000",           # 16kHz（Whisper 最优）
        "-ac", "1",               # 单声道
        "-b:a", "64k",            # 64kbps，够用且文件小
        audio_path
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"音频提取失败: {r.stderr[-300:]}")
    size_mb = Path(audio_path).stat().st_size / 1024 / 1024
    print(f"  音频提取完成：{size_mb:.1f}MB")
    return audio_path

# ── 格式转换 ──────────────────────────────────────────────────────
def seconds_to_srt_time(s: float) -> str:
    h = int(s) // 3600
    m = (int(s) % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{int(sec):02d},{int((sec%1)*1000):03d}"

def segments_to_srt(segments) -> str:
    lines = []
    for i, seg in enumerate(segments, 1):
        start = seconds_to_srt_time(seg["start"])
        end   = seconds_to_srt_time(seg["end"])
        text  = seg["text"].strip()
        if text:
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)

# ── 转写：Groq（免费，推荐）─────────────────────────────────────
def transcribe_groq(audio_path: str) -> list:
    from openai import OpenAI
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("需要 GROQ_API_KEY，免费申请：https://console.groq.com")

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    print("  调用 Groq Whisper API...")
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=f,
            response_format="verbose_json",
            language="zh",
            timestamp_granularities=["segment"],
        )
    return [{"start": s.start, "end": s.end, "text": s.text} for s in result.segments]

# ── 转写：OpenAI Whisper API ──────────────────────────────────────
def transcribe_openai(audio_path: str) -> list:
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("需要 OPENAI_API_KEY")

    client = OpenAI(api_key=api_key)

    # Whisper API 限制 25MB，需要分块
    size_mb = Path(audio_path).stat().st_size / 1024 / 1024
    if size_mb > 24:
        return transcribe_openai_chunked(client, audio_path)

    print("  调用 OpenAI Whisper API...")
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            language="zh",
            timestamp_granularities=["segment"],
        )
    return [{"start": s.start, "end": s.end, "text": s.text} for s in result.segments]

def transcribe_openai_chunked(client, audio_path: str, chunk_min=10) -> list:
    """超过 25MB 的音频分块处理"""
    import math
    audio = Path(audio_path)
    duration_s = get_audio_duration(str(audio))
    chunk_s = chunk_min * 60
    n_chunks = math.ceil(duration_s / chunk_s)
    print(f"  音频较长，分 {n_chunks} 段处理...")

    all_segments = []
    offset = 0.0
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n_chunks):
            chunk_path = str(Path(tmp) / f"chunk_{i:02d}.mp3")
            subprocess.run([
                "ffmpeg", "-y", "-i", str(audio),
                "-ss", str(int(offset)), "-t", str(chunk_s),
                "-c", "copy", chunk_path
            ], capture_output=True)
            print(f"    第 {i+1}/{n_chunks} 段...")
            with open(chunk_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    model="whisper-1", file=f,
                    response_format="verbose_json", language="zh",
                    timestamp_granularities=["segment"],
                )
            for s in result.segments:
                all_segments.append({
                    "start": s.start + offset,
                    "end":   s.end   + offset,
                    "text":  s.text
                })
            offset += chunk_s
    return all_segments

# ── 转写：本地 faster-whisper ─────────────────────────────────────
def transcribe_local(audio_path: str) -> list:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("请先安装：pip install faster-whisper")

    print("  加载本地 Whisper 模型（首次需下载 ~1.5GB）...")
    model = WhisperModel("large-v3", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, language="zh", beam_size=5)
    return [{"start": s.start, "end": s.end, "text": s.text} for s in segments]

def get_audio_duration(audio_path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_path],
        capture_output=True, text=True
    )
    import json
    return float(json.loads(r.stdout).get("format", {}).get("duration", 3600))

# ── 自动加载 .env 文件 ─────────────────────────────────────────────
def load_env():
    for path in [
        os.path.expanduser("~/.shared-skills/api-registry/.env"),
        os.path.expanduser("~/.hermes/.env"),
        ".env",
    ]:
        if os.path.exists(path):
            for line in open(path):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k = k.strip(); v = v.strip().strip('"').strip("'")
                    if k and v and k not in os.environ:
                        os.environ[k] = v

# ── 主函数 ────────────────────────────────────────────────────────
def run(video_path: str, out_srt: str, provider: str = "auto"):
    load_env()

    # 自动选 provider
    if provider == "auto":
        if os.environ.get("GROQ_API_KEY"):
            provider = "groq"
            print("  使用 Groq Whisper（免费）")
        elif os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
            print("  使用 OpenAI Whisper API")
        else:
            provider = "local"
            print("  使用本地 faster-whisper（无 API Key）")

    with tempfile.TemporaryDirectory() as tmp:
        print("提取音频...")
        audio = extract_audio(video_path, tmp)

        print(f"转写中（{provider}）...")
        if provider == "groq":
            segments = transcribe_groq(audio)
        elif provider == "openai":
            segments = transcribe_openai(audio)
        elif provider == "local":
            segments = transcribe_local(audio)
        else:
            raise ValueError(f"未知 provider: {provider}")

    srt = segments_to_srt(segments)
    Path(out_srt).write_text(srt, encoding="utf-8")
    print(f"✅ 字幕生成完成：{out_srt}（{len(segments)} 行）")
    return out_srt

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--video",    required=True, help="输入视频路径")
    p.add_argument("--out",      required=True, help="输出 SRT 路径")
    p.add_argument("--provider", default="auto", help="groq | openai | local | auto")
    args = p.parse_args()
    run(args.video, args.out, args.provider)
