"""
导入数据集图片到图片数据库
"""
import os
import sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))

from shared.database import SessionLocal
from shared.models import ImageDatabase


def import_dataset():
    """导入数据集图片到数据库"""

    # 数据集目录
    dataset_dir = r"G:\ShuangChuang\ShuangC\backend\uploads\images"

    if not os.path.exists(dataset_dir):
        print(f"❌ 数据集目录不存在: {dataset_dir}")
        return

    print("=" * 60)
    print("导入数据集图片到图片数据库")
    print("=" * 60)
    print(f"数据集目录: {dataset_dir}")
    print()

    db = SessionLocal()

    # 获取所有图片文件
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp'}
    image_files = []

    for root, dirs, files in os.walk(dataset_dir):
        for file in files:
            if Path(file).suffix.lower() in image_extensions:
                image_files.append(os.path.join(root, file))

    print(f"📁 找到 {len(image_files)} 张图片")
    print()

    # 按文件夹分组
    folders = {}
    for img_path in image_files:
        # 获取相对于数据集根目录的文件夹路径
        rel_path = os.path.relpath(os.path.dirname(img_path), dataset_dir)
        if rel_path == '.':
            folder = '/'
        else:
            folder = '/' + rel_path.replace('\\', '/')

        if folder not in folders:
            folders[folder] = []
        folders[folder].append(img_path)

    print(f"📂 共有 {len(folders)} 个文件夹:")
    for folder, images in folders.items():
        print(f"   {folder}: {len(images)} 张图片")
    print()

    # 导入图片
    imported_count = 0
    skipped_count = 0

    for folder, images in folders.items():
        print(f"正在导入文件夹: {folder}")

        for img_path in images:
            filename = os.path.basename(img_path)

            # 检查是否已存在
            existing = db.query(ImageDatabase).filter(
                ImageDatabase.path == img_path
            ).first()

            if existing:
                skipped_count += 1
                continue

            # 获取图片尺寸
            try:
                with Image.open(img_path) as img:
                    width, height = img.size
                mime_type = f"image/{img.format.lower()}"
            except Exception as e:
                print(f"   ⚠️  无法读取图片信息: {filename}")
                width, height = None, None
                mime_type = "image/jpeg"

            # 添加到数据库
            db_image = ImageDatabase(
                filename=filename,
                path=img_path,
                folder=folder,
                size=os.path.getsize(img_path),
                mime_type=mime_type,
                width=width,
                height=height,
                is_folder=False
            )
            db.add(db_image)
            imported_count += 1

            if imported_count % 10 == 0:
                print(f"   已导入 {imported_count} 张...")

    # 提交到数据库
    try:
        db.commit()
        print()
        print("=" * 60)
        print(f"✅ 导入完成！")
        print(f"   新增: {imported_count} 张图片")
        print(f"   跳过: {skipped_count} 张图片（已存在）")
        print("=" * 60)
    except Exception as e:
        db.rollback()
        print(f"❌ 导入失败: {e}")
    finally:
        db.close()


def list_database_images():
    """列出数据库中的所有图片"""
    print("\n" + "=" * 60)
    print("数据库中的图片列表")
    print("=" * 60)

    db = SessionLocal()
    images = db.query(ImageDatabase).order_by(ImageDatabase.folder, ImageDatabase.filename).all()

    if not images:
        print("数据库中没有图片")
        db.close()
        return

    # 按文件夹分组显示
    current_folder = None
    for img in images:
        if img.folder != current_folder:
            current_folder = img.folder
            print(f"\n📁 {current_folder}")

        size_mb = img.size / 1024 / 1024 if img.size else 0
        size_str = f"{size_mb:.2f}MB" if img.size else "未知"
        dimension = f"{img.width}x{img.height}" if img.width and img.height else "未知"

        print(f"   {img.id:3d}. {img.filename:30s} | {size_str:8s} | {dimension}")

    print(f"\n共 {len(images)} 张图片")
    db.close()


def clear_database():
    """清空数据库中的所有图片（慎用！）"""
    print("\n" + "⚠️  警告：即将清空数据库中的所有图片！".center(60, "="))
    confirm = input("确认清空？(输入 yes 确认): ")

    if confirm.lower() != 'yes':
        print("已取消")
        return

    db = SessionLocal()
    count = db.query(ImageDatabase).count()
    db.query(ImageDatabase).delete()
    db.commit()
    db.close()

    print(f"✅ 已删除 {count} 张图片")


if __name__ == "__main__":
    import sys

    print("\n" + "🖼️  图片数据库管理工具".center(60, "="))
    print()
    print("请选择操作:")
    print("  1. 导入数据集图片")
    print("  2. 查看数据库图片")
    print("  3. 清空数据库（慎用）")
    print()

    choice = input("请输入选项 (1/2/3): ").strip()

    if choice == '1':
        import_dataset()
        list_database_images()
    elif choice == '2':
        list_database_images()
    elif choice == '3':
        clear_database()
    else:
        print("无效选项")

    print()
    input("按回车键退出...")
