"""车辆裁剪工具：从帧中截取车辆区域，用于属性识别。"""
import os
import cv2


def save_vehicle_crop(
    frame, bbox, track_id, frame_id, output_dir="outputs/crops"
) -> str | None:
    """截取车辆区域并保存，返回路径。bbox 格式为 (x1, y1, x2, y2)。"""
    os.makedirs(output_dir, exist_ok=True)

    x1, y1, x2, y2 = map(int, bbox)
    crop = frame[y1:y2, x1:x2]

    if crop.size == 0:
        return None

    path = os.path.join(output_dir, f"track_{track_id}_frame_{frame_id}.jpg")
    cv2.imwrite(path, crop)
    return path
