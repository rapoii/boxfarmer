"""Known working models for Blackbox.ai free tier."""
from __future__ import annotations

WORKING_MODELS = [
    "blackboxai/openai/gpt-5.4",
    "blackboxai/openai/gpt-5.4-pro",
    "blackboxai/openai/gpt-5.4-nano",
    "blackboxai/openai/gpt-5.3-codex",
    "blackboxai/x-ai/grok-4.3",
    "blackboxai/google/gemini-3.5-flash",
    "blackboxai/moonshotai/kimi-k3",
    "blackboxai/mistral/codestral",
    "blackboxai/nvidia/nemotron-3-ultra",
    "blackboxai/meta/llama-3.1-70b",
    "blackboxai/meta/llama-3.1-8b",
    "blackboxai/morph/morph-v3-fast",
    "blackboxai/amazon/nova-micro",
    "z-ai/glm-5.2",
    "blackboxai/deepseek/deepseek-v4-pro",
]

# 9Router prefix mapping (bb/xxx → blackboxai/xxx)
NINEROUTER_MAP = {
    "bb/gpt-5.4": "blackboxai/openai/gpt-5.4",
    "bb/gpt-5.4-pro": "blackboxai/openai/gpt-5.4-pro",
    "bb/gpt-5.4-nano": "blackboxai/openai/gpt-5.4-nano",
    "bb/gpt-5.3-codex": "blackboxai/openai/gpt-5.3-codex",
    "bb/grok-4.3": "blackboxai/x-ai/grok-4.3",
    "bb/claude-sonnet-4.6": "blackboxai/anthropic/claude-3.5-sonnet",
    "bb/claude-opus-4.8": "blackboxai/anthropic/claude-3-opus",
    "bb/claude-fable-5": "blackboxai/anthropic/claude-fable-5",
    "bb/deepseek-v4-flash": "blackboxai/deepseek/deepseek-v4-flash",
    "bb/gpt-5.5": "blackboxai/openai/gpt-5.5",
}
