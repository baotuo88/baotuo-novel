# AIMETA P=任务告警服务_失败超时通知|R=任务失败告警发送|NR=不含任务执行|E=GenerationAlertService|X=internal|A=服务类|D=smtplib,httpx|S=net,db|RD=./README.ai
from __future__ import annotations

import asyncio
import logging
import smtplib
import time
from dataclasses import dataclass
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.system_config import SystemConfig

logger = logging.getLogger(__name__)

_ALERT_COOLDOWN_CACHE: dict[str, float] = {}


@dataclass(frozen=True)
class GenerationAlertPolicy:
    enabled: bool
    webhook_url: str
    webhook_timeout_seconds: float
    email_to: str
    smtp_subject_prefix: str
    cooldown_seconds: int
    failure_rate_threshold_percent: float
    stale_running_threshold: int
    queue_backlog_threshold: int


class GenerationAlertService:
    _DEFAULTS = {
        "generation.alert.enabled": "true",
        "generation.alert.webhook_url": "",
        "generation.alert.webhook_timeout_seconds": "6",
        "generation.alert.email_to": "",
        "generation.alert.smtp_subject_prefix": "[宝拓小说]",
        "generation.alert.cooldown_seconds": "600",
        "generation.alert.failure_rate_threshold_percent": "20",
        "generation.alert.stale_running_threshold": "1",
        "generation.alert.queue_backlog_threshold": "50",
    }

    _SMTP_KEYS = [
        "smtp.server",
        "smtp.port",
        "smtp.username",
        "smtp.password",
        "smtp.from",
    ]

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _parse_bool(raw: Any, default: bool) -> bool:
        if raw is None:
            return default
        normalized = str(raw).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default

    @staticmethod
    def _parse_int(raw: Any, *, default: int, min_value: int, max_value: int) -> int:
        try:
            value = int(str(raw).strip()) if raw is not None else default
        except Exception:
            value = default
        return max(min_value, min(max_value, value))

    @staticmethod
    def _parse_float(raw: Any, *, default: float, min_value: float, max_value: float) -> float:
        try:
            value = float(str(raw).strip()) if raw is not None else default
        except Exception:
            value = default
        return max(min_value, min(max_value, value))

    async def _load_config_map(self, keys: list[str]) -> dict[str, str]:
        rows = (
            await self.session.execute(
                select(SystemConfig.key, SystemConfig.value).where(SystemConfig.key.in_(keys))
            )
        ).all()
        return {str(key): str(value or "") for key, value in rows}

    async def _load_smtp_config(self) -> Optional[dict[str, str]]:
        config_map = await self._load_config_map(self._SMTP_KEYS)
        if any(not config_map.get(key, "").strip() for key in self._SMTP_KEYS):
            return None
        return config_map

    async def load_policy(self) -> GenerationAlertPolicy:
        keys = list(self._DEFAULTS.keys())
        config_map = await self._load_config_map(keys)

        def value_of(key: str) -> str:
            raw = config_map.get(key)
            if raw is None:
                return self._DEFAULTS[key]
            return str(raw).strip()

        return GenerationAlertPolicy(
            enabled=self._parse_bool(value_of("generation.alert.enabled"), True),
            webhook_url=value_of("generation.alert.webhook_url"),
            webhook_timeout_seconds=self._parse_float(
                value_of("generation.alert.webhook_timeout_seconds"),
                default=6.0,
                min_value=1.0,
                max_value=30.0,
            ),
            email_to=value_of("generation.alert.email_to"),
            smtp_subject_prefix=value_of("generation.alert.smtp_subject_prefix") or "[宝拓小说]",
            cooldown_seconds=self._parse_int(
                value_of("generation.alert.cooldown_seconds"),
                default=600,
                min_value=0,
                max_value=24 * 3600,
            ),
            failure_rate_threshold_percent=self._parse_float(
                value_of("generation.alert.failure_rate_threshold_percent"),
                default=20.0,
                min_value=0.0,
                max_value=100.0,
            ),
            stale_running_threshold=self._parse_int(
                value_of("generation.alert.stale_running_threshold"),
                default=1,
                min_value=0,
                max_value=10000,
            ),
            queue_backlog_threshold=self._parse_int(
                value_of("generation.alert.queue_backlog_threshold"),
                default=50,
                min_value=0,
                max_value=10000,
            ),
        )

    async def _send_webhook(self, *, webhook_url: str, payload: dict[str, Any], timeout_seconds: float) -> None:
        url = str(webhook_url or "").strip()
        if not url:
            return
        async with httpx.AsyncClient(timeout=max(1.0, float(timeout_seconds))) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

    async def _send_email(self, *, to_email: str, subject: str, content: str) -> None:
        smtp_config = await self._load_smtp_config()
        if not smtp_config:
            raise RuntimeError("SMTP 配置不完整")

        server = smtp_config["smtp.server"].strip()
        port = self._parse_int(smtp_config.get("smtp.port"), default=465, min_value=1, max_value=65535)
        username = smtp_config["smtp.username"].strip()
        password = smtp_config["smtp.password"]
        from_value = (smtp_config.get("smtp.from") or username).strip() or username

        display_name, from_addr = parseaddr(from_value)
        if not from_addr or "@" not in from_addr:
            from_addr = username
        if display_name:
            formatted_from = formataddr((Header(display_name, "utf-8").encode(), from_addr))
        else:
            formatted_from = from_addr

        message = MIMEText(content, "plain", "utf-8")
        message["Subject"] = Header(subject, "utf-8").encode()
        message["From"] = formatted_from
        message["To"] = to_email

        def _send() -> None:
            smtp: Optional[smtplib.SMTP] = None
            try:
                if port == 465:
                    smtp = smtplib.SMTP_SSL(server, port, timeout=10)
                else:
                    smtp = smtplib.SMTP(server, port, timeout=10)
                    smtp.starttls()
                if username and password:
                    smtp.login(username, password)
                smtp.sendmail(from_addr, [to_email], message.as_string())
            finally:
                if smtp is not None:
                    try:
                        smtp.quit()
                    except Exception:
                        pass

        await asyncio.to_thread(_send)

    async def notify_task_failure(
        self,
        *,
        task_id: str,
        task_type: str,
        project_id: str,
        chapter_number: Optional[int],
        user_id: Optional[int],
        stage_label: str,
        error_message: str,
        request_id: Optional[str],
    ) -> dict[str, Any]:
        policy = await self.load_policy()
        if not policy.enabled:
            return {"sent": False, "reason": "disabled"}

        chapter_fragment = f":{chapter_number}" if chapter_number is not None else ""
        error_key = str(error_message or "").strip().splitlines()[0][:120]
        fingerprint = f"{task_type}:{project_id}{chapter_fragment}:{error_key}"
        now = time.time()
        last_sent = _ALERT_COOLDOWN_CACHE.get(fingerprint)
        if last_sent and policy.cooldown_seconds > 0 and (now - last_sent) < policy.cooldown_seconds:
            return {"sent": False, "reason": "cooldown"}

        stage_value = str(stage_label or "").strip() or "执行失败"
        error_value = str(error_message or "").strip() or "未知错误"
        request_value = str(request_id or "").strip() or "-"
        subject = f"{policy.smtp_subject_prefix} 任务失败告警: {task_type}"
        lines = [
            "检测到生成任务失败，请及时处理：",
            f"- task_id: {task_id}",
            f"- task_type: {task_type}",
            f"- project_id: {project_id}",
            f"- chapter_number: {chapter_number if chapter_number is not None else '-'}",
            f"- user_id: {user_id if user_id is not None else '-'}",
            f"- stage: {stage_value}",
            f"- request_id: {request_value}",
            f"- error: {error_value}",
            f"- occurred_at: {datetime.utcnow().isoformat()}",
        ]
        content = "\n".join(lines)

        sent_channels: list[str] = []
        channel_errors: list[str] = []

        if policy.webhook_url:
            payload = {
                "event": "generation.task.failed",
                "task_id": task_id,
                "task_type": task_type,
                "project_id": project_id,
                "chapter_number": chapter_number,
                "user_id": user_id,
                "stage_label": stage_value,
                "error_message": error_value,
                "request_id": request_value,
                "occurred_at": datetime.utcnow().isoformat(),
            }
            try:
                await self._send_webhook(
                    webhook_url=policy.webhook_url,
                    payload=payload,
                    timeout_seconds=policy.webhook_timeout_seconds,
                )
                sent_channels.append("webhook")
            except Exception as exc:
                channel_errors.append(f"webhook: {str(exc)[:180]}")
                logger.warning(
                    "任务失败告警 webhook 发送失败: task=%s project=%s error=%s",
                    task_id,
                    project_id,
                    exc,
                )

        if policy.email_to:
            try:
                await self._send_email(
                    to_email=policy.email_to,
                    subject=subject,
                    content=content,
                )
                sent_channels.append("email")
            except Exception as exc:
                channel_errors.append(f"email: {str(exc)[:180]}")
                logger.warning(
                    "任务失败告警邮件发送失败: task=%s project=%s error=%s",
                    task_id,
                    project_id,
                    exc,
                )

        if sent_channels:
            _ALERT_COOLDOWN_CACHE[fingerprint] = now
            return {"sent": True, "channels": sent_channels, "errors": channel_errors}
        if channel_errors:
            return {"sent": False, "reason": "send_failed", "errors": channel_errors}
        return {"sent": False, "reason": "no_channel"}
