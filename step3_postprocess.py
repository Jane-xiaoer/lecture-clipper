#!/usr/bin/env python3
"""
Step 3: 字幕烧入 — 标题（顶部全程）+ 字幕（底部跟读）硬编码进视频
视频内容不做任何裁剪。

用法：
  python step3_postprocess.py --clips clips/ --out published/
  python step3_postprocess.py --clips clips/ --out published/ --ffmpeg /path/to/ffmpeg

ffmpeg 要求：需编译 libass（用于烧入字幕）
  - 先运行 python setup_ffmpeg.py 自动安装
  - 或手动指定 --ffmpeg 路径
"""
import argparse, re, subprocess, sys, tempfile
from pathlib import Path

# ── 路径配置 ──────────────────────────────────────────────────────
def find_ffmpeg():
    """优先读 setup_ffmpeg.py 保存的配置，否则自动搜索"""
    import shutil

    # 读已保存配置
    config = Path.home() / ".lecture-clipper" / "config.txt"
    if config.exists():
        for line in config.read_text().splitlines():
            if line.startswith("FFMPEG="):
                ff = line.split("=", 1)[1].strip()
                if Path(ff).exists():
                    return ff

    # 搜索常见位置
    candidates = [
        str(Path.home() / ".lecture-clipper" / "ffmpeg"),
        "/Users/jane/downloaded/Recordly/node_modules/ffmpeg-static/ffmpeg",  # Jane 的机器
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        "ffmpeg",
    ]
    for ff in candidates:
        resolved = shutil.which(ff) or (ff if Path(ff).exists() else None)
        if not resolved:
            continue
        r = subprocess.run([resolved, "-filters"], capture_output=True, text=True, timeout=5)
        if "ass" in r.stdout or "subtitles" in r.stdout:
            return resolved

    return None

# ── 字体 ──────────────────────────────────────────────────────────
CHINESE_FONTS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",   # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux
    "/Library/Fonts/Arial Unicode MS.ttf",
]

def find_font():
    for f in CHINESE_FONTS:
        if Path(f).exists():
            return f
    return None

# ── SRT 解析 ──────────────────────────────────────────────────────
def srt_time_to_sec(t):
    h, m, rest = t.strip().split(':')
    s, ms = rest.split(',')
    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000

def sec_to_srt_time(s):
    h = int(s) // 3600
    m = (int(s) % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{int(sec):02d},{int((sec%1)*1000):03d}"

def parse_srt(srt_path):
    content = srt_path.read_text(encoding='utf-8')
    entries = []
    for block in re.split(r'\n\n+', content.strip()):
        lines = block.strip().split('\n')
        time_line = next((l for l in lines if '-->' in l), None)
        if not time_line:
            continue
        s_str, e_str = time_line.split('-->')
        text = ' '.join(l for l in lines if '-->' not in l and not l.strip().isdigit()).strip()
        if text:
            entries.append({
                'start': srt_time_to_sec(s_str),
                'end':   srt_time_to_sec(e_str),
                'text':  text
            })
    return entries

# ── 视频信息 ──────────────────────────────────────────────────────
def get_video_info(video_path):
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', str(video_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    import json as _json
    d = _json.loads(r.stdout)
    for s in d.get('streams', []):
        if s.get('codec_type') == 'video':
            return s.get('width', 1080), s.get('height', 1920)
    return 1080, 1920

def get_video_duration(video_path):
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', str(video_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    import json as _json
    d = _json.loads(r.stdout)
    return float(d.get('format', {}).get('duration', 60))

# ── ASS 生成 ──────────────────────────────────────────────────────
def srt_to_ass_time(t):
    """HH:MM:SS,mmm → H:MM:SS.cc"""
    t = t.strip()
    parts = t.replace(',', '.').split(':')
    h, m = parts[0], parts[1]
    s_ms = parts[2]       # SS.mmm
    return f"{int(h)}:{m}:{s_ms[:-1]}"   # 去掉最后一位毫秒

def sec_to_ass_time(s):
    h = int(s) // 3600
    m = (int(s) % 3600) // 60
    sec = s % 60
    return f"{h}:{m:02d}:{int(sec):02d}.{int((sec%1)*100):02d}"

def split_title_two_lines(title, max_per_line=9):
    """超过 max_per_line 字就折两行"""
    if len(title) <= max_per_line:
        return title
    mid = len(title) // 2
    return title[:mid] + r'\N' + title[mid:]

def build_ass(entries, title, width, height, font_name):
    font_size_sub   = max(50, height // 28)
    font_size_title = max(80, height // 18)
    margin_bottom   = height // 12

    ass_header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding\n"
        # 字幕：白字黑边，底部居中
        f"Style: Sub,{font_name},{font_size_sub},&H00FFFFFF,&H000000FF,&H00000000,&H90000000,"
        f"1,0,0,0,100,100,0,0,1,4,1,2,30,30,{margin_bottom},1\n"
        # 标题：金黄大字，顶部居中，全程显示
        f"Style: Title,{font_name},{font_size_title},&H0000FFFF,&H000000FF,&H00000000,&HC0000000,"
        f"1,0,0,0,100,100,2,0,1,6,2,8,40,40,{height//10},1\n\n"
        "[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )

    events = []

    # 标题：全程显示
    duration = entries[-1]['end'] if entries else 60
    title_end = sec_to_ass_time(duration + 1)
    title_display = split_title_two_lines(title)
    events.append(f"Dialogue: 0,0:00:00.00,{title_end},Title,,0,0,0,,{title_display}")

    # 字幕：逐条
    for e in entries:
        t_start = sec_to_ass_time(e['start'])
        t_end   = sec_to_ass_time(e['end'])
        events.append(f"Dialogue: 0,{t_start},{t_end},Sub,,0,0,0,,{e['text']}")

    return ass_header + '\n'.join(events)

# ── 单个视频处理 ──────────────────────────────────────────────────
def process_clip(video_path, srt_path, title, output_path, font_path, ffmpeg, tmp_dir):
    entries = parse_srt(srt_path)
    if not entries:
        print(f"  ✗ SRT 为空")
        return False

    width, height = get_video_info(video_path)
    font_name = "PingFang SC" if font_path and "PingFang" in font_path else (
                "STHeiti Light" if font_path and "STHeiti" in font_path else
                "WenQuanYi Micro Hei")

    # 生成 ASS
    ass_content = build_ass(entries, title, width, height, font_name)
    import os
    ass_path = Path(f"/tmp/lc_subs_{os.getpid()}.ass")
    ass_path.write_text(ass_content, encoding='utf-8')

    # 烧入
    cmd = [
        ffmpeg, '-y',
        '-i', str(video_path),
        '-vf', f"ass=filename={str(ass_path).replace(':', '\\:')}",
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
        '-c:a', 'aac',
        str(output_path)
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    ass_path.unlink(missing_ok=True)

    if r.returncode != 0:
        print(f"  ✗ 烧入失败: {r.stderr[-400:]}")
        return False

    return True

# ── 主函数 ────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--clips',  default='clips',     help='切片目录（含 subtitles/ 子目录）')
    p.add_argument('--out',    default='published',  help='输出目录')
    p.add_argument('--ffmpeg', default=None,         help='指定 ffmpeg 路径（可选）')
    args = p.parse_args()

    clips_dir = Path(args.clips)
    srt_dir   = clips_dir / 'subtitles'
    out_dir   = Path(args.out)

    # 找 ffmpeg
    ffmpeg = args.ffmpeg or find_ffmpeg()
    if not ffmpeg:
        print("❌ 找不到含 libass 的 ffmpeg！")
        print("   请先运行：python setup_ffmpeg.py")
        sys.exit(1)
    print(f"ffmpeg: {ffmpeg}")

    # 找字体
    font_path = find_font()
    if font_path:
        print(f"字体: {font_path}")
    else:
        print("⚠️  未找到中文字体，字幕可能显示方块")

    videos = sorted(clips_dir.glob("*.mp4"))
    print(f"视频: {len(videos)} 个\n")

    out_dir.mkdir(parents=True, exist_ok=True)

    ok_count = 0
    with tempfile.TemporaryDirectory() as tmp_dir:
        for i, video_path in enumerate(videos, 1):
            srt_path = srt_dir / (video_path.stem + '.srt')
            if not srt_path.exists():
                print(f"[{i:02d}] ✗ 找不到 SRT: {video_path.name}")
                continue

            title = re.sub(r'^\d+_', '', video_path.stem)
            output_path = out_dir / video_path.name

            print(f"[{i:02d}/{len(videos)}] {title}")
            ok = process_clip(video_path, srt_path, title, output_path, font_path, ffmpeg, tmp_dir)

            if ok and output_path.exists():
                mb = output_path.stat().st_size / 1024 / 1024
                print(f"  ✓ {output_path.name} ({mb:.0f}MB)")
                ok_count += 1
            else:
                print(f"  ✗ 失败")

    print(f"\n=== 完成 {ok_count}/{len(videos)} ===")
    print(f"输出: {out_dir}")

    # 自动弹出文件夹（macOS）
    import platform
    if platform.system() == 'Darwin':
        subprocess.run(['open', str(out_dir)])

if __name__ == '__main__':
    main()
