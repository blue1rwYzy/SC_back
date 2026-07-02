"""
重构 inference_results 表的迁移脚本
"""
from database import engine, Base, SessionLocal
from sqlalchemy import text

def migrate():
    """执行迁移"""
    db = SessionLocal()
    try:
        print("🔄 开始迁移 inference_results 表...")

        # 1. 删除旧表
        print("1️⃣ 删除旧表...")
        db.execute(text("DROP TABLE IF EXISTS inference_results CASCADE"))
        db.commit()
        print("   ✅ 旧表已删除")

        # 2. 创建新表
        print("2️⃣ 创建新表...")
        from models import InferenceResult
        Base.metadata.create_all(bind=engine, tables=[InferenceResult.__table__])
        print("   ✅ 新表已创建")

        # 3. 创建索引
        print("3️⃣ 创建索引...")
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_inference_batch_name ON inference_results(batch_name);
            CREATE INDEX IF NOT EXISTS idx_inference_task_id ON inference_results(task_id);
            CREATE INDEX IF NOT EXISTS idx_inference_severity_level ON inference_results(severity_level);
            CREATE INDEX IF NOT EXISTS idx_inference_created_at ON inference_results(created_at);
        """))
        db.commit()
        print("   ✅ 索引已创建")

        print("✅ 迁移完成！")

    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
