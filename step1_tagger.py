#!/usr/bin/env python3
"""
Step 1: 话题标注
LLM 读完整字幕，语义分组，输出 tagger_result.json

用法：
  python step1_tagger.py --srt input.srt --out metadata/
  python step1_tagger.py --srt input.srt --out metadata/ --model gemini
"""
import argparse, json, re, sys
from pathlib import Path

def parse_srt(srt_path):
    content = Path(srt_path).read_text(encoding='utf-8')
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

def build_numbered_transcript(entries):
    lines = []
    for i, e in enumerate(entries):
        mins = int(e['start']) // 60
        secs = int(e['start']) % 60
        lines.append(f"[{i:04d}|{mins:02d}:{secs:02d}] {e['text']}")
    return '\n'.join(lines)

TAGGER_PROMPT = """你是一个讲座内容分析专家。以下是一段中文直播讲座的完整字幕，格式为：
[行号|时间] 内容

请分析并输出所有话题的分组。要求：
1. 语义归类，不是关键词匹配（例：'砖头壳子'、'楼市'、'买地' = 房地产话题）
2. 广告、招生、闲聊、过渡语 → 标记为 skip
3. 同一话题可能在多处出现（碎片化），每处单独列出 range
4. range 格式为行号区间 [起始行号, 结束行号]（含两端）

输出严格 JSON，格式如下：
{
  "topics": [
    {
      "id": "topic_1",
      "name": "话题名称（简洁，10字以内）",
      "ranges": [[起始行号, 结束行号], ...],
      "total_lines": 估算行数
    },
    {
      "id": "skip",
      "name": "广告/招生/闲聊",
      "ranges": [[...], ...],
      "total_lines": 估算行数
    }
  ]
}

只输出 JSON，不要任何解释文字。

字幕内容：
{transcript}
"""

def run(srt_path, out_dir, model_name=None):
    from model_router import pick_model, call_llm

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("解析字幕...")
    entries = parse_srt(srt_path)
    print(f"共 {len(entries)} 行字幕")

    transcript = build_numbered_transcript(entries)
    # 保存供检查
    (out_dir / 'transcript_numbered.txt').write_text(transcript, encoding='utf-8')

    print(f"\n选择模型...")
    model = pick_model(task="tagging", force_model=model_name)
    print(f"使用：{model.name} (context: {model.context_k}k)")

    prompt = TAGGER_PROMPT.replace("{transcript}", transcript)
    token_estimate = len(transcript) // 2  # 粗估
    print(f"预计输入约 {token_estimate:,} tokens，开始标注...")

    raw = call_llm(prompt, model)

    # 提取 JSON
    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not json_match:
        print("❌ 模型输出不是有效 JSON，原始输出已保存")
        (out_dir / 'tagger_raw.txt').write_text(raw, encoding='utf-8')
        sys.exit(1)

    result = json.loads(json_match.group())
    (out_dir / 'tagger_result.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8'
    )

    # 生成人工审核报告
    report = ["# 话题标注结果（请人工审核）\n"]
    for t in result['topics']:
        if t['id'] == 'skip':
            continue
        dur = sum(
            entries[min(r[1], len(entries)-1)]['end'] - entries[max(0, r[0])]['start']
            for r in t['ranges']
        )
        report.append(f"## {t['name']} ({dur/60:.1f}min)")
        for r in t['ranges']:
            s = entries[max(0,r[0])]['start']
            e = entries[min(r[1],len(entries)-1)]['end']
            preview = entries[max(0,r[0])]['text'][:30]
            report.append(f"- 行 {r[0]}-{r[1]} ({s/60:.1f}-{e/60:.1f}min): {preview}...")
        report.append("")

    (out_dir / 'tagger_review.md').write_text('\n'.join(report), encoding='utf-8')

    topics = [t for t in result['topics'] if t['id'] != 'skip']
    print(f"\n✅ 标注完成：{len(topics)} 个话题（不含 skip）")
    print(f"   输出：{out_dir}/tagger_result.json")
    print(f"   审核：{out_dir}/tagger_review.md")
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--srt', required=True)
    parser.add_argument('--out', default='metadata')
    parser.add_argument('--model', default=None, help='指定模型关键词，如 gemini / gpt4o / claude')
    args = parser.parse_args()
    run(args.srt, args.out, args.model)
