# AIMETA P=管理员模式_管理API请求响应结构|R=用户管理_统计响应|NR=不含业务逻辑|E=AdminSchema|X=internal|A=Pydantic模式|D=pydantic|S=none|RD=./README.ai
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Statistics(BaseModel):
    novel_count: int
    user_count: int
    api_request_count: int


class DailyRequestLimit(BaseModel):
    limit: int = Field(..., ge=0, description="匿名用户每日可用次数")


class UpdateLogRead(BaseModel):
    id: int
    content: str
    created_at: datetime
    created_by: Optional[str] = None
    is_pinned: bool

    class Config:
        from_attributes = True


class UpdateLogBase(BaseModel):
    content: Optional[str] = None
    is_pinned: Optional[bool] = None


class UpdateLogCreate(UpdateLogBase):
    content: str


class UpdateLogUpdate(UpdateLogBase):
    pass


class AdminNovelSummary(BaseModel):
    id: str
    title: str
    owner_id: int
    owner_username: str
    genre: str
    last_edited: str
    completed_chapters: int
    total_chapters: int


class LLMCallLogRead(BaseModel):
    id: int
    user_id: Optional[int] = None
    project_id: Optional[str] = None
    request_type: str
    provider: str
    model: Optional[str] = None
    status: str
    latency_ms: Optional[int] = None
    input_chars: int
    output_chars: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: Optional[float] = None
    finish_reason: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LLMCallSummary(BaseModel):
    period_hours: int
    total_calls: int
    success_calls: int
    error_calls: int
    success_rate: float
    avg_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int
    total_estimated_cost_usd: float


class LLMGroupedTrendSeries(BaseModel):
    key: str
    total_calls: int
    points: list[int]


class LLMGroupedTrendResponse(BaseModel):
    period_hours: int
    group_by: str
    buckets: list[str]
    series: list[LLMGroupedTrendSeries]


class LLMErrorTopItem(BaseModel):
    error_type: str
    sample_message: str
    count: int
    latest_at: datetime


class LLMBudgetAlertItem(BaseModel):
    scope_type: str
    scope_key: str
    scope_label: str
    spent_usd: float
    limit_usd: float
    usage_ratio: float
    level: str
    is_alerting: bool


class LLMBudgetAlertResponse(BaseModel):
    generated_at: datetime
    warning_threshold: float
    critical_threshold: float
    global_alert: Optional[LLMBudgetAlertItem] = None
    users: list[LLMBudgetAlertItem]
    projects: list[LLMBudgetAlertItem]


class WriterTaskQueueItem(BaseModel):
    task_id: str
    task_type: str
    chapter_id: Optional[int] = None
    project_id: str
    project_title: str
    chapter_number: Optional[int] = None
    status: str
    queue_state: str
    owner_user_id: int
    owner_username: Optional[str] = None
    progress_percent: int
    stage_label: Optional[str] = None
    status_message: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int
    word_count: int = 0
    selected_version_id: Optional[int] = None
    heartbeat_at: Optional[datetime] = None
    heartbeat_age_seconds: Optional[int] = None
    updated_at: datetime
    age_minutes: int


class WriterTaskQueueSummary(BaseModel):
    queued_count: int
    running_count: int
    completed_count: int
    failed_count: int
    canceled_count: int
    stale_running_count: int
    avg_running_age_minutes: float
    recent_window_hours: int
    recent_finished_count: int
    recent_failed_count: int
    recent_failure_rate_percent: float
    recent_avg_duration_seconds: float
    recent_p95_duration_seconds: float


class WriterTaskFailureTopItem(BaseModel):
    error_key: str
    sample_message: str
    count: int


class WriterTaskQueueResponse(BaseModel):
    total: int
    status_group: str
    status_counts: dict[str, int]
    heartbeat_timeout_seconds: int
    summary: WriterTaskQueueSummary
    failure_top: list[WriterTaskFailureTopItem]
    items: list[WriterTaskQueueItem]


class WriterTaskRetryRequest(BaseModel):
    chapter_id: int = Field(..., ge=1)
    retry_mode: Literal["auto", "generate", "evaluate"] = "auto"
    writing_notes: Optional[str] = None
    force: bool = False


class WriterTaskRetryResponse(BaseModel):
    accepted: bool
    chapter_id: int
    project_id: str
    chapter_number: int
    previous_status: str
    dispatched_action: Literal["generate", "evaluate"]
    message: str
