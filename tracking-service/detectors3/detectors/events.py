"""
detectors/events.py
===================
事件检测器集合。所有检测器都从 KinematicEstimator 提供的 TrackState 出发，
对运动学量做时间窗口判定，输出离散事件 + 置信度。

包含：
  - SpeedingDetector       持续超速
  - AbruptStopDetector     急刹（潜在事故）
  - StationaryDetector     长时间静止（确认事故 / 抛锚）
  - LaneChangeDetector     横向位移突增（变道事件，非"违规"）
  - CongestionDetector     区域均速过低（拥堵）
"""

from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

from .kinematic import TrackState


# ----------------------------------------------------------------------
# 事件数据结构
# ----------------------------------------------------------------------
@dataclass
class Event:
    """一个被检测出的事件。"""
    track_id: int
    event_type: str          # "speeding" | "abrupt_stop" | "stationary" | "lane_change" | "congestion"
    confidence: float        # 0~1
    frame_idx: int
    extra: dict              # 额外信息，例如 {"speed_kmh": 132.5}


# ----------------------------------------------------------------------
# 1) 超速：滑窗 + 比例确认 + 状态可恢复
# ----------------------------------------------------------------------
class SpeedingDetector:
    """
    判定逻辑：过去 window_s 秒内有 >= ratio 比例的样本超过 limit_kmh，
    则进入 SPEEDING 状态。一旦回到 limit_kmh - hysteresis 以下同等时间，
    就退出 SPEEDING。
    """

    def __init__(
        self,
        limit_kmh: float = 120.0,
        fps: float = 30.0,
        window_s: float = 1.0,
        ratio: float = 0.7,
        hysteresis_kmh: float = 5.0,
    ):
        self.limit = limit_kmh
        self.fps = fps
        self.window = max(3, int(window_s * fps))
        self.ratio = ratio
        self.hysteresis = hysteresis_kmh

        self._buf: Dict[int, Deque[float]] = defaultdict(
            lambda: deque(maxlen=self.window)
        )
        self._is_speeding: Dict[int, bool] = {}

    def update(self, ts: TrackState, frame_idx: int) -> Optional[Event]:
        if not ts.valid:
            return None
        if not ts.in_speed_zone:
            return None
        buf = self._buf[ts.track_id]
        buf.append(ts.speed_smooth)

        if len(buf) < self.window:
            return None

        arr = np.asarray(buf)
        currently_speeding = self._is_speeding.get(ts.track_id, False)

        if not currently_speeding:
            # 进入条件
            if (arr > self.limit).mean() >= self.ratio:
                self._is_speeding[ts.track_id] = True
                avg_over = float(arr[arr > self.limit].mean())
                conf = min(1.0, (avg_over - self.limit) / 30.0 + 0.5)
                return Event(
                    track_id=ts.track_id,
                    event_type="speeding",
                    confidence=conf,
                    frame_idx=frame_idx,
                    extra={"speed_kmh": float(arr[-1]), "avg_kmh": avg_over},
                )
        else:
            # 退出条件
            low_thr = self.limit - self.hysteresis
            if (arr < low_thr).mean() >= self.ratio:
                self._is_speeding[ts.track_id] = False
        return None

    def is_currently_speeding(self, track_id: int) -> bool:
        return self._is_speeding.get(track_id, False)


# ----------------------------------------------------------------------
# 2) 急刹：加速度阈值
# ----------------------------------------------------------------------
class AbruptStopDetector:
    """
    判定：短时间内出现显著减速，且加速度低于阈值。
    冷却期 cooldown_s 防止同一车辆重复触发。
    """

    def __init__(
        self,
        accel_threshold: float = -10.0,
        min_initial_speed_kmh: float = 45.0,
        cooldown_s: float = 5.0,
        fps: float = 30.0,
    ):
        self.threshold = accel_threshold
        self.min_speed = min_initial_speed_kmh
        self.fps = fps
        self.cooldown_frames = int(cooldown_s * fps)
        self._last_trigger: Dict[int, int] = {}

    def update(self, ts: TrackState, frame_idx: int) -> Optional[Event]:
        if not ts.valid:
            return None
        if not ts.in_speed_zone:
            return None
        last = self._last_trigger.get(ts.track_id, -10**9)
        if frame_idx - last < self.cooldown_frames:
            return None

        # 暖机保护：每个 track 至少稳定跟踪约 2 秒才能触发。
        if len(ts.history) < int(2.0 * self.fps):
            return None

        # 用约 1 秒前的速度判断是否真的发生明显减速，而不是平滑抖动。
        if len(ts.history) < int(1.0 * self.fps):
            return None
        lookback = min(len(ts.history), max(12, int(1.0 * self.fps)))
        old = ts.history[-lookback]
        old_speed_kmh = old[5] if len(old) > 5 else float(np.hypot(old[3], old[4])) * 3.6
        if old_speed_kmh < self.min_speed:
            return None

        speed_drop_kmh = old_speed_kmh - ts.speed_smooth
        required_drop = max(18.0, old_speed_kmh * 0.35)
        if speed_drop_kmh < required_drop:
            return None
        if ts.speed_smooth > old_speed_kmh * 0.75:
            return None

        if ts.accel_smooth < self.threshold:
            self._last_trigger[ts.track_id] = frame_idx
            severity = min(1.0, max(abs(ts.accel_smooth) / 16.0, speed_drop_kmh / max(old_speed_kmh, 1.0)))
            return Event(
                track_id=ts.track_id,
                event_type="abrupt_stop",
                confidence=severity,
                frame_idx=frame_idx,
                extra={
                    "accel_mps2": ts.accel_smooth,
                    "speed_before_kmh": old_speed_kmh,
                    "speed_now_kmh": ts.speed_smooth,
                    "speed_drop_kmh": speed_drop_kmh,
                },
            )
        return None


# ----------------------------------------------------------------------
# 3) 长时间静止：确认事故 / 抛锚 / 异常停车
# ----------------------------------------------------------------------
class StationaryDetector:
    """
    判定：连续 min_duration_s 秒内速度持续低于 threshold_kmh，
    并且速度波动很小（std < speed_std_max），才判定为静止。
    需要足够多观测帧才生效，避免新车前几帧误判。
    状态可恢复：再次加速会清除标记。
    """

    def __init__(
        self,
        threshold_kmh: float = 8.0,
        min_duration_s: float = 3.0,
        fps: float = 30.0,
        recover_kmh: float = 15.0,
        speed_std_max: float = 4.0,
    ):
        self.threshold = threshold_kmh
        self.window = max(5, int(min_duration_s * fps))
        self.recover = recover_kmh
        self.speed_std_max = speed_std_max
        self._buf: Dict[int, Deque[float]] = defaultdict(
            lambda: deque(maxlen=self.window)
        )
        self._is_stationary: Dict[int, bool] = {}

    def update(self, ts: TrackState, frame_idx: int) -> Optional[Event]:
        if not ts.valid:
            return None
        if not ts.in_speed_zone:
            return None
        buf = self._buf[ts.track_id]
        buf.append(ts.speed_smooth)

        if len(buf) < self.window:
            return None

        arr = np.array(buf, dtype=float)
        avg = float(np.mean(arr))
        std = float(np.std(arr))
        currently = self._is_stationary.get(ts.track_id, False)

        if not currently and avg < self.threshold and std < self.speed_std_max:
            self._is_stationary[ts.track_id] = True
            conf = max(0.4, 1.0 - avg / self.threshold)
            stability_bonus = max(0.0, 1.0 - std / self.speed_std_max)
            conf = min(1.0, conf * 0.7 + stability_bonus * 0.3)
            return Event(
                track_id=ts.track_id,
                event_type="stationary",
                confidence=conf,
                frame_idx=frame_idx,
                extra={"avg_kmh": round(avg, 1), "std_kmh": round(std, 1),
                       "duration_s": round(self.window / 30.0, 1)},
            )
        elif currently and avg > self.recover:
            self._is_stationary[ts.track_id] = False
        return None

    def is_currently_stationary(self, track_id: int) -> bool:
        return self._is_stationary.get(track_id, False)


# ----------------------------------------------------------------------
# 4) 变道：基于自身轨迹的横向位移
# ----------------------------------------------------------------------
class LaneChangeDetector:
    """
    判定：在 window_s 秒内，垂直于自身行驶方向的位移超过 lateral_threshold_m。

    *不需要*车道线模型，物理意义明确。
    *不再*谎称"违规变道"——仅作为事件 lane_change 输出。
    """

    def __init__(
        self,
        fps: float = 30.0,
        window_s: float = 1.0,
        lateral_threshold_m: float = 2.5,  # 一个车道的宽度约 3.5m，过半即记一次变道
        min_speed_kmh: float = 15.0,        # 太慢的不判（行驶方向不稳）
        cooldown_s: float = 1.5,
    ):
        self.fps = fps
        self.window = max(5, int(window_s * fps))
        self.lateral_thr = lateral_threshold_m
        self.min_speed = min_speed_kmh
        self.cooldown_frames = int(cooldown_s * fps)
        self._last_trigger: Dict[int, int] = {}

    def update(self, ts: TrackState, frame_idx: int) -> Optional[Event]:
        if not ts.valid or len(ts.history) < self.window:
            return None
        if not ts.in_speed_zone:
            return None
        if ts.speed_smooth < self.min_speed:
            return None
        last = self._last_trigger.get(ts.track_id, -10**9)
        if frame_idx - last < self.cooldown_frames:
            return None

        # 取 window 内的轨迹，做主成分：第一主成分 = 行驶方向，第二主成分 = 横向
        pts = np.array([(h[1], h[2]) for h in list(ts.history)[-self.window:]])
        pts -= pts.mean(axis=0)
        # SVD：v[0] 主方向，v[1] 横向
        try:
            _, _, vh = np.linalg.svd(pts, full_matrices=False)
        except np.linalg.LinAlgError:
            return None
        if vh.shape[0] < 2:
            return None

        lateral_axis = vh[1]
        lateral_proj = pts @ lateral_axis
        lateral_span_px = float(lateral_proj.max() - lateral_proj.min())

        # 像素 → 米：用实际标定的 ppm_local
        ppm_use = ts.ppm_local if ts.ppm_local > 0 else 8.0
        lateral_span_m = lateral_span_px / ppm_use

        if lateral_span_m > self.lateral_thr:
            self._last_trigger[ts.track_id] = frame_idx
            conf = min(1.0, lateral_span_m / (self.lateral_thr * 2))
            return Event(
                track_id=ts.track_id,
                event_type="lane_change",
                confidence=conf,
                frame_idx=frame_idx,
                extra={"lateral_m": lateral_span_m},
            )
        return None


# ----------------------------------------------------------------------
# 5) 拥堵：区域均速
# ----------------------------------------------------------------------
class CongestionDetector:
    """
    判定：当前帧画面里，至少 min_vehicles 辆车的平均速度 < threshold_kmh，
    则认为发生拥堵。这个是场景级事件而非个体事件。
    加入冷却期：同一段拥堵只触发一次开始事件，结束后可再次触发。
    """

    def __init__(self, threshold_kmh: float = 20.0, min_vehicles: int = 4,
                 cooldown_s: float = 10.0, fps: float = 30.0):
        self.threshold = threshold_kmh
        self.min_vehicles = min_vehicles
        self.cooldown_frames = int(cooldown_s * fps)
        self._last_trigger = -10**9
        self._in_congestion = False

    def update(self, all_states: List[TrackState], frame_idx: int) -> Optional[Event]:
        valid = [s for s in all_states if s.valid and len(s.history) > 10]
        if len(valid) < self.min_vehicles:
            if self._in_congestion:
                self._in_congestion = False
            return None
        avg = float(np.mean([s.speed_smooth for s in valid]))
        if avg < self.threshold:
            # 进入拥堵状态，只在首次触发时发出事件
            if not self._in_congestion:
                self._in_congestion = True
                # 冷却期内不再触发
                if frame_idx - self._last_trigger < self.cooldown_frames:
                    return None
                self._last_trigger = frame_idx
                return Event(
                    track_id=-1,
                    event_type="congestion",
                    confidence=min(1.0, 1.0 - avg / self.threshold),
                    frame_idx=frame_idx,
                    extra={"avg_kmh": avg, "n_vehicles": len(valid)},
                )
        else:
            self._in_congestion = False
        return None


# ----------------------------------------------------------------------
# 事件总线：把所有事件汇总输出
# ----------------------------------------------------------------------
class EventBus:
    """简单事件总线，支持订阅 + 历史查询 + JSON 导出。"""

    def __init__(self):
        self.events: List[Event] = []

    def emit(self, event: Optional[Event]):
        if event is not None:
            self.events.append(event)

    def recent(self, current_frame: int, window_frames: int = 90) -> List[Event]:
        return [e for e in self.events if current_frame - e.frame_idx <= window_frames]

    def to_records(self, fps: float = 30.0) -> List[dict]:
        return [{
            "frame": e.frame_idx,
            "time_s": round(e.frame_idx / fps, 2),
            "track_id": e.track_id,
            "type": e.event_type,
            "confidence": round(e.confidence, 3),
            **e.extra,
        } for e in self.events]
