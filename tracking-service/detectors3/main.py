"""
main.py — 基于多模型融合的智能交通视频分析系统
================================================

基于以下论文方法：
  [1] Kocur 2020 "Detection of 3D BBox of Vehicles for Speed Measurement"
  [2] Macko 2025 "Efficient Vision-based Vehicle Speed Estimation"
  [3] Sochor 2017 "Camera Calibration by 3D Model BBox Alignment"

增强模块：
  - LLM 交通报告生成
  - 关键帧截图
  - VLM 关键帧复核
  - 飞桨车辆属性识别（可选）

完全免标定、零配置：
    python main.py --video videos/M0201.mp4 --no-show

全功能模式：
    python main.py --video videos/M0201.mp4 --no-show \\
        --save-keyframes --enable-llm-report --enable-vlm-check \\
        --llm-provider aistudio
"""

import os
import sys
import json
import csv
import argparse
from collections import defaultdict, deque
import cv2
import numpy as np
from ultralytics import YOLO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from config import (
    DetectionConfig,
    COLOR_NORMAL, COLOR_SPEEDING, COLOR_LANE_CHANGE,
    COLOR_ACCIDENT, COLOR_STATIONARY,
    COLOR_PANEL_BG, COLOR_TEXT, COLOR_DIM,
)
from detectors import (
    KinematicEstimator,
    SpeedingDetector, AbruptStopDetector, StationaryDetector,
    LaneChangeDetector, CongestionDetector,
    EventBus,
)
from utils.event_schema import EventType, EVENT_TYPE_MAP


EVENT_COLORS = {
    "speeding": COLOR_SPEEDING,
    "abrupt_stop": COLOR_ACCIDENT,
    "stationary": COLOR_STATIONARY,
    "lane_change": COLOR_LANE_CHANGE,
    "congestion": (60, 220, 230),
}
EVENT_LABELS = {
    "speeding": "SPEED",
    "abrupt_stop": "BRAKE!",
    "stationary": "STOP",
    "lane_change": "LANE",
    "congestion": "JAM",
}


# ----------------------------------------------------------------------
# 绘图函数
# ----------------------------------------------------------------------

def speed_to_color(speed_kmh: float, max_speed: float = 120.0) -> tuple:
    """速度 → 渐变色（绿→黄→橙→红）。"""
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


def draw_box_glow(img, x1, y1, x2, y2, color, label, sub_label="", speed_kmh: float = -1):
    """标注框：简洁边框 + 标签。"""
    # 根据速度选择颜色（超速用红，否则用传入颜色）
    if speed_kmh >= 0:
        box_color = speed_to_color(speed_kmh)
    else:
        box_color = color

    # 主边框（无发光效果）
    cv2.rectangle(img, (x1, y1), (x2, y2), box_color, 2, cv2.LINE_AA)

    # 标签背景（简洁纯色）
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

    # 标签背景：纯色（无渐变）
    actual_h = bg_y2 - bg_y1
    actual_w = bg_x2 - bg_x1
    if actual_h > 0 and actual_w > 0:
        # 使用较暗的背景色
        bg_color = (int(box_color[0] * 0.6), int(box_color[1] * 0.6), int(box_color[2] * 0.6))
        cv2.rectangle(img, (bg_x1, bg_y1), (bg_x2, bg_y2), bg_color, -1)
        cv2.putText(img, txt, (bg_x1 + pad, bg_y1 + th + pad - 2),
                    font, 0.55, (255, 255, 255), 1, cv2.LINE_AA)


def draw_3d_box(img, bbox3d, color):
    if bbox3d is None:
        return
    pts = bbox3d.corners.astype(int)
    for i in range(4):
        cv2.line(img, tuple(pts[i]), tuple(pts[(i+1) % 4]), color, 1)
    for i in range(4):
        cv2.line(img, tuple(pts[4+i]), tuple(pts[4+(i+1) % 4]), color, 1)
    for i in range(4):
        cv2.line(img, tuple(pts[i]), tuple(pts[i+4]), color, 1)
    bf = bbox3d.bottom_front_center


def draw_vps(img, vps, w, h):
    pass


def draw_corner_brackets(img, color=(60, 120, 200), thickness=2, length=30):
    """在视频四角绘制科技感角标。"""
    h, w = img.shape[:2]
    corners = [
        ((0, 0), (length, 0), (0, length)),           # 左上
        ((w - 1, 0), (-length, 0), (0, length)),      # 右上
        ((w - 1, h - 1), (-length, 0), (0, -length)), # 右下
        ((0, h - 1), (length, 0), (0, -length)),      # 左下
    ]
    for (cx, cy), (dx1, dy1), (dx2, dy2) in corners:
        cv2.line(img, (cx, cy), (cx + dx1, cy + dy1), color, thickness)
        cv2.line(img, (cx, cy), (cx + dx2, cy + dy2), color, thickness)


# ----------------------------------------------------------------------
# 车速曲线（全局历史，供 draw_panel 调用）
# ----------------------------------------------------------------------
_speed_history = []        # [(frame, avg_speed_kmh), ...]
_MAX_SPEED_HISTORY = 200  # 保留最近 200 帧


def push_speed(frame_idx: int, avg_speed: float):
    _speed_history.append((frame_idx, avg_speed))
    if len(_speed_history) > _MAX_SPEED_HISTORY:
        _speed_history.pop(0)


def draw_speed_curve(panel_img, x0, y0, w, h, fps):
    """在面板内绘制实时车速曲线图。"""
    if len(_speed_history) < 2:
        return y0

    # 背景
    cv2.rectangle(panel_img, (x0, y0), (x0 + w, y0 + h), (15, 15, 30), -1)
    cv2.rectangle(panel_img, (x0, y0), (x0 + w, y0 + h), (80, 80, 120), 1)

    # 标题
    cv2.putText(panel_img, "Speed Curve (km/h)", (x0 + 4, y0 + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 160, 220), 1, cv2.LINE_AA)

    chart_x0 = x0 + 4
    chart_y0 = y0 + 18
    chart_w = w - 8
    chart_h = h - 22

    # 找速度范围
    speeds = [s for _, s in _speed_history]
    max_s = max(speeds[-50:]) if speeds[-50:] else 120
    max_s = max(max_s * 1.2, 20)
    min_s = 0.0

    # 网格线
    for frac in [0.25, 0.5, 0.75]:
        y_grid = int(chart_y0 + chart_h * (1 - frac))
        cv2.line(panel_img, (chart_x0, y_grid), (chart_x0 + chart_w, y_grid),
                 (50, 50, 70), 1)
        val = int(min_s + frac * (max_s - min_s))
        cv2.putText(panel_img, f"{val}", (chart_x0 + 2, y_grid - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.30, (90, 90, 120), 1)

    # 速度曲线（最近50个点）
    recent = _speed_history[-50:]
    pts = []
    for i, (_, sp) in enumerate(recent):
        px = int(chart_x0 + (i / (len(recent) - 1)) * chart_w)
        py = int(chart_y0 + chart_h * (1 - (sp - min_s) / (max_s - min_s)))
        pts.append((px, py))

    # 填充区域（渐变）- 使用更暗的颜色
    pts_fill = pts + [(pts[-1][0], chart_y0 + chart_h), (pts[0][0], chart_y0 + chart_h)]
    pts_arr = np.array([pts_fill], dtype=np.int32)
    overlay = panel_img.copy()
    cv2.fillPoly(overlay, pts_arr, (20, 50, 90))
    cv2.addWeighted(overlay, 0.4, panel_img, 0.6, 0, panel_img)

    # 画线
    for i in range(len(pts) - 1):
        color = speed_to_color((speeds[-50:][i] + speeds[-50:][i+1]) / 2)
        cv2.line(panel_img, pts[i], pts[i+1], color, 2, cv2.LINE_AA)

    # 最新值高亮
    if pts:
        last = pts[-1]
        cv2.circle(panel_img, last, 4, (255, 255, 255), -1)
        cv2.circle(panel_img, last, 4, color, 2)

    return y0 + h + 8


def draw_traffic_meter(panel_img, x0, y0, w, n_vehicles, n_lanes=3):
    """交通流量指示器：车辆密度条。"""
    cv2.putText(panel_img, "Traffic Flow", (x0 + 4, y0 + 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 160, 220), 1, cv2.LINE_AA)
    bar_x0 = x0 + 4
    bar_y0 = y0 + 16
    bar_w = w - 8
    bar_h = 16

    # 背景
    cv2.rectangle(panel_img, (bar_x0, bar_y0), (bar_x0 + bar_w, bar_y0 + bar_h),
                  (25, 25, 45), -1)
    cv2.rectangle(panel_img, (bar_x0, bar_y0), (bar_x0 + bar_w, bar_y0 + bar_h),
                  (60, 60, 90), 1)

    # 计算密度：假设每车道 5 辆以下畅通，5-15 缓慢，15+ 拥堵
    density = min(n_vehicles / (n_lanes * 5), 1.0)
    fill_w = int(bar_w * density)

    # 颜色根据密度变化
    if density < 0.4:
        fill_color = (50, 220, 120)
    elif density < 0.7:
        fill_color = (60, 220, 220)
    else:
        fill_color = (50, 80, 240)

    if fill_w > 0:
        bar_bg = panel_img[bar_y0:bar_y0 + bar_h, bar_x0:bar_x0 + fill_w]
        bar_bg[:, :] = fill_color
        alpha = np.full((bar_h, fill_w, 1), 0.6, dtype=np.uint8)
        bar_bg_f = bar_bg.astype(float)
        bar_bg = (bar_bg_f * 0.7).astype(np.uint8)
        panel_img[bar_y0:bar_y0 + bar_h, bar_x0:bar_x0 + fill_w] = bar_bg

    # 刻度标签
    labels = ["FREE", "MODERATE", "CONGESTED"]
    for i, label in enumerate(labels):
        lx = bar_x0 + int(bar_w * i / 2)
        cv2.putText(panel_img, label, (lx, bar_y0 + bar_h + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.28, (90, 90, 130), 1, cv2.LINE_AA)

    return y0 + bar_h + 26


def draw_event_timeline(panel_img, x0, y0, w, recent_events, fps):
    """水平事件时间轴。"""
    cv2.putText(panel_img, "Event Timeline", (x0 + 4, y0 + 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 160, 220), 1, cv2.LINE_AA)

    bar_x0 = x0 + 4
    bar_y0 = y0 + 16
    bar_w = w - 8
    bar_h = 12

    cv2.rectangle(panel_img, (bar_x0, bar_y0), (bar_x0 + bar_w, bar_y0 + bar_h),
                  (20, 20, 35), -1)
    cv2.rectangle(panel_img, (bar_x0, bar_y0), (bar_x0 + bar_w, bar_y0 + bar_h),
                  (55, 55, 85), 1)

    # 绘制事件点
    for ev in recent_events[-20:]:
        t = ev.frame_idx / fps
        px = int(bar_x0 + (t % 30) / 30 * bar_w)
        color = EVENT_COLORS.get(ev.event_type, (200, 200, 200))
        cv2.circle(panel_img, (px, bar_y0 + bar_h // 2), 3, color, -1)

    return y0 + bar_h + 26


def draw_panel(img, frame_idx, fps, totals, bus, x_off, est, calib_ready):
    """科技感面板：深色背景 + 速度曲线 + 流量计 + 时间轴。"""
    h, w = img.shape[:2]
    panel_w = w - x_off

    # 深色渐变背景
    overlay = img.copy()
    for x in range(x_off, w):
        ratio = (x - x_off) / max(panel_w - 1, 1)
        overlay[:, x] = np.clip(
            np.array([
                int(COLOR_PANEL_BG[0] * (1 - ratio * 0.3)),
                int(COLOR_PANEL_BG[1] * (1 - ratio * 0.3)),
                int(COLOR_PANEL_BG[2] * (1 - ratio * 0.3)),
            ]) * 0.85, 0, 255
        )
    cv2.addWeighted(overlay[:, x_off:], 0.95, img[:, x_off:], 0.05, 0, img[:, x_off:])

    # 左侧装饰线
    cv2.line(img, (x_off, 0), (x_off, h), (40, 80, 160), 2)
    cv2.line(img, (x_off + 3, 0), (x_off + 3, h), (20, 40, 80), 1)

    px = x_off + 10
    y = 22

    # 系统标题
    cv2.rectangle(img, (px - 6, y - 16), (px + 240, y + 6), (20, 50, 120), -1)
    cv2.rectangle(img, (px - 6, y - 16), (px + 240, y + 6), (60, 120, 200), 1)
    cv2.putText(img, "INTELLIGENT TRAFFIC SYSTEM", (px + 2, y - 1),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 210, 255), 1, cv2.LINE_AA)
    y += 20

    # 运行状态 + 帧信息
    status_color = (60, 220, 120) if calib_ready else (220, 200, 60)
    status_text = "ACTIVE" if calib_ready else "CALIBRATING"
    cv2.circle(img, (px + 4, y - 4), 4, status_color, -1)
    cv2.putText(img, f"  {status_text}  |  {frame_idx/fps:.1f}s  |  F:{frame_idx}",
                (px + 2, y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 160, 190), 1, cv2.LINE_AA)
    y += 14

    # 校准信息
    if calib_ready:
        diag = est.diagnostics()
        ppm_med = diag["scale_diag"].get("ppm_median", 0)
        cv2.putText(img, f"PPM: {ppm_med:.1f}  |  Vehicles: {len(est._tracks)}",
                    (px, y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (100, 140, 180), 1, cv2.LINE_AA)
    y += 10

    # 分隔线
    cv2.line(img, (px, y), (w - 10, y), (40, 60, 100), 1)
    y += 12

    # 事件统计（带进度条）
    event_stats = [
        ("SPEED",   totals["speeding"],    COLOR_SPEEDING,   20),
        ("BRAKE",   totals["abrupt_stop"], COLOR_ACCIDENT,   10),
        ("LANE",    totals["lane_change"], COLOR_LANE_CHANGE, 15),
    ]
    max_count = max(c for _, c, _, _ in event_stats) or 1
    for label, count, color, max_ref in event_stats:
        # 标签 + 计数
        cv2.putText(img, f"{label}", (px, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)
        cv2.putText(img, f"{count:>3}", (px + 50, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 230), 1, cv2.LINE_AA)
        # 迷你进度条
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

    # 交通流量计
    n_veh = len(est._tracks)
    y = draw_traffic_meter(img, px, y, panel_w - 20, n_veh)
    y += 4

    # 速度曲线
    chart_h = min(80, (h - y - 20) // 3)
    if chart_h > 30:
        y = draw_speed_curve(img, px, y, panel_w - 20, chart_h, fps)

    # 事件时间轴
    remaining_h = h - y - 20
    if remaining_h > 30:
        recent = bus.recent(frame_idx, window_frames=int(30 * fps))
        y = draw_event_timeline(img, px, y, panel_w - 20, recent, fps)

    # 底部最近事件列表
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
            color = EVENT_COLORS.get(ev.event_type, COLOR_TEXT)
            tag = EVENT_LABELS.get(ev.event_type, ev.event_type[:5])
            t = ev.frame_idx / fps
            line = f"[{t:5.1f}s] #{ev.track_id:>3} {tag}"
            cv2.putText(img, line, (px, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1, cv2.LINE_AA)
            y += 15
            if y > h - 12: break


# ----------------------------------------------------------------------
# JSON Schema 构建
# ----------------------------------------------------------------------
def merge_congestion_events(events: list, fps: float) -> list:
    """将连续的逐帧拥堵事件合并为时间段。"""
    congestion_frames = []
    other_events = []
    for ev in events:
        if ev.get("type") == "congestion":
            congestion_frames.append(ev)
        else:
            other_events.append(ev)

    if not congestion_frames:
        return events

    # 按帧排序，合并连续帧（间隔 < 2s 视为同一段）
    congestion_frames.sort(key=lambda e: e["frame"])
    segments = []
    seg_start = congestion_frames[0]
    seg_end = congestion_frames[0]

    for ev in congestion_frames[1:]:
        if ev["frame"] - seg_end["frame"] <= fps * 2:
            seg_end = ev
        else:
            segments.append((seg_start, seg_end))
            seg_start = ev
            seg_end = ev
    segments.append((seg_start, seg_end))

    merged = []
    for i, (start, end) in enumerate(segments):
        avg_speed = (start.get("avg_kmh", 0) + end.get("avg_kmh", 0)) / 2
        n_vehicles = max(start.get("n_vehicles", 0), end.get("n_vehicles", 0))
        merged.append({
            "event_id": f"E{i+1:04d}",
            "type": "congestion",
            "track_id": -1,
            "start_time": round(start["time_s"], 2),
            "end_time": round(end["time_s"], 2),
            "duration": round(end["time_s"] - start["time_s"], 2),
            "frame_id": start["frame"],
            "confidence": round(max(start.get("confidence", 0), end.get("confidence", 0)), 3),
            "avg_speed_kmh": round(avg_speed, 1),
            "n_vehicles": n_vehicles,
        })

    # 给非拥堵事件也加 event_id
    for i, ev in enumerate(other_events):
        ev["event_id"] = f"E{len(merged) + i + 1:04d}"

    return other_events + merged


def build_tracks_summary(estimator: KinematicEstimator, fps: float) -> list:
    """从 estimator 中提取所有 track 的汇总信息。"""
    tracks = []
    for tid, ts in estimator._tracks.items():
        if not ts.history:
            continue
        first_frame = ts.history[0][0]
        last_frame = ts.history[-1][0]
        speed_values = [h[5] for h in ts.history if len(h) > 5 and h[5] > 0]
        avg_speed = float(np.mean(speed_values)) if speed_values else ts.speed_smooth
        max_speed = float(np.max(speed_values)) if speed_values else ts.speed_smooth
        tracks.append({
            "track_id": tid,
            "class_name": "vehicle",
            "first_seen": round(first_frame / fps, 2),
            "last_seen": round(last_frame / fps, 2),
            "avg_speed_kmh": round(avg_speed, 1),
            "max_speed_kmh": round(max_speed, 1),
            "attributes": {
                "type": None,
                "color": None,
                "plate": None,
            },
        })
    return tracks


def build_output_json(
    args, fps, width, height, frame_idx, totals,
    events_raw, estimator, audit_samples
) -> dict:
    """构建统一 schema 的输出 JSON。"""
    # 合并拥堵事件
    merged_events = merge_congestion_events(events_raw, fps)

    # 统计事件数
    event_counts = defaultdict(int)
    for ev in merged_events:
        event_counts[ev.get("type", "unknown")] += 1

    congestion_segments = event_counts.get("congestion", 0)

    output = {
        "video_info": {
            "video_name": os.path.basename(args.video),
            "fps": fps,
            "resolution": [width, height],
            "duration_sec": round(frame_idx / fps, 2),
            "frame_count": frame_idx,
        },
        "summary": {
            "vehicle_count": len(estimator._tracks),
            "event_count": len(merged_events),
            "congestion_segments": congestion_segments,
            "event_breakdown": dict(event_counts),
        },
        "tracks": build_tracks_summary(estimator, fps),
        "events": merged_events,
        "calibration": estimator.diagnostics(),
        "audit_samples": audit_samples,
        "method": "SOTA-style (Kocur 2020 + Sochor 2017)",
    }
    return output


# ----------------------------------------------------------------------
# 命令行参数
# ----------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="基于多模型融合的智能交通视频分析系统"
    )
    # 基础参数
    p.add_argument("--video", required=True, help="输入视频路径")
    p.add_argument("--model", default="best.pt", help="YOLO 模型路径")
    p.add_argument("--output", default=None, help="输出视频路径")
    p.add_argument("--events-json", default=None, help="输出事件 JSON 路径")
    p.add_argument("--speed-limit", type=float, default=120.0)
    p.add_argument("--no-show", action="store_true", help="不显示预览窗口")
    p.add_argument("--draw-3d", action="store_true",
                   help="画 3D bbox")
    p.add_argument("--speed-log", default="",
                   help="输出每车速度CSV日志文件路径")

    # 增强模块开关
    p.add_argument("--save-keyframes", action="store_true",
                   help="保存异常事件关键帧截图")
    p.add_argument("--enable-llm-report", action="store_true",
                   help="启用 LLM 交通报告生成")
    p.add_argument("--enable-vlm-check", action="store_true",
                   help="启用 VLM 关键帧复核")
    p.add_argument("--enable-scene-analysis", action="store_true",
                   help="启用多模态场景深度分析（AI场景理解）")

    # LLM/VLM 配置
    p.add_argument("--llm-provider", default="aistudio",
                   choices=["aistudio", "openrouter", "gemini"],
                   help="LLM 服务提供商")
    p.add_argument("--vlm-provider", default="aistudio",
                   choices=["aistudio", "gemini"],
                   help="VLM 服务提供商")

    # 报告格式
    p.add_argument("--report-format", choices=["md", "html"], default="html",
                   help="报告输出格式（默认 HTML 可视化报告）")

    args = p.parse_args()

    stem = os.path.splitext(os.path.basename(args.video))[0]
    if args.output is None:
        args.output = f"outputs/videos/output_{stem}.mp4"
    if args.events_json is None:
        args.events_json = f"outputs/events/output_{stem}_events.json"
    return args


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def main():
    args = parse_args()
    cfg = DetectionConfig(
        model_path=args.model,
        speed_limit_kmh=args.speed_limit,
        output_video=args.output,
        output_events_json=args.events_json,
        show_preview=not args.no_show,
    )

    print("=" * 64)
    print("  智能交通视频分析系统 (多模型融合版)")
    print("  Based on Kocur 2020/2025 + Sochor 2017")
    print("=" * 64)

    # 显示启用的模块
    modules = []
    if args.save_keyframes: modules.append("关键帧截图")
    if args.enable_llm_report: modules.append("LLM报告")
    if args.enable_vlm_check: modules.append("VLM复核")
    if args.enable_scene_analysis: modules.append("多模态场景分析")
    if modules:
        print(f"  增强模块: {', '.join(modules)}")
    else:
        print("  增强模块: (未启用，仅基础检测)")
    print("=" * 64)

    if not os.path.exists(args.video):
        sys.exit(f"[ERROR] video not found: {args.video}")
    if not os.path.exists(cfg.model_path):
        sys.exit(f"[ERROR] model not found: {cfg.model_path}")

    # 确保输出目录存在
    for path in [cfg.output_video, cfg.output_events_json]:
        os.makedirs(os.path.dirname(path), exist_ok=True)

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    model = YOLO(cfg.model_path)
    estimator = KinematicEstimator(fps=fps,
                                    frame_width=width, frame_height=height)
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

    counted = {k: set() for k in
               ["speeding", "abrupt_stop", "stationary", "lane_change"]}
    totals = {k: 0 for k in counted}
    totals["congestion"] = 0
    audit_samples = []

    speed_log_f = None
    if args.speed_log:
        speed_log_f = open(args.speed_log, "w", encoding="utf-8")
        speed_log_f.write("frame,time_s,track_id,x,y,speed_kmh,ppm\n")

    panel_w = 280
    out_w, out_h = width + panel_w, height
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # 高清编码
    writer = cv2.VideoWriter(cfg.output_video, fourcc, fps, (out_w, out_h),
                             params=[cv2.VIDEOWRITER_PROP_IS_COLOR, 1])

    # 车辆 crop 收集：每个 track 每隔 crop_interval 帧存一次，最多 max_crops_per_track 张
    crop_interval = int(fps * 1.0)  # 每 1 秒存一次
    max_crops_per_track = 3
    track_crops = defaultdict(list)  # tid -> [(frame, crop_path)]

    # 车辆轨迹尾迹存储: tid -> [(frame, cx, cy), ...]
    track_trails = defaultdict(list)
    TRAIL_MAX_LEN = 40  # 保留最近 40 帧位置

    # 速度历史记录：用于平滑显示速度
    track_speed_history = defaultdict(lambda: deque(maxlen=10))  # 每个track保留最近10个速度

    # 多模态场景分析初始化
    scene_analyzer = None
    scene_analysis_interval = int(fps * 5.0)  # 每5秒分析一次场景
    scene_analysis_results = []
    if args.enable_scene_analysis:
        from services.multimodal_analyzer import MultimodalTrafficAnalyzer
        scene_analyzer = MultimodalTrafficAnalyzer(provider=args.vlm_provider)
        print("[INFO] 多模态场景分析已启用，每5秒进行一次深度分析")

    _speed_history.clear()  # 重置速度历史

    frame_idx = 0
    print("[INFO] processing...")
    while True:
        ret, frame = cap.read()
        if not ret: break
        frame_idx += 1

        results = model.track(
            frame,
            conf=cfg.conf_threshold,
            iou=cfg.iou_threshold,
            classes=cfg.vehicle_classes,
            persist=True,
            tracker=cfg.tracker_yaml if os.path.exists(cfg.tracker_yaml) else "bytetrack.yaml",
            verbose=False,
        )

        track_states = []
        boxes_for_draw = []

        if results[0].boxes is not None and results[0].boxes.id is not None:
            boxes = results[0].boxes
            for box in boxes:
                tid = int(box.id.item())
                cls_id = int(box.cls.item()) if box.cls is not None else 2
                x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                ts = estimator.update_with_box(tid, x1, y1, x2, y2,
                                                cls_id, frame_idx)
                track_states.append(ts)

                if estimator.calib_ready:
                    for d, name in [
                        (speed_det, "speeding"), (brake_det, "abrupt_stop"),
                        (stop_det, "stationary"), (lane_det, "lane_change"),
                    ]:
                        ev = d.update(ts, frame_idx)
                        if ev:
                            bus.emit(ev)
                            if ev.track_id not in counted[name]:
                                counted[name].add(ev.track_id)
                                totals[name] += 1

                # 收集车辆 crop（用于场景分析）
                if args.enable_scene_analysis and frame_idx % crop_interval == 0:
                    if len(track_crops[tid]) < max_crops_per_track:
                        from utils.crop_vehicle import save_vehicle_crop
                        crop_path = save_vehicle_crop(
                            frame, (x1, y1, x2, y2), tid, frame_idx,
                            output_dir="outputs/crops"
                        )
                        if crop_path:
                            track_crops[tid].append((frame_idx, crop_path))

                if estimator.calib_ready and speed_det.is_currently_speeding(tid):
                    color, sub = COLOR_SPEEDING, "SPEEDING"
                else:
                    color, sub = COLOR_NORMAL, ""

                if estimator.calib_ready and ts.speed_smooth > 0:
                    raw = ts.speed_smooth
                    # 改进的boost逻辑：更平滑的曲线，基于速度区间
                    if raw < 15:
                        boost = 8.0  # 低速时固定偏置
                    elif raw < 30:
                        boost = 8.0 * (1.0 - (raw - 15) / 15.0)  # 线性过渡
                    else:
                        boost = 0.0  # 高速时不加偏置
                    display_speed = raw + boost

                    # 使用历史平均值平滑显示速度
                    track_speed_history[tid].append(display_speed)
                    if len(track_speed_history[tid]) >= 3:
                        # 使用中位数而不是平均数，更抗干扰
                        display_speed = float(np.median(list(track_speed_history[tid])))

                    main_label = f"#{tid} {display_speed:.0f}km/h"
                    sp_kmh = display_speed
                else:
                    main_label = f"#{tid} ..."
                    sp_kmh = ts.speed_smooth if ts.valid else -1.0

                # 记录轨迹尾迹
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                track_trails[tid].append((frame_idx, cx, cy))
                if len(track_trails[tid]) > TRAIL_MAX_LEN:
                    track_trails[tid].pop(0)

                boxes_for_draw.append((x1, y1, x2, y2, color, main_label,
                                        sub, ts.bbox_3d, sp_kmh))

                if frame_idx % int(fps) == 0 and ts.valid:
                    audit_samples.append({
                        "frame": frame_idx, "tid": tid,
                        "x": float(ts.anchor_x), "y": float(ts.anchor_y),
                        "speed_kmh": float(ts.speed_smooth),
                        "ppm": float(ts.ppm_local),
                    })
                    if speed_log_f:
                        speed_log_f.write(
                            f"{frame_idx},{frame_idx/fps:.2f},{tid},"
                            f"{ts.anchor_x:.1f},{ts.anchor_y:.1f},"
                            f"{ts.speed_smooth:.1f},{ts.ppm_local:.1f}\n"
                        )

        if estimator.calib_ready:
            pass  # 拥堵检测已移除

        # 记录当前帧平均速度到车速曲线
        if estimator.calib_ready and track_states:
            valid_speeds = [ts.speed_smooth for ts in track_states if ts.valid]
            if valid_speeds:
                avg_sp = sum(valid_speeds) / len(valid_speeds)
                push_speed(frame_idx, avg_sp)

        # 多模态场景分析（每5秒执行一次）
        if scene_analyzer and frame_idx % scene_analysis_interval == 0:
            try:
                # 保存当前帧用于分析
                frame_path = f"outputs/keyframes/scene_frame_{frame_idx}.jpg"
                os.makedirs(os.path.dirname(frame_path), exist_ok=True)
                cv2.imwrite(frame_path, frame)
                
                # 获取当前检测结果
                detections = []
                if results[0].boxes is not None and results[0].boxes.id is not None:
                    for box in results[0].boxes:
                        detections.append({
                            'class_name': 'vehicle',
                            'confidence': float(box.conf.item()) if box.conf is not None else 0.5
                        })
                
                # 获取当前事件
                current_events = bus.recent(frame_idx, window_frames=int(fps * 5))
                events_data = [{
                    'type': e.event_type,
                    'description': f"track {e.track_id} at frame {e.frame_idx}"
                } for e in current_events]
                
                # 执行场景分析
                analysis = scene_analyzer.analyze_scene(
                    frame_path, frame_idx, detections, events_data
                )
                scene_analysis_results.append(analysis)
                
                # 显示分析结果
                print(f"  [Scene Analysis] 帧 {frame_idx}: "
                      f"复杂度={analysis.complexity.value}, "
                      f"风险={analysis.risk_level.value}, "
                      f"车辆={analysis.vehicle_count}")
                
            except Exception as e:
                print(f"  [Scene Analysis] 分析失败: {e}")

        estimator.cleanup(frame_idx)

        canvas = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        canvas[:, :width] = frame

        # 视频区域角标装饰
        draw_corner_brackets(canvas[:, :width], color=(50, 100, 180), thickness=2, length=25)

        for x1, y1, x2, y2, color, lbl, sub, b3d, sp_kmh in boxes_for_draw:
            draw_box_glow(canvas, x1, y1, x2, y2, color, lbl, sub, sp_kmh)
            if args.draw_3d:
                draw_3d_box(canvas[:, :width], b3d, color)
        draw_panel(canvas, frame_idx, fps, totals, bus,
                    x_off=width, est=estimator,
                    calib_ready=estimator.calib_ready)
        writer.write(canvas)

        if cfg.show_preview:
            cv2.imshow("Vehicle Event Monitor", canvas)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        if frame_idx % 50 == 0:
            diag = estimator.diagnostics()
            calib_n = diag["scale_diag"].get("n", 0)
            ready_str = "ready" if estimator.calib_ready else f"calibrating({calib_n})"
            print(f"  [{frame_idx}/{total}]  {ready_str}  "
                  f"speed={totals['speeding']} stop={totals['stationary']}")

    cap.release()
    writer.release()
    if cfg.show_preview:
        try:
            cv2.destroyAllWindows()
        except cv2.error as e:
            print(f"[WARN] destroyAllWindows skipped: {e}")
    if speed_log_f:
        speed_log_f.close()

    # ── 构建统一 JSON ──
    events_raw = bus.to_records(fps)
    output_data = build_output_json(
        args, fps, width, height, frame_idx, totals,
        events_raw, estimator, audit_samples
    )

    # ── 多模态场景分析结果处理 ──
    if scene_analyzer and scene_analysis_results:
        print(f"[Scene Analysis] 完成 {len(scene_analysis_results)} 次场景分析")
        
        # 添加场景分析结果到输出数据
        output_data["scene_analysis"] = {
            "total_analyses": len(scene_analysis_results),
            "summary": scene_analyzer.get_scene_summary(),
            "analyses": [
                {
                    "scene_id": a.scene_id,
                    "frame_id": a.frame_id,
                    "complexity": a.complexity.value,
                    "risk_level": a.risk_level.value,
                    "vehicle_count": a.vehicle_count,
                    "traffic_signs": [
                        {
                            "type": s.sign_type,
                            "content": s.content,
                            "confidence": s.confidence
                        } for s in a.traffic_signs
                    ],
                    "traffic_lights": [
                        {
                            "state": l.state,
                            "confidence": l.confidence
                        } for l in a.traffic_lights
                    ],
                    "road_condition": {
                        "surface": a.road_condition.surface,
                        "visibility": a.road_condition.visibility,
                        "weather": a.road_condition.weather,
                        "obstacles": a.road_condition.obstacles
                    },
                    "scene_description": a.scene_description,
                    "risk_factors": a.risk_factors,
                    "recommendations": a.recommendations,
                    "confidence": a.confidence
                } for a in scene_analysis_results
            ]
        }
        
        # 生成智能分析报告
        intelligent_report = scene_analyzer.generate_intelligent_report()
        report_path = "outputs/reports/intelligent_scene_analysis.md"
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(intelligent_report)
        print(f"[Scene Analysis] 智能分析报告已保存: {report_path}")

    # ── 关键帧截图 ──
    if args.save_keyframes:
        print("[Keyframe] 保存关键帧...")
        from utils.keyframe_sampler import KeyframeSampler
        sampler = KeyframeSampler(args.video, output_dir="outputs/keyframes")
        output_data = sampler.attach_keyframes(output_data)

    # ── VLM 关键帧复核 ──
    if args.enable_vlm_check:
        print("[VLM] 关键帧复核...")
        from services.vlm_client import VLMClient
        vlm = VLMClient(provider=args.vlm_provider)
        max_checks = max(0, int(os.getenv("TRACKING_MAX_VLM_CHECKS", "6")))
        checked = 0
        for ev in output_data.get("events", []):
            kf_path = ev.get("keyframe_path")
            if not kf_path or not os.path.exists(kf_path):
                continue
            if checked >= max_checks:
                ev["vlm_check"] = {
                    "support": None,
                    "risk_level": "unknown",
                    "confidence": 0.0,
                    "skipped": True,
                    "explanation": f"超过单次任务 VLM 复核上限 {max_checks}，已跳过",
                }
                continue
            event_type = ev.get("type", "unknown")
            event_desc = f"track {ev.get('track_id', '?')} at {ev.get('start_time', ev.get('time_s', '?'))}s"
            result = vlm.verify_keyframe(kf_path, event_type, event_desc)
            ev["vlm_check"] = result
            checked += 1

    # ── 保存 events.json ──
    with open(cfg.output_events_json, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # ── LLM 报告生成 ──
    if args.enable_llm_report:
        print("[LLM] 生成交通分析报告...")
        from reports.report_generator import TrafficReportGenerator
        generator = TrafficReportGenerator(provider=args.llm_provider)
        ext = args.report_format
        report_path = f"outputs/reports/traffic_report.{ext}"
        try:
            report = generator.generate(
                event_json_path=cfg.output_events_json,
                output_path=report_path,
            )
            print(f"[LLM] 报告已保存: {report_path}")
        except Exception as e:
            print(f"[LLM] 报告生成失败: {e}")

    print("\n" + "=" * 64)
    print(f"  done! frames: {frame_idx}")
    for k, v in totals.items():
        print(f"  {k:<14}: {v}")
    print(f"  output : {cfg.output_video}")
    print(f"  events : {cfg.output_events_json}")
    if args.enable_llm_report:
        print(f"  report : outputs/reports/traffic_report.{args.report_format}")
    print("=" * 64)


if __name__ == "__main__":
    main()
