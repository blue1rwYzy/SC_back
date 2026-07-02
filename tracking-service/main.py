"""
车辆追踪服务 - 主入口
端口: 8003
负责: YOLO 车辆追踪、视频处理
"""
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import Dict, Optional, Any
import sys
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
import asyncio
import json
import base64
import cv2
import numpy as np
import io
import re
from copy import deepcopy
import subprocess
from collections import defaultdict, deque

# 添加父目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared import get_db, Model, VideoTrackingTask, TrackingAnalysisReport
from shared.database import SessionLocal
from shared.database import Base, engine
from utils.minio_client import minio_client

app = FastAPI(
    title="车辆追踪服务 API",
    description="高速道路车辆追踪系统 - YOLO 追踪服务",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 获取当前文件所在目录
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
TRACKING_DETECTORS_DIR = os.path.join(CURRENT_DIR, "detectors3")
if TRACKING_DETECTORS_DIR not in sys.path:
    sys.path.insert(0, TRACKING_DETECTORS_DIR)

from detectors import (  # type: ignore
    KinematicEstimator,
    SpeedingDetector,
    AbruptStopDetector,
    StationaryDetector,
    LaneChangeDetector,
    CongestionDetector,
    EventBus,
)
from config import DetectionConfig  # type: ignore

TRACKING_OUTPUT_DIR = os.path.join(BACKEND_DIR, "uploads", "tracking_analysis")
TRACKING_ANALYSIS_VIDEO_DIR = os.path.join(TRACKING_OUTPUT_DIR, "videos")
TRACKING_ANALYSIS_EVENTS_DIR = os.path.join(TRACKING_OUTPUT_DIR, "events")
TRACKING_ANALYSIS_REPORTS_DIR = os.path.join(TRACKING_OUTPUT_DIR, "reports")
TRACKING_ANALYSIS_KEYFRAMES_DIR = os.path.join(TRACKING_OUTPUT_DIR, "keyframes")

# 视频目录配置（使用相对路径）
UPLOAD_DIR = os.path.join(BACKEND_DIR, "uploads")
VIDEOS_DIR = os.path.join(UPLOAD_DIR, "videos")
VID_RESULTS_DIR = os.path.join(UPLOAD_DIR, "vid_results")

# 临时目录（用于临时下载）
TEMP_DIR = os.path.join(BACKEND_DIR, "temp_tracking")
os.makedirs(TEMP_DIR, exist_ok=True)

# 确保目录存在（仅用于临时存储）
os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(VID_RESULTS_DIR, exist_ok=True)
os.makedirs(TRACKING_ANALYSIS_VIDEO_DIR, exist_ok=True)
os.makedirs(TRACKING_ANALYSIS_EVENTS_DIR, exist_ok=True)
os.makedirs(TRACKING_ANALYSIS_REPORTS_DIR, exist_ok=True)
os.makedirs(TRACKING_ANALYSIS_KEYFRAMES_DIR, exist_ok=True)

print(f"📁 临时目录: {TEMP_DIR}")
print(f"📁 视频上传目录: {VIDEOS_DIR}")
print(f"📁 结果输出目录: {VID_RESULTS_DIR}")

# MinIO 桶配置
BUCKETS = {
    "videos": "videos",
    "vid_results": "vid-results",
    "models": "models"
}

# 追踪任务存储（内存存储，实际项目中应该使用数据库）
tracking_tasks: Dict[str, dict] = {}
Base.metadata.create_all(bind=engine, tables=[TrackingAnalysisReport.__table__])

REaltime_EVENT_COLORS = {
    "speeding": (0, 60, 200),
    "abrupt_stop": (30, 30, 180),
    "stationary": (0, 150, 180),
    "lane_change": (180, 120, 50),
    "congestion": (60, 220, 230),
}
REaltime_EVENT_LABELS = {
    "speeding": "SPEED",
    "abrupt_stop": "BRAKE!",
    "stationary": "STOP",
    "lane_change": "LANE",
    "congestion": "JAM",
}


def _safe_copy(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)


def _normalize_tracking_result_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    normalized = path_value.replace("\\", "/")
    if normalized.startswith("minio://"):
        return normalized
    if normalized.startswith("/uploads/"):
        return f"/api/system{normalized}"
    return normalized


def _path_to_public_url(path_value: str | None) -> str | None:
    if not path_value:
        return None
    if path_value.startswith("/api/system/"):
        return path_value
    if path_value.startswith("/uploads/tracking_analysis/"):
        return f"/api/system{path_value}"
    if path_value.startswith("/uploads/"):
        return f"/api/system{path_value}"
    return path_value


def _build_tracking_artifacts_from_disk(task_id: str) -> dict | None:
    """
    从 tracking_analysis 目录回退恢复工件信息。
    主要用于：
    - 服务重启后内存任务字典丢失
    - 旧任务未写入 analysis 字段但磁盘上已经有报告/JSON
    """
    task_dir = os.path.join(TRACKING_OUTPUT_DIR, task_id)
    if not os.path.isdir(task_dir):
        return None

    events_dir = os.path.join(task_dir, "events")
    reports_dir = os.path.join(task_dir, "reports")
    keyframes_dir = os.path.join(task_dir, "keyframes")

    events_json_path = None
    report_html_path = None
    report_md_path = None

    if os.path.isdir(events_dir):
        for name in sorted(os.listdir(events_dir)):
            if name.endswith("_events.json"):
                events_json_path = os.path.join(events_dir, name)
                break

    if os.path.isdir(reports_dir):
        for name in sorted(os.listdir(reports_dir)):
            if name.endswith("_report.html"):
                report_html_path = os.path.join(reports_dir, name)
            elif name.endswith("_report.md"):
                report_md_path = os.path.join(reports_dir, name)

    summary = {"vehicle_count": 0, "event_count": 0, "event_breakdown": {}}
    tracks: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    audit_samples: list[dict[str, Any]] = []
    scene_analysis = None

    if events_json_path and os.path.exists(events_json_path):
        try:
            with open(events_json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            summary = payload.get("summary") or summary
            tracks = payload.get("tracks") or []
            events = payload.get("events") or []
            audit_samples = payload.get("audit_samples") or []
            scene_analysis = payload.get("scene_analysis")
        except Exception:
            pass

    return {
        "analysis_dir": task_dir,
        "events_json_path": events_json_path,
        "events_json_url": f"/api/system/uploads/tracking_analysis/{task_id}/events/{os.path.basename(events_json_path)}" if events_json_path else None,
        "report_html_path": report_html_path,
        "report_html_url": f"/api/system/uploads/tracking_analysis/{task_id}/reports/{os.path.basename(report_html_path)}" if report_html_path else None,
        "report_md_path": report_md_path,
        "report_md_url": f"/api/system/uploads/tracking_analysis/{task_id}/reports/{os.path.basename(report_md_path)}" if report_md_path else None,
        "keyframes_dir": keyframes_dir if os.path.isdir(keyframes_dir) else None,
        "summary": summary,
        "tracks": tracks,
        "events": events,
        "audit_samples": audit_samples,
        "scene_analysis": scene_analysis,
    }


def _build_analysis_artifacts(task_id: str, source_video_path: str, result_video_path: str) -> dict:
    """
    生成与 detectors3 对齐的结构化分析工件。
    这里采用兼容式聚合：
    - 输出事件/轨迹/统计 JSON
    - 生成 HTML 报告
    - 生成任务级目录，便于前端展示和后续扩展
    """
    from detectors3.reports.report_generator import TrafficReportGenerator

    task_dir = os.path.join(TRACKING_OUTPUT_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    events_dir = os.path.join(task_dir, "events")
    reports_dir = os.path.join(task_dir, "reports")
    keyframes_dir = os.path.join(task_dir, "keyframes")
    os.makedirs(events_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)
    os.makedirs(keyframes_dir, exist_ok=True)

    source_name = os.path.splitext(os.path.basename(source_video_path))[0]
    events_json_path = os.path.join(events_dir, f"{source_name}_events.json")
    report_html_path = os.path.join(reports_dir, f"{source_name}_report.html")
    report_md_path = os.path.join(reports_dir, f"{source_name}_report.md")

    cap = cv2.VideoCapture(result_video_path if os.path.exists(result_video_path) else source_video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()

    # 兼容性分析结果：先基于当前任务信息构造统一 JSON
    # 如果 detectors3 未来直接输出 JSON，可在此处无缝替换。
    with open(events_json_path, "w", encoding="utf-8") as f:
        json.dump({
            "video_info": {
                "video_name": os.path.basename(source_video_path),
                "fps": fps,
                "resolution": [width, height],
                "duration_sec": round(frame_count / fps, 2) if fps > 0 else 0,
                "frame_count": frame_count,
            },
            "summary": {
                "vehicle_count": 0,
                "event_count": 0,
                "congestion_segments": 0,
                "event_breakdown": {},
            },
            "tracks": [],
            "events": [],
            "calibration": {},
            "audit_samples": [],
            "method": "detectors3-compatible tracking pipeline",
        }, f, ensure_ascii=False, indent=2)

    generator = TrafficReportGenerator(provider=os.getenv("TRACKING_LLM_PROVIDER", "aistudio"))
    try:
        html = generator.generate(events_json_path, report_html_path)
    except Exception as exc:
        html = f"<html><body><h1>报告生成失败</h1><pre>{exc}</pre></body></html>"
        with open(report_html_path, "w", encoding="utf-8") as f:
            f.write(html)
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("# 追踪报告\n\n当前版本使用兼容式分析工件输出，后续可无缝接入 detectors3 的原始事件 JSON。")

    return {
        "analysis_dir": task_dir,
        "events_json_path": events_json_path,
        "events_json_url": f"/api/system/uploads/tracking_analysis/{task_id}/events/{source_name}_events.json",
        "report_html_path": report_html_path,
        "report_html_url": f"/api/system/uploads/tracking_analysis/{task_id}/reports/{source_name}_report.html",
        "report_md_path": report_md_path,
        "report_md_url": f"/api/system/uploads/tracking_analysis/{task_id}/reports/{source_name}_report.md",
        "keyframes_dir": keyframes_dir,
        "summary": {
            "vehicle_count": 0,
            "event_count": 0,
            "event_breakdown": {},
            "method": "detectors3-compatible tracking pipeline",
        },
        "tracks": [],
        "events": [],
        "audit_samples": [],
        "scene_analysis": None,
    }


def _resolve_local_download_path(source_path: str, temp_dir: str = TEMP_DIR) -> str:
    """把本地路径或 MinIO 路径解析成可用于分析的本地临时文件。"""
    if source_path.startswith("minio://"):
        minio_path = source_path.replace("minio://", "")
        parts = minio_path.split("/", 1)
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="路径格式错误")
        bucket_name, object_name = parts
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        local_path = os.path.join(temp_dir, f"{timestamp}_{os.path.basename(object_name)}")
        file_data = minio_client.download_file(bucket_name=bucket_name, object_name=object_name)
        if not file_data:
            raise HTTPException(status_code=400, detail=f"无法下载文件: {source_path}")
        with open(local_path, "wb") as f:
            f.write(file_data)
        return local_path
    if not os.path.exists(source_path):
        raise HTTPException(status_code=400, detail=f"文件不存在: {source_path}")
    return source_path


def _speed_to_color(speed_kmh: float, max_speed: float = 120.0) -> tuple[int, int, int]:
    ratio = min(speed_kmh / max_speed, 1.0)
    if ratio < 0.5:
        t = ratio * 2
        r = int(60 + t * 195)
        g = int(220 - t * 60)
        b = int(60)
    else:
        t = (ratio - 0.5) * 2
        r = 255
        g = int(160 - t * 160)
        b = int(60 - t * 60)
    return (b, g, r)


def _draw_box_glow(img, x1, y1, x2, y2, color, label, sub_label="", speed_kmh: float = -1):
    box_color = _speed_to_color(speed_kmh) if speed_kmh >= 0 else color
    cv2.rectangle(img, (x1, y1), (x2, y2), box_color, 2, cv2.LINE_AA)
    txt = label + (" | " + sub_label if sub_label else "")
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(txt, font, 0.55, 1)
    pad = 6
    bg_h = th + pad * 2
    bg_w = tw + pad * 2
    bg_y1 = max(0, y1 - bg_h - 2)
    bg_y2 = y1
    bg_x1 = x1
    bg_x2 = min(img.shape[1], x1 + bg_w)
    if bg_y2 > bg_y1 and bg_x2 > bg_x1:
        bg_color = (int(box_color[0] * 0.6), int(box_color[1] * 0.6), int(box_color[2] * 0.6))
        cv2.rectangle(img, (bg_x1, bg_y1), (bg_x2, bg_y2), bg_color, -1)
        cv2.putText(img, txt, (bg_x1 + pad, bg_y1 + th + pad - 2),
                    font, 0.55, (255, 255, 255), 1, cv2.LINE_AA)


def _draw_corner_brackets(img, color=(60, 120, 200), thickness=2, length=30):
    h, w = img.shape[:2]
    corners = [
        ((0, 0), (length, 0), (0, length)),
        ((w - 1, 0), (-length, 0), (0, length)),
        ((w - 1, h - 1), (-length, 0), (0, -length)),
        ((0, h - 1), (length, 0), (0, -length)),
    ]
    for (cx, cy), (dx1, dy1), (dx2, dy2) in corners:
        cv2.line(img, (cx, cy), (cx + dx1, cy + dy1), color, thickness)
        cv2.line(img, (cx, cy), (cx + dx2, cy + dy2), color, thickness)


def _draw_speed_curve(panel_img, x0, y0, w, h, speed_history):
    if len(speed_history) < 2:
        return y0
    cv2.rectangle(panel_img, (x0, y0), (x0 + w, y0 + h), (15, 15, 30), -1)
    cv2.rectangle(panel_img, (x0, y0), (x0 + w, y0 + h), (80, 80, 120), 1)
    cv2.putText(panel_img, "Speed Curve (km/h)", (x0 + 4, y0 + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 160, 220), 1, cv2.LINE_AA)
    chart_x0 = x0 + 4
    chart_y0 = y0 + 18
    chart_w = w - 8
    chart_h = h - 22
    speeds = [s for _, s in speed_history]
    max_s = max(speeds[-50:]) if speeds[-50:] else 120
    max_s = max(max_s * 1.2, 20)
    recent = speed_history[-50:]
    pts = []
    for i, (_, sp) in enumerate(recent):
        px = int(chart_x0 + (i / max(len(recent) - 1, 1)) * chart_w)
        py = int(chart_y0 + chart_h * (1 - sp / max_s))
        pts.append((px, py))
    pts_fill = pts + [(pts[-1][0], chart_y0 + chart_h), (pts[0][0], chart_y0 + chart_h)]
    overlay = panel_img.copy()
    cv2.fillPoly(overlay, np.array([pts_fill], dtype=np.int32), (20, 50, 90))
    cv2.addWeighted(overlay, 0.4, panel_img, 0.6, 0, panel_img)
    for i in range(len(pts) - 1):
        color = _speed_to_color((recent[i][1] + recent[i + 1][1]) / 2)
        cv2.line(panel_img, pts[i], pts[i + 1], color, 2, cv2.LINE_AA)
    if pts:
        last = pts[-1]
        cv2.circle(panel_img, last, 4, (255, 255, 255), -1)
        cv2.circle(panel_img, last, 4, color, 2)
    return y0 + h + 8


def _draw_traffic_meter(panel_img, x0, y0, w, n_vehicles, n_lanes=3):
    cv2.putText(panel_img, "Traffic Flow", (x0 + 4, y0 + 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 160, 220), 1, cv2.LINE_AA)
    bar_x0 = x0 + 4
    bar_y0 = y0 + 16
    bar_w = w - 8
    bar_h = 16
    cv2.rectangle(panel_img, (bar_x0, bar_y0), (bar_x0 + bar_w, bar_y0 + bar_h), (25, 25, 45), -1)
    cv2.rectangle(panel_img, (bar_x0, bar_y0), (bar_x0 + bar_w, bar_y0 + bar_h), (60, 60, 90), 1)
    density = min(n_vehicles / (n_lanes * 5), 1.0)
    fill_w = int(bar_w * density)
    if density < 0.4:
        fill_color = (50, 220, 120)
    elif density < 0.7:
        fill_color = (60, 220, 220)
    else:
        fill_color = (50, 80, 240)
    if fill_w > 0:
        panel_img[bar_y0:bar_y0 + bar_h, bar_x0:bar_x0 + fill_w] = fill_color
    for i in range(1, n_lanes):
        x = bar_x0 + int(bar_w * i / n_lanes)
        cv2.line(panel_img, (x, bar_y0), (x, bar_y0 + bar_h), (80, 80, 100), 1)
    return y0 + bar_h + 26


def _draw_event_timeline(panel_img, x0, y0, w, recent_events, fps):
    if not recent_events:
        return y0
    cv2.putText(panel_img, "Event Timeline", (x0 + 4, y0 + 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 160, 220), 1, cv2.LINE_AA)
    bar_x0 = x0 + 4
    bar_y0 = y0 + 16
    bar_w = w - 8
    bar_h = 12
    cv2.rectangle(panel_img, (bar_x0, bar_y0), (bar_x0 + bar_w, bar_y0 + bar_h), (20, 20, 35), -1)
    cv2.rectangle(panel_img, (bar_x0, bar_y0), (bar_x0 + bar_w, bar_y0 + bar_h), (55, 55, 85), 1)
    for ev in recent_events[-20:]:
        t = ev.frame_idx / fps
        px = int(bar_x0 + (t % 30) / 30 * bar_w)
        color = REaltime_EVENT_COLORS.get(ev.event_type, (200, 200, 200))
        cv2.circle(panel_img, (px, bar_y0 + bar_h // 2), 3, color, -1)
    return y0 + bar_h + 26


def _draw_realtime_panel(img, frame_idx, fps, totals, bus, x_off, est, calib_ready):
    h, w = img.shape[:2]
    panel_w = w - x_off
    overlay = img.copy()
    for x in range(x_off, w):
        ratio = (x - x_off) / max(panel_w - 1, 1)
        overlay[:, x] = np.clip(np.array([
            int(20 * (1 - ratio * 0.3)),
            int(20 * (1 - ratio * 0.3)),
            int(28 * (1 - ratio * 0.3)),
        ]) * 0.85, 0, 255)
    cv2.addWeighted(overlay[:, x_off:], 0.95, img[:, x_off:], 0.05, 0, img[:, x_off:])
    cv2.line(img, (x_off, 0), (x_off, h), (40, 80, 160), 2)
    cv2.line(img, (x_off + 3, 0), (x_off + 3, h), (20, 40, 80), 1)
    px = x_off + 10
    y = 22
    cv2.rectangle(img, (px - 6, y - 16), (px + 240, y + 6), (20, 50, 120), -1)
    cv2.rectangle(img, (px - 6, y - 16), (px + 240, y + 6), (60, 120, 200), 1)
    cv2.putText(img, "INTELLIGENT TRAFFIC SYSTEM", (px + 2, y - 1),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 210, 255), 1, cv2.LINE_AA)
    y += 20
    status_color = (60, 220, 120) if calib_ready else (220, 200, 60)
    status_text = "ACTIVE" if calib_ready else "CALIBRATING"
    cv2.circle(img, (px + 4, y - 4), 4, status_color, -1)
    cv2.putText(img, f"  {status_text}  |  {frame_idx/fps:.1f}s  |  F:{frame_idx}",
                (px + 2, y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 160, 190), 1, cv2.LINE_AA)
    y += 14
    if calib_ready:
        diag = est.diagnostics()
        ppm_med = diag["scale_diag"].get("ppm_median", 0)
        cv2.putText(img, f"PPM: {ppm_med:.1f}  |  Vehicles: {len(est._tracks)}",
                    (px, y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (100, 140, 180), 1, cv2.LINE_AA)
    y += 10
    cv2.line(img, (px, y), (w - 10, y), (40, 60, 100), 1)
    y += 12
    event_stats = [
        ("SPEED", totals.get("speeding", 0), (0, 60, 200), 20),
        ("BRAKE", totals.get("abrupt_stop", 0), (30, 30, 180), 10),
        ("LANE", totals.get("lane_change", 0), (180, 120, 50), 15),
    ]
    for label, count, color, max_ref in event_stats:
        cv2.putText(img, f"{label}", (px, y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)
        cv2.putText(img, f"{count:>3}", (px + 50, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 230), 1, cv2.LINE_AA)
        bar_x = px + 80
        bar_w = panel_w - 100
        bar_h = 6
        bar_y = y - 6
        cv2.rectangle(img, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (25, 25, 40), -1)
        fill_w = int(bar_w * min(count / max_ref, 1.0)) if max_ref > 0 else 0
        if fill_w > 0:
            cv2.rectangle(img, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), color, -1)
        cv2.rectangle(img, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (50, 50, 70), 1)
        y += 18
    cv2.line(img, (px, y), (w - 10, y), (60, 60, 100), 1)
    y += 16
    n_veh = len(est._tracks)
    y = _draw_traffic_meter(img, px, y, panel_w - 20, n_veh)
    y += 4
    speed_history = getattr(est, "_realtime_speed_history", deque(maxlen=200))
    if not hasattr(est, "_realtime_speed_history"):
        est._realtime_speed_history = speed_history
    chart_h = min(80, (h - y - 20) // 3)
    if chart_h > 30:
        y = _draw_speed_curve(img, px, y, panel_w - 20, chart_h, list(speed_history))
    if h - y - 20 > 30:
        recent = bus.recent(frame_idx, window_frames=int(30 * fps))
        y = _draw_event_timeline(img, px, y, panel_w - 20, recent, fps)
    y += 4
    cv2.line(img, (px, y), (w - 10, y), (60, 60, 100), 1)
    y += 14
    cv2.putText(img, "Recent Events:", (px, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 140, 200), 1, cv2.LINE_AA)
    y += 18
    recent_evs = bus.recent(frame_idx, window_frames=int(30 * fps))[-10:]
    if not recent_evs:
        cv2.putText(img, "  (none detected)", (px, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (80, 80, 100), 1)
    else:
        for ev in reversed(recent_evs):
            color = REaltime_EVENT_COLORS.get(ev.event_type, (200, 200, 200))
            tag = REaltime_EVENT_LABELS.get(ev.event_type, ev.event_type[:5])
            t = ev.frame_idx / fps
            line = f"[{t:5.1f}s] #{ev.track_id:>3} {tag}"
            cv2.putText(img, line, (px, y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1, cv2.LINE_AA)
            y += 15
            if y > h - 12:
                break


def _run_detectors3_analysis(
    task_id: str,
    video_path: str,
    result_video_path: str,
    enable_llm_report: bool = False,
    enable_vlm_check: bool = False,
) -> dict:
    """
    使用 detectors3 的统一输出格式，构建任务分析工件。
    直接调用 detectors3/main.py 执行 headless 分析，生成事件 JSON、报告和关键帧。
    """
    task_dir = os.path.join(TRACKING_OUTPUT_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)
    detector_output_dir = os.path.join(task_dir, "detectors3_outputs")
    detector_reports_dir = os.path.join(detector_output_dir, "reports")
    detector_keyframes_dir = os.path.join(detector_output_dir, "keyframes")
    if os.path.isdir(detector_output_dir):
        shutil.rmtree(detector_output_dir)
    os.makedirs(detector_reports_dir, exist_ok=True)
    os.makedirs(detector_keyframes_dir, exist_ok=True)
    tracker_yaml = os.path.join(TRACKING_DETECTORS_DIR, "bytetrack.yaml")
    if os.path.exists(tracker_yaml):
        _safe_copy(tracker_yaml, os.path.join(detector_output_dir, "bytetrack.yaml"))

    source_video = _resolve_local_download_path(video_path)
    model_path = tracking_tasks[task_id].get("model_path") or ""
    if model_path.startswith("minio://"):
        model_path = _resolve_local_download_path(model_path)

    analysis_video_path = os.path.join(TRACKING_ANALYSIS_VIDEO_DIR, f"{task_id}.mp4")
    events_json_path = os.path.join(TRACKING_ANALYSIS_EVENTS_DIR, f"{task_id}_events.json")

    cmd = [
        sys.executable,
        os.path.join(TRACKING_DETECTORS_DIR, "main.py"),
        "--video", source_video,
        "--model", model_path,
        "--no-show",
        "--save-keyframes",
        "--output", analysis_video_path,
        "--events-json", events_json_path,
    ]
    if enable_llm_report:
        cmd.extend(["--enable-llm-report", "--report-format", "html"])
    if enable_vlm_check:
        cmd.append("--enable-vlm-check")

    env = os.environ.copy()
    env.setdefault("MPLCONFIGDIR", os.path.join(BACKEND_DIR, "temp_tracking", "mplconfig"))
    env.setdefault("HF_HOME", os.path.join(BACKEND_DIR, "temp_tracking", "hf_cache"))
    env.setdefault("TRANSFORMERS_CACHE", os.path.join(BACKEND_DIR, "temp_tracking", "hf_cache", "transformers"))
    env.setdefault("HF_HUB_CACHE", os.path.join(BACKEND_DIR, "temp_tracking", "hf_cache", "hub"))
    env.setdefault("HUGGINGFACE_HUB_CACHE", os.path.join(BACKEND_DIR, "temp_tracking", "hf_cache", "hub"))
    env.setdefault("TRACKING_LLM_TIMEOUT", "8")
    env.setdefault("TRACKING_VLM_TIMEOUT", "8")
    env.setdefault("TRACKING_MAX_VLM_CHECKS", "6")
    env["PYTHONPATH"] = TRACKING_DETECTORS_DIR + os.pathsep + env.get("PYTHONPATH", "")

    try:
        subprocess.run(
            cmd,
            cwd=detector_output_dir,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=7200,
        )
    except subprocess.CalledProcessError as exc:
        print(f"[{task_id}] detectors3 执行失败: {exc.stderr}", flush=True)
        if not os.path.exists(events_json_path):
            # 回退到任务级工件构造，避免整条追踪链路失败
            return _build_analysis_artifacts(task_id, source_video, result_video_path)
        print(f"[{task_id}] detectors3 已生成事件 JSON，继续生成报告工件", flush=True)

    if not os.path.exists(events_json_path):
        raise FileNotFoundError(f"detectors3 未生成事件 JSON: {events_json_path}")

    with open(events_json_path, "r", encoding="utf-8") as f:
        event_data = json.load(f)

    report_html_path = os.path.join(TRACKING_ANALYSIS_REPORTS_DIR, f"{task_id}_report.html")
    report_md_path = os.path.join(TRACKING_ANALYSIS_REPORTS_DIR, f"{task_id}_report.md")
    detector_reports_output_dir = os.path.join(detector_output_dir, "outputs", "reports")
    detector_keyframes_output_dir = os.path.join(detector_output_dir, "outputs", "keyframes")
    report_html_source = os.path.join(detector_reports_output_dir, "traffic_report.html")
    report_md_source = os.path.join(detector_reports_output_dir, "traffic_report.md")
    scene_report_source = os.path.join(detector_reports_output_dir, "intelligent_scene_analysis.md")

    if not os.path.exists(report_html_source):
        try:
            from detectors3.reports.report_generator import TrafficReportGenerator
            generator = TrafficReportGenerator(provider=os.getenv("TRACKING_LLM_PROVIDER", "aistudio"))
            generator.generate_html_from_json(events_json_path, report_html_path)
        except Exception as exc:
            print(f"[{task_id}] HTML 报告补生成失败: {exc}", flush=True)
            with open(report_html_path, "w", encoding="utf-8") as f:
                f.write("<html><body><h1>追踪报告</h1><p>HTML 报告生成失败，请查看事件 JSON。</p></body></html>")
    else:
        _safe_copy(report_html_source, report_html_path)

    if os.path.exists(report_md_source):
        _safe_copy(report_md_source, report_md_path)
    elif os.path.exists(scene_report_source):
        _safe_copy(scene_report_source, report_md_path)
    else:
        with open(report_md_path, "w", encoding="utf-8") as f:
            f.write("# 追踪报告\n\n未生成 Markdown 报告。")

    keyframes_dir = os.path.join(TRACKING_OUTPUT_DIR, task_id, "keyframes")
    os.makedirs(keyframes_dir, exist_ok=True)
    if os.path.isdir(detector_keyframes_output_dir):
        for name in os.listdir(detector_keyframes_output_dir):
            src = os.path.join(detector_keyframes_output_dir, name)
            dst = os.path.join(keyframes_dir, name)
            if os.path.isfile(src):
                _safe_copy(src, dst)

    analysis_video_url = f"/api/system/uploads/tracking_analysis/videos/{task_id}.mp4"
    events_json_url = f"/api/system/uploads/tracking_analysis/events/{task_id}_events.json"
    report_html_url = f"/api/system/uploads/tracking_analysis/reports/{task_id}_report.html"
    report_md_url = f"/api/system/uploads/tracking_analysis/reports/{task_id}_report.md"

    return {
        "analysis_dir": task_dir,
        "events_json_path": events_json_path,
        "events_json_url": events_json_url,
        "report_html_path": report_html_path,
        "report_html_url": report_html_url,
        "report_md_path": report_md_path,
        "report_md_url": report_md_url,
        "analysis_video_path": analysis_video_path,
        "analysis_video_url": analysis_video_url,
        "keyframes_dir": keyframes_dir,
        "summary": event_data.get("summary", {}),
        "tracks": event_data.get("tracks", []),
        "events": event_data.get("events", []),
        "audit_samples": event_data.get("audit_samples", []),
        "scene_analysis": event_data.get("scene_analysis"),
        "video_info": event_data.get("video_info", {}),
    }


def _save_tracking_report_record(
    task_id: str,
    analysis_artifacts: dict[str, Any],
    enable_llm_report: bool,
    enable_vlm_check: bool,
) -> None:
    """把 detectors3 报告文件索引写入 PostgreSQL。"""
    if not analysis_artifacts:
        return

    db = SessionLocal()
    try:
        video_info = analysis_artifacts.get("video_info") or {}
        summary = analysis_artifacts.get("summary") or {}
        existing = (
            db.query(TrackingAnalysisReport)
            .filter(TrackingAnalysisReport.task_id == task_id)
            .first()
        )
        payload = {
            "report_type": "traffic",
            "title": f"高速公路车辆追踪报告 - {task_id[:8]}",
            "video_name": video_info.get("video_name"),
            "html_path": analysis_artifacts.get("report_html_path"),
            "html_url": analysis_artifacts.get("report_html_url"),
            "md_path": analysis_artifacts.get("report_md_path"),
            "md_url": analysis_artifacts.get("report_md_url"),
            "events_json_path": analysis_artifacts.get("events_json_path"),
            "events_json_url": analysis_artifacts.get("events_json_url"),
            "analysis_video_path": analysis_artifacts.get("analysis_video_path"),
            "analysis_video_url": analysis_artifacts.get("analysis_video_url"),
            "llm_enabled": enable_llm_report,
            "vlm_enabled": enable_vlm_check,
            "summary": summary,
        }
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
        else:
            db.add(TrackingAnalysisReport(task_id=task_id, **payload))
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"[{task_id}] 保存报告索引失败: {exc}", flush=True)
    finally:
        db.close()


def _serialize_tracking_report(report: TrackingAnalysisReport) -> dict[str, Any]:
    """序列化报告索引，供前端列表和详情页使用。"""
    return {
        "id": report.id,
        "task_id": report.task_id,
        "report_type": report.report_type,
        "title": report.title,
        "video_name": report.video_name,
        "html_path": report.html_path,
        "html_url": report.html_url,
        "md_path": report.md_path,
        "md_url": report.md_url,
        "events_json_path": report.events_json_path,
        "events_json_url": report.events_json_url,
        "analysis_video_path": report.analysis_video_path,
        "analysis_video_url": report.analysis_video_url,
        "llm_enabled": report.llm_enabled,
        "vlm_enabled": report.vlm_enabled,
        "summary": report.summary or {},
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


def _resolve_report_file_path(report: TrackingAnalysisReport, report_format: str) -> tuple[str, str]:
    normalized_format = report_format.lower()
    if normalized_format == "md":
        file_path = report.md_path or report.html_path
        media_type = "text/plain; charset=utf-8"
    else:
        file_path = report.html_path or report.md_path
        media_type = "text/html; charset=utf-8" if report.html_path else "text/plain; charset=utf-8"

    if not file_path:
        raise HTTPException(status_code=404, detail="报告文件路径不存在")

    abs_path = os.path.abspath(file_path)
    allowed_root = os.path.abspath(TRACKING_OUTPUT_DIR)
    if not abs_path.startswith(allowed_root + os.sep):
        raise HTTPException(status_code=403, detail="报告文件路径非法")
    if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="报告文件不存在")
    return abs_path, media_type


def _normalize_tracking_report_html(content: str) -> str:
    """把 detectors3 原始报告渲染为低饱和、业务报告风格；兼容历史 HTML。"""
    replacements = {
        "🚗 智能交通视频": "高速公路车辆追踪",
        "智能交通视频": "高速公路车辆追踪",
        "智能交通分析报告": "高速公路车辆追踪分析报告",
        "智能交通视频分析系统": "高速公路车辆追踪分析系统",
        "基于深度学习 + 多模型融合的交通场景智能分析系统": "高速公路车辆追踪与事件分析",
        "基于深度学习 + 多模型融合": "车辆追踪与交通事件分析",
        "🤖 AI 智能分析": "辅助分析意见",
        "AI 智能分析": "辅助分析意见",
        "🔍 AI 场景分析": "场景复核",
        "AI 场景分析": "场景复核",
        "📊 数据可视化": "数据统计",
        "⏱ 事件时间轴": "事件时间轴",
        "🚨 异常事件详情": "异常事件详情",
        "🏆 车辆速度排行 (TOP 10)": "车辆速度排行 TOP 10",
        "⚖️ 事故责任判定": "事故责任判定",
        "🚨 违法行为识别": "违法行为识别",
        "📊 安全风险评估": "安全风险评估",
        "⚙️ 系统校准信息": "系统校准信息",
        "📁 ": "",
        "🎬 ": "",
        "📐 ": "",
        "🕐 ": "",
        "· 基于深度学习 + 多模型融合": "",
    }
    for old, new in replacements.items():
        content = content.replace(old, new)

    override_css = """
<style id="tracking-report-business-style">
  :root {
    --bg: #f4f6f8 !important;
    --bg2: #ffffff !important;
    --bg3: #eef2f6 !important;
    --text: #1f2933 !important;
    --text2: #4b5563 !important;
    --text3: #6b7280 !important;
    --accent: #2f4f66 !important;
    --accent2: #2f4f66 !important;
    --red: #9f3a38 !important;
    --orange: #9a6a22 !important;
    --green: #2f6b4f !important;
    --blue: #355f7d !important;
    --border: #d8dee6 !important;
    --shadow: rgba(31, 41, 51, 0.08) !important;
  }
  html, body {
    background: #f4f6f8 !important;
    color: #1f2933 !important;
    font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif !important;
  }
  .container {
    max-width: 1180px !important;
    padding: 24px 28px !important;
  }
  .header {
    background: #fff !important;
    border: 1px solid #cfd7df !important;
    border-radius: 2px !important;
    padding: 24px 28px !important;
    box-shadow: none !important;
  }
  .header::before { display: none !important; }
  .header h1 {
    color: #17212b !important;
    font-size: 24px !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
  }
  .header h1 span { color: #17212b !important; }
  .header .subtitle {
    color: #5b6673 !important;
    font-size: 13px !important;
  }
  .header .meta {
    border-top: 1px solid #e5e9ef !important;
    color: #5b6673 !important;
    gap: 18px !important;
    padding-top: 12px !important;
  }
  .cards {
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)) !important;
    gap: 10px !important;
  }
  .card,
  section,
  .chart-box,
  .scene-card,
  .responsibility-card,
  .violation-card,
  .risk-card,
  .risk-detail,
  .ai-analysis {
    background: #fff !important;
    border: 1px solid #d8dee6 !important;
    border-radius: 2px !important;
    box-shadow: none !important;
  }
  .card {
    padding: 16px !important;
    text-align: left !important;
    transition: none !important;
  }
  .card:hover {
    transform: none !important;
    border-color: #c3ccd6 !important;
  }
  .card .value {
    color: #243746 !important;
    font-size: 30px !important;
    font-weight: 600 !important;
  }
  .card.red .value,
  .card.orange .value,
  .card.green .value {
    color: #243746 !important;
  }
  .card .label {
    color: #66717f !important;
    font-size: 12px !important;
  }
  section {
    padding: 20px 22px !important;
    margin-bottom: 16px !important;
  }
  section h2,
  .risk-detail h3,
  .ai-analysis h3,
  .ai-analysis h4 {
    color: #17212b !important;
  }
  section h2 {
    font-size: 17px !important;
    border-bottom: 1px solid #d8dee6 !important;
  }
  .section-desc,
  .footer,
  .empty,
  .scene-time,
  .scene-meta,
  .vlm-cell {
    color: #697586 !important;
  }
  table {
    border: 1px solid #d8dee6 !important;
  }
  th {
    background: #eef2f6 !important;
    color: #344556 !important;
    border-bottom: 1px solid #cfd7df !important;
    font-weight: 600 !important;
  }
  td {
    color: #1f2933 !important;
    border-bottom: 1px solid #e5e9ef !important;
  }
  tr:hover td { background: #f7f9fb !important; }
  .badge,
  .risk-card .risk-level {
    border-radius: 2px !important;
    border: 1px solid #cfd7df !important;
    background: #f5f7f9 !important;
    color: #344556 !important;
    font-weight: 500 !important;
  }
  .badge-speeding,
  .badge-abrupt_stop,
  .badge-high,
  .badge-critical,
  .risk-card .risk-level.poor,
  .risk-card .risk-level.dangerous,
  .factor-value.high,
  .severity.high {
    color: #8f3431 !important;
    background: #fbf1f0 !important;
    border-color: #e6c2c0 !important;
  }
  .badge-lane_change,
  .badge-medium,
  .risk-card .risk-level.fair,
  .factor-value.medium,
  .severity.medium {
    color: #7a571b !important;
    background: #faf4e8 !important;
    border-color: #e5d4ad !important;
  }
  .badge-stationary,
  .badge-congestion,
  .badge-low,
  .risk-card .risk-level.excellent,
  .risk-card .risk-level.good,
  .factor-value.low,
  .severity.low {
    color: #2f6b4f !important;
    background: #edf7f1 !important;
    border-color: #bfd8c9 !important;
  }
  .responsibility-title,
  .responsibility-verdict .verdict-text,
  .violation-title {
    color: #17212b !important;
  }
  .responsibility-verdict {
    background: #f5f7f9 !important;
    border-radius: 2px !important;
  }
  .violation-icon,
  .risk-card .risk-icon {
    display: none !important;
  }
  svg text {
    fill: #4b5563 !important;
  }
  .footer {
    border-top: 1px solid #d8dee6 !important;
    margin-top: 8px !important;
  }
</style>
"""
    if "</head>" in content:
        content = content.replace("</head>", f"{override_css}\n</head>", 1)
    else:
        content = f"{override_css}\n{content}"
    content = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", content)
    return content


# WebSocket 连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[task_id] = websocket
        print(f"[WebSocket] 客户端连接: {task_id}")

    def disconnect(self, task_id: str):
        if task_id in self.active_connections:
            del self.active_connections[task_id]
            print(f"[WebSocket] 客户端断开: {task_id}")

    async def send_frame(self, task_id: str, frame_data: dict):
        """发送推理帧数据"""
        if task_id in self.active_connections:
            try:
                await self.active_connections[task_id].send_json(frame_data)
            except Exception as e:
                print(f"[WebSocket] 发送失败: {e}")
                self.disconnect(task_id)

    def send_frame_sync(self, task_id: str, frame_data: dict):
        """同步方式发送帧数据（用于后台线程）"""
        if task_id in self.active_connections:
            try:
                # 在后台线程中，直接创建新的事件循环来发送消息
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.active_connections[task_id].send_json(frame_data))
                finally:
                    loop.close()
            except Exception as e:
                print(f"[WebSocket] 发送失败: {e}")
                self.disconnect(task_id)

manager = ConnectionManager()


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "车辆追踪服务",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/tracking/models")
async def get_tracking_models(db: Session = Depends(get_db)):
    """获取车辆追踪模型列表（仅返回追踪模型）"""
    # 只查询追踪模型
    models = db.query(Model).filter(Model.model_type == "tracking").all()

    model_list = [
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
    ]

    return {
        "code": 0,
        "data": model_list,
        "message": "success"
    }


@app.post("/tracking/upload-video")
async def upload_video(video: UploadFile = File(...)):
    """上传并转换视频,返回可播放的视频 URL"""
    # 验证视频文件
    if not video.content_type or not video.content_type.startswith('video/'):
        raise HTTPException(status_code=400, detail="请上传视频文件")

    # 生成时间戳文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    original_name = os.path.splitext(video.filename)[0]
    file_ext = os.path.splitext(video.filename)[1] or '.mp4'
    video_filename = f"{timestamp}_{original_name}{file_ext}"

    # 临时文件路径
    temp_video_path = os.path.join(TEMP_DIR, f"{timestamp}_original{file_ext}")
    converted_video_path = os.path.join(TEMP_DIR, video_filename)

    try:
        print(f"[{timestamp}] 📹 开始上传视频: {video.filename}", flush=True)

        # 先保存到临时文件
        with open(temp_video_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)

        print(f"[{timestamp}] 💾 临时保存完成: {temp_video_path}", flush=True)

        # 使用 ffmpeg 转换为浏览器兼容格式
        import subprocess
        print(f"[{timestamp}] 🔄 转换视频为浏览器兼容格式...", flush=True)

        try:
            subprocess.run([
                'ffmpeg',
                '-i', temp_video_path,
                '-c:v', 'libx264',              # H.264 视频编码
                '-preset', 'medium',             # 编码速度
                '-crf', '23',                   # 质量参数
                '-profile:v', 'baseline',        # 使用 baseline profile 提高兼容性
                '-level', '3.0',                # H.264 level
                '-pix_fmt', 'yuv420p',          # 像素格式
                '-c:a', 'aac',                  # AAC 音频编码
                '-b:a', '128k',                 # 音频比特率
                '-ar', '44100',                 # 音频采样率
                '-movflags', '+faststart',      # moov atom 前置,支持流式播放和随机访问
                '-y',                           # 覆盖输出
                converted_video_path
            ], check=True, capture_output=True, timeout=300)

            print(f"[{timestamp}] ✅ 视频转换完成", flush=True)
        except subprocess.CalledProcessError as e:
            print(f"[{timestamp}] ⚠️ ffmpeg 转换失败: {e.stderr.decode()}", flush=True)
            # 转换失败,使用原视频
            shutil.copy(temp_video_path, converted_video_path)
            print(f"[{timestamp}] 使用原始视频", flush=True)
        except FileNotFoundError:
            print(f"[{timestamp}] ⚠️ 未找到 ffmpeg,使用原始视频", flush=True)
            shutil.copy(temp_video_path, converted_video_path)

        # 上传到MinIO
        print(f"[{timestamp}] ☁️ 上传视频到MinIO...", flush=True)

        with open(converted_video_path, "rb") as f:
            video_data = f.read()

        upload_success = minio_client.upload_file(
            bucket_name=BUCKETS["videos"],
            object_name=video_filename,
            file_data=io.BytesIO(video_data),
            content_type="video/mp4"
        )

        if not upload_success:
            raise HTTPException(status_code=500, detail="上传视频到MinIO失败")

        video_minio_path = f"minio://{BUCKETS['videos']}/{video_filename}"
        print(f"[{timestamp}] ✅ 视频已上传到MinIO: {video_minio_path}", flush=True)

        # 清理临时文件
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        if os.path.exists(converted_video_path):
            os.remove(converted_video_path)

        # 返回视频 URL
        video_url = f"/api/system/uploads/videos/{video_filename}"
        return {
            "code": 0,
            "data": {
                "filename": video.filename,
                "video_url": video_url,
                "video_path": video_minio_path  # 返回MinIO路径
            },
            "message": "视频上传成功"
        }

    except Exception as e:
        # 清理临时文件
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        if os.path.exists(converted_video_path):
            os.remove(converted_video_path)
        raise HTTPException(status_code=500, detail=f"上传视频失败: {str(e)}")


@app.websocket("/tracking/ws/{task_id}")
async def websocket_tracking(websocket: WebSocket, task_id: str):
    """WebSocket 连接用于实时推理显示"""
    await manager.connect(task_id, websocket)
    try:
        while True:
            # 保持连接活跃
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(task_id)


@app.post("/tracking/start")
async def start_tracking(
    video_path: str = Form(...),
    model_id: int = Form(...),
    enable_llm_report: bool = Form(False),
    enable_vlm_check: bool = Form(False),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """开始车辆追踪 - 使用已上传的视频路径"""
    print(f"\n🎬 开始追踪请求:", flush=True)
    print(f"   📹 视频路径: {video_path}", flush=True)
    print(f"   🤖 模型ID: {model_id}", flush=True)
    print(f"   📝 LLM报告: {enable_llm_report}", flush=True)
    print(f"   🔎 VLM复核: {enable_vlm_check}", flush=True)

    # 处理视频路径：支持MinIO路径和本地路径
    local_video_path = video_path
    video_minio_path = None

    if video_path.startswith("minio://"):
        # MinIO路径格式: minio://videos/xxx.mp4
        print(f"   ☁️ 检测到MinIO路径，准备下载视频到本地临时目录", flush=True)
        video_minio_path = video_path

        # 解析MinIO路径
        minio_path = video_path.replace("minio://", "")
        parts = minio_path.split("/", 1)
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="MinIO路径格式错误")

        bucket_name = parts[0]
        object_name = parts[1]

        # 下载视频到临时目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.basename(object_name)
        local_video_path = os.path.join(TEMP_DIR, f"{timestamp}_{filename}")

        print(f"   ⬇️ 从MinIO下载: {bucket_name}/{object_name} -> {local_video_path}", flush=True)
        video_data = minio_client.download_file(bucket_name=bucket_name, object_name=object_name)

        if not video_data:
            raise HTTPException(status_code=400, detail=f"无法从MinIO下载视频: {video_path}")

        # 保存到本地临时文件
        with open(local_video_path, "wb") as f:
            f.write(video_data)

        print(f"   ✅ 视频下载成功: {local_video_path}", flush=True)
    else:
        # 本地路径，验证文件是否存在
        if not os.path.exists(video_path):
            raise HTTPException(status_code=400, detail="视频文件不存在")
        print(f"   💾 使用本地视频路径", flush=True)

    # 获取模型信息
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    print(f"   🔍 模型信息: {model.name} (路径: {model.path})", flush=True)

    # 处理模型路径：支持MinIO路径
    local_model_path = model.path

    if model.path.startswith("minio://"):
        # MinIO模型路径，需要下载
        print(f"   ☁️ 检测到MinIO模型路径，准备下载模型", flush=True)

        # 解析MinIO路径
        minio_path = model.path.replace("minio://", "")
        parts = minio_path.split("/", 1)
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="模型MinIO路径格式错误")

        bucket_name = parts[0]
        object_name = parts[1]

        # 下载模型到临时目录
        model_filename = os.path.basename(object_name)
        local_model_path = os.path.join(TEMP_DIR, f"model_{model_filename}")

        print(f"   ⬇️ 从MinIO下载模型: {bucket_name}/{object_name} -> {local_model_path}", flush=True)
        model_data = minio_client.download_file(bucket_name=bucket_name, object_name=object_name)

        if not model_data:
            raise HTTPException(status_code=400, detail=f"无法从MinIO下载模型: {model.path}")

        # 保存到本地临时文件
        with open(local_model_path, "wb") as f:
            f.write(model_data)

        print(f"   ✅ 模型下载成功: {local_model_path}", flush=True)

    # 生成任务ID
    task_id = str(uuid.uuid4())

    # 创建任务记录
    video_filename = os.path.basename(local_video_path)
    tracking_tasks[task_id] = {
        "task_id": task_id,
        "model_id": model_id,
        "model_path": local_model_path,
        "video_path": local_video_path,
        "video_minio_path": video_minio_path,  # 记录原始MinIO路径
        "video_filename": video_filename,
        "status": "pending",
        "progress": 0,
        "result_video_url": None,
        "error": None,
        "enable_llm_report": enable_llm_report,
        "enable_vlm_check": enable_vlm_check,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    print(f"   🎯 任务创建成功: {task_id}", flush=True)

    # 后台执行追踪任务
    background_tasks.add_task(
        run_vehicle_tracking_realtime,
        task_id,
        local_model_path,
        local_video_path,
        enable_llm_report,
        enable_vlm_check,
    )

    return {
        "code": 0,
        "data": {"task_id": task_id},
        "message": "追踪任务已启动"
    }


def run_vehicle_tracking(task_id: str, model_path: str, video_path: str):
    """后台执行车辆追踪任务"""
    try:
        from ultralytics import YOLO

        print(f"[{task_id}] 开始车辆追踪任务")
        print(f"[{task_id}] 模型路径: {model_path}")
        print(f"[{task_id}] 视频路径: {video_path}")

        # 更新状态为处理中
        tracking_tasks[task_id]["status"] = "processing"
        tracking_tasks[task_id]["progress"] = 10

        # 检查模型文件是否存在
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"模型文件不存在: {model_path}")

        # 检查视频文件是否存在
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        # 加载模型
        print(f"[{task_id}] 加载模型...")
        model = YOLO(model_path)
        tracking_tasks[task_id]["progress"] = 20

        # 准备结果视频文件名（使用 tracked_ 前缀 + 原视频名）
        original_filename = os.path.basename(video_path)
        original_name = os.path.splitext(original_filename)[0]
        result_filename = f"tracked_{original_name}.mp4"
        result_path = os.path.join(VID_RESULTS_DIR, result_filename)

        tracking_tasks[task_id]["progress"] = 30

        print(f"[{task_id}] 开始追踪推理...")
        # 执行追踪 (使用 stream=True 避免内存积累)
        results = model.track(
            source=video_path,
            tracker='bytetrack.yaml',  # 使用 ByteTrack 追踪器
            save=True,                  # 保存结果视频
            stream=True,                # 流式处理,避免内存积累
            conf=0.5,                   # 置信度阈值
            line_width=2,               # 边框线宽
            project=VID_RESULTS_DIR,    # 项目目录
            name=task_id,               # 任务子目录名
            exist_ok=True               # 允许覆盖
        )

        # 消费生成器以完成处理
        for r in results:
            pass  # 让生成器执行完成,YOLO 会自动保存视频

        tracking_tasks[task_id]["progress"] = 80

        # 查找生成的结果视频
        task_result_dir = os.path.join(VID_RESULTS_DIR, task_id)
        print(f"[{task_id}] 查找结果视频: {task_result_dir}")

        if os.path.exists(task_result_dir):
            # 查找视频文件
            video_files = [f for f in os.listdir(task_result_dir) if f.endswith(('.mp4', '.avi', '.mov'))]

            if video_files:
                # YOLO 生成的原始视频
                source_video = os.path.join(task_result_dir, video_files[0])
                print(f"[{task_id}] 找到结果视频: {source_video}")

                # 使用 ffmpeg 转换为浏览器兼容格式
                import subprocess
                temp_result = result_path.replace('.mp4', '_temp.mp4')

                tracking_tasks[task_id]["progress"] = 85
                print(f"[{task_id}] 转换结果视频为浏览器兼容格式...")

                try:
                    subprocess.run([
                        'ffmpeg',
                        '-i', source_video,
                        '-c:v', 'libx264',              # H.264 视频编码
                        '-preset', 'fast',               # 快速编码
                        '-crf', '23',                   # 质量参数
                        '-profile:v', 'baseline',        # 使用 baseline profile 提高兼容性
                        '-level', '3.0',                # H.264 level
                        '-pix_fmt', 'yuv420p',          # 像素格式
                        '-c:a', 'aac',                  # AAC 音频编码
                        '-b:a', '128k',                 # 音频比特率
                        '-ar', '44100',                 # 音频采样率
                        '-movflags', '+faststart',      # moov atom 前置,支持流式播放和随机访问
                        '-y',                           # 覆盖输出文件
                        temp_result
                    ], check=True, capture_output=True, timeout=600)

                    # 转换成功,使用转换后的视频
                    shutil.move(temp_result, result_path)
                    print(f"[{task_id}] 结果视频格式转换完成")
                except subprocess.CalledProcessError as e:
                    print(f"[{task_id}] ffmpeg 转换失败: {e.stderr.decode()}")
                    # 如果转换失败,直接使用 YOLO 生成的视频
                    print(f"[{task_id}] 使用原始结果视频...")
                    shutil.move(source_video, result_path)
                except FileNotFoundError:
                    print(f"[{task_id}] 未找到 ffmpeg,使用原始结果视频...")
                    shutil.move(source_video, result_path)
                finally:
                    # 清理临时文件
                    if os.path.exists(temp_result):
                        os.remove(temp_result)

                # 清理临时目录
                shutil.rmtree(task_result_dir, ignore_errors=True)
            else:
                raise FileNotFoundError(f"未找到生成的结果视频")
        else:
            raise FileNotFoundError(f"结果目录不存在: {task_result_dir}")

        tracking_tasks[task_id]["progress"] = 100
        tracking_tasks[task_id]["status"] = "completed"
        tracking_tasks[task_id]["result_video_url"] = f"/api/system/uploads/vid_results/{result_filename}"
        tracking_tasks[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

        # 保存到数据库
        try:
            db = SessionLocal()
            # 获取视频信息
            cap = cv2.VideoCapture(video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.release()

            cap_result = cv2.VideoCapture(result_path)
            duration = cap_result.get(cv2.CAP_PROP_FRAME_COUNT) / fps if fps > 0 else 0
            cap_result.release()

            # 计算相对路径
            original_relative_path = os.path.relpath(video_path, UPLOAD_DIR)
            result_relative_path = f"vid_results/{result_filename}"

            task_record = VideoTrackingTask(
                task_id=task_id,
                model_id=tracking_tasks[task_id]["model_id"],
                original_video_path=video_path,
                original_video_name=os.path.basename(video_path),
                original_video_relative_path=original_relative_path,
                result_video_path=result_path,
                result_video_name=result_filename,
                result_video_relative_path=result_relative_path,
                status="completed",
                progress=100,
                total_frames=total_frames,
                processed_frames=total_frames,
                fps=fps,
                duration=duration,
                created_at=datetime.fromisoformat(tracking_tasks[task_id]["created_at"].replace('Z', '+00:00')) if 'Z' in tracking_tasks[task_id]["created_at"] else datetime.fromisoformat(tracking_tasks[task_id]["created_at"]),
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc)
            )
            db.add(task_record)
            db.commit()
            db.close()
            print(f"[{task_id}] 任务记录已保存到数据库")
        except Exception as db_error:
            print(f"[{task_id}] 保存数据库记录失败: {db_error}")

        print(f"[{task_id}] 追踪任务完成！")

    except Exception as e:
        error_msg = str(e)
        print(f"[{task_id}] 车辆追踪失败: {error_msg}")
        tracking_tasks[task_id]["status"] = "failed"
        tracking_tasks[task_id]["error"] = error_msg
        tracking_tasks[task_id]["progress"] = 0


def run_vehicle_tracking_realtime(
    task_id: str,
    model_path: str,
    video_path: str,
    enable_llm_report: bool = False,
    enable_vlm_check: bool = False,
):
    """后台执行车辆追踪任务 - 实时版本(通过 WebSocket 推送帧)"""
    temp_files_to_cleanup = []  # 临时文件清理列表
    analysis_artifacts: dict[str, Any] = {}

    try:
        import time

        print(f"[{task_id}] 开始实时车辆追踪任务", flush=True)
        print(f"[{task_id}] 模型路径: {model_path}", flush=True)
        print(f"[{task_id}] 视频路径: {video_path}", flush=True)

        # 记录需要清理的临时文件
        if video_path.startswith(TEMP_DIR):
            temp_files_to_cleanup.append(video_path)
        if model_path.startswith(TEMP_DIR):
            temp_files_to_cleanup.append(model_path)

        # 更新状态为处理中
        tracking_tasks[task_id]["status"] = "processing"
        tracking_tasks[task_id]["progress"] = 10

        # 检查模型和视频文件
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"模型文件不存在: {model_path}")
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        # 加载模型
        print(f"[{task_id}] 加载模型...")
        model = __import__("ultralytics").YOLO(model_path)
        tracking_tasks[task_id]["progress"] = 20

        # 获取视频信息
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        print(f"[{task_id}] 视频信息: {total_frames} 帧, {fps} FPS")

        cfg = DetectionConfig(
            model_path=model_path,
            output_video="",
            output_events_json="",
            show_preview=False,
        )
        estimator = KinematicEstimator(fps=fps, frame_width=width, frame_height=height)
        speed_det = SpeedingDetector(cfg.speed_limit_kmh, fps,
                                     cfg.speed_window_s, cfg.speed_ratio,
                                     cfg.speed_hysteresis_kmh)
        brake_det = AbruptStopDetector(cfg.abrupt_accel_threshold,
                                       cfg.abrupt_min_initial_speed_kmh, fps=fps)
        stop_det = StationaryDetector(cfg.stationary_threshold_kmh,
                                      cfg.stationary_min_duration_s, fps)
        lane_det = LaneChangeDetector(fps, cfg.lane_change_window_s,
                                      cfg.lane_change_lateral_m,
                                      cfg.lane_change_min_speed_kmh)
        cong_det = CongestionDetector(cfg.congestion_threshold_kmh,
                                      cfg.congestion_min_vehicles,
                                      cooldown_s=10.0, fps=fps)
        bus = EventBus()
        speed_history = deque(maxlen=200)
        setattr(estimator, "_realtime_speed_history", speed_history)
        totals = {
            "speeding": 0,
            "abrupt_stop": 0,
            "stationary": 0,
            "lane_change": 0,
            "congestion": 0,
        }

        # 准备结果视频文件名（使用 tracked_ 前缀 + 原视频名）
        original_filename = os.path.basename(video_path)
        original_name = os.path.splitext(original_filename)[0]
        result_filename = f"tracked_{original_name}.mp4"
        result_path = os.path.join(VID_RESULTS_DIR, result_filename)
        task_result_dir = os.path.join(VID_RESULTS_DIR, task_id)
        os.makedirs(task_result_dir, exist_ok=True)

        tracking_tasks[task_id]["progress"] = 30

        print(f"[{task_id}] 开始实时追踪推理...")

        # 执行追踪 (stream=True 逐帧处理)
        results = model.track(
            source=video_path,
            tracker='bytetrack.yaml',
            save=False,  # 不自动保存,我们手动保存
            stream=True,
            conf=0.5,
            line_width=2,
            show_labels=True,
            show_conf=True,
        )

        # 准备视频写入器
        writer = None
        frame_count = 0
        start_time = time.time()
        temp_video_path = os.path.join(task_result_dir, "temp_result.mp4")

        # 逐帧处理并推送
        for r in results:
            frame_count += 1
            frame = r.orig_img.copy() if getattr(r, "orig_img", None) is not None else None
            if frame is None:
                continue

            boxes_for_draw = []
            track_states = []
            if r.boxes is not None and r.boxes.id is not None:
                for box in r.boxes:
                    tid = int(box.id.item())
                    cls_id = int(box.cls.item()) if box.cls is not None else 2
                    x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                    ts = estimator.update_with_box(tid, x1, y1, x2, y2, cls_id, frame_count)
                    track_states.append(ts)
                    if estimator.calib_ready:
                        for d, name in [
                            (speed_det, "speeding"),
                            (brake_det, "abrupt_stop"),
                            (stop_det, "stationary"),
                            (lane_det, "lane_change"),
                        ]:
                            ev = d.update(ts, frame_count)
                            if ev:
                                bus.emit(ev)
                                totals[name] += 1
                    if estimator.calib_ready and speed_det.is_currently_speeding(tid):
                        color, sub = (0, 60, 200), "SPEEDING"
                    else:
                        color, sub = (80, 160, 60), ""
                    if estimator.calib_ready and ts.speed_smooth > 0:
                        raw = ts.speed_smooth
                        if raw < 15:
                            boost = 8.0
                        elif raw < 30:
                            boost = 8.0 * (1.0 - (raw - 15) / 15.0)
                        else:
                            boost = 0.0
                        display_speed = raw + boost
                        if len(speed_history) >= 3:
                            recent_speeds = [speed for _, speed in list(speed_history)[-3:]]
                            display_speed = float(np.median(recent_speeds))
                        main_label = f"#{tid} {display_speed:.0f}km/h"
                        sp_kmh = display_speed
                    else:
                        main_label = f"#{tid} ..."
                        sp_kmh = ts.speed_smooth if ts.valid else -1.0
                    boxes_for_draw.append((x1, y1, x2, y2, color, main_label, sub, ts.bbox_3d, sp_kmh))

            if estimator.calib_ready and track_states:
                valid_speeds = [ts.speed_smooth for ts in track_states if ts.valid]
                if valid_speeds:
                    speed_history.append((frame_count, float(sum(valid_speeds) / len(valid_speeds))))

            estimator.cleanup(frame_count)

            canvas = np.zeros((height, width + 280, 3), dtype=np.uint8)
            canvas[:, :width] = frame
            _draw_corner_brackets(canvas[:, :width], color=(50, 100, 180), thickness=2, length=25)
            for x1, y1, x2, y2, color, lbl, sub, b3d, sp_kmh in boxes_for_draw:
                _draw_box_glow(canvas, x1, y1, x2, y2, color, lbl, sub, sp_kmh)
            _draw_realtime_panel(canvas, frame_count, fps, totals, bus, x_off=width, est=estimator, calib_ready=estimator.calib_ready)

            if writer is None:
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter(temp_video_path, fourcc, fps, (canvas.shape[1], canvas.shape[0]))

            writer.write(canvas)

            if frame_count % 5 == 0:
                _, buffer = cv2.imencode('.jpg', canvas, [cv2.IMWRITE_JPEG_QUALITY, 70])
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                progress = int(30 + (frame_count / total_frames) * 50)
                elapsed = time.time() - start_time
                current_fps = frame_count / elapsed if elapsed > 0 else 0
                frame_data = {
                    "type": "frame",
                    "frame": frame_base64,
                    "frame_number": frame_count,
                    "total_frames": total_frames,
                    "progress": progress,
                    "fps": round(current_fps, 2),
                }
                if task_id in manager.active_connections:
                    manager.send_frame_sync(task_id, frame_data)

            tracking_tasks[task_id]["progress"] = int(30 + (frame_count / total_frames) * 50)

        # 关闭视频写入器
        if writer:
            writer.release()

        print(f"[{task_id}] 追踪完成,共处理 {frame_count} 帧", flush=True)
        tracking_tasks[task_id]["progress"] = 80

        # 转换视频格式
        print(f"[{task_id}] 转换视频为浏览器兼容格式...", flush=True)
        import subprocess

        try:
            subprocess.run([
                'ffmpeg',
                '-i', temp_video_path,
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-profile:v', 'baseline',
                '-level', '3.0',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-ar', '44100',
                '-movflags', '+faststart',
                '-y',
                result_path
            ], check=True, capture_output=True, timeout=600)

            print(f"[{task_id}] 视频转换完成", flush=True)
        except Exception as e:
            print(f"[{task_id}] 视频转换失败: {e}", flush=True)
            shutil.copy(temp_video_path, result_path)

        # 清理临时文件
        shutil.rmtree(task_result_dir, ignore_errors=True)

        # 上传结果视频到MinIO
        print(f"[{task_id}] ☁️ 上传结果视频到MinIO...", flush=True)
        result_minio_path = None

        with open(result_path, "rb") as f:
            result_video_data = f.read()

        upload_success = minio_client.upload_file(
            bucket_name=BUCKETS["vid_results"],
            object_name=result_filename,
            file_data=io.BytesIO(result_video_data),
            content_type="video/mp4"
        )

        if upload_success:
            result_minio_path = f"minio://{BUCKETS['vid_results']}/{result_filename}"
            print(f"[{task_id}] ✅ 结果视频已上传到MinIO: {result_minio_path}", flush=True)
        else:
            print(f"[{task_id}] ⚠️ 结果视频上传MinIO失败", flush=True)

        # 删除本地结果文件（已上传到MinIO）
        if os.path.exists(result_path):
            os.remove(result_path)
            print(f"[{task_id}] 🗑️ 已删除本地结果文件: {result_path}", flush=True)

        # 生成 detectors3 兼容分析工件
        try:
            print(f"[{task_id}] 📦 生成 detectors3 分析工件...", flush=True)
            tracking_tasks[task_id]["progress"] = 85
            analysis_artifacts = _run_detectors3_analysis(
                task_id,
                video_path,
                result_path,
                enable_llm_report=enable_llm_report,
                enable_vlm_check=enable_vlm_check,
            )
            tracking_tasks[task_id]["progress"] = 92
            _save_tracking_report_record(
                task_id,
                analysis_artifacts,
                enable_llm_report=enable_llm_report,
                enable_vlm_check=enable_vlm_check,
            )
            print(f"[{task_id}] ✅ 分析工件已生成", flush=True)
        except Exception as analysis_error:
            print(f"[{task_id}] ⚠️ 分析工件生成失败: {analysis_error}", flush=True)
            analysis_artifacts = {
                "analysis_dir": None,
                "events_json_path": None,
                "events_json_url": None,
                "report_html_path": None,
                "report_html_url": None,
                "report_md_path": None,
                "report_md_url": None,
                "keyframes_dir": None,
                "summary": {"vehicle_count": 0, "event_count": 0, "event_breakdown": {}},
                "tracks": [],
                "events": [],
                "audit_samples": [],
                "scene_analysis": None,
            }

        # 完成
        tracking_tasks[task_id]["progress"] = 100
        tracking_tasks[task_id]["status"] = "completed"
        # 使用完整的tracking服务URL
        tracking_tasks[task_id]["result_video_url"] = f"/api/system/uploads/vid_results/{result_filename}"
        tracking_tasks[task_id]["result_minio_path"] = result_minio_path
        tracking_tasks[task_id]["analysis"] = analysis_artifacts
        tracking_tasks[task_id]["events_json_url"] = analysis_artifacts.get("events_json_url")
        tracking_tasks[task_id]["report_html_url"] = analysis_artifacts.get("report_html_url")
        tracking_tasks[task_id]["report_md_url"] = analysis_artifacts.get("report_md_url")
        tracking_tasks[task_id]["analysis_video_url"] = analysis_artifacts.get("analysis_video_url")
        tracking_tasks[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

        # 保存到数据库
        try:
            db = SessionLocal()

            # 使用MinIO路径保存到数据库
            original_video_minio = tracking_tasks[task_id].get("video_minio_path") or video_path

            # 计算视频时长
            duration = total_frames / fps if fps > 0 else 0

            task_record = VideoTrackingTask(
                task_id=task_id,
                model_id=tracking_tasks[task_id]["model_id"],
                original_video_path=original_video_minio,  # 保存MinIO路径
                original_video_name=os.path.basename(video_path),
                original_video_relative_path=original_video_minio,
                result_video_path=result_minio_path or result_path,  # 保存MinIO路径
                result_video_name=result_filename,
                result_video_relative_path=result_minio_path or result_filename,
                status="completed",
                progress=100,
                total_frames=total_frames,
                processed_frames=frame_count,
                fps=fps,
                duration=duration,
                created_at=datetime.fromisoformat(tracking_tasks[task_id]["created_at"].replace('Z', '+00:00')) if 'Z' in tracking_tasks[task_id]["created_at"] else datetime.fromisoformat(tracking_tasks[task_id]["created_at"]),
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc)
            )
            db.add(task_record)
            db.commit()
            db.close()
            print(f"[{task_id}] 任务记录已保存到数据库", flush=True)
        except Exception as db_error:
            print(f"[{task_id}] 保存数据库记录失败: {db_error}", flush=True)

        # 发送完成消息
        print(f"[{task_id}] 准备发送完成消息...", flush=True)
        print(f"[{task_id}] WebSocket连接状态: {task_id in manager.active_connections}", flush=True)
        print(f"[{task_id}] 结果视频URL: {tracking_tasks[task_id]['result_video_url']}", flush=True)

        if task_id in manager.active_connections:
            try:
                manager.send_frame_sync(task_id, {
                    "type": "complete",
                    "result_url": tracking_tasks[task_id]["result_video_url"],
                    "message": "追踪完成"
                })
                print(f"[{task_id}] ✅ 完成消息已发送", flush=True)
            except Exception as ws_error:
                print(f"[{task_id}] ⚠️ 发送WebSocket消息失败: {ws_error}", flush=True)
        else:
            print(f"[{task_id}] ⚠️ WebSocket已断开，无法发送完成消息", flush=True)

        print(f"[{task_id}] 追踪任务完成！", flush=True)

    except Exception as e:
        error_msg = str(e)
        print(f"[{task_id}] 车辆追踪失败: {error_msg}", flush=True)
        tracking_tasks[task_id]["status"] = "failed"
        tracking_tasks[task_id]["error"] = error_msg
        tracking_tasks[task_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

        # 发送错误消息
        if task_id in manager.active_connections:
            manager.send_frame_sync(task_id, {
                "type": "error",
                "error": error_msg
            })

    finally:
        # 清理临时文件
        print(f"\n[{task_id}] 🗑️ 开始清理临时文件...", flush=True)
        for temp_file in temp_files_to_cleanup:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    print(f"[{task_id}]    ✅ 已删除: {temp_file}", flush=True)
                except Exception as e:
                    print(f"[{task_id}]    ⚠️ 删除失败: {temp_file} - {e}", flush=True)
        print(f"[{task_id}] ✅ 临时文件清理完成", flush=True)


@app.get("/tracking/status/{task_id}")
async def get_tracking_status(task_id: str):
    """获取追踪任务状态"""
    if task_id not in tracking_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "code": 0,
        "data": tracking_tasks[task_id],
        "message": "success"
    }


@app.get("/tracking/tasks")
async def get_all_tasks():
    """获取所有追踪任务"""
    return {
        "code": 0,
        "data": {
            "total": len(tracking_tasks),
            "tasks": list(tracking_tasks.values())
        },
        "message": "success"
    }


@app.get("/tracking/artifacts/{task_id}")
async def get_tracking_artifacts(task_id: str):
    """获取追踪任务的分析工件。"""
    task = tracking_tasks.get(task_id)
    if task is None:
        task = {"status": "completed", "progress": 100}

    analysis = task.get("analysis") or _build_tracking_artifacts_from_disk(task_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="任务不存在或工件未生成")

    return {
        "code": 0,
        "data": {
            "task_id": task_id,
            "status": task.get("status"),
            "progress": task.get("progress"),
            "result_video_url": task.get("result_video_url"),
            "analysis_video_url": task.get("analysis_video_url"),
            "events_json_url": task.get("events_json_url"),
            "report_html_url": task.get("report_html_url"),
            "report_md_url": task.get("report_md_url"),
            "summary": analysis.get("summary", {}),
            "tracks": analysis.get("tracks", []),
            "events": analysis.get("events", []),
            "audit_samples": analysis.get("audit_samples", []),
            "scene_analysis": analysis.get("scene_analysis"),
        },
        "message": "success"
    }


@app.get("/tracking/reports")
async def get_tracking_reports(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """获取 PostgreSQL 中保存的追踪报告索引列表。"""
    safe_limit = min(max(limit, 1), 200)
    safe_offset = max(offset, 0)
    query = db.query(TrackingAnalysisReport)
    total = query.count()
    reports = (
        query.order_by(TrackingAnalysisReport.created_at.desc(), TrackingAnalysisReport.id.desc())
        .offset(safe_offset)
        .limit(safe_limit)
        .all()
    )
    return {
        "code": 0,
        "data": {
            "total": total,
            "reports": [_serialize_tracking_report(report) for report in reports],
        },
        "message": "success",
    }


@app.get("/tracking/reports/{report_id}")
async def get_tracking_report(report_id: int, db: Session = Depends(get_db)):
    """获取单条追踪报告索引详情。"""
    report = db.query(TrackingAnalysisReport).filter(TrackingAnalysisReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告记录不存在")
    return {
        "code": 0,
        "data": _serialize_tracking_report(report),
        "message": "success",
    }


@app.delete("/tracking/reports/{report_id}")
async def delete_tracking_report(report_id: int, db: Session = Depends(get_db)):
    """删除报告索引及其本地分析工件。"""
    report = db.query(TrackingAnalysisReport).filter(TrackingAnalysisReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告记录不存在")

    allowed_root = os.path.abspath(TRACKING_OUTPUT_DIR)
    candidate_files = [
        report.html_path,
        report.md_path,
        report.events_json_path,
        report.analysis_video_path,
    ]
    deleted_files: list[str] = []
    for file_path in candidate_files:
        if not file_path:
            continue
        abs_path = os.path.abspath(file_path)
        if not abs_path.startswith(allowed_root + os.sep):
            continue
        if os.path.isfile(abs_path):
            try:
                os.remove(abs_path)
                deleted_files.append(abs_path)
            except OSError as exc:
                print(f"[report:{report_id}] 删除文件失败 {abs_path}: {exc}", flush=True)

    task_dir = os.path.join(TRACKING_OUTPUT_DIR, report.task_id)
    abs_task_dir = os.path.abspath(task_dir)
    if abs_task_dir.startswith(allowed_root + os.sep) and os.path.isdir(abs_task_dir):
        shutil.rmtree(abs_task_dir, ignore_errors=True)

    db.delete(report)
    db.commit()
    return {
        "code": 0,
        "data": {"id": report_id, "deleted_files": deleted_files},
        "message": "success",
    }


@app.get("/tracking/reports/{report_id}/content")
async def get_tracking_report_content(
    report_id: int,
    format: str = "html",
    db: Session = Depends(get_db),
):
    """通过数据库报告索引读取报告文件内容。"""
    report = db.query(TrackingAnalysisReport).filter(TrackingAnalysisReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="报告记录不存在")

    file_path, media_type = _resolve_report_file_path(report, format)
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    if media_type.startswith("text/html"):
        content = _normalize_tracking_report_html(content)
        return HTMLResponse(content=content, media_type=media_type)
    return PlainTextResponse(content=content, media_type=media_type)


@app.get("/uploads/tracking_analysis/{file_path:path}")
async def serve_tracking_analysis(file_path: str, request: Request):
    """提供 tracking_analysis 目录下的工件文件。"""
    full_path = os.path.join(TRACKING_OUTPUT_DIR, file_path)
    if not os.path.exists(full_path) or not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail=f"工件文件不存在: {file_path}")

    ext = os.path.splitext(full_path)[1].lower()
    content_type = "application/octet-stream"
    if ext in [".html", ".htm"]:
        content_type = "text/html; charset=utf-8"
    elif ext in [".json"]:
        content_type = "application/json; charset=utf-8"
    elif ext in [".md", ".txt"]:
        content_type = "text/plain; charset=utf-8"
    elif ext in [".jpg", ".jpeg"]:
        content_type = "image/jpeg"
    elif ext in [".png"]:
        content_type = "image/png"
    elif ext in [".mp4"]:
        content_type = "video/mp4"

    if content_type.startswith("video/"):
        return range_requests_response(request, full_path, content_type="video/mp4")

    return FileResponse(full_path, media_type=content_type)


# ============ 视频流式服务（支持 Range 请求）============
def range_requests_response(
    request: Request,
    file_path: str,
    content_type: str = "video/mp4"
):
    """支持 HTTP Range 请求的视频流式响应"""
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")

    if range_header:
        # 解析 Range 请求
        byte_range = range_header.replace("bytes=", "").split("-")
        start = int(byte_range[0]) if byte_range[0] else 0
        end = int(byte_range[1]) if byte_range[1] else file_size - 1
        end = min(end, file_size - 1)
        content_length = end - start + 1

        def file_iterator():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk_size = min(8192, remaining)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Type": content_type,
        }
        return StreamingResponse(
            file_iterator(),
            status_code=206,
            headers=headers,
            media_type=content_type
        )
    else:
        # 完整文件响应
        def file_iterator():
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk

        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": content_type,
        }
        return StreamingResponse(
            file_iterator(),
            headers=headers,
            media_type=content_type
        )


@app.get("/uploads/videos/{file_path:path}")
async def serve_video(file_path: str, request: Request):
    """提供视频文件服务 - 从 MinIO 代理返回"""
    from fastapi.responses import StreamingResponse
    result = minio_client.get_file_stream(BUCKETS["videos"], file_path)
    if not result:
        raise HTTPException(status_code=404, detail=f"视频文件不存在: {file_path}")
    response, content_type, content_length = result
    return StreamingResponse(
        response,
        media_type=content_type or "video/mp4",
        headers={"Content-Length": str(content_length), "Accept-Ranges": "bytes"}
    )


@app.get("/uploads/vid_results/{file_path:path}")
async def serve_result_video(file_path: str, request: Request):
    """提供结果视频文件服务 - 从 MinIO 代理返回"""
    from fastapi.responses import StreamingResponse
    result = minio_client.get_file_stream(BUCKETS["vid_results"], file_path)
    if not result:
        raise HTTPException(status_code=404, detail=f"结果视频不存在: {file_path}")
    response, content_type, content_length = result
    return StreamingResponse(
        response,
        media_type=content_type or "video/mp4",
        headers={"Content-Length": str(content_length), "Accept-Ranges": "bytes"}
    )


# ============ 静态文件服务 ============
# 注意：视频文件通过上面的端点处理，这里只处理其他静态文件
# app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("🚀 启动车辆追踪服务...")
    print("📍 访问地址: http://localhost:51034")
    print("📚 API 文档: http://localhost:51034/docs")
    print("="*60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=51034)
