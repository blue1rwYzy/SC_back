"""
测试数据库连接和环境
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

def test_database():
    """测试数据库连接"""
    print("=" * 50)
    print("测试数据库连接")
    print("=" * 50)

    try:
        from shared.database import test_connection, SessionLocal
        from shared.models import Model

        # 测试连接
        if not test_connection():
            return False

        # 测试查询
        db = SessionLocal()
        models = db.query(Model).all()
        print(f"✅ 查询成功！共有 {len(models)} 个模型")
        for model in models:
            print(f"   - {model.name} ({model.version})")
        db.close()

        return True

    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return False


def test_yolo():
    """测试 YOLO 模型"""
    print("\n" + "=" * 50)
    print("测试 YOLO 模型")
    print("=" * 50)

    try:
        from ultralytics import YOLO
        import os

        model_path = r"G:\ShuangChuang\ShuangC\ultralytics-main\runs\detect\train4_highrpd_v2\weights\best.pt"

        if not os.path.exists(model_path):
            print(f"❌ 模型文件不存在: {model_path}")
            return False

        print(f"📦 加载模型: {model_path}")
        model = YOLO(model_path)
        print(f"✅ 模型加载成功！")

        # 获取模型信息
        print(f"   - 模型类型: {type(model)}")
        print(f"   - 类别数量: {len(model.names)}")
        print(f"   - 类别列表: {list(model.names.values())}")

        return True

    except Exception as e:
        print(f"❌ YOLO 模型加载失败: {e}")
        return False


def test_directories():
    """测试目录结构"""
    print("\n" + "=" * 50)
    print("测试目录结构")
    print("=" * 50)

    dirs = {
        "上传目录": r"G:\ShuangChuang\ShuangC\backend\uploads",
        "图片目录": r"G:\ShuangChuang\ShuangC\backend\uploads\images",
        "结果目录": r"G:\ShuangChuang\ShuangC\backend\uploads\results",
    }

    all_ok = True
    for name, path in dirs.items():
        if os.path.exists(path):
            print(f"✅ {name}: {path}")
        else:
            print(f"❌ {name}: {path} (不存在)")
            all_ok = False

    return all_ok


if __name__ == "__main__":
    print("\n" + "🔍 环境检测开始".center(50, "="))
    print()

    results = {
        "数据库连接": test_database(),
        "YOLO 模型": test_yolo(),
        "目录结构": test_directories(),
    }

    print("\n" + "=" * 50)
    print("检测结果")
    print("=" * 50)

    for name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")

    if all(results.values()):
        print("\n" + "🎉 所有检测通过！系统可以正常运行".center(50, "="))
    else:
        print("\n" + "⚠️  部分检测失败，请检查配置".center(50, "="))

    print()
