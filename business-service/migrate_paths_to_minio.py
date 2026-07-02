"""
数据库路径迁移脚本：本地路径 → MinIO 路径
将数据库中所有本地文件路径转换为 MinIO 格式

执行前请确保：
1. 所有文件已经迁移到 MinIO
2. 已备份数据库
3. MinIO 服务正在运行
"""
import sys
import os
import re
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加父目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared import get_db, Model, InferenceResult, VideoTrackingTask
from config.minio_config import BUCKETS


def extract_relative_path(full_path, pattern):
    """
    从完整路径中提取相对路径

    Args:
        full_path: 完整路径
        pattern: 要匹配的模式（如 'uploads\\images\\' 或 'uploads/images/'）

    Returns:
        相对路径（已统一为 / 分隔符）
    """
    # 同时处理 Windows 和 Unix 路径分隔符
    normalized_path = full_path.replace('\\', '/')

    # 使用正则表达式提取 uploads/xxx/ 之后的部分
    match = re.search(pattern, normalized_path, re.IGNORECASE)
    if match:
        # 提取匹配位置之后的所有内容
        relative_path = normalized_path[match.end():]
        return relative_path
    return None


def migrate_model_paths(db):
    """迁移 Model 表的路径"""
    print("\n" + "="*60)
    print("迁移 Model 表路径")
    print("="*60)

    models = db.query(Model).all()
    print(f"找到 {len(models)} 条模型记录")
    updated_count = 0

    for model in models:
        old_path = model.path

        # 跳过已经是 MinIO 路径的
        if old_path.startswith("minio://"):
            print(f"✓ 模型 {model.name} 已经是 MinIO 路径，跳过")
            continue

        # 提取文件名
        filename = os.path.basename(old_path)

        # 判断模型类型（JC 或 ZZ）
        if re.search(r'[/\\]model[/\\]JC[/\\]', old_path, re.IGNORECASE):
            # 检测模型
            new_path = f"minio://{BUCKETS['models']}/JC/{filename}"
            updated = True
        elif re.search(r'[/\\]model[/\\]ZZ[/\\]', old_path, re.IGNORECASE):
            # 追踪模型
            new_path = f"minio://{BUCKETS['models']}/ZZ/{filename}"
            updated = True
        else:
            print(f"⚠️ 警告: 无法识别路径格式: {old_path}")
            print(f"  模型名: {model.name}")
            continue

        # 更新路径
        model.path = new_path
        updated_count += 1

        print(f"✓ 模型 {model.name} (ID: {model.id}):")
        print(f"  旧: {old_path}")
        print(f"  新: {new_path}")

    db.commit()
    print(f"\n✅ Models 表迁移完成，更新了 {updated_count}/{len(models)} 条记录")
    return updated_count


def migrate_inference_result_paths(db):
    """迁移 InferenceResult 表的路径"""
    print("\n" + "="*60)
    print("迁移 InferenceResult 表路径")
    print("="*60)

    results = db.query(InferenceResult).all()
    print(f"找到 {len(results)} 条推理结果记录")
    updated_count = 0
    show_limit = 5  # 只显示前5条详细信息

    for idx, result in enumerate(results):
        updated = False

        # 迁移原图路径 (original_image)
        if result.original_image and not result.original_image.startswith("minio://"):
            # 提取相对路径: uploads/images/ 之后的部分
            relative_path = extract_relative_path(result.original_image, r'uploads/images/')

            if relative_path:
                result.original_image = f"minio://{BUCKETS['images']}/{relative_path}"
                updated = True
            else:
                if idx < show_limit:
                    print(f"⚠️ 无法提取原图相对路径: {result.original_image}")

        # 迁移结果图路径 (result_image)
        if result.result_image and not result.result_image.startswith("minio://"):
            # 提取相对路径: uploads/img_results/ 之后的部分
            relative_path = extract_relative_path(result.result_image, r'uploads/img_results/')

            if relative_path:
                result.result_image = f"minio://{BUCKETS['img_results']}/{relative_path}"
                updated = True
            else:
                if idx < show_limit:
                    print(f"⚠️ 无法提取结果图相对路径: {result.result_image}")

        if updated:
            updated_count += 1

            # 只显示前几条的详细信息
            if updated_count <= show_limit:
                print(f"\n✓ 结果 ID {result.id} (batch: {result.batch_name}):")
                print(f"  原图: {result.original_image[:100]}{'...' if len(result.original_image) > 100 else ''}")
                print(f"  结果: {result.result_image[:100]}{'...' if len(result.result_image) > 100 else ''}")

    db.commit()

    if updated_count > show_limit:
        print(f"\n... 还有 {updated_count - show_limit} 条记录已更新（未显示详情）")

    print(f"\n✅ InferenceResults 表迁移完成，更新了 {updated_count}/{len(results)} 条记录")
    return updated_count


def migrate_video_tracking_paths(db):
    """迁移 VideoTrackingTask 表的路径"""
    print("\n" + "="*60)
    print("迁移 VideoTrackingTask 表路径")
    print("="*60)

    tasks = db.query(VideoTrackingTask).all()
    print(f"找到 {len(tasks)} 条视频追踪任务记录")
    updated_count = 0

    for task in tasks:
        updated = False

        # 迁移原视频路径 (original_video_path)
        if task.original_video_path and not task.original_video_path.startswith("minio://"):
            # 提取相对路径: uploads/videos/ 之后的部分
            relative_path = extract_relative_path(task.original_video_path, r'uploads/videos/')

            if relative_path:
                task.original_video_path = f"minio://{BUCKETS['videos']}/{relative_path}"
                updated = True
            else:
                print(f"⚠️ 无法提取原视频相对路径: {task.original_video_path}")

        # 迁移结果视频路径 (result_video_path)
        if task.result_video_path and not task.result_video_path.startswith("minio://"):
            # 提取相对路径: uploads/vid_results/ 之后的部分
            relative_path = extract_relative_path(task.result_video_path, r'uploads/vid_results/')

            if relative_path:
                task.result_video_path = f"minio://{BUCKETS['vid_results']}/{relative_path}"
                updated = True
            else:
                print(f"⚠️ 无法提取结果视频相对路径: {task.result_video_path}")

        # 同时更新相对路径字段（如果有）
        if hasattr(task, 'original_video_relative_path') and task.original_video_relative_path:
            # 已经是相对路径格式，只需统一分隔符
            task.original_video_relative_path = task.original_video_relative_path.replace('\\', '/')

        if hasattr(task, 'result_video_relative_path') and task.result_video_relative_path:
            task.result_video_relative_path = task.result_video_relative_path.replace('\\', '/')

        if updated:
            updated_count += 1
            print(f"\n✓ 任务 {task.task_id} (ID: {task.id}):")
            print(f"  原视频: {task.original_video_path}")
            print(f"  结果:   {task.result_video_path}")

    db.commit()
    print(f"\n✅ VideoTrackingTasks 表迁移完成，更新了 {updated_count}/{len(tasks)} 条记录")
    return updated_count


def preview_changes(db):
    """预览将要进行的更改（不实际修改数据库）"""
    print("\n" + "="*60)
    print("预览模式：检查将要迁移的数据")
    print("="*60)

    # 检查 Models
    print("\n1. Models 表:")
    models = db.query(Model).all()
    minio_count = sum(1 for m in models if m.path.startswith("minio://"))
    local_count = len(models) - minio_count
    print(f"  总记录: {len(models)}")
    print(f"  已迁移: {minio_count}")
    print(f"  待迁移: {local_count}")

    if local_count > 0:
        print("\n  示例数据（待迁移）:")
        for m in models:
            if not m.path.startswith("minio://"):
                print(f"    - {m.name}: {m.path}")

    # 检查 InferenceResults
    print("\n2. InferenceResults 表:")
    results = db.query(InferenceResult).limit(1000).all()  # 限制查询数量
    minio_count = sum(1 for r in results if r.original_image and r.original_image.startswith("minio://"))
    local_count = sum(1 for r in results if r.original_image and not r.original_image.startswith("minio://"))
    print(f"  总记录: {len(results)} (只检查前1000条)")
    print(f"  已迁移: {minio_count}")
    print(f"  待迁移: {local_count}")

    # 检查 VideoTrackingTasks
    print("\n3. VideoTrackingTasks 表:")
    tasks = db.query(VideoTrackingTask).all()
    minio_count = sum(1 for t in tasks if t.original_video_path and t.original_video_path.startswith("minio://"))
    local_count = len(tasks) - minio_count
    print(f"  总记录: {len(tasks)}")
    print(f"  已迁移: {minio_count}")
    print(f"  待迁移: {local_count}")


def main():
    """主函数"""
    print("\n" + "="*60)
    print("数据库路径迁移脚本")
    print("本地路径 → MinIO 路径")
    print("="*60)

    # 获取数据库连接
    db = next(get_db())

    try:
        # 先预览
        preview_changes(db)

        # 确认操作
        print("\n" + "="*60)
        print("⚠️  此操作将修改数据库中的文件路径！")
        print("="*60)
        print("\n请确保：")
        print("1. ✅ 所有文件已迁移到 MinIO")
        print("2. ✅ 已备份数据库")
        print("3. ✅ MinIO 服务正在运行")

        confirm = input("\n确认执行迁移？(yes/no): ")
        if confirm.lower() != 'yes':
            print("❌ 取消迁移")
            return

        # 执行迁移
        total_updated = 0

        # 1. 迁移 Model 表
        count = migrate_model_paths(db)
        total_updated += count

        # 2. 迁移 InferenceResult 表
        count = migrate_inference_result_paths(db)
        total_updated += count

        # 3. 迁移 VideoTrackingTask 表
        count = migrate_video_tracking_paths(db)
        total_updated += count

        # 总结
        print("\n" + "="*60)
        print("✅ 迁移完成！")
        print("="*60)
        print(f"总共更新了 {total_updated} 条记录")
        print("\n建议验证：")
        print("1. 查询数据库确认路径格式正确")
        print("2. 重启 business-service 和 inference-service")
        print("3. 测试前端访问图片和推理结果")
        print("4. 检查日志确认无错误")

    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        print("\n已回滚所有更改")

    finally:
        db.close()


if __name__ == "__main__":
    main()
