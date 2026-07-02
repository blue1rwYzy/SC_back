"""
数据库连接配置 - 共享模块
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

# 数据库配置
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:mm@localhost:5432/defect_detection"
)

# 创建引擎
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False  # 设为 True 可以看到 SQL 语句
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明基类
Base = declarative_base()


def get_db():
    """
    获取数据库会话 (用于 FastAPI Depends)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """
    获取数据库会话 (用于普通函数)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    初始化数据库（创建所有表）
    """
    # 导入所有模型以确保它们被注册到 Base.metadata
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    print("✅ 数据库表初始化完成")


def test_connection():
    """
    测试数据库连接
    """
    try:
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        print("✅ 数据库连接成功！")
        return True
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return False


if __name__ == "__main__":
    # 测试连接
    test_connection()
