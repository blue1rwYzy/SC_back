# MinIO 对象存储迁移方案

## 📊 可行性分析

### 当前存储情况

**存储位置**: `G:\ShuangChuang\ShuangC\backend\uploads`

**存储内容统计**:
- 文件总数: **1061** 个
- 占用空间: **2.1 GB**
- 主要目录:
  - `images/` - 原始图片
  - `results/` - 推理结果
  - `videos/` - 视频文件
  - `vid_results/` - 视频推理结果

**涉及的功能模块**:
1. 模型文件上传/下载
2. 图片上传/查看/删除
3. 图片ZIP批量上传
4. 推理结果存储
5. 视频上传/追踪
6. 视频推理结果

### MinIO 优势

✅ **可行性: 非常高 (推荐迁移)**

**优势**:
1. ✅ **分布式存储**: 支持横向扩展,突破单机磁盘限制
2. ✅ **S3 兼容**: 与 AWS S3 API 完全兼容,生态丰富
3. ✅ **高可用**: 支持数据备份、冗余、容灾
4. ✅ **访问控制**: 精细的权限管理和访问策略
5. ✅ **版本控制**: 支持对象版本管理
6. ✅ **跨平台**: 支持 Windows/Linux/Docker 部署
7. ✅ **Web 界面**: 自带管理界面,方便管理
8. ✅ **成本优势**: 开源免费,相比云存储成本低

**适用场景**:
- ✅ 文件数量大 (当前 1061 个,未来可能增长)
- ✅ 多类型文件 (图片、视频、模型文件)
- ✅ 需要远程访问
- ✅ 未来可能部署到云端或多服务器
- ✅ 需要专业的对象存储服务

### 迁移成本评估

**开发成本**: 中等
- 预计开发时间: 4-8 小时
- 需要修改的文件: 约 3-5 个
- 代码改动量: 约 300-500 行

**运维成本**: 低
- MinIO 部署简单 (Docker 一键部署)
- 配置简单,维护方便

**风险评估**: 低
- MinIO 成熟稳定,社区活跃
- Python SDK 完善 (boto3/minio)
- 可以保留原有磁盘存储作为备份

---

## 🚀 MinIO 迁移完整教程

### 阶段一: MinIO 服务部署

#### 方案 A: Docker 部署 (推荐)

**1. 安装 Docker Desktop** (Windows)
- 下载: https://www.docker.com/products/docker-desktop
- 安装并启动 Docker Desktop

**2. 部署 MinIO**

创建 `docker-compose.yml`:

```yaml
version: '3.8'

services:
  minio:
    image: minio/minio:latest
    container_name: minio
    ports:
      - "9000:9000"      # API 端口
      - "9001:9001"      # Web Console 端口
    environment:
      MINIO_ROOT_USER: admin             # 管理员用户名
      MINIO_ROOT_PASSWORD: admin123456   # 管理员密码 (至少8位)
    volumes:
      - G:\ShuangChuang\ShuangC\minio\data:/data
    command: server /data --console-address ":9001"
    restart: always
```

启动 MinIO:
```bash
cd G:\ShuangChuang\ShuangC\backend\business-service
docker-compose up -d
```

**3. 访问 MinIO 控制台**
- URL: http://localhost:9001
- 用户名: admin
- 密码: admin123456

**4. 创建存储桶 (Bucket)**

登录后创建以下 Bucket:
- `models` - 存储模型文件
- `images` - 存储原始图片
- `results` - 存储推理结果
- `videos` - 存储视频文件
- `vid-results` - 存储视频推理结果

#### 方案 B: Windows 原生部署

```bash
# 下载 MinIO
curl https://dl.min.io/server/minio/release/windows-amd64/minio.exe -O

# 创建数据目录
mkdir G:\ShuangChuang\ShuangC\minio\data

# 设置环境变量
set MINIO_ROOT_USER=admin
set MINIO_ROOT_PASSWORD=admin123456

# 启动 MinIO
minio.exe server G:\ShuangChuang\ShuangC\minio\data --console-address ":9001"
```

---

### 阶段二: Python 代码集成

#### 1. 安装依赖

```bash
conda activate backendJC
pip install minio boto3
```

#### 2. 创建 MinIO 工具类

创建文件 `utils/minio_client.py`:

```python
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
        endpoint: str = "localhost:9000",
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

            print(f"✅ 上传成功: {bucket_name}/{object_name}")
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
                print(f"✅ 下载成功: {bucket_name}/{object_name} -> {file_path}")
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
            print(f"✅ 删除成功: {bucket_name}/{object_name}")
            return True

        except S3Error as e:
            print(f"❌ 删除失败: {e}")
            return False

    def list_objects(
        self,
        bucket_name: str,
        prefix: str = "",
        recursive: bool = True
    ) -> list:
        """
        列出对象

        Args:
            bucket_name: 存储桶名称
            prefix: 对象前缀
            recursive: 是否递归

        Returns:
            对象列表
        """
        try:
            objects = self.client.list_objects(
                bucket_name=bucket_name,
                prefix=prefix,
                recursive=recursive
            )
            return [obj.object_name for obj in objects]

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


# 全局单例
minio_client = MinIOClient(
    endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
    access_key=os.getenv("MINIO_ACCESS_KEY", "admin"),
    secret_key=os.getenv("MINIO_SECRET_KEY", "admin123456"),
    secure=os.getenv("MINIO_SECURE", "false").lower() == "true"
)
```

#### 3. 修改配置文件

创建 `config/minio_config.py`:

```python
"""MinIO 配置"""
import os

# MinIO 连接配置
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "admin123456")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# 存储桶配置
BUCKETS = {
    "models": "models",        # 模型文件
    "images": "images",        # 原始图片
    "results": "results",      # 推理结果
    "videos": "videos",        # 视频文件
    "vid_results": "vid-results"  # 视频推理结果
}

# 是否启用 MinIO (方便切换)
USE_MINIO = os.getenv("USE_MINIO", "true").lower() == "true"
```

#### 4. 修改上传接口

修改 `main.py` 中的上传函数:

```python
from utils.minio_client import minio_client
from config.minio_config import BUCKETS, USE_MINIO
from datetime import datetime

# 图片上传示例
@app.post("/api/images/upload")
async def upload_image(
    file: UploadFile = File(...),
    folder: str = Form("default"),
    db: Session = Depends(get_db)
):
    """上传图片 - 支持 MinIO"""
    try:
        # 生成唯一文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_ext = os.path.splitext(file.filename)[1]
        filename = f"{folder}/{timestamp}_{file.filename}"

        if USE_MINIO:
            # 使用 MinIO 存储
            success = minio_client.upload_file(
                bucket_name=BUCKETS["images"],
                object_name=filename,
                file_data=file.file,
                content_type=file.content_type or "image/jpeg"
            )

            if not success:
                raise HTTPException(status_code=500, detail="上传失败")

            # 生成访问URL (7天有效)
            from datetime import timedelta
            file_url = minio_client.get_presigned_url(
                bucket_name=BUCKETS["images"],
                object_name=filename,
                expires=timedelta(days=7)
            )
        else:
            # 使用本地磁盘存储 (向后兼容)
            save_dir = os.path.join(IMAGES_DIR, folder)
            os.makedirs(save_dir, exist_ok=True)

            file_path = os.path.join(save_dir, f"{timestamp}_{file.filename}")
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            file_url = f"/uploads/images/{folder}/{timestamp}_{file.filename}"

        # 保存到数据库
        db_image = ImageDatabase(
            filename=filename,
            folder=folder,
            file_path=file_url if USE_MINIO else file_path,
            upload_date=datetime.now()
        )
        db.add(db_image)
        db.commit()
        db.refresh(db_image)

        return {
            "code": 0,
            "message": "上传成功",
            "data": {
                "id": db_image.id,
                "filename": filename,
                "url": file_url
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 图片下载/查看示例
@app.get("/api/images/{image_id}")
async def get_image(image_id: int, db: Session = Depends(get_db)):
    """获取图片 - 支持 MinIO"""
    image = db.query(ImageDatabase).filter(ImageDatabase.id == image_id).first()

    if not image:
        raise HTTPException(status_code=404, detail="图片不存在")

    if USE_MINIO:
        # 从 MinIO 获取
        url = minio_client.get_presigned_url(
            bucket_name=BUCKETS["images"],
            object_name=image.filename,
            expires=timedelta(hours=1)
        )
        # 重定向到预签名URL
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=url)
    else:
        # 从本地磁盘获取
        from fastapi.responses import FileResponse
        return FileResponse(image.file_path)


# 图片删除示例
@app.delete("/api/images/{image_id}")
async def delete_image(image_id: int, db: Session = Depends(get_db)):
    """删除图片 - 支持 MinIO"""
    image = db.query(ImageDatabase).filter(ImageDatabase.id == image_id).first()

    if not image:
        raise HTTPException(status_code=404, detail="图片不存在")

    if USE_MINIO:
        # 从 MinIO 删除
        minio_client.delete_file(
            bucket_name=BUCKETS["images"],
            object_name=image.filename
        )
    else:
        # 从本地磁盘删除
        if os.path.exists(image.file_path):
            os.remove(image.file_path)

    # 从数据库删除
    db.delete(image)
    db.commit()

    return {"code": 0, "message": "删除成功"}
```

---

### 阶段三: 数据迁移

#### 1. 创建迁移脚本

创建 `scripts/migrate_to_minio.py`:

```python
"""
将现有磁盘文件迁移到 MinIO
"""
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.minio_client import minio_client
from config.minio_config import BUCKETS
from tqdm import tqdm

def migrate_directory(local_dir: str, bucket_name: str, prefix: str = ""):
    """迁移目录到 MinIO"""

    if not os.path.exists(local_dir):
        print(f"⚠️  目录不存在: {local_dir}")
        return

    # 确保存储桶存在
    minio_client.ensure_bucket(bucket_name)

    # 遍历文件
    files = []
    for root, dirs, filenames in os.walk(local_dir):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            # 计算相对路径
            rel_path = os.path.relpath(file_path, local_dir)
            object_name = os.path.join(prefix, rel_path).replace("\\", "/")
            files.append((file_path, object_name))

    print(f"📂 准备迁移 {len(files)} 个文件从 {local_dir} 到 {bucket_name}")

    # 上传文件
    success_count = 0
    fail_count = 0

    for file_path, object_name in tqdm(files, desc=f"迁移到 {bucket_name}"):
        # 检查是否已存在
        if minio_client.file_exists(bucket_name, object_name):
            print(f"⏭️  跳过(已存在): {object_name}")
            success_count += 1
            continue

        # 上传
        success = minio_client.upload_file(
            bucket_name=bucket_name,
            object_name=object_name,
            file_path=file_path
        )

        if success:
            success_count += 1
        else:
            fail_count += 1
            print(f"❌ 失败: {file_path}")

    print(f"\n✅ 迁移完成: 成功 {success_count}, 失败 {fail_count}")
    print(f"存储桶: {bucket_name}, 总文件数: {len(files)}\n")


def main():
    """主函数"""
    print("=" * 60)
    print("开始迁移文件到 MinIO")
    print("=" * 60)

    base_dir = r"G:\ShuangChuang\ShuangC\backend\uploads"

    # 迁移各个目录
    migrations = [
        (os.path.join(base_dir, "images"), BUCKETS["images"], ""),
        (os.path.join(base_dir, "results"), BUCKETS["results"], ""),
        (os.path.join(base_dir, "videos"), BUCKETS["videos"], ""),
        (os.path.join(base_dir, "vid_results"), BUCKETS["vid_results"], ""),
    ]

    for local_dir, bucket, prefix in migrations:
        migrate_directory(local_dir, bucket, prefix)

    print("=" * 60)
    print("🎉 所有迁移任务完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

#### 2. 执行迁移

```bash
conda activate backendJC
cd G:\ShuangChuang\ShuangC\backend\business-service
python scripts/migrate_to_minio.py
```

---

### 阶段四: 测试验证

#### 1. 功能测试清单

```bash
# 测试上传
curl -X POST "http://localhost:8001/api/images/upload" \
  -F "file=@test.jpg" \
  -F "folder=test"

# 测试查看
curl "http://localhost:8001/api/images/1"

# 测试删除
curl -X DELETE "http://localhost:8001/api/images/1"
```

#### 2. 性能测试

创建 `scripts/benchmark_minio.py`:

```python
"""MinIO 性能测试"""
import time
from utils.minio_client import minio_client
from config.minio_config import BUCKETS

def benchmark_upload(file_path: str, count: int = 10):
    """上传性能测试"""
    bucket = BUCKETS["images"]

    start = time.time()
    for i in range(count):
        minio_client.upload_file(
            bucket_name=bucket,
            object_name=f"benchmark/test_{i}.jpg",
            file_path=file_path
        )
    elapsed = time.time() - start

    print(f"上传 {count} 个文件耗时: {elapsed:.2f}秒")
    print(f"平均每个文件: {elapsed/count:.3f}秒")

if __name__ == "__main__":
    benchmark_upload("test.jpg", 10)
```

---

### 阶段五: 环境配置

#### 1. 环境变量配置

创建 `.env` 文件:

```bash
# MinIO 配置
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=admin123456
MINIO_SECURE=false

# 是否启用 MinIO (true/false)
USE_MINIO=true
```

#### 2. Docker Compose 完整配置

```yaml
version: '3.8'

services:
  # MinIO 对象存储
  minio:
    image: minio/minio:latest
    container_name: minio
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: admin123456
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

  # 业务服务
  business-service:
    build: .
    ports:
      - "8001:8001"
    environment:
      - MINIO_ENDPOINT=minio:9000
      - USE_MINIO=true
    depends_on:
      - minio
    restart: always

volumes:
  minio_data:
```

---

## 📚 常见问题

### Q1: MinIO 和传统文件系统有什么区别?

**MinIO (对象存储)**:
- ✅ 扁平化存储,通过唯一 key 访问
- ✅ 支持分布式,可横向扩展
- ✅ 自带版本控制、权限管理
- ✅ 通过 HTTP API 访问
- ❌ 不支持文件追加写入
- ❌ 不支持文件系统操作(mv, cp等)

**传统文件系统**:
- ✅ 目录层级结构
- ✅ 支持文件追加、移动
- ✅ 本地访问速度快
- ❌ 难以扩展
- ❌ 缺乏权限管理
- ❌ 备份麻烦

### Q2: 迁移后原有文件怎么办?

**方案**: 保留原有文件作为备份
- MinIO 迁移后,原磁盘文件可以保留
- 通过 `USE_MINIO` 环境变量切换
- 数据库中同时记录两种路径

### Q3: 如何回退到磁盘存储?

```bash
# 设置环境变量
export USE_MINIO=false

# 或修改 .env
USE_MINIO=false

# 重启服务
```

### Q4: MinIO 性能如何?

**内网环境**:
- 上传: ~100-200 MB/s
- 下载: ~200-500 MB/s
- 延迟: <10ms

**公网环境**:
- 受网络带宽限制
- 建议使用 CDN 加速

### Q5: 如何备份 MinIO 数据?

```bash
# 方法1: mc 工具镜像备份
mc mirror minio/images /backup/images

# 方法2: 导出为文件
mc cp --recursive minio/images /backup/

# 方法3: Docker 卷备份
docker run --rm -v minio_data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/minio-backup.tar.gz /data
```

---

## 🎯 总结

### 推荐迁移步骤

1. ✅ **测试环境部署** (1小时)
   - Docker 部署 MinIO
   - 创建 Bucket
   - 测试上传/下载

2. ✅ **代码开发** (3-4小时)
   - 创建 MinIO 工具类
   - 修改上传/下载接口
   - 保留兼容性开关

3. ✅ **小规模测试** (1小时)
   - 迁移部分测试数据
   - 功能测试
   - 性能测试

4. ✅ **全量迁移** (2-3小时)
   - 执行迁移脚本
   - 验证数据完整性
   - 切换到 MinIO

5. ✅ **监控观察** (1周)
   - 观察稳定性
   - 性能监控
   - 保留原文件备份

### 预期收益

- 📈 **可扩展性**: 支持未来数据增长
- 🔒 **数据安全**: 专业的权限管理和版本控制
- 🚀 **性能提升**: 分布式架构,支持并发访问
- 💰 **成本节约**: 开源免费,无云存储费用
- 🛠️ **易维护**: Web 界面管理,运维简单

### 是否推荐迁移?

**强烈推荐** ✅

理由:
1. 当前数据量适中 (2.1GB),迁移成本低
2. 未来数据增长预期,MinIO 更有优势
3. MinIO 成熟稳定,风险可控
4. 部署简单,维护方便
5. 可平滑过渡,支持回退

**建议**: 先在测试环境验证,确认无问题后再迁移生产环境。
