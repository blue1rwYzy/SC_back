"""
detectors/kinematic.py
======================
SOTA-style 车辆运动学估算器（v7：VP1缺失时纯bbox-rate + 智能融合）。

核心改进（v5 → v6）：
  1. 道路方向感知速度：将 KF 像素速度投影到 VP1 方向（道路方向），
     而非简单 hypot(vX, vZ)。这消除了"斜着开被判超速"的问题。
  2. 鲁棒 bbox 宽度变化率：用 Theil-Sen 回归替代普通最小二乘，
     对 bbox 抖动有天然抗性。
  3. 自适应 EMA：速度变化一致时加速收敛，抖动时加强平滑。
  4. 双通道加权融合：KF投影速度（稳定但依赖ppm）与 bbox-rate速度
     （独立于ppm但噪声大）按各自置信度加权融合。
  5. 焦距从消失点几何估算，替代 max(w,h) 的粗略猜测。
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional, Tuple

import numpy as np

from .vanishing_points import VanishingPointDetector, VanishingPoints
from .lifting_3d import lift_2d_to_3d, Bbox3D
from .scale_calibration import (
    ScaleCalibrator,
    VEHICLE_WIDTHS_M, DEFAULT_VEHICLE_WIDTH_M,
)


@dataclass
class TrackState:
    track_id: int
    cls_id: int = 2

    x: float = 0.0
    y: float = 0.0
    bbox_2d: Tuple[float, float, float, float] = (0, 0, 0, 0)
    bbox_3d: Optional[Bbox3D] = None
    anchor_x: float = 0.0
    anchor_y: float = 0.0

    bbox_w_history: Deque[Tuple[int, float]] = field(
        default_factory=lambda: deque(maxlen=20)
    )
    bbox_w_smooth: float = 0.0
    bbox_w_rate: float = 0.0
    bbox_w_rate_conf: float = 0.0

    # 跟踪y坐标历史，用于判断运动方向
    y_history: Deque[Tuple[int, float]] = field(
        default_factory=lambda: deque(maxlen=10)
    )
    is_approaching: bool = False  # True=驶来(向下), False=驶离(向上)

    P: np.ndarray = field(default_factory=lambda: np.eye(4) * 10.0)
    vx_ps: float = 0.0
    vy_ps: float = 0.0

    speed_kmh: float = 0.0
    speed_smooth: float = 0.0
    accel_mps2: float = 0.0
    accel_smooth: float = 0.0
    heading_rad: float = 0.0
    vX_mps: float = 0.0
    vZ_mps: float = 0.0
    vY_mps: float = 0.0
    ppm_local: float = 0.0
    z_estimated: float = 0.0
    focal_px: float = 0.0

    speed_kf_proj: float = 0.0
    speed_bbox_rate: float = 0.0
    speed_fusion_weight: float = 0.5

    history: Deque[Tuple[int, float, float, float, float, float]] = field(
        default_factory=lambda: deque(maxlen=90)
    )
    last_frame: int = -1
    valid: bool = False
    in_speed_zone: bool = False


class KinematicEstimator:
    PROCESS_NOISE_POS = 1.0
    PROCESS_NOISE_VEL = 4.0
    MEAS_NOISE = 4.0
    VP_REESTIMATE_INTERVAL = 60
    PPM_CLIP_MIN = 1.0
    PPM_CLIP_MAX = 100.0
    DEFAULT_FOCAL_PX = 1080.0
    HIGHWAY_SPEED_GAIN = 8.0

    def __init__(self, fps: float = 30.0,
                 frame_width: int = 1024, frame_height: int = 540,
                 max_missing_frames: int = 30,
                 focal_px: Optional[float] = None,
                 max_speed_kmh: float = 150.0,
                 speed_zone_y_ratio: float = 0.50):
        self.fps = fps
        self.dt = 1.0 / fps
        self.max_missing = max_missing_frames
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.focal_px = float(focal_px) if focal_px else float(max(frame_width, frame_height))
        self._max_speed_kmh = max_speed_kmh
        self._speed_zone_y_min = frame_height * speed_zone_y_ratio

        self._vp_det = VanishingPointDetector(frame_width, frame_height)
        self._scaler = ScaleCalibrator()
        self._vps: VanishingPoints = self._vp_det.vps
        self._frames_since_vp = 0
        self._tracks: Dict[int, TrackState] = {}

        self._F = np.array([
            [1, 0, self.dt, 0],
            [0, 1, 0, self.dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=np.float64)
        self._H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0],
        ], dtype=np.float64)
        qp, qv = self.PROCESS_NOISE_POS, self.PROCESS_NOISE_VEL
        self._Q = np.diag([qp, qp, qv, qv])
        self._R = np.eye(2) * self.MEAS_NOISE

    # ------------------------------------------------------------------
    def update_with_box(
        self, track_id: int,
        x1: float, y1: float, x2: float, y2: float,
        cls_id: int, frame_idx: int,
    ) -> TrackState:
        cx_2d = (x1 + x2) / 2
        cy_2d = (y1 + y2) / 2

        self._vp_det.update_track(track_id, cx_2d, cy_2d, frame_idx)
        self._frames_since_vp += 1
        if self._frames_since_vp >= self.VP_REESTIMATE_INTERVAL:
            self._vps = self._vp_det.estimate()
            self._frames_since_vp = 0

        bbox3d = None
        anchor_x, anchor_y = cx_2d, cy_2d
        if self._vps.is_ready():
            bbox3d = lift_2d_to_3d((x1, y1, x2, y2), self._vps)
            if bbox3d is not None:
                ax, ay = bbox3d.bottom_front_center
                anchor_x, anchor_y = ax, ay

        bbox_width_px = float(x2 - x1)
        self._scaler.add_sample_with_width(anchor_y, bbox_width_px, cls_id)

        if track_id not in self._tracks:
            ts = TrackState(track_id=track_id, cls_id=cls_id,
                            x=anchor_x, y=anchor_y,
                            bbox_2d=(x1, y1, x2, y2),
                            bbox_3d=bbox3d,
                            anchor_x=anchor_x, anchor_y=anchor_y)
            self._tracks[track_id] = ts
            ts.last_frame = frame_idx
            ts.bbox_w_smooth = bbox_width_px
            ts.bbox_w_history.append((frame_idx, bbox_width_px))
            ts.history.append((frame_idx, anchor_x, anchor_y, 0.0, 0.0, 0.0))
            return ts

        ts = self._tracks[track_id]
        ts.cls_id = cls_id
        ts.bbox_2d = (x1, y1, x2, y2)
        ts.bbox_3d = bbox3d
        ts.anchor_x = anchor_x
        ts.anchor_y = anchor_y
        skipped = max(1, frame_idx - ts.last_frame)

        # 更新y坐标历史，判断运动方向
        ts.y_history.append((frame_idx, anchor_y))
        if len(ts.y_history) >= 3:
            recent_y = [y for _, y in ts.y_history]
            y_trend = recent_y[-1] - recent_y[0]
            ts.is_approaching = y_trend > 0  # y增加=驶来(向下)

        # bbox 宽度时间序列（鲁棒回归）
        ts.bbox_w_history.append((frame_idx, bbox_width_px))
        recent_w = [w for _, w in ts.bbox_w_history]
        ts.bbox_w_smooth = float(np.median(recent_w))
        if len(ts.bbox_w_history) >= 5:
            ts.bbox_w_rate, ts.bbox_w_rate_conf = self._robust_bbox_rate(ts.bbox_w_history)

        # 像素 KF（仅平滑 anchor）
        F = self._F.copy()
        F[0, 2] = self.dt * skipped
        F[1, 3] = self.dt * skipped
        x_state = np.array([ts.x, ts.y, ts.vx_ps, ts.vy_ps])
        x_pred = F @ x_state
        P_pred = F @ ts.P @ F.T + self._Q * skipped
        z = np.array([anchor_x, anchor_y])
        innov = z - self._H @ x_pred
        S = self._H @ P_pred @ self._H.T + self._R
        try:
            K = P_pred @ self._H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return ts
        x_new = x_pred + K @ innov
        P_new = (np.eye(4) - K @ self._H) @ P_pred
        ts.x, ts.y, ts.vx_ps, ts.vy_ps = x_new
        ts.P = P_new
        ts.last_frame = frame_idx

        ppm_at_y = self._scaler.ppm_at(ts.y)
        if ppm_at_y <= 0:
            ppm_at_y = max(1.0, self._scaler.median_ppm())
        ppm_at_y = max(self.PPM_CLIP_MIN, min(self.PPM_CLIP_MAX, ppm_at_y))
        ts.ppm_local = ppm_at_y

        in_zone = ts.y > self._speed_zone_y_min
        ts.in_speed_zone = in_zone

        if in_zone:
            speed_kf_proj = self._compute_road_direction_speed(ts)
            ts.speed_kf_proj = speed_kf_proj

            speed_bbox = self._depth_speed_from_bbox_rate(ts)
            ts.speed_bbox_rate = speed_bbox

            ts.speed_kmh = self._fuse_speeds(ts, speed_kf_proj, speed_bbox)
            ts.speed_kmh *= self.HIGHWAY_SPEED_GAIN
            ts.speed_kmh = max(0.0, min(self._max_speed_kmh, ts.speed_kmh))

            if not hasattr(self, '_recent_raw_speeds'):
                self._recent_raw_speeds: Dict[int, Deque[float]] = {}
            if track_id not in self._recent_raw_speeds:
                self._recent_raw_speeds[track_id] = deque(maxlen=5)
            self._recent_raw_speeds[track_id].append(ts.speed_kmh)
            if len(self._recent_raw_speeds[track_id]) >= 3:
                ts.speed_kmh = float(np.median(self._recent_raw_speeds[track_id]))

            if ts.speed_smooth > 2.0 and ts.speed_kmh > 0:
                max_delta = max(8.0, ts.speed_smooth * 0.25) * skipped
                delta = ts.speed_kmh - ts.speed_smooth
                if abs(delta) > max_delta:
                    ts.speed_kmh = ts.speed_smooth + np.sign(delta) * max_delta

            ts.vX_mps = ts.vx_ps / ppm_at_y
            ts.vZ_mps = speed_bbox / 3.6 if speed_bbox > 0 else 0.0
            ts.vY_mps = ts.vZ_mps
            ts.vX_mps = float(np.clip(ts.vX_mps, -60.0, 60.0))
            ts.vZ_mps = float(np.clip(ts.vZ_mps, -60.0, 60.0))
            ts.heading_rad = float(np.arctan2(ts.vZ_mps, ts.vX_mps))

            ts.speed_smooth = self._adaptive_ema(ts)

            n_lookback = max(2, int(0.3 * self.fps))
            if len(ts.history) >= n_lookback:
                old = ts.history[-n_lookback]
                old_speed_smooth = old[5] if len(old) > 5 else float(np.hypot(old[3], old[4])) * 3.6
                dt_total = (frame_idx - old[0]) / self.fps
                if dt_total > 1e-6:
                    raw_accel = (ts.speed_smooth / 3.6 - old_speed_smooth / 3.6) / dt_total
                    alpha_accel = 0.2
                    ts.accel_mps2 = alpha_accel * raw_accel + (1 - alpha_accel) * ts.accel_mps2

            ts.accel_mps2 = float(np.clip(ts.accel_mps2, -12.0, 8.0))
            ts.accel_smooth = ts.accel_mps2

        ts.history.append((frame_idx, ts.x, ts.y, ts.vX_mps, ts.vZ_mps, ts.speed_smooth))
        ts.valid = (len(ts.history) >= 5 and self._scaler.is_ready())
        return ts

    # ------------------------------------------------------------------
    def _robust_bbox_rate(self, bbox_w_history: Deque) -> Tuple[float, float]:
        """Theil-Sen 鲁棒回归计算 bbox 宽度变化率。

        Theil-Sen 取所有点对斜率的中位数，对离群点天然免疫。
        返回 (rate_px_per_s, confidence_0_to_1)。
        """
        n = len(bbox_w_history)
        if n < 5:
            return 0.0, 0.0

        frames = np.array([f for f, _ in bbox_w_history], dtype=float)
        widths = np.array([w for _, w in bbox_w_history])

        t_secs = frames / self.fps

        slopes = []
        for i in range(n):
            for j in range(i + 1, n):
                dt = t_secs[j] - t_secs[i]
                if dt > 1e-6:
                    slopes.append((widths[j] - widths[i]) / dt)

        if not slopes:
            return 0.0, 0.0

        slopes = np.array(slopes)
        med_slope = float(np.median(slopes))

        mad = float(np.median(np.abs(slopes - med_slope)))
        if mad < 1e-6:
            return med_slope, 0.9

        inlier_mask = np.abs(slopes - med_slope) < 2.5 * mad
        conf = float(inlier_mask.mean())
        conf = max(0.0, min(1.0, conf))

        return med_slope, conf

    # ------------------------------------------------------------------
    def _compute_road_direction_speed(self, ts: TrackState) -> float:
        """将 KF 像素速度投影到道路方向（VP1方向），再转为物理速度。

        核心思想：
          VP1 是道路方向的消失点。车辆沿道路行驶时，其在图像上的
          运动方向指向 VP1。因此，将 KF 估计的像素速度向量投影到
          VP1 方向，得到的标量速度就是沿道路的像素速度。
          再除以 ppm 即得物理速度。

        v7 改进：当 VP1 不可用时返回 0，让 bbox-rate 通道独立工作。
        """
        if ts.ppm_local <= 0:
            return 0.0

        vx = ts.vx_ps
        vy = ts.vy_ps
        pixel_speed = np.hypot(vx, vy)
        if pixel_speed < 0.5:
            return 0.0

        if self._vps.vp1 is not None:
            vp_x, vp_y = self._vps.vp1
            road_dx = vp_x - ts.x
            road_dy = vp_y - ts.y
            road_norm = np.hypot(road_dx, road_dy)
            if road_norm > 1e-6:
                road_dir_x = road_dx / road_norm
                road_dir_y = road_dy / road_norm
                proj = vx * road_dir_x + vy * road_dir_y
                proj = max(0.0, abs(proj))
            else:
                proj = pixel_speed
        else:
            return 0.0

        speed_mps = proj / ts.ppm_local
        return float(speed_mps * 3.6)

    # ------------------------------------------------------------------
    def _depth_speed_from_bbox_rate(self, ts: TrackState) -> float:
        """从 bbox 宽度变化率反推深度方向速度 (km/h)。

        透视方程: bbox_w = focal * car_w / z
        求导: dz/dt = -focal * car_w / bbox_w² * d(bbox_w)/dt

        v7 改进：置信度>0.9时不乘系数，避免系统性低估。
        v8 改进：区分驶来/驶离，驶来车辆速度高估需修正。
                 根据车辆在画面中的位置动态调整修正系数。
        """
        if ts.bbox_w_smooth < 5.0 or ts.bbox_w_rate_conf < 0.3:
            return 0.0

        true_w = VEHICLE_WIDTHS_M.get(ts.cls_id, DEFAULT_VEHICLE_WIDTH_M)

        focal = self._estimate_focal_from_vp()
        ts.focal_px = focal

        ts.z_estimated = focal * true_w / ts.bbox_w_smooth
        dz_dt = -focal * true_w / (ts.bbox_w_smooth ** 2) * ts.bbox_w_rate

        speed_ms = float(dz_dt)
        speed_kmh = speed_ms * 3.6

        speed_kmh = max(0.0, min(220.0, abs(speed_kmh)))

        # 驶来车辆修正：靠近摄像头时bbox变化率会被透视放大，需降低估算
        if ts.is_approaching:
            # 根据y坐标动态调整修正系数
            # y越大（靠近画面底部，距离近），修正越强
            y_ratio = (ts.y - self._speed_zone_y_min) / (self.frame_height - self._speed_zone_y_min)
            y_ratio = max(0.0, min(1.0, y_ratio))
            # 距离远(y小) -> approach_factor = 0.75
            # 距离近(y大) -> approach_factor = 0.55
            approach_factor = 0.75 - 0.2 * y_ratio
            speed_kmh *= approach_factor

        if ts.bbox_w_rate_conf >= 0.9:
            return speed_kmh
        return speed_kmh * ts.bbox_w_rate_conf

    # ------------------------------------------------------------------
    def _estimate_focal_from_vp(self) -> float:
        """从消失点几何估算焦距（像素）。

        利用 VP1 和 VP2 的正交关系：
          若 VP1 和 VP2 已知且正交（道路场景通常满足），
          则焦距 f = sqrt(-(VP1-PP)·(VP2-PP))
          其中 PP 是主点（图像中心）。
        """
        if not self._vps.is_ready():
            return self.focal_px

        vp1 = self._vps.vp1
        vp2 = self._vps.vp2
        pp_x = self.frame_width / 2.0
        pp_y = self.frame_height / 2.0

        dx1 = vp1[0] - pp_x
        dy1 = vp1[1] - pp_y
        dx2 = vp2[0] - pp_x
        dy2 = vp2[1] - pp_y

        dot = dx1 * dx2 + dy1 * dy2
        if dot >= 0:
            return self.focal_px

        f = np.sqrt(-dot)
        f = max(200.0, min(5000.0, f))
        return f

    # ------------------------------------------------------------------
    def _fuse_speeds(self, ts: TrackState, speed_kf: float, speed_bbox: float) -> float:
        """双通道速度加权融合 (v7)。

        KF投影速度：稳定、平滑，但依赖 VP1 + ppm 标定精度。
        bbox-rate速度：独立于 ppm，但对 bbox 抖动敏感。

        v7 改进：
          - KF 不可用时（speed_kf==0），完全信任 bbox-rate
          - bbox 置信度高时（>0.8），以 bbox 为主，不因差异大而惩罚
          - 两者都可靠但差异大时，取保守值
        """
        if speed_kf <= 0 and speed_bbox <= 0:
            return 0.0
        if speed_kf <= 0:
            ts.speed_fusion_weight = 1.0
            return speed_bbox
        if speed_bbox <= 0:
            ts.speed_fusion_weight = 0.0
            return speed_kf

        w_bbox = ts.bbox_w_rate_conf
        w_bbox = max(0.1, min(0.9, w_bbox))

        diff_ratio = abs(speed_kf - speed_bbox) / max(speed_kf, speed_bbox)

        if w_bbox > 0.8:
            w_kf = 1.0 - w_bbox
        elif diff_ratio > 0.5:
            w_bbox *= 0.3
            w_kf = 1.0 - w_bbox
        else:
            w_kf = 1.0 - w_bbox

        ts.speed_fusion_weight = w_bbox
        return w_kf * speed_kf + w_bbox * speed_bbox

    # ------------------------------------------------------------------
    def _adaptive_ema(self, ts: TrackState) -> float:
        """锚定 EMA 平滑：按跟踪时长分级降 alpha。

        核心思想：用前几帧建立"基准速度"，之后只允许在基准附近小幅浮动。
        - 新目标 (< 0.5s): alpha=0.12，快速收敛到初始速度
        - 已建立 (0.5~1.5s): alpha=0.06，缓慢跟踪真实变化
        - 稳定目标 (> 1.5s): alpha=0.03，极度稳定，忽略噪声

        改进：添加速度一致性检查，防止相邻帧速度差异过大
        """
        speed = ts.speed_kmh
        prev = ts.speed_smooth

        if prev == 0.0:
            return speed

        n = len(ts.history)
        if n < 15:
            alpha = 0.45
        elif n < 45:
            alpha = 0.30
        else:
            alpha = 0.18

        result = alpha * speed + (1 - alpha) * prev

        # 速度一致性检查：限制单帧最大变化
        max_delta = max(8.0, prev * 0.25)
        if abs(result - prev) > max_delta:
            result = prev + np.sign(result - prev) * max_delta

        return max(0.0, min(220.0, result))

    # ------------------------------------------------------------------
    def update(self, track_id: int, cx: float, cy: float, frame_idx: int) -> TrackState:
        return self.update_with_box(track_id, cx-30, cy-20, cx+30, cy+20,
                                    cls_id=2, frame_idx=frame_idx)

    def get(self, track_id: int) -> Optional[TrackState]:
        return self._tracks.get(track_id)

    def cleanup(self, current_frame: int) -> None:
        dead = [tid for tid, ts in self._tracks.items()
                if current_frame - ts.last_frame > self.max_missing]
        for tid in dead:
            self._vp_det.finalize_track(tid)
            del self._tracks[tid]
            if hasattr(self, '_recent_raw_speeds') and tid in self._recent_raw_speeds:
                del self._recent_raw_speeds[tid]
        self._vp_det.cleanup_dead_tracks(current_frame)

    def all_states(self):
        return list(self._tracks.values())

    @property
    def vps(self) -> VanishingPoints:
        return self._vps

    @property
    def calib_ready(self) -> bool:
        return self._scaler.is_ready()

    def avg_ppm(self) -> float:
        """返回当前标定的平均 ppm（像素/米）"""
        return self._scaler.median_ppm()

    def diagnostics(self) -> dict:
        return {
            "vp1": self._vps.vp1, "vp2": self._vps.vp2,
            "vp_confidence": self._vps.confidence_vp1,
            "scale_diag": self._scaler.diagnostics(),
            "n_tracks": len(self._tracks),
            "focal_px": self.focal_px,
            "focal_from_vp": self._estimate_focal_from_vp(),
        }
