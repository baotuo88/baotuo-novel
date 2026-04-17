# AIMETA P=系统配置默认值_初始配置数据|R=默认配置字典|NR=不含配置逻辑|E=SYSTEM_CONFIG_DEFAULTS|X=internal|A=配置字典|D=none|S=none|RD=./README.ai
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..core.config import Settings


def _to_optional_str(value: Optional[object]) -> Optional[str]:
    return str(value) if value is not None else None


def _bool_to_text(value: bool) -> str:
    return "true" if value else "false"


@dataclass(frozen=True)
class SystemConfigDefault:
    key: str
    value_getter: Callable[[Settings], Optional[str]]
    description: Optional[str] = None


SYSTEM_CONFIG_DEFAULTS: list[SystemConfigDefault] = [
    SystemConfigDefault(
        key="llm.api_key",
        value_getter=lambda config: config.openai_api_key,
        description="默认 LLM API Key，用于后台调用大模型。",
    ),
    SystemConfigDefault(
        key="llm.base_url",
        value_getter=lambda config: _to_optional_str(config.openai_base_url),
        description="默认大模型 API Base URL。",
    ),
    SystemConfigDefault(
        key="llm.model",
        value_getter=lambda config: config.openai_model_name,
        description="默认 LLM 模型名称。",
    ),
    SystemConfigDefault(
        key="llm.retry.max_retries",
        value_getter=lambda _config: "1",
        description="LLM 请求失败后的重试次数（不含首次请求）。",
    ),
    SystemConfigDefault(
        key="llm.retry.backoff_ms",
        value_getter=lambda _config: "600",
        description="LLM 重试退避时间（毫秒），采用指数退避。",
    ),
    SystemConfigDefault(
        key="llm.fallback.models",
        value_getter=lambda _config: "gpt-4o-mini,gpt-4.1-mini",
        description="主模型失败后可自动回退的模型列表（逗号分隔）。",
    ),
    SystemConfigDefault(
        key="llm.budget.daily_usd.global",
        value_getter=lambda _config: "0",
        description="全局每日预算（USD），0 表示关闭。",
    ),
    SystemConfigDefault(
        key="llm.budget.daily_usd.user.default",
        value_getter=lambda _config: "0",
        description="默认用户每日预算（USD），0 表示关闭。可用 llm.budget.daily_usd.user.{user_id} 单独覆盖。",
    ),
    SystemConfigDefault(
        key="llm.budget.daily_usd.project.default",
        value_getter=lambda _config: "0",
        description="默认项目每日预算（USD），0 表示关闭。可用 llm.budget.daily_usd.project.{project_id} 单独覆盖。",
    ),
    SystemConfigDefault(
        key="llm.budget.circuit_mode",
        value_getter=lambda _config: "degrade",
        description="预算熔断策略：degrade=自动降级模型，block=直接拒绝请求。",
    ),
    SystemConfigDefault(
        key="llm.budget.degrade_model",
        value_getter=lambda _config: "gpt-4o-mini",
        description="预算熔断为 degrade 时使用的降级模型。",
    ),
    SystemConfigDefault(
        key="llm.budget.reserve_output_tokens",
        value_getter=lambda _config: "1200",
        description="预算预估时保留的输出 token 数，用于预判本次调用成本。",
    ),
    SystemConfigDefault(
        key="llm.budget.alert.thresholds",
        value_getter=lambda _config: "0.5,0.8,1.0",
        description="预算告警阈值（比例，逗号分隔），例如 0.5,0.8,1.0。",
    ),
    SystemConfigDefault(
        key="smtp.server",
        value_getter=lambda config: config.smtp_server,
        description="用于发送邮件验证码的 SMTP 服务器地址。",
    ),
    SystemConfigDefault(
        key="smtp.port",
        value_getter=lambda config: _to_optional_str(config.smtp_port),
        description="SMTP 服务端口。",
    ),
    SystemConfigDefault(
        key="smtp.username",
        value_getter=lambda config: config.smtp_username,
        description="SMTP 登录用户名。",
    ),
    SystemConfigDefault(
        key="smtp.password",
        value_getter=lambda config: config.smtp_password,
        description="SMTP 登录密码。",
    ),
    SystemConfigDefault(
        key="smtp.from",
        value_getter=lambda config: config.email_from,
        description="邮件显示的发件人名称或邮箱。",
    ),
    SystemConfigDefault(
        key="auth.allow_registration",
        value_getter=lambda config: _bool_to_text(config.allow_registration),
        description="是否允许用户自助注册。",
    ),
    SystemConfigDefault(
        key="auth.linuxdo_enabled",
        value_getter=lambda config: _bool_to_text(config.enable_linuxdo_login),
        description="是否启用 Linux.do OAuth 登录。",
    ),
    SystemConfigDefault(
        key="subscription.require_for_system_key",
        value_getter=lambda _config: "true",
        description="无自定义 API Key 时，是否必须存在有效订阅才允许使用系统默认 Key。",
    ),
    SystemConfigDefault(
        key="subscription.plan.basic.daily_request_limit",
        value_getter=lambda _config: "200",
        description="basic 套餐每日请求次数上限（仅系统 Key 生效）。",
    ),
    SystemConfigDefault(
        key="subscription.plan.basic.daily_budget_usd",
        value_getter=lambda _config: "0",
        description="basic 套餐每日预算上限（USD，0 表示不限制，仅系统 Key 生效）。",
    ),
    SystemConfigDefault(
        key="subscription.plan.pro.daily_request_limit",
        value_getter=lambda _config: "500",
        description="pro 套餐每日请求次数上限（仅系统 Key 生效）。",
    ),
    SystemConfigDefault(
        key="subscription.plan.pro.daily_budget_usd",
        value_getter=lambda _config: "5",
        description="pro 套餐每日预算上限（USD，仅系统 Key 生效）。",
    ),
    SystemConfigDefault(
        key="linuxdo.client_id",
        value_getter=lambda config: config.linuxdo_client_id,
        description="Linux.do OAuth Client ID。",
    ),
    SystemConfigDefault(
        key="linuxdo.client_secret",
        value_getter=lambda config: config.linuxdo_client_secret,
        description="Linux.do OAuth Client Secret。",
    ),
    SystemConfigDefault(
        key="linuxdo.redirect_uri",
        value_getter=lambda config: _to_optional_str(config.linuxdo_redirect_uri),
        description="Linux.do OAuth 回调地址。",
    ),
    SystemConfigDefault(
        key="linuxdo.auth_url",
        value_getter=lambda config: _to_optional_str(config.linuxdo_auth_url),
        description="Linux.do OAuth 授权地址。",
    ),
    SystemConfigDefault(
        key="linuxdo.token_url",
        value_getter=lambda config: _to_optional_str(config.linuxdo_token_url),
        description="Linux.do OAuth Token 获取地址。",
    ),
    SystemConfigDefault(
        key="linuxdo.user_info_url",
        value_getter=lambda config: _to_optional_str(config.linuxdo_user_info_url),
        description="Linux.do 用户信息接口地址。",
    ),
    SystemConfigDefault(
        key="writer.chapter_versions",
        value_getter=lambda config: _to_optional_str(config.writer_chapter_versions),
        description="每次生成章节的候选版本数量。",
    ),
    SystemConfigDefault(
        key="generation.task.worker_count",
        value_getter=lambda config: _to_optional_str(config.generation_task_workers),
        description="任务执行 worker 数量（运行中修改需重启服务生效）。",
    ),
    SystemConfigDefault(
        key="generation.task.heartbeat_interval_seconds",
        value_getter=lambda config: _to_optional_str(config.generation_task_heartbeat_interval_seconds),
        description="任务心跳写入间隔（秒）。",
    ),
    SystemConfigDefault(
        key="generation.task.stale_timeout_seconds",
        value_getter=lambda config: _to_optional_str(config.generation_task_stale_timeout_seconds),
        description="任务卡死判定阈值（秒）。",
    ),
    SystemConfigDefault(
        key="generation.task.stale_scan_interval_seconds",
        value_getter=lambda config: _to_optional_str(config.generation_task_stale_scan_interval_seconds),
        description="卡死任务扫描周期（秒）。",
    ),
    SystemConfigDefault(
        key="generation.task.chapter_timeout_seconds",
        value_getter=lambda config: _to_optional_str(config.generation_task_chapter_timeout_seconds),
        description="章节生成任务超时时间（秒）。",
    ),
    SystemConfigDefault(
        key="generation.task.blueprint_timeout_seconds",
        value_getter=lambda config: _to_optional_str(config.generation_task_blueprint_timeout_seconds),
        description="蓝图生成任务超时时间（秒）。",
    ),
    SystemConfigDefault(
        key="generation.task.auto_retry_max",
        value_getter=lambda config: _to_optional_str(config.generation_task_auto_retry_max),
        description="任务失败后自动重试上限。",
    ),
    SystemConfigDefault(
        key="generation.task.retry_backoff_base_seconds",
        value_getter=lambda config: _to_optional_str(config.generation_task_retry_backoff_base_seconds),
        description="自动重试基础退避时间（秒）。",
    ),
    SystemConfigDefault(
        key="generation.task.retry_backoff_max_seconds",
        value_getter=lambda config: _to_optional_str(config.generation_task_retry_backoff_max_seconds),
        description="自动重试最大退避时间（秒）。",
    ),
    SystemConfigDefault(
        key="generation.task.policy_refresh_interval_seconds",
        value_getter=lambda config: _to_optional_str(config.generation_task_policy_refresh_interval_seconds),
        description="任务策略热更新刷新周期（秒）。",
    ),
    SystemConfigDefault(
        key="embedding.provider",
        value_getter=lambda config: config.embedding_provider,
        description="嵌入模型提供方，支持 openai 或 ollama。",
    ),
    SystemConfigDefault(
        key="embedding.api_key",
        value_getter=lambda config: config.embedding_api_key,
        description="嵌入模型专用 API Key，留空则使用默认 LLM API Key。",
    ),
    SystemConfigDefault(
        key="embedding.base_url",
        value_getter=lambda config: _to_optional_str(config.embedding_base_url),
        description="嵌入模型使用的 Base URL，留空则使用默认 LLM Base URL。",
    ),
    SystemConfigDefault(
        key="embedding.model",
        value_getter=lambda config: config.embedding_model,
        description="OpenAI 嵌入模型名称。",
    ),
    SystemConfigDefault(
        key="embedding.model_vector_size",
        value_getter=lambda config: _to_optional_str(config.embedding_model_vector_size),
        description="嵌入向量维度，留空则自动检测。",
    ),
    SystemConfigDefault(
        key="ollama.embedding_base_url",
        value_getter=lambda config: _to_optional_str(config.ollama_embedding_base_url),
        description="Ollama 嵌入模型服务地址。",
    ),
    SystemConfigDefault(
        key="ollama.embedding_model",
        value_getter=lambda config: config.ollama_embedding_model,
        description="Ollama 嵌入模型名称。",
    ),
]
