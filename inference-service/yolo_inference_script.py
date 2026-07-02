"""
YOLO 推理脚本 - 独立推理模块
要求: Ultralytics >= 8.4.9 (通过 pip install --upgrade ultralytics==8.4.9 安装)
"""

import argparse
import json
import sys
from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser(description="KY004 道路缺陷检测推理")
    parser.add_argument("--model", type=str, required=True, help="模型路径")
    parser.add_argument("--source", type=str, required=True, help="图片/视频/文件夹路径")
    parser.add_argument("--conf", type=float, required=True, help="置信度阈值")
    parser.add_argument("--imgsz", type=int, required=True, help="推理分辨率")
    parser.add_argument("--project", type=str, required=True, help="输出项目路径")
    parser.add_argument("--name", type=str, required=True, help="输出文件夹名称")
    args = parser.parse_args()

    # 加载模型
    print(f"加载模型: {args.model}", file=sys.stderr)
    model = YOLO(args.model)

    import os
    import glob

    # 收集所有图片文件
    source = args.source
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')
    if os.path.isdir(source):
        image_files = sorted([
            f for f in glob.glob(os.path.join(source, '*'))
            if f.lower().endswith(image_extensions)
        ])
    else:
        image_files = [source]

    total = len(image_files)
    print(f"开始推理，共 {total} 张图片", file=sys.stderr)
    print(f"置信度阈值: {args.conf}", file=sys.stderr)

    all_results = []
    actual_save_dir = None

    for idx, img_path in enumerate(image_files):
        results = model.predict(
            source=img_path,
            imgsz=args.imgsz,
            conf=args.conf,
            save=True,
            show=False,
            half=True,
            project=args.project if args.project else "",
            name=args.name,
            verbose=False,
            exist_ok=True,
        )

        if results and actual_save_dir is None:
            actual_save_dir = str(results[0].save_dir)

        for r in results:
            img_result = {
                "path": str(r.path),
                "orig_shape": list(r.orig_shape),
                "detections": []
            }
            if r.boxes is not None and len(r.boxes) > 0:
                for box in r.boxes:
                    img_result["detections"].append({
                        "class_id": int(box.cls[0]),
                        "confidence": float(box.conf[0]),
                        "bbox": box.xyxy[0].tolist(),
                    })
            all_results.append(img_result)

        # 每张图片完成后输出进度到 stdout
        print(json.dumps({
            "type": "progress",
            "current": idx + 1,
            "total": total,
            "progress": round((idx + 1) / total * 100),
        }, ensure_ascii=False), flush=True)

    print(f"实际保存目录: {actual_save_dir}", file=sys.stderr)

    # 最终结果输出（最后一行）
    print(json.dumps({
        "type": "done",
        "save_dir": actual_save_dir,
        "results": all_results,
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
