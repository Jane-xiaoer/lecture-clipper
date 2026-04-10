#!/usr/bin/env python3
"""
Step 2: 视频切片器 - 整合 tagger_result + split_result，输出所有话题视频

用法：
  python step2_cutter.py --video input.mp4 --srt input.srt --meta metadata/ --out clips/
  python step2_cutter.py --video input.mp4 --srt input.srt --meta metadata/ --out clips/ --dry-run
"""
import argparse, json, re, subprocess, sys, tempfile
from pathlib import Path

def get_args():
    p = argparse.ArgumentParser()
    p.add_argument('--video', required=True, help='输入视频路径')
    p.add_argument('--srt',   required=True, help='输入字幕路径')
    p.add_argument('--meta',  default='metadata', help='metadata 目录（含 tagger_result.json）')
    p.add_argument('--out',   default='clips', help='输出目录')
    p.add_argument('--dry-run', action='store_true')
    return p.parse_args()

_args = get_args() if __name__ == '__main__' else None

def _get_paths():
    if _args:
        return _args.video, _args.srt, Path(_args.meta), Path(_args.out)
    # 兼容直接 import 使用
    raise RuntimeError("请通过命令行参数指定路径")

# 运行时动态解析路径
import sys as _sys
if __name__ == '__main__':
    _a = get_args()
    SRT_PATH     = _a.srt
    VIDEO_PATH   = _a.video
    OUTPUT_DIR   = Path(_a.out)
    METADATA_DIR = Path(_a.meta)
else:
    SRT_PATH = VIDEO_PATH = None
    OUTPUT_DIR = METADATA_DIR = None

FILLER_RE = re.compile(
    r'^(所以说?我?跟你这么说|那么|好吧|好的|嗯|对吗|对的?|啊|然后|就是说?'
    r'|你知道吗?|继续|接着|下面|接下来说?|我跟你说|我告诉你|我跟你这么说'
    r'|他是我跟你这么说|所以我跟你这么说啊?|我给你说|想问您|是不是|对不对'
    r'|知道吗?|能明白吗?|古之所贵|你懂吗?|可以吗?|好吗?|哈哈+)[啊哦~！,，。？?]*$'
)

def parse_srt(srt_path):
    with open(srt_path, encoding='utf-8') as f:
        content = f.read()
    entries = []
    for block in re.split(r'\n\n+', content.strip()):
        lines = block.strip().split('\n')
        time_line = next((l for l in lines if '-->' in l), None)
        if not time_line:
            continue
        s, e = time_line.split('-->')
        def ts2sec(ts):
            ts = ts.strip().replace(',', '.')
            h, m, sec = ts.split(':')
            return int(h)*3600 + int(m)*60 + float(sec)
        text = ' '.join(l for l in lines if '-->' not in l and not l.strip().isdigit()).strip()
        if text:
            entries.append({'start': ts2sec(s), 'end': ts2sec(e), 'text': text})
    return entries

def sec_fmt(s):
    s = int(s)
    return f"{s//3600}:{(s%3600)//60:02d}:{s%60:02d}"

def srt_time(s):
    h = int(s) // 3600
    m = (int(s) % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{int(sec):02d},{int((sec%1)*1000):03d}"

def is_filler(text):
    t = text.strip()
    return len(t) <= 2 or bool(FILLER_RE.match(t))

def trim_range(entries, s_idx, e_idx, max_trim=6):
    for i in range(s_idx, min(s_idx + max_trim, e_idx)):
        if not is_filler(entries[i]['text']):
            s_idx = i
            break
    for i in range(e_idx, max(e_idx - max_trim, s_idx), -1):
        if not is_filler(entries[i]['text']):
            e_idx = i
            break
    return s_idx, e_idx

def ranges_to_segments(ranges, entries):
    """把 [[s,e],[s,e]...] 转为可用的片段列表，跳过过短片段"""
    segments = []
    for r in ranges:
        s_idx = max(0, r[0])
        e_idx = min(r[1], len(entries)-1)
        if e_idx <= s_idx:
            continue
        s_idx, e_idx = trim_range(entries, s_idx, e_idx)
        dur = entries[e_idx]['end'] - entries[s_idx]['start']
        if dur < 15:
            continue
        segments.append({
            'start_sec': entries[s_idx]['start'],
            'end_sec':   entries[e_idx]['end'],
            'dur':       dur,
            'lines':     entries[s_idx:e_idx+1]
        })
    return segments

def build_clip_list(tag_result, split_result, entries):
    """把所有话题整合成最终切片列表"""
    clips = []

    for topic in tag_result['topics']:
        tid = topic['id']
        if tid == 'skip':
            continue

        total_sec = sum(
            entries[min(r[1], len(entries)-1)]['end'] - entries[max(0, r[0])]['start']
            for r in topic['ranges']
        )

        if tid in split_result:
            # 用分割方案出子话题
            for sub in split_result[tid]:
                segs = ranges_to_segments(sub['ranges'], entries)
                if not segs:
                    continue
                dur = sum(s['dur'] for s in segs)
                if dur < 30:
                    continue
                clips.append({
                    'title':    sub['sub_title'],
                    'segments': segs,
                    'total_min': dur / 60,
                    'seg_count': len(segs)
                })
        else:
            # 直接出整个话题
            segs = ranges_to_segments(topic['ranges'], entries)
            if not segs:
                continue
            dur = sum(s['dur'] for s in segs)
            if dur < 30:
                continue
            clips.append({
                'title':    topic['name'],
                'segments': segs,
                'total_min': dur / 60,
                'seg_count': len(segs)
            })

    # 按时间排序（第一个片段的起始时间）
    clips.sort(key=lambda c: c['segments'][0]['start_sec'])
    return clips

def generate_srt(segments, out_path):
    srt_entries = []
    timeline_offset = 0.0
    idx = 1
    for seg in segments:
        seg_start = seg['start_sec']
        for line in seg['lines']:
            rel_start = line['start'] - seg_start + timeline_offset
            rel_end   = line['end']   - seg_start + timeline_offset
            srt_entries.append(f"{idx}\n{srt_time(rel_start)} --> {srt_time(rel_end)}\n{line['text']}\n")
            idx += 1
        timeline_offset += seg['end_sec'] - seg['start_sec']
    out_path.write_text('\n'.join(srt_entries), encoding='utf-8')

def concat_ffmpeg(segments, out_path, tmp_dir):
    if len(segments) == 1:
        seg = segments[0]
        cmd = ['ffmpeg', '-y', '-ss', str(seg['start_sec']), '-to', str(seg['end_sec']),
               '-i', VIDEO_PATH, '-c', 'copy', str(out_path)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode == 0

    tmp_clips = []
    for i, seg in enumerate(segments):
        tmp_clip = Path(tmp_dir) / f"seg_{i:03d}.mp4"
        cmd = ['ffmpeg', '-y', '-ss', str(seg['start_sec']), '-to', str(seg['end_sec']),
               '-i', VIDEO_PATH,
               '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
               '-c:a', 'aac', '-ar', '44100', str(tmp_clip)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return False
        tmp_clips.append(tmp_clip)

    concat_list = Path(tmp_dir) / 'concat.txt'
    concat_list.write_text('\n'.join(f"file '{str(c)}'" for c in tmp_clips), encoding='utf-8')
    cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
           '-i', str(concat_list), '-c', 'copy', str(out_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0

def main():
    print("=== 讲座切片器 Final（话题拼接 + 分割方案整合）===\n")

    entries = parse_srt(SRT_PATH)
    print(f"字幕：{len(entries)} 行")

    tag_result  = json.loads((METADATA_DIR / 'tagger_result.json').read_text(encoding='utf-8'))
    split_result = json.loads((METADATA_DIR / 'split_result.json').read_text(encoding='utf-8'))

    clips = build_clip_list(tag_result, split_result, entries)
    print(f"共 {len(clips)} 个切片\n")

    print("="*60)
    for i, c in enumerate(clips, 1):
        segs_note = f"（{c['seg_count']}段拼接）" if c['seg_count'] > 1 else ""
        print(f"[{i:02d}] {c['title']} — {c['total_min']:.1f}min {segs_note}")
        for j, seg in enumerate(c['segments']):
            print(f"     片段{j+1}: {sec_fmt(seg['start_sec'])} → {sec_fmt(seg['end_sec'])} ({seg['dur']/60:.1f}min)")

    if '--dry-run' in sys.argv:
        print("\n--dry-run 模式，不执行剪辑")
        return

    print(f"\n开始剪辑 {len(clips)} 个...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    srt_dir = OUTPUT_DIR / 'subtitles'
    srt_dir.mkdir(exist_ok=True)

    ok_count = 0
    with tempfile.TemporaryDirectory() as tmp_dir:
        for i, c in enumerate(clips, 1):
            title_safe = re.sub(r'[^\w\u4e00-\u9fff·]', '', c['title'])[:32]
            out_path = OUTPUT_DIR / f"{i:02d}_{title_safe}.mp4"
            srt_path = srt_dir / f"{i:02d}_{title_safe}.srt"

            segs_note = f"，{c['seg_count']}段拼接" if c['seg_count'] > 1 else ""
            print(f"\n[{i:02d}/{len(clips)}] {c['title']} ({c['total_min']:.1f}min{segs_note})...")

            generate_srt(c['segments'], srt_path)
            ok = concat_ffmpeg(c['segments'], out_path, tmp_dir)

            if ok and out_path.exists():
                mb = out_path.stat().st_size / 1024 / 1024
                print(f"  ✓ {out_path.name} ({mb:.0f}MB)")
                ok_count += 1
            else:
                print(f"  ✗ 失败")

    print(f"\n=== 完成 {ok_count}/{len(clips)} 个 ===")
    print(f"视频：{OUTPUT_DIR}")
    print(f"字幕：{srt_dir}")

if __name__ == '__main__':
    main()
