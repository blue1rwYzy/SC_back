"""
数据库配置
使用SQLite数据库存储系统管理数据
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# 数据库文件路径(相对路径,存储在backend目录下)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.path.join(BASE_DIR, "system_management.db")

# SQLite数据库URL
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# 创建引擎
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite需要此配置
    echo=False  # 设为True可以看到SQL语句
)

# 创建Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建Base类
Base = declarative_base()


def get_db():
    """
    获取数据库会话
    用于FastAPI依赖注入
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    初始化数据库表
    在应用启动时调用
    """
    from models import system_models  # 导入模型

    # 创建所有表
    Base.metadata.create_all(bind=engine)
    print(f"✅ 数据库初始化完成: {DATABASE_PATH}")
