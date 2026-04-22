# AIMETA P=LLM配置模式_模型配置请求响应|R=LLM配置结构|NR=不含业务逻辑|E=LLMConfigSchema|X=internal|A=Pydantic模式|D=pydantic|S=none|RD=./README.ai
from typing import Optional

from pydantic import BaseModel, ConfigDict, HttpUrl, Field


class LLMConfigBase(BaseModel):
    llm_provider_url: Optional[HttpUrl] = Field(default=None, description="自定义 LLM 服务地址")
    llm_provider_api_key: Optional[str] = Field(default=None, description="自定义 LLM API Key")
    llm_provider_model: Optional[str] = Field(default=None, description="自定义模型名称")


class LLMConfigCreate(LLMConfigBase):
    pass


class LLMConfigRead(LLMConfigBase):
    user_id: int
    model_config = ConfigDict(from_attributes=True)


class ModelListRequest(BaseModel):
    llm_provider_url: Optional[str] = Field(default=None, description="LLM 服务地址")
    llm_provider_api_key: str = Field(..., description="LLM API Key")


class LLMConnectionTestRequest(BaseModel):
    llm_provider_url: Optional[str] = Field(default=None, description="LLM 服务地址")
    llm_provider_api_key: str = Field(..., description="LLM API Key")
    llm_provider_model: Optional[str] = Field(default=None, description="待验证模型（可选）")


class LLMConnectionTestResult(BaseModel):
    success: bool = Field(..., description="连接验证是否成功")
    provider: str = Field(..., description="识别到的提供商")
    message: str = Field(..., description="验证结果说明")
    latency_ms: Optional[int] = Field(default=None, description="请求耗时（毫秒）")
    model_count: int = Field(default=0, description="返回模型数量")
    sample_models: list[str] = Field(default_factory=list, description="示例模型列表")
