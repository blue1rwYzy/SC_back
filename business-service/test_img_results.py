"""
测试 img-results bucket 中的对象路径
"""
import sys
import os
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from utils.minio_client import minio_client
from config.minio_config import BUCKETS

print("\n" + "="*60)
print("检查 img-results bucket 中的对象")
print("="*60)

bucket_name = BUCKETS["img_results"]
print(f"\nBucket: {bucket_name}")

try:
    objects = minio_client.list_objects(
        bucket_name=bucket_name,
        recursive=True
    )

    print(f"\n找到的对象:\n")

    # 只显示 predict4 相关的
    predict4_objects = []
    for obj in objects:
        if "predict4" in obj.object_name:
            predict4_objects.append(obj)
            print(f"  {obj.object_name}")

    print(f"\n总共: {len(predict4_objects)} 个 predict4 相关的对象")

    if predict4_objects:
        print(f"\n示例对象路径:")
        example = predict4_objects[0].object_name
        print(f"  完整路径: {example}")

        # 测试生成预签名 URL
        from datetime import timedelta
        url = minio_client.get_presigned_url(
            bucket_name=bucket_name,
            object_name=example,
            expires=timedelta(hours=1)
        )

        if url:
            print(f"\n✅ 预签名 URL 生成成功:")
            print(f"  {url[:150]}...")
        else:
            print(f"\n❌ 预签名 URL 生成失败")

except Exception as e:
    print(f"\n❌ 错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
