# AIMETA P=蓝图生成服务_同步与异步共享|R=对话整理_提示词生成_蓝图落库|NR=不含HTTP路由|E=generate_blueprint_for_project|X=internal|A=服务函数|D=llm,sqlalchemy|S=db,net|RD=./README.ai
from __future__ import annotations

import json
import logging
import os
from typing import Awaitable, Callable, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas.novel import Blueprint, BlueprintGenerationResponse
from ..services.llm_service import LLMService
from ..services.novel_service import NovelService
from ..services.prompt_service import PromptService
from ..utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)


def blueprint_completion_message() -> str:
    return "太棒了！我已经根据我们的对话整理出完整的小说蓝图。请确认是否进入写作阶段，或提出修改意见。"


def _ensure_prompt(prompt: str | None, name: str) -> str:
    if not prompt:
        raise HTTPException(status_code=500, detail=f"未配置名为 {name} 的提示词，请联系管理员")
    return prompt


def _resolve_blueprint_timeout_seconds() -> float:
    raw = os.getenv("BLUEPRINT_GENERATE_TIMEOUT_SECONDS", "420").strip()
    try:
        value = float(raw)
    except ValueError:
        return 420.0
    return max(60.0, min(540.0, value))


def _build_formatted_history(history_records: List) -> List[Dict[str, str]]:
    formatted_history: List[Dict[str, str]] = []
    for record in history_records:
        role = record.role
        content = record.content
        if not role or not content:
            continue
        try:
            normalized = unwrap_markdown_json(content)
            data = json.loads(normalized)
            if role == "user":
                user_value = data.get("value", data)
                if isinstance(user_value, str):
                    formatted_history.append({"role": "user", "content": user_value})
            elif role == "assistant":
                ai_message = data.get("ai_message") if isinstance(data, dict) else None
                if ai_message:
                    formatted_history.append({"role": "assistant", "content": ai_message})
        except (json.JSONDecodeError, AttributeError):
            continue
    return formatted_history


async def _emit_progress(
    callback: Optional[Callable[[int, str, str], Awaitable[None]]],
    *,
    progress: int,
    stage: str,
    message: str,
) -> None:
    if not callback:
        return
    await callback(progress, stage, message)


async def generate_blueprint_for_project(
    session: AsyncSession,
    *,
    project_id: str,
    user_id: int,
    progress_callback: Optional[Callable[[int, str, str], Awaitable[None]]] = None,
) -> BlueprintGenerationResponse:
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, user_id)
    logger.info("项目 %s 开始生成蓝图", project_id)

    history_records = await novel_service.list_conversations(project_id)
    if not history_records:
        logger.warning("项目 %s 缺少对话历史，无法生成蓝图", project_id)
        raise HTTPException(status_code=400, detail="缺少对话历史，请先完成概念对话后再生成蓝图")

    formatted_history = _build_formatted_history(history_records)
    if not formatted_history:
        logger.warning("项目 %s 对话历史格式异常，无法提取有效内容", project_id)
        raise HTTPException(
            status_code=400,
            detail="无法从历史对话中提取有效内容，请检查对话历史格式或重新进行概念对话",
        )

    await _emit_progress(
        progress_callback,
        progress=12,
        stage="准备上下文",
        message="正在整理概念对话内容",
    )

    project.status = "blueprint_generating"
    await session.commit()

    try:
        system_prompt = _ensure_prompt(await prompt_service.get_prompt("screenwriting"), "screenwriting")
        blueprint_timeout = _resolve_blueprint_timeout_seconds()

        await _emit_progress(
            progress_callback,
            progress=45,
            stage="AI生成蓝图",
            message="模型正在生成蓝图结构",
        )

        blueprint_raw = await llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=formatted_history,
            temperature=0.3,
            user_id=user_id,
            timeout=blueprint_timeout,
            project_id=project_id,
            request_type="blueprint",
            max_retries_override=0,
            allow_fallback_models=False,
        )
        blueprint_raw = remove_think_tags(blueprint_raw)

        await _emit_progress(
            progress_callback,
            progress=82,
            stage="解析与校验",
            message="正在解析蓝图并写入项目",
        )

        blueprint_normalized = unwrap_markdown_json(blueprint_raw)
        blueprint_sanitized = sanitize_json_like_text(blueprint_normalized)
        try:
            blueprint_data = json.loads(blueprint_sanitized)
        except json.JSONDecodeError as exc:
            logger.error(
                "项目 %s 蓝图生成 JSON 解析失败: %s\n原始响应: %s\n标准化后: %s\n清洗后: %s",
                project_id,
                exc,
                blueprint_raw[:500],
                blueprint_normalized[:500],
                blueprint_sanitized[:500],
            )
            raise HTTPException(
                status_code=500,
                detail=f"蓝图生成失败，AI 返回的内容格式不正确。请重试或联系管理员。错误详情: {str(exc)}",
            ) from exc

        blueprint = Blueprint(**blueprint_data)
        await novel_service.replace_blueprint(project_id, blueprint)
        if blueprint.title:
            project.title = blueprint.title
        project.status = "blueprint_ready"
        await session.commit()
        logger.info("项目 %s 蓝图生成完成并标记为 blueprint_ready", project_id)

        await _emit_progress(
            progress_callback,
            progress=100,
            stage="完成",
            message="蓝图生成完成",
        )

        return BlueprintGenerationResponse(
            blueprint=blueprint,
            ai_message=blueprint_completion_message(),
        )
    except Exception:
        project.status = "blueprint_failed"
        await session.commit()
        raise
