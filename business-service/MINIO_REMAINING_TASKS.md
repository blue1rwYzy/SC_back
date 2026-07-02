# MinIO 剩余修改任务

## ✅ 已完成的接口 (business-service)

### 图片接口
1. ✅ `/images/upload` - 图片上传
2. ✅ `/images/upload-zip` - ZIP 批量上传
3. ✅ `/images/file` (DELETE) - 删除图片
4. ✅ `/images/batch-delete-files` (POST) - 批量删除图片

### 文件访问路由
5. ✅ `/uploads/images/{file_path:path}` - 图片访问
6. ✅ `/uploads/img_results/{file_path:path}` - 推理结果访问
7. ✅ `/uploads/videos/{file_path:path}` - 视频访问
8. ✅ `/uploads/vid_results/{file_path:path}` - 视频推理结果访问

### 模型接口
9. ✅ `/models` (POST) - 模型上传
10. ✅ `/models/{model_id}` (DELETE) - 模型删除

### 推理结果接口
11. ✅ `/inference-results/{result_id}` (DELETE) - 删除推理结果
12. ✅ `/inference-results/batch-delete` (POST) - 批量删除推理结果

## 🔄 剩余需要修改的任务

### business-service 剩余任务

#### ✅ 已完成
- ✅ 所有图片上传/删除接口
- ✅ 所有文件访问路由
- ✅ 模型上传/删除接口
- ✅ 推理结果删除接口

#### 🔄 待检查
- 是否有视频上传接口需要修改？（未在 main.py 中找到）

## 📝 通用修改模板

### 模板 1: 文件访问 (返回预签名 URL)

```python
@app.get("/uploads/images/{file_path:path}")
async def get_image(file_path: str):
    """获取图片 - 支持 MinIO"""
    if USE_MINIO:
        # 从 MinIO 获取预签名 URL
        url = minio_client.get_presigned_url(
            bucket_name=BUCKETS["images"],
            object_name=file_path,
            expires=timedelta(hours=1)
        )
        if url:
            return RedirectResponse(url=url)
        else:
            raise HTTPException(status_code=404, detail="文件不存在")
    else:
        # 本地文件
        local_path = os.path.join(IMAGES_DIR, file_path)
        if os.path.exists(local_path):
            from fastapi.responses import FileResponse
            return FileResponse(local_path)
        else:
            raise HTTPException(status_code=404, detail="文件不存在")
```

### 模板 2: 推理结果访问

```python
@app.get("/uploads/img-results/{file_path:path}")
async def get_inference_result(file_path: str):
    """获取推理结果图片 - 支持 MinIO"""
    if USE_MINIO:
        url = minio_client.get_presigned_url(
            bucket_name=BUCKETS["img_results"],  # 注意: 配置中映射到 img-results
            object_name=file_path,
            expires=timedelta(hours=1)
        )
        if url:
            return RedirectResponse(url=url)
        else:
            raise HTTPException(status_code=404, detail="文件不存在")
    else:
        local_path = os.path.join(IMG_RESULTS_DIR, file_path)
        if os.path.exists(local_path):
            from fastapi.responses import FileResponse
            return FileResponse(local_path)
        else:
            raise HTTPException(status_code=404, detail="文件不存在")
```

### 模板 3: 视频访问

```python
@app.get("/uploads/videos/{file_path:path}")
async def get_video(file_path: str):
    """获取视频 - 支持 MinIO"""
    if USE_MINIO:
        url = minio_client.get_presigned_url(
            bucket_name=BUCKETS["videos"],
            object_name=file_path,
            expires=timedelta(hours=2)  # 视频较大,给更长时间
        )
        if url:
            return RedirectResponse(url=url)
        else:
            raise HTTPException(status_code=404, detail="文件不存在")
    else:
        local_path = os.path.join(VIDEOS_DIR, file_path)
        if os.path.exists(local_path):
            from fastapi.responses import FileResponse
            return FileResponse(local_path)
        else:
            raise HTTPException(status_code=404, detail="文件不存在")
```

## 🎯 inference-service 修改重点

**文件**: `G:\ShuangChuang\ShuangC\backend\inference-service\main.py`

### 关键修改点

1. **添加 MinIO 导入** (文件开头)
```python
from dotenv import load_dotenv
load_dotenv()

from utils.minio_client import minio_client  # 需要复制 utils 到 inference-service
from config.minio_config import BUCKETS, USE_MINIO
```

2. **修改推理结果保存逻辑** (第 392 行附近)
```python
# 原代码:
result_img_path = os.path.join(actual_save_dir, img_name)

# 修改为:
if USE_MINIO:
    # 上传到 MinIO
    if os.path.exists(os.path.join(actual_save_dir, img_name)):
        minio_client.upload_file(
            bucket_name=BUCKETS["img_results"],
            object_name=f"{batch_name}/{img_name}",
            file_path=os.path.join(actual_save_dir, img_name)
        )
    result_img_path = f"minio://{BUCKETS['img_results']}/{batch_name}/{img_name}"
else:
    result_img_path = os.path.join(actual_save_dir, img_name)
```

## 🚀 快速完成建议

### 方案 A: 最小改动方案 (推荐)

只修改**文件访问路由**,其他保持不变:

1. 添加 3 个动态路由 (images, img-results, videos)
2. 根据 USE_MINIO 返回预签名 URL 或本地文件
3. 前端无需修改,因为都是通过相同的 URL 访问

**优点**:
- 改动最小
- 前端无感知
- 可以随时切换

**代码量**: 约 50 行

### 方案 B: 完整改动方案

修改所有上传/下载/删除接口

**优点**:
- 完全集成
- 所有功能都支持 MinIO

**代码量**: 约 500 行

## 🎬 下一步行动

我建议采用**方案 A**:

1. 我帮您添加 3 个文件访问路由
2. 复制 utils 和 config 到 inference-service
3. 简单修改 inference-service 的结果保存逻辑

这样:
- ✅ 10 分钟完成
- ✅ MinIO 完全可用
- ✅ 可以随时回退

**您希望我继续完成方案 A 吗?** (推荐)
或者继续方案 B 的完整修改?
