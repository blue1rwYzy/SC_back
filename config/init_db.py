"""
数据库初始化脚本（Python 版本）
避免 SQL 文件编码问题
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine, text
from shared.models import Base, Model, ImageDatabase


def init_database():
    """初始化数据库"""

    print("=" * 60)
    print("初始化数据库")
    print("=" * 60)

    # 数据库连接（连接到 postgres 数据库）
    admin_url = "postgresql://postgres:mm@localhost:5432/postgres"

    try:
        # 1. 创建数据库
        print("\n[1/5] 创建数据库...")
        engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        conn = engine.connect()

        # 删除已存在的数据库
        conn.execute(text("DROP DATABASE IF EXISTS defect_detection;"))
        print("  ✅ 删除旧数据库（如果存在）")

        # 创建新数据库
        conn.execute(text("CREATE DATABASE defect_detection ENCODING 'UTF8';"))
        print("  ✅ 创建新数据库 defect_detection")

        conn.close()
        engine.dispose()

        # 2. 连接到新数据库并创建表
        print("\n[2/5] 创建数据表...")
        from shared.database import engine as db_engine

        # 创建所有表
        Base.metadata.create_all(bind=db_engine)
        print("  ✅ models - 模型管理表")
        print("  ✅ image_database - 图片数据库表")
        print("  ✅ inference_tasks - 推理任务表")
        print("  ✅ inference_results - 推理结果表")

        # 3. 插入初始模型数据
        print("\n[3/5] 插入初始数据...")
        from shared.database import SessionLocal

        db = SessionLocal()

        # 模型路径
        model_path = r"G:\ShuangChuang\ShuangC\ultralytics-main\runs\detect\train4_highrpd_v2\weights\best.pt"

        # 检查模型文件是否存在
        if os.path.exists(model_path):
            print(f"  ✅ 找到模型文件: {model_path}")
        else:
            print(f"  ⚠️  模型文件不存在: {model_path}")
            print(f"  提示: 请确认模型路径是否正确")

        # 插入模型
        model = Model(
            name="best.pt",
            path=model_path,
            version="v2.0",
            description="高速公路缺陷检测模型 - 最佳权重",
            model_type="detection",
            is_active=True
        )
        db.add(model)
        db.commit()
        print(f"  ✅ 插入模型: {model.name} ({model.version})")

        # 4. 插入测试图片数据（如果存在）
        print("\n[4/5] 插入测试图片...")

        dataset_dir = r"G:\ShuangChuang\ShuangC\backend\uploads\images"

        if os.path.exists(dataset_dir):
            # 获取前 3 张图片作为测试数据
            test_images = []
            for file in os.listdir(dataset_dir):
                if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    test_images.append(file)
                    if len(test_images) >= 3:
                        break

            for idx, filename in enumerate(test_images, 1):
                img_path = os.path.join(dataset_dir, filename)
                folder = '/测试图片'

                img = ImageDatabase(
                    filename=filename,
                    path=img_path,
                    folder=folder,
                    size=os.path.getsize(img_path),
                    mime_type='image/jpeg'
                )
                db.add(img)
                print(f"  ✅ 插入测试图片 {idx}: {filename}")

            db.commit()
        else:
            print(f"  ⚠️  数据集目录不存在: {dataset_dir}")
            print(f"  跳过插入测试图片")

        db.close()

        # 5. 验证
        print("\n[5/5] 验证数据库...")
        db = SessionLocal()

        model_count = db.query(Model).count()
        image_count = db.query(ImageDatabase).count()

        print(f"  ✅ 模型数量: {model_count}")
        print(f"  ✅ 图片数量: {image_count}")

        db.close()

        # 完成
        print("\n" + "=" * 60)
        print("✅ 数据库初始化完成！")
        print("=" * 60)
        print("\n数据库信息:")
        print(f"  - 主机: localhost")
        print(f"  - 端口: 5432")
        print(f"  - 数据库: defect_detection")
        print(f"  - 用户: postgres")
        print(f"\n下一步:")
        print(f"  1. 运行 python test_connection.py 测试连接")
        print(f"  2. 运行 python import_dataset.py 导入更多图片")
        print(f"  3. 运行 start_all.bat 启动服务")
        print()

        return True

    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = init_database()

    if success:
        print("\n按回车键退出...")
        input()
    else:
        print("\n初始化失败，请检查错误信息")
        print("按回车键退出...")
        input()
        sys.exit(1)
