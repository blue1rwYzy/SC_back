"""MinIO 配置"""
import os

# MinIO 连接配置
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "admin123456")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# 存储桶配置 (注意: MinIO 中使用连字符 -)
BUCKETS = {
    "models": "models",           # 模型文件
    "images": "images",           # 原始图片
    "img_results": "img-results", # 图片推理结果 (注意: 本地 img_results -> MinIO img-results)
    "videos": "videos",           # 视频文件
    "vid_results": "vid-results"  # 视频推理结果 (注意: 本地 vid_results -> MinIO vid-results)
}

# 是否启用 MinIO (方便切换)
USE_MINIO = os.getenv("USE_MINIO", "true").lower() == "true"
