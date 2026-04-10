#!/usr/bin/env python3
"""
自动安装带 libass 的 ffmpeg（字幕烧入必须）

用法：
  python setup_ffmpeg.py

支持系统：
  macOS (arm64 / x86_64)
  Linux (x86_64 / arm64)
  Windows: 请手动下载，见下方说明

安装位置：~/.lecture-clipper/ffmpeg
"""
import os, platform, shutil, stat, subprocess, sys, urllib.request, zipfile
from pathlib import Path

INSTALL_DIR = Path.home() / ".lecture-clipper"
FFMPEG_BIN  = INSTALL_DIR / "ffmpeg"

# 下载源（静态编译版，含 libass / libfreetype / fontconfig）
DOWNLOAD_URLS = {
    # macOS — evermeet.cx 提供 Apple Silicon + Intel 版本
    ("Darwin", "arm64"):  "https://evermeet.cx/ffmpeg/ffmpeg-7.1.zip",
    ("Darwin", "x86_64"): "https://evermeet.cx/ffmpeg/ffmpeg-7.1.zip",
    # Linux — John Van Sickle 静态编译版
    ("Linux", "x86_64"):  "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
    ("Linux", "aarch64"): "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz",
}

def check_existing():
    """检查系统上是否已有含 libass 的 ffmpeg"""
    for ff in [str(FFMPEG_BIN), "ffmpeg", "/usr/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]:
        resolved = shutil.which(ff) or (ff if Path(ff).exists() else None)
        if not resolved:
            continue
        try:
            r = subprocess.run([resolved, "-filters"], capture_output=True, text=True, timeout=5)
            if "ass" in r.stdout or "subtitles" in r.stdout:
                return resolved
        except Exception:
            continue
    return None

def download_ffmpeg():
    system = platform.system()
    machine = platform.machine()

    # 统一 arm64 标识
    if machine in ("arm64", "aarch64"):
        machine_key = "arm64" if system == "Darwin" else "aarch64"
    else:
        machine_key = "x86_64"

    key = (system, machine_key)
    if key not in DOWNLOAD_URLS:
        print(f"❌ 不支持的系统：{system} {machine}")
        print_manual_instructions(system)
        sys.exit(1)

    url = DOWNLOAD_URLS[key]
    print(f"下载 ffmpeg ({system} {machine_key})...")
    print(f"  来源: {url}")

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    tmp = INSTALL_DIR / ("ffmpeg_dl" + (".zip" if url.endswith(".zip") else ".tar.xz"))

    # 带进度的下载
    def reporthook(count, block_size, total_size):
        if total_size > 0:
            pct = min(100, count * block_size * 100 // total_size)
            print(f"\r  {pct}%", end="", flush=True)

    urllib.request.urlretrieve(url, tmp, reporthook)
    print("\n  下载完成")

    # 解压
    print("  解压中...")
    if url.endswith(".zip"):
        with zipfile.ZipFile(tmp) as z:
            # evermeet.cx zip 里直接是 ffmpeg 二进制
            names = z.namelist()
            ff_name = next((n for n in names if n.rstrip('/') in ('ffmpeg', 'ffmpeg.exe')), names[0])
            with z.open(ff_name) as src, open(FFMPEG_BIN, 'wb') as dst:
                dst.write(src.read())
    else:
        # tar.xz — John Van Sickle 格式
        import tarfile
        with tarfile.open(tmp) as t:
            members = t.getmembers()
            ff = next(m for m in members if m.name.endswith('/ffmpeg') and not m.name.endswith('/ffprobe'))
            ff.name = "ffmpeg"
            t.extract(ff, INSTALL_DIR)

    tmp.unlink(missing_ok=True)

    # 赋予执行权限
    FFMPEG_BIN.chmod(FFMPEG_BIN.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(FFMPEG_BIN)

def verify(ffmpeg_path):
    """确认 libass 可用"""
    r = subprocess.run([ffmpeg_path, "-filters"], capture_output=True, text=True, timeout=10)
    if "ass" in r.stdout or "subtitles" in r.stdout:
        return True
    return False

def save_config(ffmpeg_path):
    """保存 ffmpeg 路径供 step3 读取"""
    config = INSTALL_DIR / "config.txt"
    config.write_text(f"FFMPEG={ffmpeg_path}\n")
    print(f"\n  配置已保存: {config}")

def print_manual_instructions(system):
    print("""
手动安装说明：
  macOS:
    1. 访问 https://evermeet.cx/ffmpeg/ 下载最新版
    2. 解压后放到 ~/.lecture-clipper/ffmpeg
    3. chmod +x ~/.lecture-clipper/ffmpeg

  Linux (Ubuntu/Debian):
    sudo apt update && sudo apt install -y ffmpeg
    （apt 版通常已含 libass）

  Windows:
    1. 访问 https://github.com/BtbN/FFmpeg-Builds/releases
    2. 下载 ffmpeg-master-latest-win64-gpl.zip
    3. 解压，把 ffmpeg.exe 放到 C:\\lecture-clipper\\ffmpeg.exe
    4. 运行 python setup_ffmpeg.py --ffmpeg C:\\lecture-clipper\\ffmpeg.exe
""")

def main():
    print("=== lecture-clipper FFmpeg 安装检查 ===\n")

    # 先检查系统上有没有现成的
    existing = check_existing()
    if existing:
        print(f"✅ 找到可用的 ffmpeg（含 libass）：{existing}")
        save_config(existing)
        print("\n无需下载，直接可用。")
        return

    print("⚠️  系统 ffmpeg 没有 libass，需要下载完整版\n")

    # Windows 不支持自动下载
    if platform.system() == "Windows":
        print_manual_instructions("Windows")
        sys.exit(0)

    try:
        ff_path = download_ffmpeg()
    except Exception as e:
        print(f"\n❌ 下载失败: {e}")
        print_manual_instructions(platform.system())
        sys.exit(1)

    print("  验证 libass...")
    if verify(ff_path):
        print(f"✅ 安装成功：{ff_path}")
        save_config(ff_path)
        print("\n现在可以运行 lecture-clipper 了。")
    else:
        print("❌ 下载的 ffmpeg 不含 libass，请手动安装")
        print_manual_instructions(platform.system())
        sys.exit(1)

if __name__ == "__main__":
    main()
