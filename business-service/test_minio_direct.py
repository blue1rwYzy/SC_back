"""
直接测试 MinIO 连接和视频列表
不通过 FastAPI，直接调用 minio_client
"""
import sys
import os
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from utils.minio_client import minio_client
from config.minio_config import BUCKETS

print("\n" + "="*60)
print("直接测试 MinIO 视频列表")
print("="*60)

bucket_name = BUCKETS["videos"]
print(f"\nBucket 名称: {bucket_name}")

try:
    # 测试连接
    print("\n1️⃣ 测试 bucket 是否存在...")
    exists = minio_client.client.bucket_exists(bucket_name)
    print(f"   Bucket '{bucket_name}' 存在: {exists}")

    if not exists:
        print(f"\n❌ Bucket '{bucket_name}' 不存在！")
        print("\n可用的 buckets:")
        buckets = minio_client.client.list_buckets()
        for bucket in buckets:
            print(f"   - {bucket.name}")
        sys.exit(1)

    # 列举对象
    print(f"\n2️⃣ 列举 bucket 中的对象...")
    objects = minio_client.list_objects(
        bucket_name=bucket_name,
        recursive=True
    )

    print(f"   返回类型: {type(objects)}")
    print(f"   是否为列表: {isinstance(objects, list)}")

    if isinstance(objects, list):
        print(f"   列表长度: {len(objects)}")

        if len(objects) == 0:
            print(f"\n❌ 返回的对象列表为空！")
            print("\n可能的原因:")
            print("1. Bucket 中没有文件")
            print("2. list_objects() 方法实现有问题")
        else:
            print(f"\n✅ 找到 {len(objects)} 个对象\n")

            video_count = 0
            for i, obj in enumerate(objects[:10], 1):  # 只显示前10个
                print(f"{i}. {obj.object_name}")
                print(f"   大小: {obj.size / 1024 / 1024:.2f} MB")
                print(f"   修改时间: {obj.last_modified}")

                # 检查是否是视频
                if obj.object_name.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')):
                    video_count += 1
                    print(f"   ✅ 视频文件")
                else:
                    print(f"   ⚠️ 非视频文件")
                print()

            if len(objects) > 10:
                print(f"... 还有 {len(objects) - 10} 个对象")

            print(f"\n📊 统计:")
            print(f"   总对象: {len(objects)}")
            print(f"   视频文件: {video_count}")
    else:
        print(f"\n⚠️ 返回的不是列表类型！")
        print(f"   尝试迭代...")

        count = 0
        for obj in objects:
            count += 1
            if count <= 5:
                print(f"   {count}. {obj.object_name}")

        print(f"\n   迭代到 {count} 个对象")

except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
