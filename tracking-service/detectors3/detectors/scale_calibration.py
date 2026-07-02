"""
detectors/scale_calibration.py
==============================
基于 3D bbox 长度的尺度标定（Sochor 2017 方法的简化版）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  原理（Sochor 论文 Section 4 "Scene Scale Inference"）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  我们已经能从 2D bbox 算出 3D bbox 的 8 个角点（lifting_3d.py）。
  
  3D bbox 在图像上的"沿 VP1 方向边长"对应车的真实长度（轿车 ~4.5m）。
  
  对每辆检测到的车 i：
    1. 计算它的 3D bbox 底部前沿和后沿之间的图像距离 length_i (像素)
    2. 它对应的真实长度 L_i (米) 取决于车型：
         car: 4.5m, suv: 4.7m, truck: 6-12m, bus: 11-13m
    3. 该车在它所处位置的 ppm = length_i / L_i

  把许多车的 (位置, ppm) 配对收集起来：
    ppm 是位置（y 坐标）的函数，可以拟合成 1/y 或多项式
    或者直接转化为单应矩阵 H

  Sochor 论文的精度可达：
    - 2017 完整版（用 3D 模型库渲染对齐）: 中位误差 0.97 km/h
    - 简化版（仅用车长先验）: 估计 5-10% 误差
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

import numpy as np


# COCO 类别 → 真实物理长度（米）
VEHICLE_LENGTHS_M = {
    1: 1.7,    # bicycle
    2: 4.5,    # car (轿车平均)
    3: 2.0,    # motorcycle
    5: 12.0,   # bus
    7: 7.0,    # truck (轻卡平均；重卡可达 16m)
}
DEFAULT_VEHICLE_LENGTH_M = 4.5

# COCO 类别 → 真实物理宽度（米）
VEHICLE_WIDTHS_M = {
    1: 0.7,    # bicycle
    2: 1.85,   # car
    3: 0.85,   # motorcycle
    5: 2.55,   # bus
    7: 2.50,   # truck
}
DEFAULT_VEHICLE_WIDTH_M = 1.85


@dataclass
class ScaleSample:
    y: float          # 图像 y 坐标
    pixel_length: float
    real_length_m: float


class ScaleCalibrator:
    """
    在线标定：每辆车一帧贡献一个 (y, ppm) 样本，累积后拟合 ppm(y) 函数。

    用法：
      calib = ScaleCalibrator()
      for each frame:
          for each track:
              calib.add_sample(y, bbox3d_length_px, cls_id)
      ppm = calib.ppm_at(y)  # 任何时候可调用
    """

    MIN_SAMPLES = 15   # 至少 15 个样本才生效
    MAX_SAMPLES = 2000

    def __init__(self):
        self._samples: Deque[ScaleSample] = deque(maxlen=self.MAX_SAMPLES)
        self._ppm_at_y_table: Optional[np.ndarray] = None  # shape (N, 2): [y, ppm]
        self._dirty = False

    def add_sample(self, y: float, pixel_length: float, cls_id: int = 2):
        if pixel_length < 5:   # 太小的 bbox 不可信
            return
        real_len = VEHICLE_LENGTHS_M.get(cls_id, DEFAULT_VEHICLE_LENGTH_M)
        self._samples.append(ScaleSample(y=y, pixel_length=pixel_length,
                                         real_length_m=real_len))
        self._dirty = True

    def add_sample_with_width(self, y: float, pixel_width: float, cls_id: int = 2):
        """用 bbox 宽度 + 车型物理宽度作为尺度标定样本。

        这比用 3D bbox 长度更直接，且没有循环依赖问题。
        """
        if pixel_width < 5:
            return
        real_w = VEHICLE_WIDTHS_M.get(cls_id, DEFAULT_VEHICLE_WIDTH_M)
        ppm_candidate = pixel_width / real_w
        # 异常值剔除：如果已有足够样本，排除 >2σ 的离群点
        if len(self._samples) >= 10:
            existing_ppms = [s.pixel_length / s.real_length_m for s in self._samples]
            med = float(np.median(existing_ppms))
            std = float(np.std(existing_ppms))
            if std > 0 and abs(ppm_candidate - med) > 2 * std:
                return
        # 用 width 当 length 字段，real_w 当 real_length（语义一致：物理尺寸）
        self._samples.append(ScaleSample(y=y, pixel_length=pixel_width,
                                         real_length_m=real_w))
        self._dirty = True

    def is_ready(self) -> bool:
        return len(self._samples) >= self.MIN_SAMPLES

    def ppm_at(self, y: float) -> float:
        """y 坐标处的 ppm（像素/米）。"""
        if not self.is_ready():
            return 0.0
        if self._dirty:
            self._rebuild_table()

        ys = self._ppm_at_y_table[:, 0]
        ppms = self._ppm_at_y_table[:, 1]
        # 用 ±50px 窗口取中值
        mask = np.abs(ys - y) < 50
        if mask.sum() >= 3:
            return float(np.median(ppms[mask]))
        # 窗口不够则扩大到 ±100px
        mask2 = np.abs(ys - y) < 100
        if mask2.sum() >= 3:
            return float(np.median(ppms[mask2]))
        # 透视模型拟合：ppm = a / (y_vp - y) + b
        # y_vp（消失点 y）取样本最小 y 的 0.5 倍（在画面上方）
        if len(self._samples) >= 5:
            y_vp = float(np.min(ys)) * 0.5
            denom = y_vp - ys
            # 避免除零
            valid = np.abs(denom) > 10
            if valid.sum() >= 3:
                inv_denom = 1.0 / denom[valid]
                ppms_valid = ppms[valid]
                # 线性回归：ppm = a * (1/(y_vp - y)) + b
                A = np.column_stack([inv_denom, np.ones_like(inv_denom)])
                try:
                    coeffs, _, _, _ = np.linalg.lstsq(A, ppms_valid, rcond=None)
                    a, b = coeffs
                    result = a / (y_vp - y) + b
                    return max(2.0, min(100.0, float(result)))
                except np.linalg.LinAlgError:
                    pass
        # 最终回退：全局中值
        return float(np.median(ppms))

    def median_ppm(self) -> float:
        if not self._samples:
            return 0.0
        ppms = [s.pixel_length / s.real_length_m for s in self._samples]
        return float(np.median(ppms))

    def _rebuild_table(self):
        rows = []
        for s in self._samples:
            ppm = s.pixel_length / s.real_length_m
            rows.append([s.y, ppm])
        arr = np.array(rows)
        # 异常值剔除：>2σ 的样本排除
        ppms = arr[:, 1]
        med = np.median(ppms)
        std = np.std(ppms)
        if std > 0:
            mask = np.abs(ppms - med) < 2 * std
            arr = arr[mask]
        # 按 y 排序
        arr = arr[arr[:, 0].argsort()]
        self._ppm_at_y_table = arr
        self._dirty = False

    # ------------------------------------------------------------------
    def diagnostics(self) -> dict:
        if not self._samples:
            return {"n": 0}
        ppms = np.array([s.pixel_length / s.real_length_m for s in self._samples])
        ys = np.array([s.y for s in self._samples])
        return {
            "n": len(self._samples),
            "ppm_min": float(ppms.min()),
            "ppm_max": float(ppms.max()),
            "ppm_median": float(np.median(ppms)),
            "ratio_far_to_near": float(ppms.max() / max(0.1, ppms.min())),
            "y_range": (float(ys.min()), float(ys.max())),
        }