from __future__ import annotations

from typing import Literal, Optional

FailureCategory = Literal[
    "timeout",
    "auth",
    "rate_limit",
    "network",
    "upstream",
    "config",
    "canceled",
    "unknown",
]

_TIMEOUT_TOKENS = (
    "timeout",
    "time out",
    "timed out",
    "deadline exceeded",
    "read timed out",
    "connect timeout",
    "超时",
    "网关超时",
)
_AUTH_TOKENS = (
    "unauthorized",
    "forbidden",
    "authentication",
    "invalid api key",
    "invalid key",
    "incorrect api key",
    "api key",
    "apikey",
    "token invalid",
    "token expired",
    "401",
    "403",
    "认证失败",
    "鉴权失败",
    "密钥无效",
)
_RATE_LIMIT_TOKENS = (
    "rate limit",
    "too many requests",
    "quota exceeded",
    "insufficient_quota",
    "429",
    "请求频率",
    "频率限制",
    "额度不足",
    "超出配额",
)
_NETWORK_TOKENS = (
    "connection refused",
    "connection reset",
    "connection error",
    "network error",
    "name or service not known",
    "temporary failure in name resolution",
    "dns",
    "ssl",
    "tls",
    "proxy error",
    "connect error",
    "read error",
    "断开连接",
    "连接失败",
    "网络异常",
)
_UPSTREAM_TOKENS = (
    "bad gateway",
    "service unavailable",
    "gateway time-out",
    "gateway timeout",
    "upstream",
    "502",
    "503",
    "504",
    "上游服务异常",
)
_CONFIG_TOKENS = (
    "not configured",
    "missing",
    "unknown model",
    "unsupported model",
    "invalid base url",
    "configuration",
    "配置错误",
    "未配置",
    "模型不存在",
    "参数错误",
)
_CANCELED_TOKENS = ("cancel", "canceled", "cancelled", "任务已取消", "取消任务")


def classify_task_failure(
    error_message: Optional[str],
    *,
    status_message: Optional[str] = None,
    stage_label: Optional[str] = None,
) -> FailureCategory:
    texts = [error_message or "", status_message or "", stage_label or ""]
    raw = " ".join(item.strip().lower() for item in texts if item and item.strip())
    if not raw:
        return "unknown"

    if any(token in raw for token in _CANCELED_TOKENS):
        return "canceled"
    if any(token in raw for token in _TIMEOUT_TOKENS):
        return "timeout"
    if any(token in raw for token in _AUTH_TOKENS):
        return "auth"
    if any(token in raw for token in _RATE_LIMIT_TOKENS):
        return "rate_limit"
    if any(token in raw for token in _NETWORK_TOKENS):
        return "network"
    if any(token in raw for token in _UPSTREAM_TOKENS):
        return "upstream"
    if any(token in raw for token in _CONFIG_TOKENS):
        return "config"

    return "unknown"


def failure_category_label(category: Optional[str]) -> str:
    mapping = {
        "timeout": "超时",
        "auth": "鉴权失败",
        "rate_limit": "限流/额度",
        "network": "网络异常",
        "upstream": "上游异常",
        "config": "配置错误",
        "canceled": "已取消",
        "unknown": "未知错误",
    }
    return mapping.get(str(category or "").strip().lower(), "未知错误")
