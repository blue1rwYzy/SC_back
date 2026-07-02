"""
检查 MinIO videos bucket 中的文件
"""
import sys
import os
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'business-service')))

from utils.minio_client import minio_client
from config.minio_config import BUCKETS

print("\n" + "="*60)
print("检查 MinIO videos bucket")
print("="*60)

try:
    # 检查 videos bucket
    bucket_name = BUCKETS["videos"]
    print(f"\nBucket 名称: {bucket_name}")

    # 列举所有对象
    objects = minio_client.list_objects(
        bucket_name=bucket_name,
        recursive=True
    )

    if not objects:
        print("\n❌ videos bucket 为空！")
        print("\n可能的原因：")
        print("1. 视频文件还未迁移到 MinIO")
        print("2. 数据库中的视频路径已更新，但文件未上传")
        print("3. Bucket 名称不匹配")

        print("\n解决方案：")
        print("1. 检查本地是否还有视频文件：")
        print("   G:\\ShuangChuang\\ShuangC\\backend\\uploads\\videos\\")
        print("\n2. 如果有，使用 mc 命令上传到 MinIO：")
        print(f"   mc cp --recursive G:/ShuangChuang/ShuangC/backend/uploads/videos/ minio/{bucket_name}/")

    else:
        print(f"\n✅ 找到 {len(objects)} 个对象：\n")

        video_count = 0
        for obj in objects:
            print(f"📄 {obj.object_name}")
            print(f"   大小: {obj.size / 1024 / 1024:.2f} MB")
            print(f"   修改时间: {obj.last_modified}")

            # 检查是否是视频格式
            if obj.object_name.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv')):
                video_count += 1
            print()

        print(f"其中视频文件: {video_count} 个")

        if video_count == 0:
            print("\n⚠️ 没有找到视频文件！")
            print("上传的文件可能不是视频格式")

except Exception as e:
    print(f"\n❌ 检查失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
