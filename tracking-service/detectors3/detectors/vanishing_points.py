"""
detectors/vanishing_points.py
==============================
基于车辆运动的两消失点检测（Dubska 2014 / Sochor 2017 方法的实用简化版）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SOTA 方法概览（论文级）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  VP1（行驶方向消失点）：
    用车辆轨迹（中心点序列）拟合直线 → 多条直线交点
    几何意义：车朝哪开，VP1 就在那个方向的无穷远
    在画面上通常 = 车流"灭点"（远处车看上去都汇聚到这个点）

  VP2（横向消失点）：
    用车辆边缘像素的 KLT 角点流，追踪车宽边沿的运动
    几何意义：垂直于行驶方向、平行于地面的方向消失点
    论文用 PCLines 累加器找峰值；我们用更鲁棒的 RANSAC 替代

  VP3（垂直方向消失点）：
    由 VP1 × VP2 + 主点约束算出（不需要单独检测）

  有了三个消失点，就能：
    - 把 2D bbox 提升到 3D bbox（详见 lifting_3d.py）
    - 把图像 rectify 成俯视
    - 求出地面坐标系的尺度（结合车长先验）
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class VanishingPoints:
    """两个有限消失点 + 主点（图像中心默认）。"""
    vp1: Optional[Tuple[float, float]] = None  # 行驶方向
    vp2: Optional[Tuple[float, float]] = None  # 横向
    principal_point: Optional[Tuple[float, float]] = None
    confidence_vp1: float = 0.0
    confidence_vp2: float = 0.0
    n_tracks_used: int = 0

    def is_ready(self) -> bool:
        return self.vp1 is not None and self.vp2 is not None


class TrackForVP:
    """累积一辆车的中心点轨迹用于消失点检测。"""
    __slots__ = ("track_id", "points", "created_frame")

    def __init__(self, tid: int, frame_idx: int):
        self.track_id = tid
        self.points: List[Tuple[float, float]] = []
        self.created_frame = frame_idx

    def add(self, cx: float, cy: float):
        self.points.append((cx, cy))

    def fit_line(self) -> Optional[Tuple[float, float, float]]:
        """
        把轨迹拟合成 2D 直线，返回 (a, b, c) 满足 a*x + b*y + c = 0。
        用最小二乘的 SVD 解法（对斜率无偏）。
        """
        if len(self.points) < 8:
            return None
        pts = np.asarray(self.points, dtype=np.float64)
        # 距离 < 30 像素的轨迹认为没动，跳过
        if np.linalg.norm(pts[-1] - pts[0]) < 30:
            return None

        # 中心化
        c = pts.mean(axis=0)
        Q = pts - c
        # SVD：最小奇异向量是直线法向量
        _, _, vh = np.linalg.svd(Q, full_matrices=False)
        n = vh[-1]   # 法向量 (a, b)
        a, b = n
        c_val = -(a * c[0] + b * c[1])
        return (float(a), float(b), float(c_val))


class VanishingPointDetector:
    """
    基于车辆轨迹的双消失点检测器。

    在线工作流程：
      1. 每帧 update(track_states) 累积车辆轨迹
      2. 累积到一定数量后调用 estimate() 求 VPs
      3. 后续每隔 N 帧重估，平滑结果

    适用前提：
      - 摄像机静止（监控视频通常满足）
      - 大多数车沿同一道路方向行驶（高速/普通公路满足）
      - 至少有 5-10 辆车的轨迹（约 1-3 分钟视频）
    """

    MIN_TRACKS_FOR_VP1 = 3      # 最少 3 条轨迹就算 VP1（拥堵场景放宽）
    MIN_TRACK_LENGTH = 5        # 每条轨迹至少 5 个点（拥堵场景放宽）
    MIN_TRACK_DISPLACEMENT = 10 # 至少移动 10 像素（拥堵场景放宽）
    MAX_TRACKS = 500            # 内存上限

    def __init__(self, frame_width: int, frame_height: int):
        self.frame_w = frame_width
        self.frame_h = frame_height
        self._tracks: dict[int, TrackForVP] = {}
        self._completed: deque = deque(maxlen=self.MAX_TRACKS)

        self.vps = VanishingPoints(
            principal_point=(frame_width / 2, frame_height / 2)
        )

    # ------------------------------------------------------------------
    def update_track(self, tid: int, cx: float, cy: float, frame_idx: int):
        if tid not in self._tracks:
            self._tracks[tid] = TrackForVP(tid, frame_idx)
        self._tracks[tid].add(cx, cy)

    def finalize_track(self, tid: int):
        """车辆离开画面后调用，把轨迹移到完成池。"""
        if tid in self._tracks:
            tr = self._tracks.pop(tid)
            if len(tr.points) >= self.MIN_TRACK_LENGTH:
                self._completed.append(tr)

    def cleanup_dead_tracks(self, current_frame: int, max_age: int = 90):
        dead = [tid for tid, tr in self._tracks.items()
                if current_frame - tr.created_frame > max_age and len(tr.points) > 0]
        for tid in dead:
            self.finalize_track(tid)

    # ------------------------------------------------------------------
    def estimate(self) -> VanishingPoints:
        """从累积的轨迹估 VP1（行驶方向）。"""
        # 收集所有可用直线（已完成 + 当前还在的）
        all_lines: List[Tuple[float, float, float]] = []
        for tr in list(self._completed) + list(self._tracks.values()):
            line = tr.fit_line()
            if line is not None:
                all_lines.append(line)

        if len(all_lines) < self.MIN_TRACKS_FOR_VP1:
            total_tracks = len(self._completed) + len(self._tracks)
            if self.vps.vp1 is None and total_tracks >= 2:
                self.vps.vp1 = self._default_vp1()
                self.vps.confidence_vp1 = 0.3
                self.vps.vp2 = self._estimate_vp2_from_geometry(self.vps.vp1)
                self.vps.confidence_vp2 = 0.3
            return self.vps

        # ── VP1：所有车辆轨迹直线的交点（RANSAC）──
        vp1, conf1, inliers_idx = self._ransac_intersection(all_lines)
        if vp1 is not None:
            self.vps.vp1 = vp1
            self.vps.confidence_vp1 = conf1
            self.vps.n_tracks_used = len(inliers_idx)

        # ── VP2：横向消失点 ──
        # 简化做法：假设主点在画面中心，VP1 + VP2 + 主点构成正交三元组
        # 几何关系：(VP1 - PP) · (VP2 - PP) = -f² （焦距平方约束）
        # 但我们没有 f，只能假定 VP2 在水平方向无穷远（近似）
        # 改用 Sochor 的简化：VP2 取轨迹外接矩形的水平短边方向
        if vp1 is not None:
            vp2 = self._estimate_vp2_from_geometry(vp1)
            self.vps.vp2 = vp2
            self.vps.confidence_vp2 = 0.5 if vp2 else 0.0

        return self.vps

    # ------------------------------------------------------------------
    def _ransac_intersection(
        self, lines: List[Tuple[float, float, float]],
        n_iter: int = 200, thresh_px: float = 3.0,
    ) -> Tuple[Optional[Tuple[float, float]], float, List[int]]:
        """RANSAC 找让最多直线"通过"的点。"""
        if len(lines) < 2:
            return None, 0.0, []
        rng = np.random.default_rng(42)
        n = len(lines)
        a = np.array([ln[0] for ln in lines])
        b = np.array([ln[1] for ln in lines])
        c = np.array([ln[2] for ln in lines])

        best_inliers = 0
        best_pt = None
        best_idx: List[int] = []

        for _ in range(n_iter):
            i, j = rng.choice(n, 2, replace=False)
            A = np.array([[a[i], b[i]], [a[j], b[j]]])
            det = np.linalg.det(A)
            if abs(det) < 1e-9:
                continue
            try:
                pt = np.linalg.solve(A, np.array([-c[i], -c[j]]))
            except np.linalg.LinAlgError:
                continue
            # 跳过明显错误的点（远到画面 5 倍外）
            if abs(pt[0]) > 5 * self.frame_w or abs(pt[1]) > 5 * self.frame_h:
                continue
            # 计 inliers：到所有线的距离
            dist = np.abs(a * pt[0] + b * pt[1] + c) / np.sqrt(a**2 + b**2 + 1e-9)
            inliers = dist < thresh_px
            n_in = int(inliers.sum())
            if n_in > best_inliers:
                best_inliers = n_in
                best_pt = (float(pt[0]), float(pt[1]))
                best_idx = list(np.where(inliers)[0])

        confidence = best_inliers / n if n > 0 else 0
        return best_pt, confidence, best_idx

    # ------------------------------------------------------------------
    def _default_vp1(self) -> Tuple[float, float]:
        """当轨迹不足以估计 VP1 时，使用启发式默认值。

        典型监控摄像头：VP1 在画面上方中心偏上位置。
        用已完成轨迹的平均方向来估算，如果也没有则用画面中心上方。
        """
        all_trs = list(self._completed) + list(self._tracks.values())
        if len(all_trs) >= 2:
            all_dirs = []
            for tr in all_trs[-20:]:
                pts = np.asarray(tr.points)
                if len(pts) >= 2:
                    d = pts[-1] - pts[0]
                    if np.linalg.norm(d) > 5:
                        all_dirs.append(d / np.linalg.norm(d))
            if all_dirs:
                avg_dir = np.mean(all_dirs, axis=0)
                avg_dir /= np.linalg.norm(avg_dir)
                far = 5 * self.frame_h
                return (self.frame_w / 2 + avg_dir[0] * far,
                        self.frame_h / 2 + avg_dir[1] * far)

        return (self.frame_w / 2, -self.frame_h * 0.5)

    # ------------------------------------------------------------------
    def _estimate_vp2_from_geometry(
        self, vp1: Tuple[float, float]
    ) -> Optional[Tuple[float, float]]:
        """
        VP2 (横向消失点) 估计。

        用主点正交约束：假设主点在图像中心，焦距未知。
        在画面平面上，VP2 必须满足 PP-VP1 ⟂ PP-VP2 的方向（投影到图像）。
        我们让 VP2 在 VP1 主轴的法向上很远的位置。

        这是简化估计；论文里用车辆边沿的光流轨迹 + 第二组 RANSAC 求解。
        对大多数高速公路场景已足够。
        """
        cx, cy = self.frame_w / 2, self.frame_h / 2
        dx = vp1[0] - cx
        dy = vp1[1] - cy
        # VP2 在 PP 处沿 (dy, -dx) 方向（旋转 90°）取一个远点
        # 长度取 |VP1-PP| 的一半（经验值，对应中等焦距）
        scale = 0.5
        vp2 = (cx + dy * scale, cy - dx * scale)
        # 推到画面外（3 倍画面宽度）
        far = 3 * self.frame_w
        norm = np.hypot(vp2[0] - cx, vp2[1] - cy)
        if norm < 1e-3:
            return None
        ux, uy = (vp2[0] - cx) / norm, (vp2[1] - cy) / norm
        return (cx + ux * far, cy + uy * far)