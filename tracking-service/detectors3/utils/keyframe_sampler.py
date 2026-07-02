"""关键帧截图模块：从视频中按事件 frame_id 截取关键帧。"""
import os
import cv2


class KeyframeSampler:
    def __init__(self, video_path: str, output_dir: str = "outputs/keyframes"):
        self.video_path = video_path
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def save_frame(self, frame_id: int, event_id: str, suffix: str = "") -> str:
        """截取指定帧并保存，返回保存路径。"""
        cap = cv2.VideoCapture(self.video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
        ok, frame = cap.read()
        cap.release()

        if not ok:
            return ""

        tag = f"_{suffix}" if suffix else ""
        output_path = os.path.join(self.output_dir, f"{event_id}{tag}.jpg")
        cv2.imwrite(output_path, frame)
        return output_path

    def attach_keyframes(self, event_data: dict) -> dict:
        """遍历事件列表，为每个事件截取关键帧并写回 keyframe_path。"""
        for event in event_data.get("events", []):
            frame_id = event.get("frame_id") or event.get("frame")
            event_id = event.get("event_id", f"E{event.get('frame', 0):04d}")

            if frame_id is None:
                continue

            try:
                path = self.save_frame(frame_id, event_id)
                if path:
                    event["keyframe_path"] = path
            except Exception as e:
                event["keyframe_error"] = str(e)

        return event_data
