#!/usr/bin/env python3
"""
lecture-clipper — 直播讲座自动切片全流程入口

用法：
  python run.py --video input.mp4 --srt input.srt
  python run.py --video input.mp4 --srt input.srt --model gemini --out ./output
  python run.py --video input.mp4 --srt input.srt --skip-step1  # 已有 tagger_result.json

步骤：
  Step 1: LLM 话题标注（需要 LLM API）
    → 生成 metadata/tagger_result.json（可人工编辑）
  Step 2: FFmpeg 视频切片（无需 LLM）
    → 生成 clips/*.mp4 + clips/subtitles/*.srt
  Step 3: FFmpeg 字幕烧入 + 口误清洗（无需 LLM）
    → 生成 published/*.mp4（最终成片）
"""
import argparse, os, subprocess, sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent

def banner(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print('='*60)

def show_topics(meta_dir):
    """在终端直接显示话题分组（时间段格式，小白可读）"""
    import json, re as _re
    meta_dir = Path(meta_dir)
    result_file = meta_dir / 'tagger_result.json'
    if not result_file.exists():
        return
    result = json.loads(result_file.read_text(encoding='utf-8'))
    topics = [t for t in result['topics'] if t.get('id') != 'skip']

    # 尝试读 transcript_numbered.txt 来还原时间（格式 [0000|MM:SS]）
    time_map = {}
    txt = meta_dir / 'transcript_numbered.txt'
    if txt.exists():
        for line in txt.read_text(encoding='utf-8').splitlines():
            m = _re.match(r'\[(\d+)\|(\d+:\d+)\]', line)
            if m:
                time_map[int(m.group(1))] = m.group(2)

    def idx2time(idx):
        return time_map.get(idx, f"#{idx}")

    print(f"\n{'─'*52}")
    print(f"  📋 AI 识别了 {len(topics)} 个话题：")
    print(f"{'─'*52}")
    for i, t in enumerate(topics, 1):
        ranges = t.get('ranges', [])
        time_parts = [f"{idx2time(r[0])}～{idx2time(r[1])}" for r in ranges]
        time_str = "  |  ".join(time_parts)
        print(f"  {i}. {t['name']}")
        if time_str:
            print(f"     时间：{time_str}")
    print(f"{'─'*52}")

def run_step(script, args_list):
    cmd = [sys.executable, str(SKILL_DIR / script)] + args_list
    print(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print(f"❌ {script} 失败 (exit {r.returncode})")
        sys.exit(r.returncode)

def main():
    p = argparse.ArgumentParser(description='讲座自动切片工具')
    p.add_argument('--video',       required=True, help='输入视频 (.mp4)')
    p.add_argument('--srt',         required=True, help='输入字幕 (.srt)')
    p.add_argument('--out',          default='./lecture_output', help='输出根目录')
    p.add_argument('--model',        default=None,  help='指定 LLM 模型（gemini/gpt4o/claude）')
    p.add_argument('--srt',          default=None,  help='已有字幕文件（可选，没有则自动转写）')
    p.add_argument('--whisper',      default='auto', help='转写服务：auto | groq | openai | local')
    p.add_argument('--skip-step0',   action='store_true', help='跳过转写，--srt 必须提供')
    p.add_argument('--skip-step1',   action='store_true', help='跳过标注，直接用已有 tagger_result.json')
    p.add_argument('--skip-step2',   action='store_true', help='跳过切片，直接用已有 clips/')
    p.add_argument('--dry-run',      action='store_true', help='Step2 只预览不执行')
    args = p.parse_args()

    out_dir   = Path(args.out)
    meta_dir  = out_dir / 'metadata'
    clips_dir = out_dir / 'clips'
    pub_dir   = out_dir / 'published'

    out_dir.mkdir(parents=True, exist_ok=True)

    # SRT 路径：用户提供 or 自动生成
    srt_path = args.srt or str(out_dir / 'input.srt')

    print(f"""
lecture-clipper 启动
  视频: {args.video}
  输出: {out_dir}
  模型: {args.model or '自动选择'}
""")

    # ── Step 0: 视频转文字 ────────────────────────────────────
    if not args.skip_step0 and not args.srt:
        banner("Step 0 / 3 — 视频转文字（Whisper）")
        run_step('step0_transcribe.py', [
            '--video', args.video,
            '--out',   srt_path,
            '--provider', args.whisper,
        ])
    elif args.srt:
        print(f"✓ 使用已有字幕: {args.srt}")
    else:
        if not Path(srt_path).exists():
            print(f"❌ --skip-step0 但找不到字幕: {srt_path}")
            sys.exit(1)

    # ── Step 1: 话题标注 ──────────────────────────────────────
    if not args.skip_step1:
        banner("Step 1 / 3 — 话题标注（LLM）")
        step1_args = ['--srt', srt_path, '--out', str(meta_dir)]
        if args.model:
            step1_args += ['--model', args.model]
        run_step('step1_tagger.py', step1_args)

        # 自然语言确认循环（小白友好）
        while True:
            show_topics(meta_dir)
            print()
            print("  ✅ 分组没问题？直接按 Enter 开始切片")
            print("  ✏️  有问题？用中文说出来（例：把第2和第3个话题合并 / 去掉广告部分）")
            feedback = input("  → ").strip()
            if not feedback:
                break
            print(f"\n  收到，正在根据你的意见重新分析...")
            step1_args_retry = ['--srt', srt_path, '--out', str(meta_dir),
                                '--feedback', feedback]
            if args.model:
                step1_args_retry += ['--model', args.model]
            run_step('step1_tagger.py', step1_args_retry)
    else:
        tagger_json = meta_dir / 'tagger_result.json'
        if not tagger_json.exists():
            print(f"❌ --skip-step1 但找不到 {tagger_json}")
            sys.exit(1)
        print(f"✓ 跳过 Step 1，使用已有: {tagger_json}")

    # ── Step 2: 视频切片 ──────────────────────────────────────
    if not args.skip_step2:
        banner("Step 2 / 3 — 视频切片（FFmpeg）")
        step2_args = [
            '--video', args.video,
            '--srt',   args.srt,
            '--meta',  str(meta_dir),
            '--out',   str(clips_dir),
        ]
        if args.dry_run:
            step2_args.append('--dry-run')
        run_step('step2_cutter.py', step2_args)

        if args.dry_run:
            print("dry-run 完成，退出")
            return
    else:
        print(f"✓ 跳过 Step 2，使用已有: {clips_dir}")

    # ── Step 3: 字幕烧入 ──────────────────────────────────────
    banner("Step 3 / 3 — 字幕烧入 + 口误清洗（FFmpeg）")
    step3_args = [
        '--clips',  str(clips_dir),
        '--out',    str(pub_dir),
    ]
    run_step('step3_postprocess.py', step3_args)

    banner("✅ 全部完成！")
    print(f"  最终成片: {pub_dir}/")

    # 尝试用系统命令打开目录
    try:
        import platform
        if platform.system() == 'Darwin':
            subprocess.run(['open', str(pub_dir)])
        elif platform.system() == 'Linux':
            subprocess.run(['xdg-open', str(pub_dir)])
    except Exception:
        pass

if __name__ == '__main__':
    main()
