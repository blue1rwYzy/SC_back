"""
推理服务 - 主入口
端口: 8002
负责: YOLO 模型推理、图片处理、实时进度推送
"""
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List, Optional
import sys
import os
import shutil
import uuid
from datetime import datetime
import zipfile
import json
import asyncio
from pathlib import Path
import io

# 添加父目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared import get_db, Model, InferenceResult

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv()

# MinIO 导入 (生产环境统一使用 MinIO)
from utils.minio_client import minio_client
from config.minio_config import BUCKETS

# 导入 YOLO
try:
    from ultralytics import YOLO
except ImportError:
    print("警告: ultralytics 未安装，推理功能将不可用")
    YOLO = None

app = FastAPI(
    title="推理服务 API",
    description="高速公路缺陷检测系统 - YOLO 推理服务",
    version="2.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 目录配置
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
IMAGES_DIR = os.path.join(UPLOAD_DIR, "images")
IMG_RESULTS_DIR = os.path.join(UPLOAD_DIR, "img_results")

# 注意: 不再预先创建这些目录
# 所有文件操作都通过 MinIO 进行，只在需要时创建临时目录，并在使用后立即删除
# os.makedirs(IMAGES_DIR, exist_ok=True)
# os.makedirs(IMG_RESULTS_DIR, exist_ok=True)

# WebSocket 连接管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[task_id] = websocket
        print(f"✅ WebSocket 连接建立: {task_id}")

    def disconnect(self, task_id: str):
        if task_id in self.active_connections:
            del self.active_connections[task_id]
            print(f"❌ WebSocket 连接断开: {task_id}")

    async def send_progress(self, task_id: str, data: dict):
        """发送进度更新"""
        if task_id in self.active_connections:
            try:
                await self.active_connections[task_id].send_json(data)
            except Exception as e:
                print(f"发送进度失败: {e}")
                self.disconnect(task_id)

manager = ConnectionManager()

# 模型缓存
# _model_cache = {}  # 已移除模型缓存机制


# 类别名称映射
CLASS_NAMES = {
    0: "Alligator_crack",      # 龟裂
    1: "Longitudinal_crack",   # 纵向裂缝
    2: "Oblique_crack",        # 斜向裂缝
    3: "Pothole",              # 坑洼
    4: "Repair",               # 修补区
    5: "Transverse_crack",     # 横向裂缝
}


def calculate_severity_level(detections: list, image_width: int, image_height: int) -> dict:
    """
    计算图像整体严重程度等级（方案三：加权综合评分）

    参数:
        detections: 检测结果列表 [{'class': str, 'confidence': float, 'bbox': [x1, y1, x2, y2]}, ...]
        image_width: 图像宽度（像素）
        image_height: 图像高度（像素）

    返回:
        {
            'level': int,           # 等级 1-5
            'score': float,         # 综合得分 0-100
            'level_text': str,      # 等级文本描述
            'level_color': str      # 等级颜色（用于前端显示）
        }
    """
    # 如果没有检测到缺陷，返回最低等级
    if not detections or len(detections) == 0:
        return {
            'level': 1,
            'score': 0,
            'level_text': '无缺陷',
            'level_color': 'green'
        }

    # 缺陷类型权重（根据对路面的危害程度）
    TYPE_WEIGHT = {
        'Pothole': 10,              # 坑洼最危险
        'Alligator_crack': 8,       # 龟裂表示结构性问题
        'Transverse_crack': 6,      # 横向裂缝容易扩展
        'Oblique_crack': 5,         # 斜向裂缝
        'Longitudinal_crack': 4,    # 纵向裂缝相对较轻
        'Repair': 2,                # 已修补区域最轻
    }

    total_score = 0
    image_area = image_width * image_height

    # 计算每个缺陷的得分
    for detection in detections:
        defect_type = detection.get('class', '')
        confidence = detection.get('confidence', 0)
        bbox = detection.get('bbox', [0, 0, 0, 0])

        # 1. 类型基础分
        base_score = TYPE_WEIGHT.get(defect_type, 5)

        # 2. 面积加成
        area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        area_ratio = area / image_area if image_area > 0 else 0

        if area_ratio > 0.15:       # 大于15%
            area_multiplier = 2.5
        elif area_ratio > 0.05:     # 5%-15%
            area_multiplier = 2.0
        elif area_ratio > 0.01:     # 1%-5%
            area_multiplier = 1.5
        else:                       # 小于1%
            area_multiplier = 1.0

        # 3. 置信度加成（置信度越高，权重越大）
        conf_multiplier = 0.5 + (confidence * 0.5)  # 范围 0.5-1.0

        # 单个缺陷得分
        defect_score = base_score * area_multiplier * conf_multiplier
        total_score += defect_score

    # 4. 数量加成（缺陷数量越多，道路状况越差）
    count = len(detections)
    if count >= 15:
        quantity_multiplier = 2.0
    elif count >= 10:
        quantity_multiplier = 1.8
    elif count >= 7:
        quantity_multiplier = 1.5
    elif count >= 5:
        quantity_multiplier = 1.3
    elif count >= 3:
        quantity_multiplier = 1.1
    else:
        quantity_multiplier = 1.0

    total_score *= quantity_multiplier

    # 归一化到 0-100
    # 调整归一化基准：
    # - 轻微: 1-2个小裂缝 ≈ 4*1.0*0.7*1.0 = 2.8
    # - 中等: 5-6个裂缝 ≈ 5*6*1.5*0.8*1.3 = 46.8
    # - 严重: 10个混合缺陷（含龟裂）≈ 8*10*2.0*0.8*1.8 = 230
    # - 极严重: 多个大坑洼 ≈ 10*5*2.5*1.0*2.0 = 250
    # 因此使用 150 作为基准更合理
    normalized_score = min(100, (total_score / 150) * 100)

    # 映射到等级（调整阈值，使评级更合理）
    if normalized_score >= 70:
        level = 5
        level_text = '极严重'
        level_color = 'purple'
    elif normalized_score >= 50:
        level = 4
        level_text = '严重'
        level_color = 'red'
    elif normalized_score >= 30:
        level = 3
        level_text = '中等'
        level_color = 'orange'
    elif normalized_score >= 15:
        level = 2
        level_text = '较轻'
        level_color = 'blue'
    else:
        level = 1
        level_text = '轻微'
        level_color = 'green'

    return {
        'level': level,
        'score': round(normalized_score, 2),
        'level_text': level_text,
        'level_color': level_color
    }


def get_next_predict_dir() -> tuple[str, str]:
    """
    获取下一个可用的 predict{i} 目录名
    返回: (完整路径, 目录名) - 不预先创建，让 YOLO 自己创建

    注意: 现在检查 MinIO 中已有的 predict 目录，而不是本地磁盘
    """
    try:
        # 从 MinIO 获取已有的 predict 目录
        existing_predicts = set()
        objects = minio_client.list_objects(
            bucket_name=BUCKETS["img_results"],
            recursive=True  # 递归列出所有对象
        )

        for obj in objects:
            # object_name 格式: predict0/image1.jpg, predict1/image2.jpg, ...
            # 提取顶层目录名
            if obj.object_name.startswith("predict"):
                parts = obj.object_name.split("/")
                if len(parts) >= 2:
                    dir_name = parts[0]
                    # 提取数字: predict0 -> 0
                    try:
                        num = int(dir_name.replace("predict", ""))
                        existing_predicts.add(num)
                    except ValueError:
                        continue

        # 找到下一个可用的编号
        i = 0
        while i in existing_predicts:
            i += 1

        dir_name = f"predict{i}"
        dir_path = os.path.join(IMG_RESULTS_DIR, dir_name)

        print(f"📁 下一个推理目录: {dir_name} (MinIO 中已有: {sorted(existing_predicts)})", flush=True)

        return dir_path, dir_name

    except Exception as e:
        print(f"⚠️ 从 MinIO 获取 predict 目录失败，使用本地检查: {e}", flush=True)
        import traceback
        traceback.print_exc()

        # 降级方案：检查本地目录
        i = 0
        while True:
            dir_name = f"predict{i}"
            dir_path = os.path.join(IMG_RESULTS_DIR, dir_name)
            if not os.path.exists(dir_path):
                return dir_path, dir_name
            i += 1


async def run_inference(
    task_id: str,
    model_path: str,
    source_paths: List[str],
    output_dir: str,
    batch_name: str,
    db: Session,
    conf: float = 0.45,
    imgsz: int = 1280,
    image_minio_map: dict = None
):
    """
    执行推理并实时推送进度（使用独立推理脚本）

    Args:
        task_id: 任务ID
        model_path: 模型路径
        source_paths: 源图片路径列表
        output_dir: 输出目录
        batch_name: 批次名称
        db: 数据库会话
        conf: 置信度阈值
        imgsz: 推理分辨率
        image_minio_map: 图片路径到 MinIO 路径的映射（用于避免重复上传）
    """
    if image_minio_map is None:
        image_minio_map = {}
    # 记录需要清理的临时目录
    temp_dirs_to_cleanup = []
    actual_save_dir = None  # 实际的推理输出目录

    # 收集临时目录（从 source_paths 提取）
    if source_paths:
        source_folder = os.path.dirname(source_paths[0])
        if "temp_" in source_folder:
            temp_dirs_to_cleanup.append(source_folder)
            print(f"📝 标记清理: 临时图片目录 {source_folder}", flush=True)

    try:
        # 发送开始消息
        await manager.send_progress(task_id, {
            "status": "processing",
            "progress": 0,
            "total": len(source_paths),
            "current": 0,
            "message": "开始推理..."
        })

        # ========== 使用独立推理脚本（subprocess 方式）==========
        # 获取图片所在的文件夹
        if source_paths:
            source_folder = os.path.dirname(source_paths[0])
        else:
            raise Exception("没有提供图片路径")

        print(f"📁 批量推理文件夹: {source_folder}")
        print(f"   图片数量: {len(source_paths)}")
        print(f"   置信度阈值: {conf}")
        print(f"   推理分辨率: {imgsz}")

        # 使用父目录作为 project，predict{i} 作为 name
        parent_dir = os.path.dirname(output_dir)
        folder_name = os.path.basename(output_dir)

        # 调用独立推理脚本
        import subprocess
        script_path = os.path.join(os.path.dirname(__file__), "yolo_inference_script.py")
        python_exe = os.getenv("PYTHON_EXE", "/opt/miniconda3/envs/backendJC/bin/python")

        cmd = [
            python_exe,
            script_path,
            "--model", model_path,
            "--source", source_folder,
            "--conf", str(conf),
            "--imgsz", str(imgsz),
            "--project", parent_dir,
            "--name", folder_name
        ]

        print(f"🚀 调用推理脚本...")
        print(f"   模型: {model_path}")
        print(f"   参数: conf={conf}, imgsz={imgsz}")

        import asyncio
        import json

        # 异步子进程，流式读取 stdout 进度
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_lines = []
        # 逐行读取 stdout，实时推送进度
        async for raw_line in proc.stdout:
            line = raw_line.decode('utf-8', errors='replace').strip()
            if not line:
                continue
            stdout_lines.append(line)
            try:
                msg = json.loads(line)
                if msg.get("type") == "progress":
                    await manager.send_progress(task_id, {
                        "status": "processing",
                        "progress": msg["progress"],
                        "total": msg["total"],
                        "current": msg["current"],
                        "message": f"推理中... {msg['current']}/{msg['total']}"
                    })
            except json.JSONDecodeError:
                pass

        await proc.wait()
        stderr_str = (await proc.stderr.read()).decode('utf-8', errors='replace')

        # 输出推理脚本的 stderr 日志
        if stderr_str:
            print("=" * 60)
            print("推理详细日志:")
            print("=" * 60)
            for line in stderr_str.strip().split('\n'):
                if line.strip():
                    print(f"   {line}")
            print("=" * 60)

        # 检查错误
        if proc.returncode != 0:
            print(f"❌ 推理脚本执行失败，返回码: {proc.returncode}")
            raise Exception(f"推理失败: {stderr_str}")

        # 最后一行是最终结果 JSON
        try:
            json_line = stdout_lines[-1]
            inference_results = json.loads(json_line)
        except (json.JSONDecodeError, IndexError) as e:
            print(f"❌ 无法解析推理结果: {e}")
            raise Exception(f"推理结果解析失败: {e}")

        # 检查是否有错误
        if isinstance(inference_results, dict) and "error" in inference_results:
            raise Exception(f"推理错误: {inference_results['error']}")

        # 提取实际保存目录和结果列表
        actual_save_dir = inference_results.get("save_dir", output_dir)
        results_list = inference_results.get("results", [])

        print(f"✅ 推理完成，共处理 {len(results_list)} 张图片")
        print(f"📁 实际保存目录: {actual_save_dir}")

        # 标记实际输出目录需要清理
        if actual_save_dir and actual_save_dir not in temp_dirs_to_cleanup:
            temp_dirs_to_cleanup.append(actual_save_dir)
            print(f"📝 标记清理: 推理输出目录 {actual_save_dir}", flush=True)

        # 解析结果并保存到数据库
        results_data = []
        for idx, img_result in enumerate(results_list):
            try:
                # 获取原始图片路径和名称
                img_path = img_result["path"]
                img_name = os.path.basename(img_path)

                print(f"📸 处理结果 {idx + 1}/{len(inference_results)}: {img_name}")

                # 解析检测结果
                detections = []
                for det in img_result["detections"]:
                    cls_id = det["class_id"]
                    conf_score = det["confidence"]
                    bbox = det["bbox"]

                    detections.append({
                        "class": CLASS_NAMES.get(cls_id, f"class_{cls_id}"),
                        "class_id": cls_id,
                        "confidence": conf_score,
                        "bbox": bbox
                    })

                # 获取图像尺寸
                img_height, img_width = img_result["orig_shape"]  # (height, width)

                # 打印检测详情
                if detections:
                    print(f"   🔍 检测到 {len(detections)} 个目标:")
                    for det in detections:
                        print(f"      - {det['class']}: 置信度 {det['confidence']:.2f}")
                else:
                    print(f"   ✓ 未检测到缺陷")

                # 计算严重程度等级
                severity = calculate_severity_level(detections, img_width, img_height)
                print(f"   📊 严重程度: {severity.get('level_text')} (评分: {severity.get('score')})")

                # 1. 处理原图路径 - 确保原图也在 MinIO 中
                original_img_minio_path = None

                # 首先检查是否已经在 MinIO 路径映射中（从图库选择的图片）
                if img_path in image_minio_map:
                    # 这张图片是从图库选择的，已经在 MinIO 中，直接使用
                    original_img_minio_path = image_minio_map[img_path]
                    print(f"   📋 使用已有 MinIO 路径: {original_img_minio_path}", flush=True)
                elif img_path.startswith(IMAGES_DIR):
                    # 这是临时目录中的图片，需要上传到 MinIO
                    if "temp_" in img_path:
                        # 临时目录（新上传的图片），使用 one/ 前缀，添加时间戳
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        original_minio_object = f"one/{timestamp}_{img_name}"
                    else:
                        # 其他情况（解压的图片等）
                        # 提取相对路径
                        rel_path = os.path.relpath(img_path, IMAGES_DIR).replace("\\", "/")
                        original_minio_object = rel_path

                    # 上传原图到 MinIO
                    print(f"   📤 上传原图到 MinIO: {original_minio_object}", flush=True)
                    upload_orig_success = minio_client.upload_file(
                        bucket_name=BUCKETS["images"],
                        object_name=original_minio_object,
                        file_path=img_path,
                        content_type="image/jpeg"
                    )

                    if upload_orig_success:
                        original_img_minio_path = f"minio://{BUCKETS['images']}/{original_minio_object}"
                        print(f"   ✅ 原图已上传: {original_img_minio_path}", flush=True)
                    else:
                        print(f"   ⚠️ 原图上传失败", flush=True)
                        original_img_minio_path = img_path
                else:
                    # 原图路径可能已经是 MinIO 格式，或者是其他路径
                    original_img_minio_path = img_path

                # 2. 上传结果图片到 MinIO
                result_img_local_path = os.path.join(actual_save_dir, img_name)
                result_img_path = None

                print(f"   📤 准备上传结果图: {result_img_local_path}", flush=True)
                print(f"      本地文件存在: {os.path.exists(result_img_local_path)}", flush=True)

                if os.path.exists(result_img_local_path):
                    # MinIO 对象名: batch_name/img_name
                    minio_object_name = f"{batch_name}/{img_name}"

                    print(f"      目标: {BUCKETS['img_results']}/{minio_object_name}", flush=True)

                    # 上传到 MinIO (bucket: img-results)
                    upload_success = minio_client.upload_file(
                        bucket_name=BUCKETS["img_results"],
                        object_name=minio_object_name,
                        file_path=result_img_local_path,
                        content_type="image/jpeg"
                    )

                    if upload_success:
                        # 使用 MinIO 路径格式
                        result_img_path = f"minio://{BUCKETS['img_results']}/{minio_object_name}"
                        print(f"   ✅ 结果图已上传到 MinIO: {result_img_path}", flush=True)
                    else:
                        # 上传失败，记录错误
                        result_img_path = result_img_local_path
                        print(f"   ❌ 结果图上传 MinIO 失败", flush=True)
                else:
                    result_img_path = result_img_local_path
                    print(f"   ❌ 本地推理结果文件不存在: {result_img_local_path}", flush=True)

                # 计算平均置信度
                avg_conf = sum(d["confidence"] for d in detections) / len(detections) if detections else 0

                result_data = {
                    "originalImage": original_img_minio_path,
                    "resultImage": result_img_path,
                    "detections": detections,
                    "confidence": avg_conf,
                    "severity": severity,
                    "imageIndex": idx
                }
                results_data.append(result_data)

                # 保存到数据库
                try:
                    # 计算相对路径
                    if original_img_minio_path and original_img_minio_path.startswith("minio://"):
                        original_rel = original_img_minio_path.replace(f"minio://{BUCKETS['images']}/", "")
                    else:
                        original_rel = os.path.relpath(original_img_minio_path or img_path, UPLOAD_DIR).replace('\\', '/')

                    if result_img_path and result_img_path.startswith("minio://"):
                        result_rel = result_img_path.replace(f"minio://{BUCKETS['img_results']}/", "")
                    else:
                        result_rel = os.path.relpath(result_img_path or result_img_local_path, UPLOAD_DIR).replace('\\', '/')

                    # 创建数据库记录
                    print(f"   💾 保存到数据库:", flush=True)
                    print(f"      原图: {original_img_minio_path}", flush=True)
                    print(f"      结果: {result_img_path}", flush=True)

                    inference_record = InferenceResult(
                        task_id=task_id,
                        batch_name=batch_name,
                        original_image=original_img_minio_path,  # MinIO 路径
                        result_image=result_img_path,  # MinIO 路径
                        original_image_rel=original_rel,
                        result_image_rel=result_rel,
                        detections=detections,  # JSONB 自动处理
                        detection_count=len(detections),
                        avg_confidence=avg_conf,
                        severity_level=severity.get('level'),
                        severity_score=severity.get('score'),
                        severity_text=severity.get('level_text'),
                        severity_color=severity.get('level_color'),
                        image_width=img_width,
                        image_height=img_height,
                        processing_time=0  # 暂时为0，后续可以添加计时
                    )
                    db.add(inference_record)
                    db.commit()
                    print(f"   ✅ 数据库保存成功", flush=True)
                except Exception as db_error:
                    print(f"⚠️ 保存数据库失败: {db_error}")
                    db.rollback()

                # 发送进度更新
                progress = int((idx + 1) / len(results_list) * 100)
                await manager.send_progress(task_id, {
                    "status": "processing",
                    "progress": progress,
                    "total": len(results_list),
                    "current": idx + 1,
                    "message": f"处理结果中... ({idx + 1}/{len(results_list)})",
                    "currentResult": result_data
                })

                await asyncio.sleep(0.1)  # 让出控制权

            except Exception as e:
                print(f"❌ 处理结果失败: {e}")
                import traceback
                traceback.print_exc()
                continue

        # 发送完成消息
        await manager.send_progress(task_id, {
            "status": "completed",
            "progress": 100,
            "total": len(results_list),
            "current": len(results_list),
            "message": "推理完成",
            "results": results_data,
            "outputDir": actual_save_dir  # 使用实际保存的目录
        })

        print(f"✅ 推理任务完成: {task_id}")

    except Exception as e:
        print(f"❌ 推理任务失败: {e}")
        import traceback
        traceback.print_exc()

        await manager.send_progress(task_id, {
            "status": "failed",
            "progress": 0,
            "message": f"推理失败: {str(e)}"
        })

    finally:
        # 清理临时目录和文件
        print(f"\n🗑️ 开始清理临时文件...", flush=True)
        for temp_dir in temp_dirs_to_cleanup:
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    print(f"   ✅ 已删除临时目录: {temp_dir}", flush=True)
                except Exception as cleanup_error:
                    print(f"   ⚠️ 清理临时目录失败: {temp_dir}, 错误: {cleanup_error}", flush=True)
        print(f"🗑️ 临时文件清理完成\n", flush=True)


# ============ WebSocket 接口 ============
@app.websocket("/ws/inference/{task_id}")
async def websocket_inference(websocket: WebSocket, task_id: str):
    """WebSocket 推理进度推送"""
    await manager.connect(task_id, websocket)
    try:
        while True:
            # 保持连接，接收客户端消息（心跳）
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(task_id)


# ============ 健康检查 ============
@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "service": "inference-service"}


# ============ 模型管理 ============
@app.get("/models")
async def get_models(db: Session = Depends(get_db)):
    """获取检测类型的模型"""
    models = db.query(Model).filter(
        Model.is_active == True,
        Model.model_type == "detection"
    ).all()
    return {
        "code": 0,
        "data": [
            {
                "id": m.id,
                "name": m.name,
                "path": m.path,
                "version": m.version,
                "description": m.description,
                "model_type": m.model_type,
                "createdAt": m.created_at.isoformat() if m.created_at else None
            }
            for m in models
        ],
        "message": "success"
    }


# ============ 图片数据库 ============
@app.get("/images/database")
async def get_image_database():
    """获取图片数据库目录树 - 从 MinIO 读取"""
    result = []

    try:
        print(f"📂 获取图片数据库 (从 MinIO: {BUCKETS['images']})", flush=True)

        # 从 MinIO 获取所有图片对象
        objects = minio_client.list_objects(
            bucket_name=BUCKETS["images"],
            recursive=True
        )

        # 构建目录树结构
        folder_map = {}  # 用于存储文件夹节点

        for obj in objects:
            object_name = obj.object_name

            # 只处理图片文件
            if not object_name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
                continue

            # 分割路径
            path_parts = object_name.split('/')
            filename = path_parts[-1]

            # 构建访问路径
            access_path = f"/uploads/images/{object_name}"

            # 如果在子目录中
            if len(path_parts) > 1:
                # 递归创建父文件夹节点
                current_path = ""
                for i, folder_name in enumerate(path_parts[:-1]):
                    parent_path = current_path
                    current_path = f"{current_path}/{folder_name}" if current_path else folder_name

                    if current_path not in folder_map:
                        folder_map[current_path] = {
                            "id": f"folder_{current_path}",
                            "filename": folder_name,
                            "path": current_path,
                            "relativePath": current_path,
                            "isFolder": True,
                            "children": [],
                            "parent": parent_path
                        }

                # 添加文件到对应文件夹
                parent_folder_path = "/".join(path_parts[:-1])
                file_node = {
                    "id": object_name,
                    "filename": filename,
                    "path": access_path,
                    "fullPath": object_name,
                    "relativePath": object_name,
                    "size": obj.size,
                    "uploadedAt": obj.last_modified.isoformat() if obj.last_modified else None,
                    "isFolder": False
                }

                if parent_folder_path in folder_map:
                    folder_map[parent_folder_path]["children"].append(file_node)
            else:
                # 根目录下的文件
                result.append({
                    "id": object_name,
                    "filename": filename,
                    "path": access_path,
                    "fullPath": object_name,
                    "relativePath": object_name,
                    "size": obj.size,
                    "uploadedAt": obj.last_modified.isoformat() if obj.last_modified else None,
                    "isFolder": False
                })

        # 组织文件夹层级结构
        root_folders = []
        for folder_path, folder_node in folder_map.items():
            parent = folder_node.get("parent")
            if not parent:  # 根级文件夹
                root_folders.append(folder_node)
            elif parent in folder_map:
                folder_map[parent]["children"].append(folder_node)

        # 合并根级文件夹和文件
        result = root_folders + result

        print(f"✅ 图片数据库加载完成，共 {len(result)} 个根级项目", flush=True)
        return {"code": 0, "data": result, "message": "success"}

    except Exception as e:
        print(f"❌ 获取图片数据库失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {"code": 0, "data": [], "message": f"获取失败: {str(e)}"}


# ============ 推理接口 ============
@app.post("/inference/start")
async def start_inference(
    model_id: int = Form(...),
    image_files: Optional[List[UploadFile]] = File(None),
    image_paths: Optional[str] = Form(None),  # JSON 字符串，数组
    conf: float = Form(0.45),
    imgsz: int = Form(1280),
    task_id: Optional[str] = Form(None),  # 任务ID，由前端生成
    db: Session = Depends(get_db)
):
    """
    启动推理任务

    支持三种输入方式:
    1. 上传单张/多张图片 (image_files)
    2. 上传压缩包 (image_files, .zip)
    3. 从图库选择 (image_paths, JSON 字符串数组)
    """
    # 获取模型
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    # 检查模型文件是否存在（支持 MinIO 和本地路径）
    model_path = model.path
    if model_path.startswith("minio://"):
        # MinIO 路径: minio://models/JC/best.pt
        # 提取 bucket 和 object_name
        path_parts = model_path.replace("minio://", "").split("/", 1)
        if len(path_parts) == 2:
            bucket_name, object_name = path_parts
            if not minio_client.file_exists(bucket_name, object_name):
                raise HTTPException(status_code=400, detail=f"模型文件不存在: {model_path}")

            # 下载模型到本地临时目录
            temp_model_dir = os.path.join(os.path.dirname(__file__), "temp_models")
            os.makedirs(temp_model_dir, exist_ok=True)
            local_model_path = os.path.join(temp_model_dir, os.path.basename(object_name))

            # 如果本地没有，则从 MinIO 下载
            if not os.path.exists(local_model_path):
                print(f"📥 从 MinIO 下载模型: {model_path} -> {local_model_path}", flush=True)
                model_data = minio_client.download_file(bucket_name, object_name)
                if model_data:
                    with open(local_model_path, "wb") as f:
                        f.write(model_data)
                    print(f"✅ 模型下载成功", flush=True)
                else:
                    raise HTTPException(status_code=500, detail=f"模型下载失败: {model_path}")
            else:
                print(f"✅ 使用本地缓存的模型: {local_model_path}", flush=True)

            # 使用本地模型路径进行推理
            model_path = local_model_path
        else:
            raise HTTPException(status_code=400, detail=f"无效的模型路径格式: {model_path}")
    else:
        # 本地路径
        if not os.path.exists(model_path):
            raise HTTPException(status_code=400, detail=f"模型文件不存在: {model_path}")

    # 使用前端传来的任务ID，如果没有则生成一个
    if not task_id:
        task_id = str(uuid.uuid4())

    # 获取下一个可用的输出目录（不预先创建，让 YOLO 自己创建）
    output_dir, dir_name = get_next_predict_dir()

    # 收集源图片路径和 MinIO 路径映射
    source_paths = []
    # 图片路径到 MinIO 路径的映射：local_path -> minio_path
    # 用于记录从图库选择的图片，避免重复上传
    image_minio_map = {}

    # 处理上传的文件
    if image_files:
        for file in image_files:
            if file.filename.endswith(('.zip', '.rar', '.7z')):
                # 处理压缩包：解压到 images/时间戳_压缩包名/ 目录
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                zip_name = os.path.splitext(file.filename)[0]  # 去掉扩展名
                extract_dir = os.path.join(IMAGES_DIR, f"{timestamp}_{zip_name}")
                os.makedirs(extract_dir, exist_ok=True)

                # 保存压缩包到临时位置
                zip_path = os.path.join(IMAGES_DIR, file.filename)
                with open(zip_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)

                # 解压
                print(f"📦 解压压缩包: {file.filename} -> {extract_dir}")
                temp_extract_dir = None
                try:
                    # 先解压到临时目录
                    temp_extract_dir = os.path.join(IMAGES_DIR, f"_temp_{timestamp}")
                    os.makedirs(temp_extract_dir, exist_ok=True)

                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(temp_extract_dir)

                    # 检查是否只有一个顶层目录（即压缩包内嵌套了同名文件夹）
                    items = os.listdir(temp_extract_dir)
                    if len(items) == 1 and os.path.isdir(os.path.join(temp_extract_dir, items[0])):
                        # 只有一个文件夹，将其内容（不是文件夹本身）移动到目标目录
                        nested_dir = os.path.join(temp_extract_dir, items[0])
                        print(f"✅ 检测到嵌套目录: {items[0]}，正在展平...")

                        # 将嵌套文件夹内的所有内容移动到目标目录
                        for item in os.listdir(nested_dir):
                            src = os.path.join(nested_dir, item)
                            dst = os.path.join(extract_dir, item)
                            shutil.move(src, dst)

                        # 删除临时目录
                        shutil.rmtree(temp_extract_dir)
                        print(f"✅ 已展平嵌套目录")
                    else:
                        # 多个文件/文件夹，直接移动所有内容到目标目录
                        for item in items:
                            src = os.path.join(temp_extract_dir, item)
                            dst = os.path.join(extract_dir, item)
                            shutil.move(src, dst)
                        # 删除临时目录
                        shutil.rmtree(temp_extract_dir)

                except Exception as e:
                    print(f"❌ 解压失败: {e}")
                    import traceback
                    traceback.print_exc()
                    # 清理临时目录
                    if temp_extract_dir and os.path.exists(temp_extract_dir):
                        shutil.rmtree(temp_extract_dir)
                    raise HTTPException(status_code=400, detail=f"解压失败: {str(e)}")
                finally:
                    # 删除压缩包
                    if os.path.exists(zip_path):
                        os.remove(zip_path)
                        print(f"🗑️ 已删除压缩包: {zip_path}")

                # 收集解压后的图片，上传到 MinIO，然后下载到本地临时目录
                print(f"📤 上传解压后的图片到 MinIO...", flush=True)

                # 创建本地临时目录
                temp_zip_dir = os.path.join(IMAGES_DIR, f"temp_{task_id}")
                os.makedirs(temp_zip_dir, exist_ok=True)

                uploaded_count = 0
                for root, dirs, files in os.walk(extract_dir):
                    for f in files:
                        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
                            local_extracted_path = os.path.join(root, f)

                            # 计算相对路径
                            rel_path = os.path.relpath(local_extracted_path, extract_dir)

                            # MinIO 对象名称: one/{timestamp}_{zip_name}/{rel_path}
                            minio_object_name = f"{timestamp}_{zip_name}/{rel_path}".replace("\\", "/")

                            # 上传到 MinIO
                            with open(local_extracted_path, "rb") as img_file:
                                upload_success = minio_client.upload_file(
                                    bucket_name=BUCKETS["images"],
                                    object_name=minio_object_name,
                                    file_data=img_file,
                                    content_type="image/jpeg"
                                )

                            if upload_success:
                                uploaded_count += 1

                                # 复制到本地临时目录用于推理
                                temp_local_path = os.path.join(temp_zip_dir, f)
                                shutil.copy(local_extracted_path, temp_local_path)
                                source_paths.append(temp_local_path)

                                # 记录这张图片已经上传到 MinIO，避免重复上传
                                minio_path = f"minio://{BUCKETS['images']}/{minio_object_name}"
                                image_minio_map[temp_local_path] = minio_path

                print(f"  ✅ 已上传 {uploaded_count} 张图片到 MinIO", flush=True)

                # 清理解压目录
                shutil.rmtree(extract_dir)
                print(f"🗑️ 已清理解压目录: {extract_dir}", flush=True)
            else:
                # 处理单张图片：上传到 MinIO images/one/ 目录，然后下载到本地临时目录
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                minio_object_name = f"one/{timestamp}_{file.filename}"

                print(f"📤 上传单张图片到 MinIO: {minio_object_name}", flush=True)

                # 上传到 MinIO
                file.file.seek(0)  # 重置文件指针
                upload_success = minio_client.upload_file(
                    bucket_name=BUCKETS["images"],
                    object_name=minio_object_name,
                    file_data=file.file,
                    content_type=file.content_type or "image/jpeg"
                )

                if upload_success:
                    print(f"  ✅ 上传成功", flush=True)

                    # 下载到本地临时目录用于推理
                    temp_one_dir = os.path.join(IMAGES_DIR, f"temp_{task_id}")
                    os.makedirs(temp_one_dir, exist_ok=True)

                    local_path = os.path.join(temp_one_dir, file.filename)
                    image_data = minio_client.download_file(
                        bucket_name=BUCKETS["images"],
                        object_name=minio_object_name
                    )

                    if image_data:
                        with open(local_path, "wb") as f:
                            f.write(image_data)
                        source_paths.append(local_path)

                        # 记录这张图片已经上传到 MinIO，避免重复上传
                        minio_path = f"minio://{BUCKETS['images']}/{minio_object_name}"
                        image_minio_map[local_path] = minio_path

                        print(f"  ✅ 已下载到本地用于推理: {local_path}（MinIO: {minio_path}）", flush=True)
                    else:
                        print(f"  ❌ 下载失败", flush=True)
                else:
                    print(f"  ❌ 上传失败", flush=True)

    # 处理图库路径（从 MinIO 下载到本地临时目录）
    elif image_paths:
        try:
            paths = json.loads(image_paths)
            print(f"📥 从图库选择 {len(paths)} 张图片", flush=True)

            # 创建临时目录用于存放从 MinIO 下载的图片
            temp_images_dir = os.path.join(IMAGES_DIR, f"temp_{task_id}")
            os.makedirs(temp_images_dir, exist_ok=True)

            for path in paths:
                # 提取相对路径
                # path 可能是: /uploads/images/test/xxx.jpg 或 /api/uploads/images/xxx.jpg
                relative_path = path
                if path.startswith("/api/uploads/images/"):
                    relative_path = path.replace("/api/uploads/images/", "")
                elif path.startswith("/uploads/images/"):
                    relative_path = path.replace("/uploads/images/", "")
                elif path.startswith("uploads/images/"):
                    relative_path = path.replace("uploads/images/", "")
                elif path.startswith("/api/system/uploads/images/"):
                    relative_path = path.replace("/api/system/uploads/images/", "")

                print(f"  下载图片: {relative_path}", flush=True)

                # 从 MinIO 下载
                image_data = minio_client.download_file(
                    bucket_name=BUCKETS["images"],
                    object_name=relative_path
                )

                if image_data:
                    # 保存到本地临时目录
                    filename = os.path.basename(relative_path)
                    local_path = os.path.join(temp_images_dir, filename)

                    with open(local_path, "wb") as f:
                        f.write(image_data)

                    source_paths.append(local_path)

                    # 记录这张图片已经在 MinIO 中，不需要重复上传
                    minio_path = f"minio://{BUCKETS['images']}/{relative_path}"
                    image_minio_map[local_path] = minio_path

                    print(f"    ✅ 已下载: {filename}（MinIO: {minio_path}）", flush=True)
                else:
                    print(f"    ⚠️ 下载失败: {relative_path}", flush=True)

        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="image_paths 格式错误")

    if not source_paths:
        raise HTTPException(status_code=400, detail="没有找到可推理的图片")

    print(f"🚀 启动推理任务: {task_id}")
    print(f"   模型: {model.name}")
    print(f"   图片数量: {len(source_paths)}")
    print(f"   输出目录: {output_dir}")

    # 获取批次名称（文件夹名，如 predict0）
    batch_name = os.path.basename(output_dir)

    # 启动后台推理任务（不等待）
    task = asyncio.create_task(run_inference(
        task_id=task_id,
        model_path=model_path,  # 使用处理后的模型路径（可能是本地缓存路径）
        source_paths=source_paths,
        output_dir=output_dir,
        batch_name=batch_name,
        db=db,
        conf=conf,
        imgsz=imgsz,
        image_minio_map=image_minio_map  # 传递 MinIO 路径映射
    ))

    # 添加任务完成回调
    def task_done_callback(t):
        try:
            t.result()  # 获取结果，如果有异常会在这里抛出
        except Exception as e:
            print(f"❌ 推理任务异常: {e}")
            import traceback
            traceback.print_exc()

    task.add_done_callback(task_done_callback)

    return {
        "code": 0,
        "data": {
            "taskId": task_id,
            "imageCount": len(source_paths),
            "outputDir": output_dir
        },
        "message": "推理任务已启动"
    }


# ============ MinIO 文件服务 ============

@app.get("/uploads/images/{file_path:path}")
async def get_image_file(file_path: str):
    """获取图片文件 - 从 MinIO 代理返回"""
    from fastapi.responses import StreamingResponse
    print(f"\n📷 [51033] 请求图片: {file_path}", flush=True)
    result = minio_client.get_file_stream(BUCKETS["images"], file_path)
    if not result:
        print(f"   ❌ 图片不存在: {file_path}", flush=True)
        raise HTTPException(status_code=404, detail="图片不存在")
    response, content_type, content_length = result
    print(f"   ✅ 代理返回成功", flush=True)
    return StreamingResponse(
        response,
        media_type=content_type,
        headers={"Content-Length": str(content_length), "Cache-Control": "max-age=3600"}
    )


@app.get("/uploads/img_results/{file_path:path}")
async def get_inference_result_file(file_path: str):
    """获取推理结果图片 - 从 MinIO 代理返回"""
    from fastapi.responses import StreamingResponse
    print(f"\n📊 [51033] 请求推理结果图片: {file_path}", flush=True)
    result = minio_client.get_file_stream(BUCKETS["img_results"], file_path)
    if not result:
        print(f"   ❌ 推理结果不存在: {file_path}", flush=True)
        raise HTTPException(status_code=404, detail="推理结果不存在")
    response, content_type, content_length = result
    print(f"   ✅ 代理返回成功", flush=True)
    return StreamingResponse(
        response,
        media_type=content_type,
        headers={"Content-Length": str(content_length), "Cache-Control": "max-age=3600"}
    )


if __name__ == "__main__":
    import uvicorn
    print("🚀 启动缺陷检测推理服务...")
    print("📍 访问地址: http://localhost:51033")
    print("📚 API 文档: http://localhost:51033/docs")
    uvicorn.run(app, host="0.0.0.0", port=51033)
