# AIMETA P=用户模式_用户和认证请求响应|R=用户结构_令牌结构|NR=不含业务逻辑|E=UserSchema_TokenSchema|X=internal|A=Pydantic模式|D=pydantic|S=none|RD=./README.ai
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """用户基础数据结构，供多处复用。"""

    username: str = Field(..., description="用户名")
    email: Optional[EmailStr] = Field(default=None, description="邮箱，可选")


class UserCreate(UserBase):
    """注册时使用的模型。"""

    password: str = Field(..., min_length=6, description="明文密码")


class UserUpdate(BaseModel):
    """用户信息修改模型。"""

    email: Optional[EmailStr] = Field(default=None, description="邮箱")
    password: Optional[str] = Field(default=None, min_length=6, description="新密码")


class UserCreateAdmin(UserCreate):
    """管理员创建用户模型。"""

    is_admin: bool = Field(default=False, description="是否为管理员")
    is_active: bool = Field(default=True, description="是否激活")


class UserUpdateAdmin(UserUpdate):
    """管理员更新用户信息模型。"""

    username: Optional[str] = Field(default=None, description="用户名")
    is_admin: Optional[bool] = Field(default=None, description="是否为管理员")
    is_active: Optional[bool] = Field(default=None, description="是否激活")


class User(UserBase):
    """对外暴露的用户信息。"""

    id: int = Field(..., description="用户主键")
    is_admin: bool = Field(default=False, description="是否为管理员")
    is_active: bool = Field(default=True, description="是否激活")
    must_change_password: bool = Field(default=False, description="是否需要强制修改密码")

    class Config:
        from_attributes = True


class UserInDB(User):
    """数据库内部使用的模型，包含哈希后的密码。"""

    hashed_password: str


class Token(BaseModel):
    """登录成功后返回的访问令牌。"""

    access_token: str
    token_type: str = "bearer"
    must_change_password: bool = Field(default=False, description="是否需要强制修改密码")


class TokenPayload(BaseModel):
    """JWT 负载信息。"""

    sub: str
    is_admin: bool = False


class UserRegistration(UserCreate):
    """注册接口需要的字段，包含邮箱验证码。"""

    verification_code: str = Field(..., min_length=4, max_length=10, description="邮箱验证码")


class PasswordChangeRequest(BaseModel):
    """管理员修改密码请求模型。"""

    old_password: str = Field(..., min_length=6, description="当前密码")
    new_password: str = Field(..., min_length=8, description="新密码")


class PasswordForgotRequest(BaseModel):
    """忘记密码 - 发送验证码请求。"""

    email: EmailStr = Field(..., description="注册邮箱")


class PasswordResetRequest(BaseModel):
    """忘记密码 - 使用验证码重置密码。"""

    email: EmailStr = Field(..., description="注册邮箱")
    verification_code: str = Field(..., min_length=4, max_length=10, description="邮箱验证码")
    new_password: str = Field(..., min_length=8, description="新密码")


class UserSubscriptionUpsert(BaseModel):
    """管理员设置用户订阅请求。"""

    plan_name: str = Field(default="basic", min_length=1, max_length=64, description="套餐名称")
    status: Literal["active", "inactive", "canceled"] = Field(default="active", description="订阅状态")
    starts_at: Optional[datetime] = Field(default=None, description="订阅开始时间")
    expires_at: Optional[datetime] = Field(default=None, description="订阅到期时间")


class UserSubscriptionRead(BaseModel):
    """用户订阅状态响应。"""

    user_id: int = Field(..., description="用户ID")
    plan_name: str = Field(..., description="套餐名称")
    status: str = Field(..., description="订阅状态")
    starts_at: Optional[datetime] = Field(default=None, description="订阅开始时间")
    expires_at: Optional[datetime] = Field(default=None, description="订阅到期时间")
    is_active: bool = Field(default=False, description="是否处于有效订阅期")


class UserSubscriptionAuditRead(BaseModel):
    """订阅审计日志响应。"""

    id: int = Field(..., description="日志ID")
    user_id: int = Field(..., description="用户ID")
    admin_user_id: Optional[int] = Field(default=None, description="操作管理员ID")
    admin_username: str = Field(..., description="操作管理员用户名")
    action: str = Field(..., description="操作类型")
    old_snapshot: str = Field(..., description="变更前快照(JSON)")
    new_snapshot: str = Field(..., description="变更后快照(JSON)")
    created_at: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True


class UserSubscriptionUsageSummaryRead(BaseModel):
    """用户订阅与当日额度使用摘要。"""

    user_id: int = Field(..., description="用户ID")
    plan_name: str = Field(..., description="套餐名称")
    status: str = Field(..., description="订阅状态")
    is_active: bool = Field(default=False, description="订阅是否有效")
    daily_request_used: int = Field(default=0, description="今日已用请求数")
    daily_request_limit: int = Field(default=0, description="今日请求上限（-1 表示无限）")
    daily_request_remaining: int = Field(default=0, description="今日剩余请求数（-1 表示无限）")
    daily_request_ratio: float = Field(default=0.0, description="请求额度使用率")
    today_estimated_cost_usd: float = Field(default=0.0, description="今日估算花费(USD)")
    daily_budget_limit_usd: float = Field(default=0.0, description="日预算上限(USD)")
    daily_budget_remaining_usd: float = Field(default=0.0, description="今日剩余预算(USD)，0 表示无限")
    daily_budget_ratio: float = Field(default=0.0, description="预算使用率")
    reset_at: datetime = Field(..., description="额度重置时间(UTC)")
    warning_level: Literal["ok", "warning", "critical", "exceeded"] = Field(
        default="ok",
        description="额度预警等级",
    )


class UserSubscriptionBillingItemRead(BaseModel):
    """订阅账单明细项（基于 LLM 调用日志）。"""

    id: int = Field(..., description="日志ID")
    created_at: datetime = Field(..., description="调用时间")
    project_id: Optional[str] = Field(default=None, description="项目ID")
    request_type: str = Field(..., description="请求类型")
    model: Optional[str] = Field(default=None, description="模型名称")
    status: str = Field(..., description="调用状态")
    estimated_input_tokens: int = Field(default=0, description="估算输入token")
    estimated_output_tokens: int = Field(default=0, description="估算输出token")
    estimated_cost_usd: float = Field(default=0.0, description="估算花费(USD)")
    latency_ms: Optional[int] = Field(default=None, description="耗时毫秒")


class UserSubscriptionBillingSummaryRead(BaseModel):
    """用户订阅账单摘要与明细。"""

    user_id: int = Field(..., description="用户ID")
    hours: int = Field(..., description="统计时间窗口(小时)")
    total_calls: int = Field(default=0, description="总调用次数")
    success_calls: int = Field(default=0, description="成功调用次数")
    total_estimated_cost_usd: float = Field(default=0.0, description="总估算花费(USD)")
    items: list[UserSubscriptionBillingItemRead] = Field(default_factory=list, description="明细记录")


class UserSubscriptionCompensationRequest(BaseModel):
    """管理员手动补偿请求额度。"""

    request_quota: int = Field(..., ge=1, le=100000, description="补偿请求次数")
    note: str = Field(..., min_length=2, max_length=500, description="补偿原因说明")


class UserSubscriptionCompensationRead(BaseModel):
    """管理员手动补偿结果。"""

    user_id: int = Field(..., description="用户ID")
    request_quota: int = Field(..., description="补偿请求次数")
    before_daily_request_used: int = Field(..., description="补偿前当日已用请求")
    after_daily_request_used: int = Field(..., description="补偿后当日已用请求")
    note: str = Field(..., description="补偿说明")
    operator: str = Field(..., description="操作人")
    created_at: datetime = Field(..., description="补偿时间")


class AuthOptions(BaseModel):
    """认证相关开关信息，供前端动态控制功能。"""

    allow_registration: bool = Field(..., description="是否允许开放用户注册")
    enable_linuxdo_login: bool = Field(..., description="是否启用 Linux.do 登录")
