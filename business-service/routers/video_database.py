"""
视频数据库管理路由
"""
import os
import uuid
import zipfile
import tempfile
import time
import gc
from datetime import datetime
from typing import List
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Depends
from sqlalchemy.orm import Session
import sys

# 添加父目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from shared import get_db, VideoTrackingTask

# 导入 MinIO 客户端和配置
from utils.minio_client import minio_client
from config.minio_config import BUCKETS

router = APIRouter(prefix="/videos", tags=["视频数据库"])


def safe_remove_file(file_path: str, max_retries: int = 3) -> bool:
    """安全删除文件，带重试机制"""
    for attempt in range(max_retries):
        try:
            # 强制垃圾回收，释放可能的文件句柄
            gc.collect()

            # 尝试删除文件
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except PermissionError as e:
            if attempt < max_retries - 1:
                # 等待一小段时间后重试
                time.sleep(0.5)
                continue
            else:
                # 最后一次尝试失败
                raise PermissionError(f"文件被占用，无法删除: {file_path}。请关闭正在播放该视频的页面后重试。")
        except Exception as e:
            raise e
    return False

# 从环境变量或配置中获取路径（在 main.py 中设置）
VIDEOS_DIR = None
VID_RESULTS_DIR = None


def set_videos_dir(videos_dir: str):
    """设置视频目录路径"""
    global VIDEOS_DIR
    VIDEOS_DIR = videos_dir


def set_vid_results_dir(vid_results_dir: str):
    """设置视频推理结果目录路径"""
    global VID_RESULTS_DIR
    VID_RESULTS_DIR = vid_results_dir


@router.get("/database")
async def get_video_database(folder: str = None):
    """获取视频数据库（从 MinIO 获取视频列表，返回树形结构）"""
    print(f"\n{'='*60}", flush=True)
    print(f"📹 [router] 开始获取视频列表", flush=True)
    print(f"Bucket: {BUCKETS['videos']}", flush=True)
    print(f"Folder: {folder}", flush=True)
    print(f"{'='*60}", flush=True)

    try:
        # 从 MinIO 列举视频对象
        objects = minio_client.list_objects(
            bucket_name=BUCKETS["videos"],
            prefix=folder if folder else None,
            recursive=True
        )

        # 构建树形结构
        folder_map = {}  # 用于存储文件夹节点
        file_list = []   # 用于存储文件节点
        total_count = 0  # 总对象数
        video_count = 0  # 视频文件数

        for obj in objects:
            total_count += 1
            object_name = obj.object_name
            parts = object_name.split('/')
            filename = parts[-1]

            print(f"  检查对象 {total_count}: {object_name}", flush=True)

            # 跳过非视频文件
            if not filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')):
                print(f"    ⚠️ 跳过非视频文件", flush=True)
                continue

            video_count += 1
            print(f"    ✅ 视频文件 {video_count}", flush=True)

            # 构建MinIO路径格式
            minio_path = f"minio://{BUCKETS['videos']}/{object_name}"

            # 构建视频节点数据
            video_node = {
                "id": object_name,
                "filename": filename,
                "path": minio_path,  # MinIO格式路径，用于传递给后端服务
                "fullPath": object_name,  # MinIO 对象名
                "relativePath": object_name,
                "size": obj.size,
                "uploadedAt": obj.last_modified.isoformat() if obj.last_modified else None,
                "isFolder": False
            }

            # 如果有文件夹层级
            if len(parts) > 1:
                folder_path = '/'.join(parts[:-1])

                # 确保文件夹节点存在
                if folder_path not in folder_map:
                    folder_map[folder_path] = {
                        "id": f"folder_{folder_path}",
                        "filename": parts[-2] if len(parts) > 1 else folder_path,
                        "path": folder_path,
                        "relativePath": folder_path,
                        "isFolder": True,
                        "children": []
                    }

                # 添加文件到对应文件夹
                folder_map[folder_path]["children"].append(video_node)
            else:
                # 根目录文件
                file_list.append(video_node)

        print(f"\n{'='*60}", flush=True)
        print(f"✅ 视频列表统计:", flush=True)
        print(f"   总对象: {total_count}", flush=True)
        print(f"   视频文件: {video_count}", flush=True)
        print(f"   文件夹: {len(folder_map)}", flush=True)
        print(f"   根文件: {len(file_list)}", flush=True)
        print(f"{'='*60}\n", flush=True)

        # 合并文件夹和文件
        result = list(folder_map.values()) + file_list

        if not result:
            print("⚠️ 结果为空，返回空消息", flush=True)
            return {"code": 0, "data": [], "message": "MinIO 中暂无视频"}

        print(f"✅ 返回 {len(result)} 个节点", flush=True)
        return {
            "code": 0,
            "data": result,
            "message": "success"
        }

    except Exception as e:
        print(f"❌ 获取 MinIO 视频列表失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {
            "code": 500,
            "data": [],
            "message": f"获取视频列表失败: {str(e)}"
        }


@router.delete("/file")
async def delete_video_file(file_path: str, db: Session = Depends(get_db)):
    """删除MinIO中的视频文件，并清理关联的数据库记录"""
    try:
        print(f"[视频删除] 收到删除请求: {file_path}", flush=True)

        # 解析路径：支持 minio://bucket/object 格式和裸对象名格式
        if file_path.startswith("minio://"):
            # 完整MinIO路径
            minio_path = file_path.replace("minio://", "")
            parts = minio_path.split("/", 1)
            if len(parts) != 2:
                return {"code": 400, "data": None, "message": "MinIO路径格式错误"}
            bucket_name, object_name = parts
        else:
            # 裸对象名，根据内容判断桶
            object_name = file_path
            # 默认尝试原始视频桶
            if minio_client.file_exists(BUCKETS["videos"], object_name):
                bucket_name = BUCKETS["videos"]
            elif minio_client.file_exists(BUCKETS["vid_results"], object_name):
                bucket_name = BUCKETS["vid_results"]
            else:
                return {"code": 404, "data": None, "message": "文件不存在"}

        # 安全检查：只允许删除视频相关桶中的文件
        allowed_buckets = [BUCKETS["videos"], BUCKETS["vid_results"]]
        if bucket_name not in allowed_buckets:
            return {"code": 403, "data": None, "message": "非法路径"}

        # 从MinIO删除文件
        success = minio_client.delete_file(bucket_name, object_name)
        if not success:
            return {"code": 500, "data": None, "message": "从MinIO删除文件失败"}

        print(f"[视频删除] ✅ 已从MinIO删除: {bucket_name}/{object_name}", flush=True)

        # 清理数据库记录
        try:
            minio_full_path = f"minio://{bucket_name}/{object_name}"
            is_original = bucket_name == BUCKETS["videos"]
            is_result = bucket_name == BUCKETS["vid_results"]

            if is_original:
                deleted_records = db.query(VideoTrackingTask).filter(
                    VideoTrackingTask.original_video_path == minio_full_path
                ).delete()
                print(f"[视频删除] 清理了 {deleted_records} 条原视频相关记录")
            elif is_result:
                deleted_records = db.query(VideoTrackingTask).filter(
                    VideoTrackingTask.result_video_path == minio_full_path
                ).delete()
                print(f"[视频删除] 清理了 {deleted_records} 条结果视频相关记录")

            db.commit()
        except Exception as db_error:
            print(f"[视频删除] 清理数据库记录失败: {db_error}")
            db.rollback()

        return {"code": 0, "data": None, "message": "删除成功"}
    except Exception as e:
        print(f"[视频删除] 删除失败: {e}", flush=True)
        return {"code": 500, "data": None, "message": f"删除失败: {str(e)}"}


@router.post("/batch-delete-files")
async def batch_delete_video_files(file_paths: List[str], db: Session = Depends(get_db)):
    """批量删除MinIO中的视频文件，并清理关联的数据库记录"""
    allowed_buckets = [BUCKETS["videos"], BUCKETS["vid_results"]]
    deleted_count = 0
    failed_files = []

    for file_path in file_paths:
        try:
            # 解析路径
            if file_path.startswith("minio://"):
                minio_path = file_path.replace("minio://", "")
                parts = minio_path.split("/", 1)
                if len(parts) != 2:
                    failed_files.append(f"{file_path}: MinIO路径格式错误")
                    continue
                bucket_name, object_name = parts
            else:
                object_name = file_path
                if minio_client.file_exists(BUCKETS["videos"], object_name):
                    bucket_name = BUCKETS["videos"]
                elif minio_client.file_exists(BUCKETS["vid_results"], object_name):
                    bucket_name = BUCKETS["vid_results"]
                else:
                    failed_files.append(f"{file_path}: 文件不存在")
                    continue

            # 安全检查
            if bucket_name not in allowed_buckets:
                failed_files.append(f"{file_path}: 非法路径")
                continue

            # 从MinIO删除文件
            success = minio_client.delete_file(bucket_name, object_name)
            if not success:
                failed_files.append(f"{file_path}: 从MinIO删除失败")
                continue

            deleted_count += 1

            # 清理数据库记录
            try:
                minio_full_path = f"minio://{bucket_name}/{object_name}"
                if bucket_name == BUCKETS["videos"]:
                    db.query(VideoTrackingTask).filter(
                        VideoTrackingTask.original_video_path == minio_full_path
                    ).delete()
                else:
                    db.query(VideoTrackingTask).filter(
                        VideoTrackingTask.result_video_path == minio_full_path
                    ).delete()
                db.commit()
            except Exception as db_error:
                print(f"[批量删除] 清理数据库记录失败: {db_error}")
                db.rollback()

        except Exception as e:
            failed_files.append(f"{file_path}: {str(e)}")

    return {
        "code": 0,
        "data": {
            "deleted": deleted_count,
            "failed": len(failed_files),
            "errors": failed_files
        },
        "message": f"成功删除 {deleted_count} 个文件" + (f", {len(failed_files)} 个失败" if failed_files else "")
    }


@router.post("/upload")
async def upload_video_to_database(
    file: UploadFile = File(...),
    folder: str = Form(default="")
):
    """上传单个视频文件到视频数据库"""
    try:
        # 构建目标文件夹路径
        if folder:
            # 标准化路径分隔符
            folder = folder.replace('\\', '/').strip('/')
            target_dir = os.path.join(VIDEOS_DIR, folder)
        else:
            target_dir = VIDEOS_DIR

        # 创建目标目录
        os.makedirs(target_dir, exist_ok=True)

        # 生成时间戳文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_name = os.path.splitext(file.filename)[0]
        file_ext = os.path.splitext(file.filename)[1] or '.mp4'
        unique_filename = f"{timestamp}_{original_name}{file_ext}"
        file_path = os.path.join(target_dir, unique_filename)

        # 保存文件
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        return {
            "code": 0,
            "data": {
                "filename": unique_filename,
                "path": file_path,
                "folder": folder or "根目录"
            },
            "message": "视频上传成功"
        }
    except Exception as e:
        return {
            "code": 500,
            "data": None,
            "message": f"上传失败: {str(e)}"
        }


@router.post("/upload-zip")
async def upload_video_zip_to_database(
    file: UploadFile = File(...),
    folder: str = Form(default="")
):
    """上传视频压缩包到视频数据库并自动解压"""
    try:
        # 构建目标文件夹路径
        if folder:
            # 标准化路径分隔符
            folder = folder.replace('\\', '/').strip('/')
            target_dir = os.path.join(VIDEOS_DIR, folder)
        else:
            target_dir = VIDEOS_DIR

        # 创建目标目录
        os.makedirs(target_dir, exist_ok=True)

        # 保存压缩包到临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_zip_path = temp_file.name

        # 解压文件
        video_extensions = ('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm')
        extracted_count = 0

        with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
            for file_info in zip_ref.filelist:
                # 跳过目录和隐藏文件
                if file_info.is_dir() or file_info.filename.startswith('.'):
                    continue

                # 只处理视频文件
                if file_info.filename.lower().endswith(video_extensions):
                    # 获取原始文件名（去除路径）
                    original_filename = os.path.basename(file_info.filename)

                    # 解压文件内容
                    file_content = zip_ref.read(file_info.filename)

                    # 保存到目标目录
                    target_file_path = os.path.join(target_dir, original_filename)
                    with open(target_file_path, 'wb') as f:
                        f.write(file_content)

                    extracted_count += 1

        # 删除临时压缩包
        os.remove(temp_zip_path)

        return {
            "code": 0,
            "data": {
                "extracted_count": extracted_count,
                "folder": folder or "根目录"
            },
            "message": f"成功解压 {extracted_count} 个视频文件"
        }
    except zipfile.BadZipFile:
        # 清理临时文件
        if 'temp_zip_path' in locals() and os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)
        return {
            "code": 400,
            "data": None,
            "message": "无效的压缩包文件"
        }
    except Exception as e:
        # 清理临时文件
        if 'temp_zip_path' in locals() and os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)
        return {
            "code": 500,
            "data": None,
            "message": f"上传失败: {str(e)}"
        }


@router.get("/results/database")
async def get_video_results_database():
    """获取推理结果视频数据库（从 MinIO vid-results bucket 获取）"""
    print(f"\n{'='*60}", flush=True)
    print(f"📊 [router] 开始获取推理结果视频列表", flush=True)
    print(f"Bucket: {BUCKETS['vid_results']}", flush=True)
    print(f"{'='*60}", flush=True)

    try:
        # 从 MinIO 列举推理结果视频对象
        objects = minio_client.list_objects(
            bucket_name=BUCKETS["vid_results"],
            recursive=True
        )

        # 构建树形结构
        folder_map = {}
        file_list = []
        total_count = 0
        video_count = 0

        for obj in objects:
            total_count += 1
            object_name = obj.object_name
            parts = object_name.split('/')
            filename = parts[-1]

            print(f"  检查对象 {total_count}: {object_name}", flush=True)

            # 跳过非视频文件
            if not filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm')):
                print(f"    ⚠️ 跳过非视频文件", flush=True)
                continue

            video_count += 1
            print(f"    ✅ 推理结果视频 {video_count}", flush=True)

            # 构建MinIO路径格式（用于删除等后端操作）
            minio_path = f"minio://{BUCKETS['vid_results']}/{object_name}"

            # 尝试匹配原视频（从文件名推断）
            original_video_name = None
            if "_tracked" in filename or "tracked_" in filename:
                original_video_name = filename.replace("_tracked", "").replace("tracked_", "")
            elif filename.count("_") >= 2:
                parts_name = filename.split("_", 1)
                if len(parts_name) > 1:
                    original_video_name = parts_name[1]

            # 如果有文件夹层级
            if len(parts) > 1:
                folder_path = '/'.join(parts[:-1])

                if folder_path not in folder_map:
                    folder_map[folder_path] = {
                        "id": f"folder_{folder_path}",
                        "filename": parts[-2] if len(parts) > 1 else folder_path,
                        "path": folder_path,
                        "relativePath": folder_path,
                        "isFolder": True,
                        "children": []
                    }

                folder_map[folder_path]["children"].append({
                    "id": object_name,
                    "filename": filename,
                    "path": minio_path,
                    "fullPath": object_name,
                    "relativePath": object_name,
                    "size": obj.size,
                    "uploadedAt": obj.last_modified.isoformat() if obj.last_modified else None,
                    "originalVideoName": original_video_name,
                    "isFolder": False,
                    "isResult": True
                })
            else:
                # 根目录文件
                file_list.append({
                    "id": object_name,
                    "filename": filename,
                    "path": minio_path,
                    "fullPath": object_name,
                    "relativePath": object_name,
                    "size": obj.size,
                    "uploadedAt": obj.last_modified.isoformat() if obj.last_modified else None,
                    "originalVideoName": original_video_name,
                    "isFolder": False,
                    "isResult": True
                })

        print(f"\n{'='*60}", flush=True)
        print(f"✅ 推理结果视频统计:", flush=True)
        print(f"   总对象: {total_count}", flush=True)
        print(f"   视频文件: {video_count}", flush=True)
        print(f"   文件夹: {len(folder_map)}", flush=True)
        print(f"   根文件: {len(file_list)}", flush=True)
        print(f"{'='*60}\n", flush=True)

        result = list(folder_map.values()) + file_list

        if not result:
            print("⚠️ 推理结果为空", flush=True)
            return {"code": 0, "data": [], "message": "MinIO 中暂无推理结果视频"}

        print(f"✅ 返回 {len(result)} 个推理结果节点", flush=True)
        return {
            "code": 0,
            "data": result,
            "message": "success"
        }

    except Exception as e:
        print(f"❌ 获取推理结果视频列表失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {
            "code": 500,
            "data": [],
            "message": f"获取推理结果列表失败: {str(e)}"
        }


@router.post("/cleanup-orphaned-records")
async def cleanup_orphaned_records(db: Session = Depends(get_db)):
    """清理数据库中的孤立记录（原视频或结果视频已被删除的记录）"""
    try:
        all_records = db.query(VideoTrackingTask).all()
        deleted_count = 0

        for record in all_records:
            should_delete = False

            # 检查原视频是否存在
            if record.original_video_path and not os.path.exists(record.original_video_path):
                should_delete = True
                print(f"[清理] 原视频不存在: {record.original_video_path}")

            # 检查结果视频是否存在
            if record.result_video_path and not os.path.exists(record.result_video_path):
                should_delete = True
                print(f"[清理] 结果视频不存在: {record.result_video_path}")

            # 删除记录
            if should_delete:
                db.delete(record)
                deleted_count += 1

        db.commit()

        return {
            "code": 0,
            "data": {"deleted": deleted_count},
            "message": f"清理了 {deleted_count} 条孤立记录"
        }
    except Exception as e:
        db.rollback()
        return {
            "code": 500,
            "data": None,
            "message": f"清理失败: {str(e)}"
        }


@router.get("/find-result")
async def find_result_video(original_video_path: str):
    """根据原视频路径查找对应的推理结果视频（从 MinIO 查询）"""
    try:
        original_filename = os.path.basename(original_video_path)
        original_name_no_ext = os.path.splitext(original_filename)[0]

        result_videos = []

        # 从 MinIO vid-results bucket 查询
        objects = minio_client.list_objects(
            bucket_name=BUCKETS["vid_results"],
            recursive=True
        )

        for obj in objects:
            filename = os.path.basename(obj.object_name)

            # 跳过非视频文件
            if not filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm')):
                continue

            # 检查是否匹配原视频名称
            if original_name_no_ext.lower() in filename.lower():
                # 构建访问路径
                access_path = f"/uploads/vid_results/{obj.object_name}"

                result_videos.append({
                    "id": obj.object_name,
                    "filename": filename,
                    "path": access_path,
                    "fullPath": obj.object_name,
                    "relativePath": obj.object_name,
                    "size": obj.size,
                    "width": None,  # MinIO 不存储视频元数据，需要时再获取
                    "height": None,
                    "duration": None,
                    "createdAt": obj.last_modified.isoformat() if obj.last_modified else None,
                    "isResult": True
                })

        if result_videos:
            # 按创建时间倒序排序
            result_videos.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
            return {
                "code": 0,
                "data": result_videos[0] if len(result_videos) == 1 else result_videos,
                "message": f"找到 {len(result_videos)} 个推理结果"
            }
        else:
            return {"code": 0, "data": None, "message": "未找到推理结果"}

    except Exception as e:
        print(f"❌ 查询推理结果失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {"code": 500, "data": None, "message": f"查询失败: {str(e)}"}
