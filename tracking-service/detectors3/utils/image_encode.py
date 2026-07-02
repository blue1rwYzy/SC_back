"""图像编码工具：将图片转为 base64 字符串，用于 VLM 多模态调用。"""
import base64


def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
