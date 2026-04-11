# lecture-clipper

把一段直播讲座视频，自动按话题切成多段短片，每段自动加字幕烧入。

**适合人群**：录完直播想二次传播的老师、讲师、博主。  
**输入**：一个 .mp4 视频  
**输出**：多个话题切片 .mp4，每段带字幕

---

## 给 AI 助手（小龙虾 / OpenClaw）的使用说明

### 第一步：安装（只需做一次）

```bash
git clone https://github.com/Jane-xiaoer/lecture-clipper.git
cd lecture-clipper
bash install.sh
```

### 第二步：运行

**方式 A：用户提供 API Key（推荐，效果最好）**

```bash
python3 run.py \
  --video /path/to/视频.mp4 \
  --api-key 用户的KEY \
  --api-provider gemini
```

支持的 `--api-provider`：
- `gemini`（Google，免费额度大，**推荐**）
- `openai`（GPT-4o）
- `anthropic`（Claude）
- `openrouter`（多模型聚合）

**方式 B：用小龙虾自带模型做话题拆解**

```bash
python3 run.py \
  --video /path/to/视频.mp4 \
  --api-base http://localhost:11434/v1 \
  --api-key ollama \
  --api-provider openai
```

把 `--api-base` 替换成小龙虾的本地模型地址即可。

---

### 交互流程（AI 助手需要理解这个）

脚本运行过程中会输出话题列表，格式如下：

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

**AI 助手处理逻辑：**
1. 把话题列表展示给用户看
2. 询问用户是否满意
3. 满意 → 向脚本输入回车（空行）
4. 不满意 → 把用户的修改意见原文输入给脚本
5. 循环直到用户满意，然后脚本自动切片完成

---

### 输出位置

默认输出到 `./lecture_output/published/`，每个话题一个 .mp4。

可以用 `--out` 指定：
```bash
python3 run.py --video 视频.mp4 --api-key KEY --api-provider gemini --out ~/Desktop/切片结果
```

---

### 常见问题

**Q：字幕烧不进去，报错 "No such filter: ass"**  
A：运行 `python3 setup_ffmpeg.py` 自动下载带 libass 的 ffmpeg。

**Q：转写很慢**  
A：申请免费 Groq Key（https://console.groq.com），然后：  
`python3 run.py --video 视频.mp4 --api-key GROQ_KEY --api-provider groq`

**Q：话题切得不准**  
A：在确认环节用中文说出调整意见，脚本会重新分析。

---

### 完整参数列表

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--video` | 输入视频路径（必填）| — |
| `--api-key` | LLM API Key | 读环境变量 |
| `--api-provider` | gemini/openai/anthropic/openrouter | gemini |
| `--api-base` | 自定义 API 地址（小龙虾/本地模型）| — |
| `--srt` | 已有字幕文件（可选）| 自动转写 |
| `--out` | 输出目录 | ./lecture_output |
| `--model` | 指定模型名称 | 自动选最优 |
| `--whisper` | 转写服务：auto/groq/openai/local | auto |
| `--skip-step0` | 跳过转写（需提供 --srt）| — |
| `--skip-step1` | 跳过话题标注 | — |
| `--skip-step2` | 跳过切片 | — |
| `--dry-run` | 只预览切片计划不执行 | — |
