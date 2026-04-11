#!/bin/bash
# lecture-clipper 一键安装脚本
# 用法：bash install.sh
set -e

echo ""
echo "=== lecture-clipper 安装中 ==="
echo ""

# 1. 安装 Python 依赖
echo "▶ 安装 Python 依赖..."
pip3 install openai --quiet

# 2. 检查 ffmpeg
echo "▶ 检查 ffmpeg..."
if command -v ffmpeg &>/dev/null; then
    FFMPEG_VER=$(ffmpeg -version 2>&1 | head -1)
    echo "  ✓ 已安装：$FFMPEG_VER"
else
    echo "  未找到 ffmpeg，尝试自动安装..."
    python3 "$(dirname "$0")/setup_ffmpeg.py"
fi

# 3. 完成
echo ""
echo "✅ 安装完成！"
echo ""
echo "使用方法："
echo "  python3 $(dirname "$0")/run.py --video 你的视频.mp4 --api-key 你的KEY --api-provider gemini"
echo ""
echo "支持的 API 提供商：gemini（推荐免费）/ openai / anthropic / openrouter"
echo "也可以不填 --api-key，直接用小龙虾自带模型做话题拆解"
echo ""
