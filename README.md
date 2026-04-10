# lecture-clipper

直播讲座自动切片工具 — 模型无关，任何 agent / 任何电脑都能跑

## 第一次使用（新电脑必做）

```bash
# 1. 安装唯一的 Python 依赖
pip install openai

# 2. 安装带字幕功能的 ffmpeg（自动检测系统，下载合适版本）
python setup_ffmpeg.py

# 3. 设置 LLM API Key（至少一个）
export GEMINI_API_KEY=你的key       # 推荐，免费额度多
export ANTHROPIC_API_KEY=你的key    # 或者用 Claude
export OPENAI_API_KEY=你的key       # 或者用 GPT-4o
export OPENROUTER_API_KEY=你的key   # 或者用 OpenRouter
```

> **为什么要 setup_ffmpeg.py？**
> 剪辑和字幕烧入用的是 ffmpeg，但系统默认安装的 ffmpeg
> 通常缺少字幕渲染功能（libass）。setup_ffmpeg.py 会自动
> 下载一个功能完整的版本，放在 ~/.lecture-clipper/ffmpeg。
> 只需运行一次，之后自动使用。

---

## 使用方法

```bash
# 完整流程（自动选最佳模型）
python run.py --video input.mp4 --srt input.srt

# 指定输出目录
python run.py --video input.mp4 --srt input.srt --out ./my_output

# 指定使用哪个模型
python run.py --video input.mp4 --srt input.srt --model gemini
python run.py --video input.mp4 --srt input.srt --model gpt4o
python run.py --video input.mp4 --srt input.srt --model claude

# 已有话题标注文件，跳过第1步
python run.py --video input.mp4 --srt input.srt --skip-step1

# 单独运行某一步
python step1_tagger.py --srt input.srt --out metadata/
python step2_cutter.py --video input.mp4 --srt input.srt --meta metadata/ --out clips/
python step3_postprocess.py --clips clips/ --out published/
```

---

## 三个步骤说明

| 步骤 | 脚本 | 需要 LLM？ | 说明 |
|------|------|-----------|------|
| Step 1 | step1_tagger.py | ✅ 是 | 读全文字幕，语义分组话题 |
| Step 2 | step2_cutter.py | ❌ 否 | FFmpeg 按话题切片 |
| Step 3 | step3_postprocess.py | ❌ 否 | 烧入标题+字幕，视频内容不动 |

Step 1 运行后会暂停，让你检查 `metadata/tagger_review.md`，
确认话题分组正确后按 Enter 继续。可以直接编辑 `metadata/tagger_result.json` 修改。

---

## 支持的模型（Step 1 用）

| 推荐度 | 模型 | API 变量 | 说明 |
|--------|------|----------|------|
| ⭐⭐⭐ | Gemini 2.0 Flash | `GEMINI_API_KEY` | 百万 token 上下文，快，便宜 |
| ⭐⭐⭐ | Claude Sonnet/Opus | `ANTHROPIC_API_KEY` | 中文语义最强 |
| ⭐⭐⭐ | Claude (OpenRouter) | `OPENROUTER_API_KEY` | 同上，走中转 |
| ⭐⭐ | GPT-4o | `OPENAI_API_KEY` | 128k 上下文够用 |

模型自动按优先级选择，有哪个 key 用哪个。

---

## 输出结构

```
输出目录/
  metadata/
    tagger_result.json    # 话题标注（可人工编辑）
    tagger_review.md      # 人工审核报告
  clips/
    01_话题名.mp4          # 原始切片（无字幕）
    subtitles/
      01_话题名.srt        # 对应字幕
  published/
    01_话题名.mp4          # 最终成片（已烧入标题+字幕）
```

---

## 常见问题

**Q: setup_ffmpeg.py 下载失败？**
macOS: `brew tap homebrew-ffmpeg/ffmpeg && brew install homebrew-ffmpeg/ffmpeg/ffmpeg --with-libass`
Linux: `sudo apt install ffmpeg` (Ubuntu/Debian 的 apt 版通常含 libass)

**Q: 字幕显示方块？**
缺少中文字体。Linux 用户：`sudo apt install fonts-wqy-microhei`

**Q: Step 1 标注结果不对？**
直接编辑 `metadata/tagger_result.json`，然后用 `--skip-step1` 重跑。
