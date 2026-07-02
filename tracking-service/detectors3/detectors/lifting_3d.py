"""
detectors/lifting_3d.py
=======================
基于消失点把 2D bbox 提升到 3D bbox（v2：用车宽反推尺度）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  v2 改进点（解决 v1 在远处车长估计严重偏大的问题）：
  
  v1 错误做法：用固定比例 car_length_ratio=0.6 估车长在 bbox 中的占比。
             远处车透视压缩严重时此比例严重失准。
  
  v2 正确做法：用 bbox 水平宽度 → 反推 ppm → 算出车长在该位置的像素数。
              因为车宽 ~1.85m 几乎所有轿车都一样，是稳定先验。
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from .vanishing_points import VanishingPoints


@dataclass
class Bbox3D:
    corners: np.ndarray  # (8, 2)

    @property
    def bottom_front_center(self) -> Tuple[float, float]:
        return (float((self.corners[0, 0] + self.corners[1, 0]) / 2),
                float((self.corners[0, 1] + self.corners[1, 1]) / 2))

    @property
    def bottom_center(self) -> Tuple[float, float]:
        return (float(self.corners[0:4, 0].mean()),
                float(self.corners[0:4, 1].mean()))


def _direction(p_from, p_to):
    dx = p_to[0] - p_from[0]
    dy = p_to[1] - p_from[1]
    n = np.hypot(dx, dy)
    if n < 1e-9: return (0.0, 0.0)
    return (dx / n, dy / n)


def lift_2d_to_3d(
    bbox_2d, vps: VanishingPoints,
    car_length_m: float = 4.5,
    car_width_m: float = 1.85,
    car_height_m: float = 1.5,
) -> Optional[Bbox3D]:
    """
    把 2D bbox 提升到 3D bbox。

    Step 1: 用 bbox 水平宽度反推该位置 ppm = bbox_w / 1.85m
    Step 2: 车长方向像素 = ppm × 4.5m
    Step 3: 沿 VP1 延伸得到后沿，沿垂直方向延伸得到顶部
    """
    if not vps.is_ready():
        return None
    x1, y1, x2, y2 = bbox_2d
    vp1 = vps.vp1
    bbox_w = x2 - x1
    bbox_h = y2 - y1
    if bbox_w < 5 or bbox_h < 5:
        return None

    # 底部前沿两端：bbox 底边的左右两点
    P0 = (float(x1), float(y2))
    P1 = (float(x2), float(y2))

    # 用车宽反推 ppm
    ppm_local = bbox_w / car_width_m

    # 车长对应的像素数
    length_px = ppm_local * car_length_m

    # 沿 VP1 方向延伸长度 length_px → 得到后沿
    dx0, dy0 = _direction(P0, vp1)
    dx1, dy1 = _direction(P1, vp1)
    P3 = (P0[0] + dx0 * length_px, P0[1] + dy0 * length_px)
    P2 = (P1[0] + dx1 * length_px, P1[1] + dy1 * length_px)

    # 顶部 4 角（车高方向，简化为图像 -y）
    height_px = ppm_local * car_height_m
    P4 = (P0[0], P0[1] - height_px)
    P5 = (P1[0], P1[1] - height_px)
    P7 = (P3[0], P3[1] - height_px)
    P6 = (P2[0], P2[1] - height_px)

    corners = np.array([P0, P1, P2, P3, P4, P5, P6, P7], dtype=np.float64)
    return Bbox3D(corners=corners)


def lifted_length_px(bbox3d: Bbox3D) -> float:
    front = bbox3d.bottom_front_center
    back = ((bbox3d.corners[2, 0] + bbox3d.corners[3, 0]) / 2,
            (bbox3d.corners[2, 1] + bbox3d.corners[3, 1]) / 2)
    return float(np.hypot(front[0] - back[0], front[1] - back[1]))