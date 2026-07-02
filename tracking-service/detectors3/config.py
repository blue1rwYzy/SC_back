"""
config.py
=========
全局配置。所有可调参数集中在这里，main.py 不再硬编码。
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class DetectionConfig:
    # ---- YOLO ----
    model_path: str = "best.pt"
    conf_threshold: float = 0.35
    iou_threshold: float = 0.45
    vehicle_classes: Optional[List[int]] = None
    tracker_yaml: str = "bytetrack.yaml"

    # ---- 物理标定 ----
    calibration_path: str = ""              # 留空 = 用默认 ppm
    default_ppm_near: float = 8.0           # 仅在无标定时使用
    default_ppm_far: float = 3.0

    # ---- 速度阈值 ----
    speed_limit_kmh: float = 120.0
    speed_window_s: float = 1.0
    speed_ratio: float = 0.7
    speed_hysteresis_kmh: float = 5.0

    # ---- 急刹 ----
    abrupt_accel_threshold: float = -10.0   # m/s²
    abrupt_min_initial_speed_kmh: float = 45.0

    # ---- 静止 / 事故 ----
    stationary_threshold_kmh: float = 1.0
    stationary_min_duration_s: float = 3.0

    # ---- 变道 ----
    lane_change_window_s: float = 1.0
    lane_change_lateral_m: float = 2.5
    lane_change_min_speed_kmh: float = 15.0

    # ---- 拥堵 ----
    congestion_threshold_kmh: float = 20.0
    congestion_min_vehicles: int = 4

    # ---- 输出 ----
    output_video: str = "output.mp4"
    output_events_json: str = "output_events.json"
    show_preview: bool = False


# 颜色 (BGR) - 暗色调，避免过亮
COLOR_NORMAL = (80, 160, 60)        # 暗绿色
COLOR_SPEEDING = (0, 60, 200)       # 暗红色
COLOR_LANE_CHANGE = (180, 120, 50)  # 暗橙色
COLOR_ACCIDENT = (30, 30, 180)      # 暗红色
COLOR_STATIONARY = (0, 150, 180)    # 暗青色
COLOR_PANEL_BG = (20, 20, 28)       # 深色面板背景
COLOR_TEXT = (200, 200, 200)        # 柔和白色
COLOR_DIM = (100, 100, 110)        # 暗灰色
