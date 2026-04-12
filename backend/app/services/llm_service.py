# AIMETA P=LLM服务_大模型调用封装|R=API调用_流式生成|NR=不含业务逻辑|E=LLMService|X=internal|A=服务类|D=openai,httpx|S=net|RD=./README.ai
import logging
import os
import time
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException, status
from openai import APIConnectionError, APITimeoutError, APIStatusError, AsyncOpenAI, InternalServerError, RateLimitError
from sqlalchemy import func, select

from ..core.config import settings
from ..models import LLMCallLog
from ..repositories.llm_config_repository import LLMConfigRepository
from ..repositories.system_config_repository import SystemConfigRepository
from ..repositories.user_repository import UserRepository
from ..services.admin_setting_service import AdminSettingService
from ..services.prompt_service import PromptService
from ..services.usage_service import UsageService
from ..utils.llm_tool import ChatMessage, LLMClient

logger = logging.getLogger(__name__)

# 估算价格（美元 / 1M tokens）。仅用于后台粗略成本估算，不作为计费依据。
MODEL_PRICING_PER_1M: Dict[str, Dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "text-embedding-3-small": {"input": 0.02, "output": 0.00},
    "text-embedding-3-large": {"input": 0.13, "output": 0.00},
}

RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


@dataclass
class BudgetPolicy:
    global_limit_usd: float
    user_limit_usd: float
    project_limit_usd: float
    mode: str
    degrade_model: str
    reserve_output_tokens: int


@dataclass
class StreamErrorInfo:
    status_code: int
    detail: str
    retryable: bool
    error_type: str

try:  # pragma: no cover - 运行环境未安装时兼容
    from ollama import AsyncClient as OllamaAsyncClient
except ImportError:  # pragma: no cover - Ollama 为可选依赖
    OllamaAsyncClient = None


class LLMService:
    """封装与大模型交互的所有逻辑，包括配额控制与配置选择。"""

    def __init__(self, session):
        self.session = session
        self.llm_repo = LLMConfigRepository(session)
        self.system_config_repo = SystemConfigRepository(session)
        self.user_repo = UserRepository(session)
        self.admin_setting_service = AdminSettingService(session)
        self.usage_service = UsageService(session)
        self._embedding_dimensions: Dict[str, int] = {}

    async def get_llm_response(
        self,
        system_prompt: str,
        conversation_history: List[Dict[str, str]],
        *,
        temperature: float = 0.7,
        user_id: Optional[int] = None,
        timeout: float = 300.0,
        response_format: Optional[str] = "json_object",
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        request_type: str = "chat",
        project_id: Optional[str] = None,
        max_retries_override: Optional[int] = None,
        allow_fallback_models: bool = True,
    ) -> str:
        messages = [{"role": "system", "content": system_prompt}, *conversation_history]
        return await self._stream_and_collect(
            messages,
            temperature=temperature,
            user_id=user_id,
            timeout=timeout,
            response_format=response_format,
            max_tokens=max_tokens,
            top_p=top_p,
            request_type=request_type,
            project_id=project_id,
            max_retries_override=max_retries_override,
            allow_fallback_models=allow_fallback_models,
        )

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        user_id: Optional[int] = None,
        timeout: float = 300.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[str] = None,
        top_p: Optional[float] = None,
        request_type: str = "chat",
        project_id: Optional[str] = None,
    ) -> str:
        """兼容旧版接口的文本生成入口，统一走 get_llm_response。"""
        return await self.get_llm_response(
            system_prompt=system_prompt or "你是一位专业写作助手。",
            conversation_history=[{"role": "user", "content": prompt}],
            temperature=temperature,
            user_id=user_id,
            timeout=timeout,
            response_format=response_format,
            max_tokens=max_tokens,
            top_p=top_p,
            request_type=request_type,
            project_id=project_id,
        )

    async def get_summary(
        self,
        chapter_content: str,
        *,
        temperature: float = 0.2,
        user_id: Optional[int] = None,
        timeout: float = 180.0,
        system_prompt: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        if not system_prompt:
            prompt_service = PromptService(self.session)
            system_prompt = await prompt_service.get_prompt("extraction")
        if not system_prompt:
            logger.error("未配置名为 'extraction' 的摘要提示词，无法生成章节摘要")
            raise HTTPException(status_code=500, detail="未配置摘要提示词，请联系管理员配置 'extraction' 提示词")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": chapter_content},
        ]
        return await self._stream_and_collect(
            messages,
            temperature=temperature,
            user_id=user_id,
            timeout=timeout,
            request_type="summary",
            project_id=project_id,
        )

    async def _stream_and_collect(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float,
        user_id: Optional[int],
        timeout: float,
        response_format: Optional[str] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        request_type: str = "chat",
        project_id: Optional[str] = None,
        max_retries_override: Optional[int] = None,
        allow_fallback_models: bool = True,
    ) -> str:
        start_at = time.perf_counter()
        input_chars = sum(len(item.get("content") or "") for item in messages)
        input_tokens = self._estimate_tokens_by_chars(input_chars)
        model_name = ""
        provider = "openai-compatible"

        try:
            config = await self._resolve_llm_config(user_id)
        except HTTPException as exc:
            await self._record_llm_call(
                user_id=user_id,
                project_id=project_id,
                request_type=request_type,
                provider=provider,
                model=model_name,
                status="error",
                latency_ms=self._elapsed_ms(start_at),
                input_chars=input_chars,
                output_chars=0,
                estimated_input_tokens=input_tokens,
                estimated_output_tokens=0,
                finish_reason=None,
                error_type=exc.__class__.__name__,
                error_message=str(exc.detail),
                commit=True,
            )
            raise

        model_name = (config.get("model") or "").strip()
        provider = self._infer_provider(config.get("base_url"))
        try:
            model_name, budget_note = await self._apply_budget_policy(
                model=model_name,
                user_id=user_id,
                project_id=project_id,
                input_tokens=input_tokens,
            )
        except HTTPException as exc:
            await self._record_llm_call(
                user_id=user_id,
                project_id=project_id,
                request_type=request_type,
                provider=provider,
                model=model_name,
                status="error",
                latency_ms=self._elapsed_ms(start_at),
                input_chars=input_chars,
                output_chars=0,
                estimated_input_tokens=input_tokens,
                estimated_output_tokens=0,
                finish_reason=None,
                error_type="BudgetCircuitOpen",
                error_message=str(exc.detail),
                commit=True,
            )
            raise

        if budget_note:
            logger.warning("LLM 预算熔断触发并降级模型：%s", budget_note)

        client = LLMClient(api_key=config["api_key"], base_url=config.get("base_url"))
        chat_messages = [ChatMessage(role=msg["role"], content=msg["content"]) for msg in messages]

        if max_retries_override is None:
            max_retries = await self._get_int_config("llm.retry.max_retries", default=1, min_value=0, max_value=4)
        else:
            max_retries = max(0, min(4, int(max_retries_override)))
        backoff_ms = await self._get_int_config("llm.retry.backoff_ms", default=600, min_value=100, max_value=10_000)
        model_candidates = await self._get_model_candidates(model_name)
        if not allow_fallback_models and model_candidates:
            model_candidates = model_candidates[:1]
        budget_filtered_candidates: List[str] = []
        budget_block_detail: Optional[str] = None
        for candidate in model_candidates:
            try:
                checked_model, _ = await self._apply_budget_policy(
                    model=candidate,
                    user_id=user_id,
                    project_id=project_id,
                    input_tokens=input_tokens,
                    allow_degrade=False,
                )
                if checked_model not in budget_filtered_candidates:
                    budget_filtered_candidates.append(checked_model)
            except HTTPException as exc:
                budget_block_detail = budget_block_detail or str(exc.detail)
                logger.warning(
                    "模型已因预算熔断被跳过：model=%s user_id=%s project_id=%s detail=%s",
                    candidate,
                    user_id,
                    project_id,
                    exc.detail,
                )

        if not budget_filtered_candidates:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=budget_block_detail or "LLM 预算熔断已触发，请稍后再试或调整预算配置",
            )
        model_candidates = budget_filtered_candidates
        last_error: Optional[StreamErrorInfo] = None
        attempt_index = 0

        logger.info(
            "Streaming LLM response: model=%s user_id=%s project_id=%s messages=%d retries=%d candidates=%s",
            model_name,
            user_id,
            project_id,
            len(messages),
            max_retries,
            model_candidates,
        )

        for candidate_i, candidate_model in enumerate(model_candidates):
            per_model_attempts = max_retries + 1 if candidate_i == 0 else 1

            for retry_i in range(per_model_attempts):
                attempt_index += 1
                full_response = ""
                finish_reason = None

                try:
                    async for part in client.stream_chat(
                        messages=chat_messages,
                        model=candidate_model,
                        temperature=temperature,
                        timeout=int(timeout),
                        response_format=response_format,
                        max_tokens=max_tokens,
                        top_p=top_p,
                    ):
                        if part.get("content"):
                            full_response += part["content"]
                        if part.get("finish_reason"):
                            finish_reason = part["finish_reason"]
                except Exception as exc:
                    error_info = self._classify_stream_error(exc)
                    last_error = error_info
                    logger.error(
                        "LLM stream failed: model=%s user_id=%s project_id=%s attempt=%s detail=%s",
                        candidate_model,
                        user_id,
                        project_id,
                        attempt_index,
                        error_info.detail,
                        exc_info=exc,
                    )
                    await self._record_llm_call(
                        user_id=user_id,
                        project_id=project_id,
                        request_type=request_type,
                        provider=provider,
                        model=candidate_model,
                        status="error",
                        latency_ms=self._elapsed_ms(start_at),
                        input_chars=input_chars,
                        output_chars=len(full_response),
                        estimated_input_tokens=input_tokens,
                        estimated_output_tokens=self._estimate_tokens_by_chars(len(full_response)),
                        finish_reason=finish_reason,
                        error_type=error_info.error_type,
                        error_message=error_info.detail,
                        commit=True,
                    )
                    if error_info.retryable and retry_i < per_model_attempts - 1:
                        await asyncio.sleep((backoff_ms * (2 ** retry_i)) / 1000)
                        continue
                    break

                logger.debug(
                    "LLM response collected: model=%s user_id=%s project_id=%s finish_reason=%s preview=%s",
                    candidate_model,
                    user_id,
                    project_id,
                    finish_reason,
                    full_response[:500],
                )

                if finish_reason == "length":
                    detail = f"AI 响应因长度限制被截断（已生成 {len(full_response)} 字符），请缩短输入内容或调整模型参数"
                    last_error = StreamErrorInfo(
                        status_code=500,
                        detail=detail,
                        retryable=False,
                        error_type="LengthTruncated",
                    )
                    await self._record_llm_call(
                        user_id=user_id,
                        project_id=project_id,
                        request_type=request_type,
                        provider=provider,
                        model=candidate_model,
                        status="error",
                        latency_ms=self._elapsed_ms(start_at),
                        input_chars=input_chars,
                        output_chars=len(full_response),
                        estimated_input_tokens=input_tokens,
                        estimated_output_tokens=self._estimate_tokens_by_chars(len(full_response)),
                        finish_reason=finish_reason,
                        error_type=last_error.error_type,
                        error_message=detail,
                        commit=True,
                    )
                    break

                if not full_response:
                    detail = f"AI 未返回有效内容（结束原因: {finish_reason or '未知'}），请稍后重试或联系管理员"
                    last_error = StreamErrorInfo(
                        status_code=500,
                        detail=detail,
                        retryable=False,
                        error_type="EmptyResponse",
                    )
                    await self._record_llm_call(
                        user_id=user_id,
                        project_id=project_id,
                        request_type=request_type,
                        provider=provider,
                        model=candidate_model,
                        status="error",
                        latency_ms=self._elapsed_ms(start_at),
                        input_chars=input_chars,
                        output_chars=0,
                        estimated_input_tokens=input_tokens,
                        estimated_output_tokens=0,
                        finish_reason=finish_reason,
                        error_type=last_error.error_type,
                        error_message=detail,
                        commit=True,
                    )
                    break

                output_chars = len(full_response)
                output_tokens = self._estimate_tokens_by_chars(output_chars)
                await self._record_llm_call(
                    user_id=user_id,
                    project_id=project_id,
                    request_type=request_type,
                    provider=provider,
                    model=candidate_model,
                    status="success",
                    latency_ms=self._elapsed_ms(start_at),
                    input_chars=input_chars,
                    output_chars=output_chars,
                    estimated_input_tokens=input_tokens,
                    estimated_output_tokens=output_tokens,
                    finish_reason=finish_reason,
                    error_type=None,
                    error_message=None,
                    commit=False,
                )
                await self.usage_service.increment("api_request_count")
                logger.info(
                    "LLM response success: model=%s user_id=%s project_id=%s chars=%d attempt=%d",
                    candidate_model,
                    user_id,
                    project_id,
                    output_chars,
                    attempt_index,
                )
                return full_response

        if last_error:
            raise HTTPException(status_code=last_error.status_code, detail=last_error.detail)
        raise HTTPException(status_code=503, detail="AI 请求失败，请稍后重试")

    def _classify_stream_error(self, exc: Exception) -> StreamErrorInfo:
        if isinstance(exc, RateLimitError):
            return StreamErrorInfo(
                status_code=429,
                detail="AI 服务触发限流，请稍后重试",
                retryable=True,
                error_type=exc.__class__.__name__,
            )

        if isinstance(exc, InternalServerError):
            detail = "AI 服务内部错误，请稍后重试"
            response = getattr(exc, "response", None)
            if response is not None:
                try:
                    payload = response.json()
                    error_data = payload.get("error", {}) if isinstance(payload, dict) else {}
                    detail = error_data.get("message_zh") or error_data.get("message") or detail
                except Exception:
                    detail = str(exc) or detail
            return StreamErrorInfo(
                status_code=503,
                detail=detail,
                retryable=True,
                error_type=exc.__class__.__name__,
            )

        if isinstance(exc, APIStatusError):
            code = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
            if code == 429:
                detail = "AI 服务触发限流，请稍后重试"
            elif code == 401:
                detail = "AI 服务鉴权失败，请检查 API Key 配置"
            elif code == 403:
                detail = "AI 服务访问被拒绝，请检查账号权限"
            elif code == 404:
                detail = "AI 模型或接口不存在，请检查模型与 Base URL"
            else:
                detail = f"AI 服务调用失败（HTTP {code or '未知'}）"
            retryable = bool(code in RETRYABLE_HTTP_STATUS) if code else True
            return StreamErrorInfo(
                status_code=429 if code == 429 else 503,
                detail=detail,
                retryable=retryable,
                error_type=exc.__class__.__name__,
            )

        if isinstance(exc, httpx.RemoteProtocolError):
            return StreamErrorInfo(
                status_code=503,
                detail="AI 服务连接被意外中断，请稍后重试",
                retryable=True,
                error_type=exc.__class__.__name__,
            )
        if isinstance(exc, (httpx.ReadTimeout, APITimeoutError)):
            return StreamErrorInfo(
                status_code=503,
                detail="AI 服务响应超时，请稍后重试",
                retryable=True,
                error_type=exc.__class__.__name__,
            )
        if isinstance(exc, APIConnectionError):
            return StreamErrorInfo(
                status_code=503,
                detail="无法连接到 AI 服务，请稍后重试",
                retryable=True,
                error_type=exc.__class__.__name__,
            )
        return StreamErrorInfo(
            status_code=500,
            detail=str(exc) or "AI 服务调用失败，请稍后重试",
            retryable=False,
            error_type=exc.__class__.__name__,
        )

    async def _get_model_candidates(self, primary_model: Optional[str]) -> List[str]:
        models: List[str] = []
        if primary_model:
            models.append(primary_model.strip())
        fallback_text = await self._get_config_value("llm.fallback.models")
        if fallback_text:
            models.extend(item.strip() for item in fallback_text.split(",") if item.strip())
        if not models:
            default_model = await self._get_config_value("llm.model")
            if default_model:
                models.append(default_model.strip())
        if not models:
            models.append("gpt-4o-mini")

        deduped: List[str] = []
        seen = set()
        for item in models:
            normalized = item.strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(normalized)
        return deduped

    async def _get_int_config(
        self,
        key: str,
        *,
        default: int,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
    ) -> int:
        raw = await self._get_config_value(key)
        value = default
        if raw not in (None, ""):
            try:
                value = int(str(raw).strip())
            except Exception:
                logger.warning("系统配置 %s 非法整数值：%s，已回退默认值 %s", key, raw, default)
                value = default
        if min_value is not None:
            value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)
        return value

    async def _get_float_config(
        self,
        key: str,
        *,
        default: float,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ) -> float:
        raw = await self._get_config_value(key)
        value = default
        if raw not in (None, ""):
            try:
                value = float(str(raw).strip())
            except Exception:
                logger.warning("系统配置 %s 非法浮点值：%s，已回退默认值 %.4f", key, raw, default)
                value = default
        if min_value is not None:
            value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)
        return value

    async def _load_budget_policy(self, user_id: Optional[int], project_id: Optional[str]) -> BudgetPolicy:
        global_limit = await self._get_float_config(
            "llm.budget.daily_usd.global",
            default=0.0,
            min_value=0.0,
            max_value=10_000_000.0,
        )

        user_limit = 0.0
        if user_id is not None:
            raw_user_limit = await self._get_config_value(f"llm.budget.daily_usd.user.{user_id}")
            if raw_user_limit in (None, ""):
                user_limit = await self._get_float_config(
                    "llm.budget.daily_usd.user.default",
                    default=0.0,
                    min_value=0.0,
                    max_value=10_000_000.0,
                )
            else:
                try:
                    user_limit = max(0.0, float(str(raw_user_limit).strip()))
                except Exception:
                    logger.warning("用户预算配置非法：user_id=%s value=%s", user_id, raw_user_limit)
                    user_limit = 0.0

        project_limit = 0.0
        if project_id:
            raw_project_limit = await self._get_config_value(f"llm.budget.daily_usd.project.{project_id}")
            if raw_project_limit in (None, ""):
                project_limit = await self._get_float_config(
                    "llm.budget.daily_usd.project.default",
                    default=0.0,
                    min_value=0.0,
                    max_value=10_000_000.0,
                )
            else:
                try:
                    project_limit = max(0.0, float(str(raw_project_limit).strip()))
                except Exception:
                    logger.warning("项目预算配置非法：project_id=%s value=%s", project_id, raw_project_limit)
                    project_limit = 0.0

        mode = (await self._get_config_value("llm.budget.circuit_mode") or "degrade").strip().lower()
        if mode not in {"degrade", "block"}:
            mode = "degrade"
        degrade_model = (await self._get_config_value("llm.budget.degrade_model") or "gpt-4o-mini").strip() or "gpt-4o-mini"
        reserve_output_tokens = await self._get_int_config(
            "llm.budget.reserve_output_tokens",
            default=1200,
            min_value=1,
            max_value=32_000,
        )

        return BudgetPolicy(
            global_limit_usd=global_limit,
            user_limit_usd=user_limit,
            project_limit_usd=project_limit,
            mode=mode,
            degrade_model=degrade_model,
            reserve_output_tokens=reserve_output_tokens,
        )

    async def _today_spend_usd(
        self,
        *,
        user_id: Optional[int] = None,
        project_id: Optional[str] = None,
    ) -> float:
        day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.coalesce(func.sum(LLMCallLog.estimated_cost_usd), 0.0)).where(
            LLMCallLog.created_at >= day_start,
            LLMCallLog.status == "success",
        )
        if user_id is not None:
            stmt = stmt.where(LLMCallLog.user_id == user_id)
        if project_id:
            stmt = stmt.where(LLMCallLog.project_id == project_id)
        value = await self.session.scalar(stmt)
        return round(float(value or 0.0), 8)

    async def _apply_budget_policy(
        self,
        *,
        model: Optional[str],
        user_id: Optional[int],
        project_id: Optional[str],
        input_tokens: int,
        allow_degrade: bool = True,
    ) -> tuple[str, Optional[str]]:
        policy = await self._load_budget_policy(user_id=user_id, project_id=project_id)
        current_model = (model or await self._get_config_value("llm.model") or "gpt-4o-mini").strip() or "gpt-4o-mini"

        if policy.global_limit_usd <= 0 and policy.user_limit_usd <= 0 and policy.project_limit_usd <= 0:
            return current_model, None

        projected_cost = self._estimate_cost_usd(
            current_model,
            input_tokens=input_tokens,
            output_tokens=policy.reserve_output_tokens,
        ) or 0.0

        exceeded_scopes: List[str] = []
        if policy.global_limit_usd > 0:
            global_spent = await self._today_spend_usd()
            if global_spent >= policy.global_limit_usd or (global_spent + projected_cost) > policy.global_limit_usd:
                exceeded_scopes.append(f"全局预算({global_spent:.6f}/{policy.global_limit_usd:.6f} USD)")
        if policy.user_limit_usd > 0 and user_id is not None:
            user_spent = await self._today_spend_usd(user_id=user_id)
            if user_spent >= policy.user_limit_usd or (user_spent + projected_cost) > policy.user_limit_usd:
                exceeded_scopes.append(f"用户预算({user_spent:.6f}/{policy.user_limit_usd:.6f} USD)")
        if policy.project_limit_usd > 0 and project_id:
            project_spent = await self._today_spend_usd(project_id=project_id)
            if project_spent >= policy.project_limit_usd or (project_spent + projected_cost) > policy.project_limit_usd:
                exceeded_scopes.append(f"项目预算({project_spent:.6f}/{policy.project_limit_usd:.6f} USD)")

        if not exceeded_scopes:
            return current_model, None

        if allow_degrade and policy.mode == "degrade" and policy.degrade_model and policy.degrade_model != current_model:
            note = (
                f"预算触发（{'、'.join(exceeded_scopes)}），"
                f"模型已从 `{current_model}` 自动降级为 `{policy.degrade_model}`"
            )
            return policy.degrade_model, note

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"LLM 预算熔断已触发：{'、'.join(exceeded_scopes)}，请稍后再试或调整预算配置",
        )

    async def _resolve_llm_config(self, user_id: Optional[int]) -> Dict[str, Optional[str]]:
        if user_id:
            config = await self.llm_repo.get_by_user(user_id)
            if config and config.llm_provider_api_key:
                return {
                    "api_key": config.llm_provider_api_key,
                    "base_url": config.llm_provider_url,
                    "model": config.llm_provider_model,
                }

        # 检查每日使用次数限制
        if user_id:
            await self._enforce_daily_limit(user_id)

        api_key = await self._get_config_value("llm.api_key")
        base_url = await self._get_config_value("llm.base_url")
        model = await self._get_config_value("llm.model")

        if not api_key:
            logger.error("未配置默认 LLM API Key，且用户 %s 未设置自定义 API Key", user_id)
            raise HTTPException(
                status_code=500,
                detail="未配置默认 LLM API Key，请联系管理员配置系统默认 API Key 或在个人设置中配置自定义 API Key"
            )

        return {"api_key": api_key, "base_url": base_url, "model": model}

    async def get_embedding(
        self,
        text: str,
        *,
        user_id: Optional[int] = None,
        model: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[float]:
        """生成文本向量，用于章节 RAG 检索，支持 openai 与 ollama 双提供方。"""
        start_at = time.perf_counter()
        input_chars = len(text or "")
        input_tokens = self._estimate_tokens_by_chars(input_chars)
        provider = await self._get_config_value("embedding.provider") or "openai"
        default_model = (
            await self._get_config_value("ollama.embedding_model") or "nomic-embed-text:latest"
            if provider == "ollama"
            else await self._get_config_value("embedding.model") or "text-embedding-3-large"
        )
        target_model = model or default_model
        base_url: Optional[str] = None

        try:
            target_model, _ = await self._apply_budget_policy(
                model=target_model,
                user_id=user_id,
                project_id=project_id,
                input_tokens=input_tokens,
                allow_degrade=False,
            )
        except HTTPException as exc:
            await self._record_llm_call(
                user_id=user_id,
                project_id=project_id,
                request_type="embedding",
                provider="ollama" if provider == "ollama" else "openai-compatible",
                model=target_model,
                status="error",
                latency_ms=self._elapsed_ms(start_at),
                input_chars=input_chars,
                output_chars=0,
                estimated_input_tokens=input_tokens,
                estimated_output_tokens=0,
                finish_reason=None,
                error_type="BudgetCircuitOpen",
                error_message=str(exc.detail),
                commit=True,
            )
            raise

        if provider == "ollama":
            if OllamaAsyncClient is None:
                logger.error("未安装 ollama 依赖，无法调用本地嵌入模型。")
                raise HTTPException(status_code=500, detail="缺少 Ollama 依赖，请先安装 ollama 包。")

            base_url = (
                await self._get_config_value("ollama.embedding_base_url")
                or await self._get_config_value("embedding.base_url")
            )
            client = OllamaAsyncClient(host=base_url)
            try:
                response = await client.embeddings(model=target_model, prompt=text)
            except Exception as exc:  # pragma: no cover - 本地服务调用失败
                logger.error(
                    "Ollama 嵌入请求失败: model=%s base_url=%s error=%s",
                    target_model,
                    base_url,
                    exc,
                    exc_info=True,
                )
                await self._record_llm_call(
                    user_id=user_id,
                    project_id=project_id,
                    request_type="embedding",
                    provider="ollama",
                    model=target_model,
                    status="error",
                    latency_ms=self._elapsed_ms(start_at),
                    input_chars=input_chars,
                    output_chars=0,
                    estimated_input_tokens=input_tokens,
                    estimated_output_tokens=0,
                    finish_reason=None,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                    commit=True,
                )
                return []
            embedding: Optional[List[float]]
            if isinstance(response, dict):
                embedding = response.get("embedding")
            else:
                embedding = getattr(response, "embedding", None)
            if not embedding:
                logger.warning("Ollama 返回空向量: model=%s", target_model)
                await self._record_llm_call(
                    user_id=user_id,
                    project_id=project_id,
                    request_type="embedding",
                    provider="ollama",
                    model=target_model,
                    status="error",
                    latency_ms=self._elapsed_ms(start_at),
                    input_chars=input_chars,
                    output_chars=0,
                    estimated_input_tokens=input_tokens,
                    estimated_output_tokens=0,
                    finish_reason=None,
                    error_type="EmptyEmbedding",
                    error_message="Ollama 返回空向量",
                    commit=True,
                )
                return []
            if not isinstance(embedding, list):
                embedding = list(embedding)
        else:
            try:
                config = await self._resolve_llm_config(user_id)
            except HTTPException as exc:
                await self._record_llm_call(
                    user_id=user_id,
                    project_id=project_id,
                    request_type="embedding",
                    provider="openai-compatible",
                    model=target_model,
                    status="error",
                    latency_ms=self._elapsed_ms(start_at),
                    input_chars=input_chars,
                    output_chars=0,
                    estimated_input_tokens=input_tokens,
                    estimated_output_tokens=0,
                    finish_reason=None,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc.detail),
                    commit=True,
                )
                raise
            api_key = await self._get_config_value("embedding.api_key") or config["api_key"]
            base_url = await self._get_config_value("embedding.base_url") or config.get("base_url")
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            try:
                response = await client.embeddings.create(
                    input=text,
                    model=target_model,
                )
            except Exception as exc:  # pragma: no cover - 网络或鉴权失败
                logger.error(
                    "OpenAI 嵌入请求失败: model=%s base_url=%s user_id=%s error=%s",
                    target_model,
                    base_url,
                    user_id,
                    exc,
                    exc_info=True,
                )
                await self._record_llm_call(
                    user_id=user_id,
                    project_id=project_id,
                    request_type="embedding",
                    provider=self._infer_provider(base_url),
                    model=target_model,
                    status="error",
                    latency_ms=self._elapsed_ms(start_at),
                    input_chars=input_chars,
                    output_chars=0,
                    estimated_input_tokens=input_tokens,
                    estimated_output_tokens=0,
                    finish_reason=None,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                    commit=True,
                )
                return []
            if not response.data:
                logger.warning("OpenAI 嵌入请求返回空数据: model=%s user_id=%s", target_model, user_id)
                await self._record_llm_call(
                    user_id=user_id,
                    project_id=project_id,
                    request_type="embedding",
                    provider=self._infer_provider(base_url),
                    model=target_model,
                    status="error",
                    latency_ms=self._elapsed_ms(start_at),
                    input_chars=input_chars,
                    output_chars=0,
                    estimated_input_tokens=input_tokens,
                    estimated_output_tokens=0,
                    finish_reason=None,
                    error_type="EmptyEmbedding",
                    error_message="OpenAI 嵌入请求返回空数据",
                    commit=True,
                )
                return []
            embedding = response.data[0].embedding

        if not isinstance(embedding, list):
            embedding = list(embedding)

        dimension = len(embedding)
        if not dimension:
            vector_size_str = await self._get_config_value("embedding.model_vector_size")
            if vector_size_str:
                dimension = int(vector_size_str)
        if dimension:
            self._embedding_dimensions[target_model] = dimension

        await self._record_llm_call(
            user_id=user_id,
            project_id=project_id,
            request_type="embedding",
            provider="ollama" if provider == "ollama" else self._infer_provider(base_url),
            model=target_model,
            status="success",
            latency_ms=self._elapsed_ms(start_at),
            input_chars=input_chars,
            output_chars=0,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=0,
            finish_reason=None,
            error_type=None,
            error_message=None,
            commit=True,
        )
        return embedding

    async def get_embedding_dimension(self, model: Optional[str] = None) -> Optional[int]:
        """获取嵌入向量维度，优先返回缓存结果，其次读取配置。"""
        provider = await self._get_config_value("embedding.provider") or "openai"
        default_model = (
            await self._get_config_value("ollama.embedding_model") or "nomic-embed-text:latest"
            if provider == "ollama"
            else await self._get_config_value("embedding.model") or "text-embedding-3-large"
        )
        target_model = model or default_model
        if target_model in self._embedding_dimensions:
            return self._embedding_dimensions[target_model]
        vector_size_str = await self._get_config_value("embedding.model_vector_size")
        return int(vector_size_str) if vector_size_str else None

    async def _enforce_daily_limit(self, user_id: int) -> None:
        limit_str = await self.admin_setting_service.get("daily_request_limit", "100")
        limit = int(limit_str or 10)
        used = await self.user_repo.get_daily_request(user_id)
        if used >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="今日请求次数已达上限，请明日再试或设置自定义 API Key。",
            )
        await self.user_repo.increment_daily_request(user_id)
        await self.session.commit()

    async def _get_config_value(self, key: str) -> Optional[str]:
        record = await self.system_config_repo.get_by_key(key)
        if record:
            return record.value
        # 兼容环境变量，首次迁移时无需立即写入数据库
        env_key = key.upper().replace(".", "_")
        return os.getenv(env_key)

    def _estimate_tokens_by_chars(self, chars: int) -> int:
        """基于字符数估算 token，用于观测，不用于精确计费。"""
        if chars <= 0:
            return 0
        # 中文平均 token 密度更高，按 1.1 倍字符近似；英文按 4 字符约 1 token 近似。
        return max(1, int(chars * 0.6))

    def _infer_provider(self, base_url: Optional[str]) -> str:
        if not base_url:
            return "openai"
        lowered = base_url.lower()
        if "ollama" in lowered:
            return "ollama"
        if "openai" in lowered:
            return "openai"
        return "openai-compatible"

    def _resolve_pricing(self, model: Optional[str]) -> Optional[Dict[str, float]]:
        if not model:
            return None
        lowered = model.lower()
        if lowered in MODEL_PRICING_PER_1M:
            return MODEL_PRICING_PER_1M[lowered]
        for key, value in MODEL_PRICING_PER_1M.items():
            if lowered.startswith(key):
                return value
        return None

    def _estimate_cost_usd(
        self,
        model: Optional[str],
        input_tokens: int,
        output_tokens: int,
    ) -> Optional[float]:
        pricing = self._resolve_pricing(model)
        if not pricing:
            return None
        input_cost = (input_tokens / 1_000_000) * pricing.get("input", 0.0)
        output_cost = (output_tokens / 1_000_000) * pricing.get("output", 0.0)
        return round(input_cost + output_cost, 8)

    def _elapsed_ms(self, start_at: float) -> int:
        return max(1, int((time.perf_counter() - start_at) * 1000))

    async def _record_llm_call(
        self,
        *,
        user_id: Optional[int],
        project_id: Optional[str] = None,
        request_type: str,
        provider: str,
        model: Optional[str],
        status: str,
        latency_ms: Optional[int],
        input_chars: int,
        output_chars: int,
        estimated_input_tokens: int,
        estimated_output_tokens: int,
        finish_reason: Optional[str],
        error_type: Optional[str],
        error_message: Optional[str],
        commit: bool,
    ) -> None:
        """将调用观测数据写入数据库。失败时仅记录日志，不影响主流程。"""
        try:
            log = LLMCallLog(
                user_id=user_id,
                project_id=(project_id[:64] if project_id else None),
                request_type=request_type,
                provider=provider or "openai-compatible",
                model=model,
                status=status,
                latency_ms=latency_ms,
                input_chars=max(0, input_chars),
                output_chars=max(0, output_chars),
                estimated_input_tokens=max(0, estimated_input_tokens),
                estimated_output_tokens=max(0, estimated_output_tokens),
                estimated_cost_usd=self._estimate_cost_usd(model, estimated_input_tokens, estimated_output_tokens),
                finish_reason=finish_reason,
                error_type=error_type,
                error_message=(error_message or "")[:2000] or None,
            )
            self.session.add(log)
            await self.session.flush()
            if commit:
                await self.session.commit()
        except Exception as exc:  # pragma: no cover - 观测失败不应阻断主链路
            logger.warning("记录 LLM 调用日志失败: %s", exc, exc_info=True)
            try:
                await self.session.rollback()
            except Exception:
                pass
