"""
检查 img-results bucket 中的对象路径
"""
import sys
import os
from dotenv import load_dotenv

load_dotenv()

# 添加 business-service 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'business-service'))

from utils.minio_client import minio_client
from config.minio_config import BUCKETS

print("\n" + "="*60)
print("检查 img-results bucket")
print("="*60)

bucket_name = BUCKETS["img_results"]
print(f"\nBucket: {bucket_name}")

try:
    objects = minio_client.list_objects(
        bucket_name=bucket_name,
        recursive=True
    )

    print(f"\n前 20 个对象:\n")

    count = 0
    predict4_count = 0
    for obj in objects:
        count += 1
        if count <= 20:
            print(f"  {count}. {obj.object_name}")

        if "predict4" in obj.object_name:
            predict4_count += 1
            if predict4_count <= 5:
                print(f"     ⭐ predict4 对象: {obj.object_name}")

    print(f"\n总对象数: {count}")
    print(f"predict4 相关: {predict4_count}")

    # 测试一个具体的路径
    test_path = "predict4/lr_00011_bottom_right.jpg"
    print(f"\n测试对象是否存在: {test_path}")
    exists = minio_client.file_exists(bucket_name, test_path)
    print(f"  存在: {exists}")

    if not exists:
        # 尝试其他可能的路径格式
        test_path2 = "img_results/predict4/lr_00011_bottom_right.jpg"
        print(f"\n测试路径2: {test_path2}")
        exists2 = minio_client.file_exists(bucket_name, test_path2)
        print(f"  存在: {exists2}")

except Exception as e:
    print(f"\n❌ 错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
