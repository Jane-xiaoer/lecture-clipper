"""
模型路由 — 自动检测可用 API，选最优模型
支持：Gemini / Claude / GPT / OpenRouter / 任何 OpenAI 兼容接口
"""
import os
from dataclasses import dataclass

@dataclass
class ModelConfig:
    name: str          # 显示名
    model_id: str      # API model id
    base_url: str      # API base URL
    api_key: str       # API key
    context_k: int     # 支持的 context 大小（千 token）

# 按优先级排列，context 越大越靠前
KNOWN_MODELS = [
    # Gemini — 超长 context，速度快，价格低
    {
        "name": "Gemini 2.0 Flash",
        "model_id": "gemini-2.0-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env_key": "GEMINI_API_KEY",
        "context_k": 1000,
    },
    {
        "name": "Gemini 1.5 Pro",
        "model_id": "gemini-1.5-pro",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env_key": "GEMINI_API_KEY",
        "context_k": 1000,
    },
    # Claude via Anthropic
    {
        "name": "Claude Sonnet 4.6",
        "model_id": "claude-sonnet-4-6-20251001",
        "base_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
        "context_k": 200,
    },
    # Claude via OpenRouter
    {
        "name": "Claude Sonnet (OpenRouter)",
        "model_id": "anthropic/claude-sonnet-4-6",
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
        "context_k": 200,
    },
    # GPT-4o via OpenAI
    {
        "name": "GPT-4o",
        "model_id": "gpt-4o",
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "context_k": 128,
    },
    # 便宜档（用于子话题拆分）
    {
        "name": "Gemini 2.0 Flash (mini task)",
        "model_id": "gemini-2.0-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env_key": "GEMINI_API_KEY",
        "context_k": 1000,
    },
    {
        "name": "GPT-4o-mini",
        "model_id": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "context_k": 128,
    },
]

def load_env_from_files():
    """加载常见 .env 文件"""
    candidates = [
        os.path.expanduser("~/.shared-skills/api-registry/.env"),
        os.path.expanduser("~/.hermes/.env"),
        os.path.join(os.getcwd(), ".env"),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, _, v = line.partition('=')
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and v and k not in os.environ:
                            os.environ[k] = v

def detect_available(min_context_k=50) -> list[ModelConfig]:
    """返回当前可用的模型列表（按优先级）"""
    load_env_from_files()
    seen = set()
    available = []
    for m in KNOWN_MODELS:
        key = os.environ.get(m["env_key"], "")
        if not key or key.startswith("your_") or m["model_id"] in seen:
            continue
        seen.add(m["model_id"])
        if m["context_k"] >= min_context_k:
            available.append(ModelConfig(
                name=m["name"],
                model_id=m["model_id"],
                base_url=m["base_url"],
                api_key=key,
                context_k=m["context_k"],
            ))
    return available

def pick_model(task="tagging", force_model: str = None) -> ModelConfig:
    """
    选择模型。
    task: "tagging" (需要大 context) | "splitting" (小任务，省钱)
    force_model: 手动指定 model_id
    """
    min_ctx = 100 if task == "tagging" else 10
    available = detect_available(min_context_k=min_ctx)

    if not available:
        raise RuntimeError(
            "没有可用的 LLM API。请设置以下任意环境变量：\n"
            "  GEMINI_API_KEY / ANTHROPIC_API_KEY / OPENROUTER_API_KEY / OPENAI_API_KEY"
        )

    if force_model:
        for m in available:
            if force_model.lower() in m.model_id.lower() or force_model.lower() in m.name.lower():
                return m
        raise ValueError(f"找不到指定模型 {force_model}，可用：{[m.name for m in available]}")

    return available[0]  # 已按优先级排好

def list_models():
    """打印可用模型列表"""
    available = detect_available(min_context_k=0)
    print("可用模型：")
    for i, m in enumerate(available, 1):
        print(f"  [{i}] {m.name} (context: {m.context_k}k)")
    return available

def call_llm(prompt: str, model: ModelConfig, system: str = "") -> str:
    """统一 LLM 调用接口，返回纯文本"""
    from openai import OpenAI

    client = OpenAI(api_key=model.api_key, base_url=model.base_url)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model=model.model_id,
        messages=messages,
        temperature=0.2,
        max_tokens=8192,
    )
    return resp.choices[0].message.content.strip()
