"""
Pydantic 数据模型 - 共享模块
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ============ 模型相关 ============
class ModelBase(BaseModel):
    name: str
    path: str
    version: Optional[str] = "v1.0"
    description: Optional[str] = None
    model_type: Optional[str] = "detection"


class ModelCreate(ModelBase):
    pass


class ModelResponse(ModelBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ 图片数据库相关 ============
class ImageDatabaseBase(BaseModel):
    filename: str
    path: str
    folder: Optional[str] = "/"
    size: Optional[int] = None
    mime_type: Optional[str] = None


class ImageDatabaseCreate(ImageDatabaseBase):
    pass


class ImageDatabaseResponse(ImageDatabaseBase):
    id: int
    url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    is_folder: bool = False
    uploaded_at: datetime

    class Config:
        from_attributes = True


# ============ 检测结果相关 ============
class DetectionItem(BaseModel):
    """单个检测对象"""
    bbox: List[float] = Field(..., description="边界框 [x, y, w, h]")
    class_name: str = Field(..., alias="class", description="类别名称")
    confidence: float = Field(..., description="置信度")
    severity: Optional[str] = Field(None, description="严重程度")

    class Config:
        populate_by_name = True


class InferenceResultBase(BaseModel):
    original_image: str
    result_image: str
    detections: List[DetectionItem]
    confidence: float


class InferenceResultResponse(InferenceResultBase):
    id: int
    task_id: str
    processing_time: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============ 推理任务相关 ============
class InferenceTaskBase(BaseModel):
    model_id: int
    image_count: Optional[int] = 0
    source_type: Optional[str] = None


class InferenceTaskCreate(InferenceTaskBase):
    pass


class InferenceTaskResponse(InferenceTaskBase):
    id: int
    task_id: str
    status: str
    result_path: Optional[str] = None
    error_message: Optional[str] = None
    progress: float = 0
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============ API 请求相关 ============
class SingleInferenceRequest(BaseModel):
    """单张图片推理请求"""
    model_id: int


class BatchInferenceRequest(BaseModel):
    """批量推理请求"""
    model_id: int


class DatabaseInferenceRequest(BaseModel):
    """数据库图片推理请求"""
    model_id: int = Field(..., alias="modelId")
    image_ids: Optional[List[str]] = Field(None, alias="imageIds")  # 修改为字符串列表，包含完整文件路径
    folder_path: Optional[str] = Field(None, alias="folderPath")

    class Config:
        populate_by_name = True


# ============ 通用响应 ============
from typing import Any

class ResponseModel(BaseModel):
    """统一响应格式"""
    code: int = 0
    data: Optional[Any] = None
    message: str = "success"
