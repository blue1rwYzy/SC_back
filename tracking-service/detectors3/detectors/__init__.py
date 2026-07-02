"""SOTA-style 车辆事件检测器（基于 Kocur 2020/2025 + Sochor 2017 论文）。"""
from .kinematic import KinematicEstimator, TrackState
from .vanishing_points import VanishingPointDetector, VanishingPoints
from .lifting_3d import lift_2d_to_3d, Bbox3D
from .scale_calibration import ScaleCalibrator, VEHICLE_LENGTHS_M
from .events import (
    Event, EventBus,
    SpeedingDetector, AbruptStopDetector, StationaryDetector,
    LaneChangeDetector, CongestionDetector,
)

__all__ = [
    "KinematicEstimator", "TrackState",
    "VanishingPointDetector", "VanishingPoints",
    "lift_2d_to_3d", "Bbox3D",
    "ScaleCalibrator", "VEHICLE_LENGTHS_M",
    "Event", "EventBus",
    "SpeedingDetector", "AbruptStopDetector", "StationaryDetector",
    "LaneChangeDetector", "CongestionDetector",
]