"""
SQLAlchemy ORM 模型定义 - 共享模块
"""
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Text, BigInteger, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class Model(Base):
    """模型管理表"""
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    path = Column(String(500), nullable=False)
    version = Column(String(50), default="v1.0")
    description = Column(Text)
    model_type = Column(String(50), default="detection")  # detection/tracking
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ImageDatabase(Base):
    """图片数据库表"""
    __tablename__ = "image_database"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    path = Column(String(500), unique=True, nullable=False)
    url = Column(String(500))
    folder = Column(String(255), default="/", index=True)
    size = Column(BigInteger)
    mime_type = Column(String(50))
    width = Column(Integer)
    height = Column(Integer)
    is_folder = Column(Boolean, default=False)
    uploaded_at = Column(DateTime, default=datetime.now, index=True)


class InferenceTask(Base):
    """推理任务表"""
    __tablename__ = "inference_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(100), unique=True, nullable=False)
    model_id = Column(Integer, ForeignKey("models.id"))
    image_count = Column(Integer, default=0)
    status = Column(String(50), default="pending", index=True)  # pending/processing/completed/failed
    source_type = Column(String(50))  # upload/database/video
    result_path = Column(String(500))
    error_message = Column(Text)
    progress = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.now, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # 关系
    model = relationship("Model")


class InferenceResult(Base):
    """推理结果表（重构版）"""
    __tablename__ = "inference_results"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(100), index=True)  # 任务ID
    batch_name = Column(String(200), index=True)  # 批次名称（文件夹名，如 predict0）

    # 图片路径
    original_image = Column(Text, nullable=False)  # 原图路径（绝对路径）
    result_image = Column(Text, nullable=False)  # 结果图路径（绝对路径）
    original_image_rel = Column(Text)  # 原图相对路径
    result_image_rel = Column(Text)  # 结果图相对路径

    # 检测详情
    detections = Column(JSONB)  # 检测详情（JSON格式）
    detection_count = Column(Integer, default=0)  # 检测数量
    avg_confidence = Column(Float, default=0)  # 平均置信度

    # 严重程度
    severity_level = Column(Integer)  # 严重程度等级 1-5
    severity_score = Column(Float)  # 严重程度得分 0-100
    severity_text = Column(String(50))  # 严重程度文字
    severity_color = Column(String(50))  # 严重程度颜色

    # 图像信息
    image_width = Column(Integer)  # 图像宽度
    image_height = Column(Integer)  # 图像高度

    # 其他
    processing_time = Column(Float)  # 处理时间（秒）
    created_at = Column(DateTime, default=datetime.now, index=True)


class VideoTrackingTask(Base):
    """视频追踪任务表"""
    __tablename__ = "video_tracking_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(100), unique=True, nullable=False, index=True)
    model_id = Column(Integer, ForeignKey("models.id"))

    # 原始视频信息
    original_video_path = Column(String(500), nullable=False)  # 原视频完整路径
    original_video_name = Column(String(255), nullable=False)  # 原视频文件名
    original_video_relative_path = Column(String(500))  # 原视频相对路径（相对于uploads/videos）

    # 结果视频信息
    result_video_path = Column(String(500))  # 结果视频完整路径
    result_video_name = Column(String(255))  # 结果视频文件名
    result_video_relative_path = Column(String(500))  # 结果视频相对路径（相对于uploads/vid_results）

    # 任务状态
    status = Column(String(50), default="pending", index=True)  # pending/processing/completed/failed
    progress = Column(Float, default=0)
    error_message = Column(Text)

    # 统计信息
    total_frames = Column(Integer)
    processed_frames = Column(Integer, default=0)
    fps = Column(Float)
    duration = Column(Float)  # 视频时长（秒）

    # 时间戳
    created_at = Column(DateTime, default=datetime.now, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    # 关系
    model = relationship("Model")


class TrackingAnalysisReport(Base):
    """视频追踪分析报告表"""
    __tablename__ = "tracking_analysis_reports"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(100), index=True, nullable=False)
    report_type = Column(String(50), default="traffic")
    title = Column(String(255))
    video_name = Column(String(255))
    html_path = Column(String(500))
    html_url = Column(String(500))
    md_path = Column(String(500))
    md_url = Column(String(500))
    events_json_path = Column(String(500))
    events_json_url = Column(String(500))
    analysis_video_path = Column(String(500))
    analysis_video_url = Column(String(500))
    llm_enabled = Column(Boolean, default=False)
    vlm_enabled = Column(Boolean, default=False)
    summary = Column(JSONB)
    created_at = Column(DateTime, default=datetime.now, index=True)
