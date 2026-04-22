# AIMETA P=提示词模式_提示模板请求响应|R=提示词结构|NR=不含业务逻辑|E=PromptSchema|X=internal|A=Pydantic模式|D=pydantic|S=none|RD=./README.ai
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PromptBase(BaseModel):
    """Prompt 基础模型。"""

    name: str = Field(..., description="唯一标识，用于代码引用")
    title: Optional[str] = Field(default=None, description="可读标题")
    content: str = Field(..., description="提示词具体内容")
    tags: Optional[List[str]] = Field(default=None, description="标签集合")


class PromptCreate(PromptBase):
    """创建 Prompt 时使用的模型。"""

    pass


class PromptUpdate(BaseModel):
    """更新 Prompt 时使用的模型。"""

    title: Optional[str] = Field(default=None)
    content: Optional[str] = Field(default=None)
    tags: Optional[List[str]] = Field(default=None)


class PromptRead(PromptBase):
    """对外暴露的 Prompt 数据结构。"""

    id: int
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def model_validate(cls, obj: Any, *args: Any, **kwargs: Any) -> "PromptRead":  # type: ignore[override]
        """在转换 ORM 模型时，将字符串标签拆分为列表。"""
        if hasattr(obj, "id") and hasattr(obj, "name"):
            raw_tags = getattr(obj, "tags", None)
            if isinstance(raw_tags, str):
                processed = [tag for tag in raw_tags.split(",") if tag]
            elif isinstance(raw_tags, list):
                processed = raw_tags
            else:
                processed = None
            data = {
                "id": getattr(obj, "id"),
                "name": getattr(obj, "name"),
                "title": getattr(obj, "title", None),
                "content": getattr(obj, "content", None),
                "tags": processed,
            }
            return super().model_validate(data, *args, **kwargs)
        return super().model_validate(obj, *args, **kwargs)


class WritingPresetBase(BaseModel):
    """写作预设基础结构。"""

    preset_id: str = Field(..., min_length=2, max_length=32, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(default=None, max_length=255)
    prompt_name: str = Field(default="writing_v2", min_length=1, max_length=64)
    temperature: float = Field(default=0.9, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=None, ge=64, le=32000)
    style_rules: List[str] = Field(default_factory=list)
    writing_notes_prefix: Optional[str] = Field(default=None, max_length=2000)


class WritingPresetUpsert(WritingPresetBase):
    pass


class WritingPresetRead(WritingPresetBase):
    is_builtin: bool = False
    is_active: bool = False


class WritingPresetActivateRequest(BaseModel):
    preset_id: Optional[str] = Field(default=None, min_length=2, max_length=32)
