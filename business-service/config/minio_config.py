"""MinIO 配置 - 生产环境专用对象存储"""
import os

# MinIO 连接配置
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "admin123456")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# 存储桶配置
# 重要：MinIO bucket 名称使用连字符 (img-results, vid-results)
BUCKETS = {
    "models": "models",           # 模型文件
    "images": "images",           # 原始图片
    "img_results": "img-results", # 图片推理结果 ⚠️ bucket 名称: img-results (连字符)
    "videos": "videos",           # 视频文件
    "vid_results": "vid-results"  # 视频推理结果 ⚠️ bucket 名称: vid-results (连字符)
}
