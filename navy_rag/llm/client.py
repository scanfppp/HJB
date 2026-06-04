"""
大模型调用客户端 — 阿里云百炼通义千问
统一接口封装，支持后续无缝切换离线模型
"""

from typing import Optional, Generator

import httpx

from config.settings import (
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL,
    LLM_MAX_TOKENS, LLM_TEMPERATURE, OFFLINE_MODE,
)
from utils.logger import get_logger

logger = get_logger(__name__)

_client = None


def _get_client():
    """获取OpenAI兼容客户端（延迟初始化）"""
    global _client
    if _client is None:
        try:
            from openai import OpenAI
            _client = OpenAI(
                api_key=LLM_API_KEY,
                base_url=LLM_BASE_URL,
            )
            logger.info(f"LLM客户端初始化: {LLM_BASE_URL}")
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")
    return _client


def chat(
    messages: list,
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
    stream: bool = False,
) -> str:
    """对话接口（同步）"""
    if OFFLINE_MODE:
        return _offline_chat(messages)

    if model is None:
        model = LLM_MODEL
    if temperature is None:
        temperature = LLM_TEMPERATURE
    if max_tokens is None:
        max_tokens = LLM_MAX_TOKENS

    client = _get_client()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
        )

        if stream:
            return _collect_stream(response)
        else:
            content = response.choices[0].message.content
            logger.info(f"LLM调用完成: 模型={model}, 输入长度≈{_count_chars(messages)}")
            return content

    except Exception as e:
        logger.error(f"LLM调用失败: {e}")
        raise


def chat_with_prompt(
    system_prompt: str,
    user_message: str,
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
) -> str:
    """便捷对话：系统提示词 + 用户消息"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    return chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)


def chat_stream(
    messages: list,
    model: str = None,
    temperature: float = None,
    max_tokens: int = None,
) -> Generator[str, None, None]:
    """流式对话接口"""
    if OFFLINE_MODE:
        yield _offline_chat(messages)
        return

    if model is None:
        model = LLM_MODEL
    if temperature is None:
        temperature = LLM_TEMPERATURE
    if max_tokens is None:
        max_tokens = LLM_MAX_TOKENS

    client = _get_client()

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

        for chunk in response:
            content = chunk.choices[0].delta.content if chunk.choices else None
            if content:
                yield content

    except GeneratorExit:
        pass
    except Exception as e:
        msg = str(e)
        if "client has been closed" in msg.lower() or "connection" in msg.lower():
            logger.info(f"LLM连接正常关闭: {msg[:80]}")
        else:
            logger.error(f"LLM流式调用失败: {e}")
            yield f"\n\n[错误] LLM调用失败: {e}"


def _collect_stream(response) -> str:
    """收集流式响应"""
    full_text = []
    for chunk in response:
        if chunk.choices[0].delta.content:
            full_text.append(chunk.choices[0].delta.content)
    return "".join(full_text)


def _offline_chat(messages: list) -> str:
    """离线模式占位（预留）"""
    from llm.offline import offline_chat
    return offline_chat(messages)


def _count_chars(messages: list) -> int:
    """估算消息总字符数"""
    return sum(len(m.get("content", "")) for m in messages)
