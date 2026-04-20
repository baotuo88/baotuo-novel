# -*- coding: utf-8 -*-
# AIMETA P=LLM工具_大模型调用辅助|R=请求构建_响应解析|NR=不含业务逻辑|E=LLMTool|X=internal|A=工具类|D=httpx|S=net|RD=./README.ai
"""OpenAI 兼容型 LLM 工具封装，保持与旧项目一致的接口体验。"""

import os
import logging
from dataclasses import asdict, dataclass
from typing import AsyncGenerator, Dict, List, Optional

from openai import APIStatusError, AsyncOpenAI


logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    role: str
    content: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


class LLMClient:
    """异步流式调用封装，兼容 OpenAI SDK。"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("缺少 OPENAI_API_KEY 配置，请在数据库或环境变量中补全。")

        resolved_base_url = (
            base_url
            or os.environ.get("OPENAI_API_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("OPENAI_API_BASE")
        )
        self._client = AsyncOpenAI(api_key=key, base_url=resolved_base_url)

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        response_format: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: int = 120,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, str], None]:
        payload = {
            "model": model or os.environ.get("OPENAI_MODEL_NAME") or os.environ.get("MODEL", "gpt-4o-mini"),
            "messages": [msg.to_dict() for msg in messages],
            "stream": True,
            "timeout": timeout,
            **kwargs,
        }
        if response_format:
            payload["response_format"] = {"type": response_format}
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        stream = await self._create_stream_with_format_fallback(
            payload=payload,
            response_format=response_format,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            yield {
                "content": choice.delta.content,
                "finish_reason": choice.finish_reason,
            }

    async def _create_stream_with_format_fallback(
        self,
        *,
        payload: Dict[str, object],
        response_format: Optional[str],
    ):
        try:
            return await self._client.chat.completions.create(**payload)
        except APIStatusError as exc:
            if not self._should_retry_without_response_format(exc, response_format):
                raise

            fallback_payload = dict(payload)
            fallback_payload.pop("response_format", None)
            logger.warning(
                "OpenAI-compatible endpoint rejected response_format, retry without response_format: status=%s model=%s",
                getattr(exc, "status_code", None)
                or getattr(getattr(exc, "response", None), "status_code", None),
                payload.get("model"),
            )
            return await self._client.chat.completions.create(**fallback_payload)

    @staticmethod
    def _should_retry_without_response_format(exc: APIStatusError, response_format: Optional[str]) -> bool:
        if not response_format:
            return False
        code = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
        if code != 400:
            return False
        text = str(exc).lower()
        keywords = [
            "response_format",
            "json_schema",
            "unsupported",
            "not support",
            "invalid type",
            "schema",
        ]
        return any(keyword in text for keyword in keywords)
