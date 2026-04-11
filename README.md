# lecture-clipper

把一段直播讲座视频，自动按话题切成多段短片，每段自动加字幕烧入。

**输入**：一个 .mp4 视频  
**输出**：多个话题切片 .mp4，每段带烧入字幕

---

## 给 AI Agent 的使用说明

适用于任何可以执行本地命令的 AI Agent，包括：
- **Claude Code** / **Codex** / **Hermes**
- **OpenClaw** / **Antigravity** / 其他 Claw 系列
- 任何支持 bash 执行的 Agent

### 第一步：安装（只需做一次）

```bash
git clone https://github.com/Jane-xiaoer/lecture-clipper.git
cd lecture-clipper
bash install.sh
```

### 第二步：运行

**方式 A：用户提供 API Key（效果最好）**

```bash
python3 run.py \
  --video /path/to/视频.mp4 \
  --api-key 用户的KEY \
  --api-provider gemini
```

`--api-provider` 可选值：
- `gemini` — Google Gemini，免费额度大，**首选**
- `openai` — GPT-4o
- `anthropic` — Claude
- `openrouter` — 多模型聚合

**方式 B：用 Agent 自带模型（无需用户提供 Key）**

```bash
python3 run.py \
  --video /path/to/视频.mp4 \
  --api-base http://localhost:11434/v1 \
  --api-key any \
  --api-provider openai
```

把 `--api-base` 替换成 Agent 自身的 OpenAI 兼容接口地址即可。  
Hermes / Antigravity / Claw 系列通常都暴露 OpenAI 兼容端点。

---

### 交互流程（Agent 必须理解这一节）

脚本分析完话题后，会在终端输出如下内容：

```
────────────────────────────────────────────────────
  📋 AI 识别了 4 个话题：
────────────────────────────────────────────────────
  1. 房地产市场分析
     时间：3:12～15:40  |  42:00～51:20
  2. 创业心态与执行力
     时间：20:00～31:20
  3. 投资避坑指南
     时间：55:10～1:08:30
  4. Q&A 问答
     时间：1:10:00～1:25:00
────────────────────────────────────────────────────

  ✅ 分组没问题？直接按 Enter 开始切片
  ✏️  有问题？用中文说出来（例：把第2和第3个话题合并 / 去掉广告部分）
  → 
```

**Agent 的处理逻辑：**

1. 读取脚本输出的话题列表，转述给用户（用自然语言，不用复制原文）
2. 问用户："这个分组对吗？有需要调整的吗？"
3. 用户说没问题 → 向脚本输入**空行（回车）**
4. 用户说有问题 → 把用户的原话直接输入给脚本
5. 脚本重新分析，再次输出话题列表，循环步骤 1-4
6. 用户最终确认后，脚本自动完成切片，输出成片路径

---

### 输出位置

默认输出到 `./lecture_output/published/`，每个话题一个 .mp4。

用 `--out` 自定义输出目录：
```bash
python3 run.py --video 视频.mp4 --api-key KEY --api-provider gemini --out ~/Desktop/切片结果
```

---

### 常见问题

**Q：报错 "No such filter: ass"（字幕烧不进去）**  
A：系统 ffmpeg 缺少 libass，运行以下命令自动修复：
```bash
python3 setup_ffmpeg.py
```

**Q：转写很慢**  
A：申请免费 Groq Key（https://console.groq.com），然后：
```bash
python3 run.py --video 视频.mp4 --api-key GROQ_KEY --api-provider groq
```

**Q：没有任何 API Key**  
A：转写会用本地 Whisper（慢），话题分析需要至少一个 LLM Key。  
推荐申请 Gemini 免费 Key：https://aistudio.google.com/apikey

---

### 完整参数表

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--video` | 输入视频路径（必填）| — |
| `--api-key` | LLM API Key | 读环境变量 |
| `--api-provider` | gemini / openai / anthropic / openrouter | gemini |
| `--api-base` | 自定义 OpenAI 兼容地址（Agent 自带模型）| — |
| `--srt` | 已有字幕文件（可选，没有则自动转写）| — |
| `--out` | 输出目录 | ./lecture_output |
| `--model` | 指定模型名称 | 自动选最优 |
| `--whisper` | 转写服务：auto / groq / openai / local | auto |
| `--skip-step0` | 跳过转写，需配合 `--srt` 使用 | — |
| `--skip-step1` | 跳过话题标注，用已有分析结果 | — |
| `--skip-step2` | 跳过切片 | — |
| `--dry-run` | 只预览切片计划，不实际执行 | — |
