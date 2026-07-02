"""
MinIO 对象存储工具类
提供文件上传、下载、删除等功能
"""
from minio import Minio
from minio.error import S3Error
from io import BytesIO
import os
from typing import Optional, BinaryIO
from datetime import timedelta

class MinIOClient:
    """MinIO 客户端封装"""

    def __init__(
        self,
        endpoint: str = "localhost:51036",
        access_key: str = "admin",
        secret_key: str = "admin123456",
        secure: bool = False
    ):
        """
        初始化 MinIO 客户端

        Args:
            endpoint: MinIO 服务地址
            access_key: 访问密钥
            secret_key: 密钥
            secure: 是否使用 HTTPS
        """
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        self.endpoint = endpoint
        self.secure = secure

    def ensure_bucket(self, bucket_name: str):
        """确保存储桶存在,不存在则创建"""
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                print(f"✅ 创建存储桶: {bucket_name}")
        except S3Error as e:
            print(f"❌ 存储桶操作失败: {e}")
            raise

    def upload_file(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str = None,
        file_data: BinaryIO = None,
        content_type: str = "application/octet-stream"
    ) -> bool:
        """
        上传文件到 MinIO

        Args:
            bucket_name: 存储桶名称
            object_name: 对象名称 (路径)
            file_path: 本地文件路径
            file_data: 文件数据流
            content_type: 文件MIME类型

        Returns:
            上传是否成功
        """
        try:
            self.ensure_bucket(bucket_name)

            if file_path:
                # 从文件路径上传
                self.client.fput_object(
                    bucket_name=bucket_name,
                    object_name=object_name,
                    file_path=file_path,
                    content_type=content_type
                )
            elif file_data:
                # 从数据流上传
                file_data.seek(0, 2)  # 移到末尾获取大小
                file_size = file_data.tell()
                file_data.seek(0)  # 回到开头

                self.client.put_object(
                    bucket_name=bucket_name,
                    object_name=object_name,
                    data=file_data,
                    length=file_size,
                    content_type=content_type
                )
            else:
                raise ValueError("必须提供 file_path 或 file_data")

            return True

        except S3Error as e:
            print(f"❌ 上传失败: {e}")
            return False

    def download_file(
        self,
        bucket_name: str,
        object_name: str,
        file_path: str = None
    ) -> Optional[bytes]:
        """
        从 MinIO 下载文件

        Args:
            bucket_name: 存储桶名称
            object_name: 对象名称
            file_path: 保存路径(可选,不提供则返回字节数据)

        Returns:
            文件字节数据 或 None
        """
        try:
            if file_path:
                # 下载到文件
                self.client.fget_object(
                    bucket_name=bucket_name,
                    object_name=object_name,
                    file_path=file_path
                )
                return None
            else:
                # 返回字节数据
                response = self.client.get_object(
                    bucket_name=bucket_name,
                    object_name=object_name
                )
                data = response.read()
                response.close()
                response.release_conn()
                return data

        except S3Error as e:
            print(f"❌ 下载失败: {e}")
            return None

    def delete_file(self, bucket_name: str, object_name: str) -> bool:
        """
        删除文件

        Args:
            bucket_name: 存储桶名称
            object_name: 对象名称

        Returns:
            删除是否成功
        """
        try:
            self.client.remove_object(
                bucket_name=bucket_name,
                object_name=object_name
            )
            return True

        except S3Error as e:
            print(f"❌ 删除失败: {e}")
            return False

    def list_objects(
        self,
        bucket_name: str,
        prefix: str = None,
        recursive: bool = True
    ) -> list:
        """
        列出对象 (返回完整对象信息)

        Args:
            bucket_name: 存储桶名称
            prefix: 对象前缀 (None 表示所有对象)
            recursive: 是否递归

        Returns:
            对象列表 (包含 object_name, size, last_modified 等信息)
        """
        try:
            objects = self.client.list_objects(
                bucket_name=bucket_name,
                prefix=prefix if prefix else "",
                recursive=recursive
            )
            # 返回完整的对象信息
            return list(objects)

        except S3Error as e:
            print(f"❌ 列出对象失败: {e}")
            return []

    def get_presigned_url(
        self,
        bucket_name: str,
        object_name: str,
        expires: timedelta = timedelta(hours=1)
    ) -> Optional[str]:
        """
        生成预签名 URL (临时访问链接)

        Args:
            bucket_name: 存储桶名称
            object_name: 对象名称
            expires: 过期时间

        Returns:
            预签名 URL
        """
        try:
            url = self.client.presigned_get_object(
                bucket_name=bucket_name,
                object_name=object_name,
                expires=expires
            )
            return url

        except S3Error as e:
            print(f"❌ 生成URL失败: {e}")
            return None

    def file_exists(self, bucket_name: str, object_name: str) -> bool:
        """检查文件是否存在"""
        try:
            self.client.stat_object(bucket_name, object_name)
            return True
        except:
            return False

    def get_file_stream(self, bucket_name: str, object_name: str):
        """直接从 MinIO 获取文件流，用于后端代理返回给浏览器"""
        try:
            stat = self.client.stat_object(bucket_name, object_name)
            response = self.client.get_object(bucket_name, object_name)
            return response, stat.content_type or "application/octet-stream", stat.size
        except Exception as e:
            print(f"❌ 获取文件流失败: {e}", flush=True)
            return None


# 全局单例
minio_client = MinIOClient(
    endpoint=os.getenv("MINIO_ENDPOINT", "localhost:51036"),
    access_key=os.getenv("MINIO_ACCESS_KEY", "admin"),
    secret_key=os.getenv("MINIO_SECRET_KEY", "admin123456"),
    secure=os.getenv("MINIO_SECURE", "false").lower() == "true"
)
