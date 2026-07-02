"""
业务服务 - 主入口
端口: 8001
负责: 模型管理、图片库管理、任务管理、用户认证
"""
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import sys
import os
import hashlib
import io

# 加载环境变量
load_dotenv()

# 导入 MinIO 配置和客户端 (生产环境统一使用 MinIO)
from utils.minio_client import minio_client
from config.minio_config import BUCKETS
try:
    import jwt as pyjwt
except ImportError:
    # 如果 PyJWT 未安装，使用替代方案
    import json
    import base64
    import hmac

    class SimpleJWT:
        @staticmethod
        def encode(payload, secret, algorithm):
            # 简单的 JWT 实现
            import time
            payload_str = json.dumps(payload, separators=(',', ':'))
            payload_b64 = base64.urlsafe_b64encode(payload_str.encode()).decode().rstrip('=')
            header_b64 = base64.urlsafe_b64encode(b'{"typ":"JWT","alg":"HS256"}').decode().rstrip('=')
            message = f"{header_b64}.{payload_b64}"
            signature = base64.urlsafe_b64encode(
                hmac.new(secret.encode(), message.encode(), 'sha256').digest()
            ).decode().rstrip('=')
            return f"{message}.{signature}"

        @staticmethod
        def decode(token, secret, algorithms):
            try:
                parts = token.split('.')
                if len(parts) != 3:
                    return None
                payload_b64 = parts[1]
                # 添加填充
                padding = 4 - len(payload_b64) % 4
                if padding != 4:
                    payload_b64 += '=' * padding
                payload_str = base64.urlsafe_b64decode(payload_b64).decode()
                payload = json.loads(payload_str)
                # 检查过期时间
                if 'exp' in payload:
                    import time
                    if payload['exp'] < time.time():
                        return None
                return payload
            except:
                return None

    pyjwt = SimpleJWT()

# 添加父目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared import (
    get_db, Model, ImageDatabase, InferenceTask, InferenceResult, VideoTrackingTask,
    ModelResponse, ImageDatabaseResponse, InferenceTaskResponse
)
from shared.database import init_db as init_shared_db
from database import init_db, SessionLocal as SystemSessionLocal
from routers import video_database, knowledge_graph

# 系统管理数据库依赖注入
def get_system_db():
    """获取系统管理数据库会话(SQLite)"""
    db = SystemSessionLocal()
    try:
        yield db
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    print("🔄 正在初始化共享数据库表...")
    init_shared_db()

    print("🔄 正在初始化系统管理数据库表...")
    init_db()

    # 初始化系统管理数据
    print("🔄 正在初始化系统管理默认数据...")
    from services.system_init_service import init_system_data
    from database import SessionLocal
    db = SessionLocal()
    try:
        init_system_data(db)
    finally:
        db.close()

    yield
    # 关闭时执行（如果需要的话）

app = FastAPI(
    title="业务服务 API",
    description="高速公路缺陷检测系统 - 业务服务",
    version="1.0.0",
    lifespan=lifespan
)

# 上传目录配置
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
IMAGES_DIR = os.path.join(UPLOAD_DIR, "images")
IMG_RESULTS_DIR = os.path.join(UPLOAD_DIR, "img_results")  # 图片推理结果
VIDEOS_DIR = os.path.join(UPLOAD_DIR, "videos")
VID_RESULTS_DIR = os.path.join(UPLOAD_DIR, "vid_results")  # 视频推理结果

# 确保目录存在
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(IMG_RESULTS_DIR, exist_ok=True)
os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(VID_RESULTS_DIR, exist_ok=True)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 访客记录中间件
from middleware.visitor_middleware import VisitorMiddleware
app.add_middleware(VisitorMiddleware)

# 注册子路由
video_database.set_videos_dir(VIDEOS_DIR)
video_database.set_vid_results_dir(VID_RESULTS_DIR)
app.include_router(video_database.router)
app.include_router(knowledge_graph.router)

# 注册系统管理路由
from routers import system_router
app.include_router(system_router.router)

# JWT 配置
SECRET_KEY = "vben-admin-secret-key-2024"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 720  # 12小时

# ============ 认证相关数据模型 ============
class LoginRequest(BaseModel):
    username: str
    password: str

# 模拟用户数据
MOCK_USERS = [
    {
        "id": 0,
        "username": "vben",
        "password": hashlib.md5("123456".encode()).hexdigest(),
        "realName": "Vben Admin",
        "roles": ["super"],
        "homePath": "/analytics"
    },
    {
        "id": 1,
        "username": "admin",
        "password": hashlib.md5("123456".encode()).hexdigest(),
        "realName": "管理员",
        "roles": ["admin"],
        "homePath": "/system/defect-detection"
    },
    {
        "id": 2,
        "username": "user",
        "password": hashlib.md5("123456".encode()).hexdigest(),
        "realName": "普通用户",
        "roles": ["user"],
        "homePath": "/system/defect-detection"
    }
]

# 权限代码
MOCK_CODES = {
    "vben": ["AC_100100", "AC_100110", "AC_100120", "AC_100010"],
    "admin": ["AC_100010", "AC_100020", "AC_100030"],
    "user": ["AC_1000001", "AC_1000002"]
}

# 菜单数据 - 包含路面缺陷检测和图像数据库管理
MOCK_MENUS = {
    "vben": [
        {
            "meta": {"order": 1, "title": "系统功能", "icon": "carbon:settings"},
            "name": "System",
            "path": "/system",
            "redirect": "/system/defect-detection",
            "children": [
                {
                    "name": "DefectDetection",
                    "path": "/system/defect-detection",
                    "component": "/system/defect-detection/index",
                    "meta": {"icon": "carbon:camera", "title": "page.system.defectDetection"}
                },
                {
                    "name": "ImageDatabase",
                    "path": "/system/image-database",
                    "component": "/system/image-database/index",
                    "meta": {"icon": "lucide:database", "title": "page.system.imageDatabase"}
                },
                {
                    "name": "KnowledgeGraph",
                    "path": "/system/knowledge-graph",
                    "component": "/system/knowledge-graph/index",
                    "meta": {"icon": "lucide:network", "title": "page.system.knowledgeGraph"}
                }
            ]
        }
    ],
    "admin": [
        {
            "meta": {"order": 1, "title": "系统功能", "icon": "carbon:settings"},
            "name": "System",
            "path": "/system",
            "redirect": "/system/defect-detection",
            "children": [
                {
                    "name": "DefectDetection",
                    "path": "/system/defect-detection",
                    "component": "/system/defect-detection/index",
                    "meta": {"icon": "carbon:camera", "title": "page.system.defectDetection"}
                },
                {
                    "name": "ImageDatabase",
                    "path": "/system/image-database",
                    "component": "/system/image-database/index",
                    "meta": {"icon": "lucide:database", "title": "page.system.imageDatabase"}
                },
                {
                    "name": "KnowledgeGraph",
                    "path": "/system/knowledge-graph",
                    "component": "/system/knowledge-graph/index",
                    "meta": {"icon": "lucide:network", "title": "page.system.knowledgeGraph"}
                }
            ]
        }
    ],
    "user": [
        {
            "meta": {"order": 1, "title": "系统功能", "icon": "carbon:settings"},
            "name": "System",
            "path": "/system",
            "redirect": "/system/defect-detection",
            "children": [
                {
                    "name": "DefectDetection",
                    "path": "/system/defect-detection",
                    "component": "/system/defect-detection/index",
                    "meta": {"icon": "carbon:camera", "title": "page.system.defectDetection"}
                },
                {
                    "name": "ImageDatabase",
                    "path": "/system/image-database",
                    "component": "/system/image-database/index",
                    "meta": {"icon": "lucide:database", "title": "page.system.imageDatabase"}
                },
                {
                    "name": "KnowledgeGraph",
                    "path": "/system/knowledge-graph",
                    "component": "/system/knowledge-graph/index",
                    "meta": {"icon": "lucide:network", "title": "page.system.knowledgeGraph"}
                }
            ]
        }
    ]
}

# ============ 认证工具函数 ============
def create_access_token(data: dict):
    """创建访问令牌"""
    import time
    to_encode = data.copy()
    expire = int(time.time()) + (ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    to_encode.update({"exp": expire})
    encoded_jwt = pyjwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    """验证令牌"""
    try:
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except:
        return None

def get_current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_system_db)):
    """从请求头获取当前用户 - 使用系统管理数据库"""
    from services.user_service import UserService

    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")

    token = authorization.replace("Bearer ", "")
    payload = verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    username = payload.get("username")
    user = UserService.get_user_by_username(db, username)

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # 返回用户字典格式,兼容现有代码
    role_codes = [role.code for role in user.roles] if user.roles else []
    return {
        "id": user.id,
        "username": user.username,
        "realName": user.real_name,
        "roles": role_codes,
        "email": user.email,
        "phone": user.phone,
        "department_id": user.department_id,
        "position": user.position,
        "is_admin": user.is_admin
    }


# ============ 健康检查 ============
@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "service": "business-service"}


# ============ 认证接口 ============
@app.post("/auth/login")
async def login(request: LoginRequest, db: Session = Depends(get_system_db)):
    """用户登录 - 使用系统管理数据库验证"""
    from services.user_service import UserService

    print(f"\n🔐 登录尝试: 用户名={request.username}", flush=True)

    # 1. 查找用户
    user = UserService.get_user_by_username(db, request.username)

    if not user:
        print(f"   ❌ 用户不存在: {request.username}", flush=True)
        return JSONResponse(
            status_code=403,
            content={"code": 403, "message": "用户名或密码错误", "data": None}
        )

    print(f"   ✅ 找到用户: {user.username} (ID: {user.id})", flush=True)

    # 2. 验证密码
    if not UserService.verify_password(request.password, user.password):
        print(f"   ❌ 密码验证失败", flush=True)
        return JSONResponse(
            status_code=403,
            content={"code": 403, "message": "用户名或密码错误", "data": None}
        )

    print(f"   ✅ 密码验证成功", flush=True)

    # 3. 检查用户状态
    print(f"   🔍 用户状态: {user.status}", flush=True)
    if not user.status:
        print(f"   ❌ 账号已被禁用", flush=True)
        return JSONResponse(
            status_code=403,
            content={"code": 403, "message": "账号已被禁用", "data": None}
        )

    print(f"   ✅ 登录成功！", flush=True)

    # 4. 获取用户角色
    role_codes = [role.code for role in user.roles] if user.roles else []

    # 5. 创建 token
    access_token = create_access_token({
        "username": user.username,
        "id": user.id,
        "roles": role_codes
    })

    # 6. 更新登录信息 (后台任务,不阻塞响应)
    try:
        UserService.update_login_info(db, user.id, "127.0.0.1")
    except:
        pass

    # 7. 返回用户信息
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": user.id,
            "username": user.username,
            "realName": user.real_name,
            "roles": role_codes,
            "homePath": "/analytics",  # 默认首页
            "accessToken": access_token
        }
    }


@app.post("/auth/refresh")
async def refresh_token(authorization: Optional[str] = Header(None)):
    """刷新令牌"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token")

    token = authorization.replace("Bearer ", "")
    payload = verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    new_token = create_access_token({
        "username": payload.get("username"),
        "id": payload.get("id"),
        "roles": payload.get("roles")
    })

    return {"code": 0, "message": "success", "data": new_token}


@app.post("/auth/logout")
async def logout():
    """用户登出"""
    return {"code": 0, "message": "success", "data": None}


@app.get("/user/info")
async def get_user_info(authorization: Optional[str] = Header(None), db: Session = Depends(get_system_db)):
    """获取用户信息"""
    user = get_current_user(authorization, db)
    return {
        "code": 0,
        "message": "success",
        "data": {
            "id": user["id"],
            "username": user["username"],
            "realName": user["realName"],
            "roles": user["roles"],
            "homePath": "/analytics"  # 默认首页
        }
    }


@app.get("/auth/codes")
async def get_user_codes(authorization: Optional[str] = Header(None), db: Session = Depends(get_system_db)):
    """获取用户权限代码"""
    user = get_current_user(authorization, db)
    # 根据角色返回权限代码
    # 超级管理员和管理员拥有所有权限
    if "SUPER_ADMIN" in user["roles"] or user.get("is_admin"):
        codes = ["AC_100000", "AC_100100", "AC_1000000", "AC_1000100"]
    else:
        codes = MOCK_CODES.get(user["username"], [])
    return {"code": 0, "message": "success", "data": codes}


@app.get("/menu/all")
async def get_user_menus(authorization: Optional[str] = Header(None), db: Session = Depends(get_system_db)):
    """获取用户菜单"""
    user = get_current_user(authorization, db)
    # 超级管理员和管理员看到所有菜单
    if "SUPER_ADMIN" in user["roles"] or user.get("is_admin"):
        menus = MOCK_MENUS.get("admin", [])
    else:
        menus = MOCK_MENUS.get(user["username"], MOCK_MENUS.get("admin", []))
    return {"code": 0, "message": "success", "data": menus}


# ============ 模型管理 ============
@app.get("/models")
async def get_models(model_type: str = None, db: Session = Depends(get_db)):
    """获取所有模型，支持按类型过滤"""
    query = db.query(Model).filter(Model.is_active == True)

    # 按类型过滤
    if model_type:
        query = query.filter(Model.model_type == model_type)

    models = query.all()
    return {
        "code": 0,
        "data": [
            {
                "id": m.id,
                "name": m.name,
                "path": m.path,
                "version": m.version,
                "description": m.description,
                "model_type": m.model_type,
                "createdAt": m.created_at.isoformat() if m.created_at else None
            }
            for m in models
        ],
        "message": "success"
    }


@app.get("/models/{model_id}")
async def get_model(model_id: int, db: Session = Depends(get_db)):
    """获取单个模型"""
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")
    return {
        "code": 0,
        "data": {
            "id": model.id,
            "name": model.name,
            "path": model.path,
            "version": model.version,
            "description": model.description,
            "model_type": model.model_type,
            "createdAt": model.created_at.isoformat() if model.created_at else None
        },
        "message": "success"
    }


@app.post("/models")
async def create_model(
    name: str = Form(...),
    version: str = Form("v1.0"),
    description: Optional[str] = Form(None),
    model_type: str = Form("detection"),
    model_file: Optional[UploadFile] = File(None),
    model_path: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """创建模型 - 支持上传文件或指定路径 - 支持 MinIO"""
    import shutil

    # 调试日志
    print(f"\n📝 收到添加模型请求:", flush=True)
    print(f"  name: {name}", flush=True)
    print(f"  version: {version}", flush=True)
    print(f"  description: {description}", flush=True)
    print(f"  model_type: {model_type}", flush=True)
    print(f"  model_file: {model_file.filename if model_file else None}", flush=True)
    print(f"  model_path: {model_path}", flush=True)

    # 验证 model_type
    if model_type not in ["detection", "tracking"]:
        raise HTTPException(status_code=400, detail="模型类型必须是 detection 或 tracking")

    # 确定 MinIO 文件夹
    if model_type == "detection":
        minio_folder = "JC"
    else:  # tracking
        minio_folder = "ZZ"

    final_model_path = None

    # 处理文件上传
    if model_file and model_file.filename:
        print(f"📤 处理模型文件上传: {model_file.filename}", flush=True)

        # 验证文件类型
        if not model_file.filename.endswith(('.pt', '.pth', '.onnx', '.engine')):
            raise HTTPException(status_code=400, detail="不支持的模型文件格式")

        # 上传到 MinIO
        object_name = f"{minio_folder}/{model_file.filename}"
        print(f"   目标路径: {BUCKETS['models']}/{object_name}", flush=True)

        # 读取文件内容
        file_content = await model_file.read()
        print(f"   文件大小: {len(file_content)} bytes", flush=True)

        # 上传到 MinIO
        success = minio_client.upload_file(
            bucket_name=BUCKETS["models"],
            object_name=object_name,
            file_data=io.BytesIO(file_content),
            content_type="application/octet-stream"
        )

        if not success:
            print(f"   ❌ MinIO 上传失败", flush=True)
            raise HTTPException(status_code=500, detail="MinIO 上传失败")

        # 存储 MinIO 路径
        final_model_path = f"minio://{BUCKETS['models']}/{object_name}"
        print(f"   ✅ 模型已上传到 MinIO: {final_model_path}", flush=True)

    # 处理路径输入
    elif model_path:
        print(f"📁 处理模型路径输入: {model_path}", flush=True)

        # 规范化路径
        model_path = os.path.normpath(model_path)
        print(f"   规范化后的路径: {model_path}", flush=True)
        print(f"   路径是否存在: {os.path.exists(model_path)}", flush=True)

        # 验证路径是否存在
        if not os.path.exists(model_path):
            raise HTTPException(status_code=400, detail=f"指定的模型路径不存在: {model_path}")

        if not os.path.isfile(model_path):
            raise HTTPException(status_code=400, detail="指定的路径不是文件")

        # 对于本地路径，也上传到 MinIO
        print(f"   📤 将本地模型上传到 MinIO...", flush=True)
        filename = os.path.basename(model_path)
        object_name = f"{minio_folder}/{filename}"

        with open(model_path, "rb") as f:
            success = minio_client.upload_file(
                bucket_name=BUCKETS["models"],
                object_name=object_name,
                file_data=f,
                content_type="application/octet-stream"
            )

        if not success:
            print(f"   ⚠️ MinIO 上传失败，使用本地路径", flush=True)
            final_model_path = model_path
        else:
            final_model_path = f"minio://{BUCKETS['models']}/{object_name}"
            print(f"   ✅ 模型已上传到 MinIO: {final_model_path}", flush=True)
    else:
        raise HTTPException(status_code=400, detail="必须提供模型文件或模型路径")

    # 检查模型名称是否已存在
    print(f"🔍 检查模型名称是否存在: {name}")
    existing_model = db.query(Model).filter(Model.name == name).first()
    if existing_model:
        error_msg = f"模型名称 '{name}' 已存在"
        print(f"❌ {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)

    # 创建数据库记录
    print(f"💾 创建数据库记录...")
    try:
        new_model = Model(
            name=name,
            path=final_model_path,
            version=version,
            description=description,
            model_type=model_type,
            is_active=True
        )

        db.add(new_model)
        db.commit()
        db.refresh(new_model)
        print(f"✅ 模型创建成功: ID={new_model.id}")
    except Exception as e:
        print(f"❌ 数据库操作失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=f"数据库操作失败: {str(e)}")

    return {
        "code": 0,
        "data": {
            "id": new_model.id,
            "name": new_model.name,
            "path": new_model.path,
            "version": new_model.version,
            "description": new_model.description,
            "model_type": new_model.model_type,
            "createdAt": new_model.created_at.isoformat() if new_model.created_at else None
        },
        "message": "模型创建成功"
    }


@app.put("/models/{model_id}")
async def update_model(
    model_id: int,
    name: str = Form(None),
    version: str = Form(None),
    description: str = Form(None),
    model_type: str = Form(None),
    db: Session = Depends(get_db)
):
    """更新模型信息"""
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    # 更新字段
    if name is not None:
        # 检查新名称是否与其他模型冲突
        existing = db.query(Model).filter(Model.name == name, Model.id != model_id).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"模型名称 '{name}' 已存在")
        model.name = name

    if version is not None:
        model.version = version

    if description is not None:
        model.description = description

    if model_type is not None:
        if model_type not in ["detection", "tracking"]:
            raise HTTPException(status_code=400, detail="模型类型必须是 detection 或 tracking")
        model.model_type = model_type

    model.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(model)

    return {
        "code": 0,
        "data": {
            "id": model.id,
            "name": model.name,
            "path": model.path,
            "version": model.version,
            "description": model.description,
            "model_type": model.model_type,
            "updatedAt": model.updated_at.isoformat() if model.updated_at else None
        },
        "message": "模型更新成功"
    }


@app.delete("/models/{model_id}")
async def delete_model(model_id: int, db: Session = Depends(get_db)):
    """删除模型（硬删除，包括物理文件）- 支持 MinIO"""
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    print(f"🗑️ 删除模型: ID={model_id}, 名称={model.name}, 路径={model.path}")

    # 检查是否有关联的推理任务
    from shared.models import InferenceTask
    related_tasks = db.query(InferenceTask).filter(InferenceTask.model_id == model_id).all()

    if related_tasks:
        print(f"⚠️ 发现 {len(related_tasks)} 个使用该模型的推理任务，将一并删除")
        # 删除所有关联的推理任务
        for task in related_tasks:
            db.delete(task)
        print(f"✅ 已删除 {len(related_tasks)} 个关联的推理任务")

    # 删除物理文件 (从 MinIO)
    if model.path and model.path.startswith("minio://"):
        # 解析路径: minio://models/JC/yolov8n.pt
        parts = model.path.replace("minio://", "").split("/", 1)
        if len(parts) == 2:
            bucket_name, object_name = parts
            success = minio_client.delete_file(bucket_name, object_name)
            if success:
                print(f"✅ 模型文件已从 MinIO 删除: {model.path}")
            else:
                print(f"⚠️ MinIO 删除失败: {model.path}")
        else:
            print(f"⚠️ MinIO 路径格式错误: {model.path}")
    else:
        print(f"⚠️ 模型路径无效或为空: {model.path}")

    # 硬删除：从数据库删除记录
    db.delete(model)
    db.commit()

    print(f"✅ 模型记录已从数据库删除")

    return {
        "code": 0,
        "data": None,
        "message": "模型删除成功"
    }


# ============ 图片数据库管理 ============
@app.get("/images/database")
async def get_image_database(folder: str = None):
    """获取图片数据库（从 MinIO 获取文件列表，返回树形结构）"""
    try:
        # 从 MinIO 列举对象
        objects = minio_client.list_objects(
            bucket_name=BUCKETS["images"],
            prefix=folder if folder else None,
            recursive=True
        )

        # 构建树形结构
        folder_map = {}  # 用于存储文件夹节点
        file_list = []   # 用于存储文件节点
        total_count = 0  # 总对象数
        image_count = 0  # 图片文件数

        for obj in objects:
            total_count += 1
            # obj 格式: folder/subfolder/file.jpg
            object_name = obj.object_name
            parts = object_name.split('/')
            filename = parts[-1]

            # 跳过非图片文件
            if not filename.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp')):
                print(f"⚠️ 跳过非图片文件: {object_name}")
                continue

            image_count += 1

            # 构建访问路径
            access_path = f"/uploads/images/{object_name}"

            # 如果有文件夹层级
            if len(parts) > 1:
                folder_path = '/'.join(parts[:-1])

                # 确保文件夹节点存在
                if folder_path not in folder_map:
                    folder_map[folder_path] = {
                        "id": f"folder_{folder_path}",
                        "filename": parts[-2] if len(parts) > 1 else folder_path,
                        "path": folder_path,
                        "relativePath": folder_path,
                        "isFolder": True,
                        "children": []
                    }

                # 添加文件到对应文件夹
                folder_map[folder_path]["children"].append({
                    "id": object_name,
                    "filename": filename,
                    "path": access_path,
                    "fullPath": object_name,
                    "relativePath": object_name,
                    "size": obj.size,
                    "uploadedAt": obj.last_modified.isoformat() if obj.last_modified else None,
                    "isFolder": False
                })
            else:
                # 根目录文件
                file_list.append({
                    "id": object_name,
                    "filename": filename,
                    "path": access_path,
                    "fullPath": object_name,
                    "relativePath": object_name,
                    "size": obj.size,
                    "uploadedAt": obj.last_modified.isoformat() if obj.last_modified else None,
                    "isFolder": False
                })

        print(f"✅ 图片列表统计: 总对象 {total_count}, 图片文件 {image_count}")

        # 合并文件夹和文件
        result = list(folder_map.values()) + file_list

        if not result:
            return {"code": 0, "data": [], "message": "MinIO 中暂无图片"}

        return {
            "code": 0,
            "data": result,
            "message": "success"
        }

    except Exception as e:
        print(f"❌ 获取 MinIO 图片列表失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "code": 500,
            "data": [],
            "message": f"获取图片列表失败: {str(e)}"
        }


@app.get("/images/{image_id}")
async def get_image(image_id: int, db: Session = Depends(get_db)):
    """获取单张图片信息"""
    image = db.query(ImageDatabase).filter(ImageDatabase.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="图片不存在")
    return {
        "code": 0,
        "data": {
            "id": image.id,
            "filename": image.filename,
            "path": image.path,
            "folder": image.folder,
            "size": image.size,
            "uploadedAt": image.uploaded_at.isoformat() if image.uploaded_at else None
        },
        "message": "success"
    }


@app.post("/images/upload")
async def upload_image(
    file: UploadFile = File(...),
    folder: str = Form(""),
    db: Session = Depends(get_db)
):
    """上传图片到 MinIO"""
    from PIL import Image
    import io

    # 清理文件夹路径
    folder = folder.strip().strip('/')

    # 生成时间戳文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    original_name = os.path.splitext(file.filename)[0]
    file_ext = os.path.splitext(file.filename)[1]
    new_filename = f"{timestamp}_{original_name}{file_ext}"

    # 构建对象路径
    if folder:
        object_name = f"{folder}/{new_filename}"
    else:
        object_name = new_filename

    try:
        # 读取文件内容
        file_content = await file.read()
        file_size = len(file_content)

        # 获取图片尺寸
        width, height = None, None
        try:
            img = Image.open(io.BytesIO(file_content))
            width, height = img.size
        except:
            pass

        # 上传到 MinIO
        file_stream = io.BytesIO(file_content)
        success = minio_client.upload_file(
            bucket_name=BUCKETS["images"],
            object_name=object_name,
            file_data=file_stream,
            content_type=file.content_type or "image/jpeg"
        )

        if not success:
            raise HTTPException(status_code=500, detail="上传到 MinIO 失败")

        # 生成访问 URL (7天有效)
        file_url = minio_client.get_presigned_url(
            bucket_name=BUCKETS["images"],
            object_name=object_name,
            expires=timedelta(days=7)
        )

        return {
            "code": 0,
            "data": {
                "filename": new_filename,
                "original_filename": file.filename,
                "path": file_url,
                "folder": folder or "/",
                "size": file_size,
                "width": width,
                "height": height,
                "storage": "minio"
            },
            "message": "上传成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@app.post("/images/upload-zip")
async def upload_zip(
    file: UploadFile = File(...),
    folder: str = Form("")
):
    """上传压缩包并批量上传图片到 MinIO"""
    import shutil
    import zipfile
    import tempfile
    import io

    # 验证文件类型
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="只支持 .zip 格式的压缩包")

    # 清理文件夹路径
    folder = folder.strip().strip('/')

    # 创建临时文件保存上传的压缩包
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_file_path = temp_file.name

    uploaded_files = []

    try:
        # 解压文件
        with zipfile.ZipFile(temp_file_path, 'r') as zip_ref:
            # 获取压缩包内的文件列表
            file_list = zip_ref.namelist()

            # 过滤出图片文件
            image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}
            image_files = [
                f for f in file_list
                if os.path.splitext(f.lower())[1] in image_extensions and not f.startswith('__MACOSX')
            ]

            if not image_files:
                raise HTTPException(status_code=400, detail="压缩包中没有找到图片文件")

            # 上传到 MinIO
            for image_file in image_files:
                try:
                    # 读取压缩包内的文件
                    file_data = zip_ref.read(image_file)

                    # 生成对象名称
                    filename = os.path.basename(image_file)
                    if folder:
                        object_name = f"{folder}/{filename}"
                    else:
                        object_name = filename

                    # 上传到 MinIO
                    file_stream = io.BytesIO(file_data)
                    success = minio_client.upload_file(
                        bucket_name=BUCKETS["images"],
                        object_name=object_name,
                        file_data=file_stream,
                        content_type="image/jpeg"
                    )

                    if success:
                        uploaded_files.append(object_name)

                except Exception as e:
                    print(f"上传文件失败 {image_file}: {e}")
                    continue

            return {
                "code": 0,
                "data": {
                    "folder": folder or "/",
                    "extracted_files": len(uploaded_files),
                    "total_files": len(image_files),
                    "storage": "minio"
                },
                "message": f"成功上传 {len(uploaded_files)}/{len(image_files)} 个图片文件到 MinIO"
            }

    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="无效的压缩包文件")
    except Exception as e:
        print(f"解压失败: {e}")
        raise HTTPException(status_code=500, detail=f"解压失败: {str(e)}")
    finally:
        # 清理临时文件
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


@app.delete("/images/file")
async def delete_image_file(file_path: str):
    """从 MinIO 删除图片文件"""
    try:
        # file_path 格式: folder/filename 或 filename
        object_name = file_path.replace("\\", "/")

        success = minio_client.delete_file(
            bucket_name=BUCKETS["images"],
            object_name=object_name
        )

        if not success:
            raise HTTPException(status_code=500, detail="从 MinIO 删除失败")

        return {"code": 0, "data": None, "message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"删除文件失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除文件失败: {str(e)}")


@app.post("/images/batch-delete-files")
async def batch_delete_image_files(file_paths: List[str]):
    """从 MinIO 批量删除图片文件"""
    deleted_count = 0
    failed_files = []

    for file_path in file_paths:
        try:
            object_name = file_path.replace("\\", "/")

            success = minio_client.delete_file(
                bucket_name=BUCKETS["images"],
                object_name=object_name
            )

            if success:
                deleted_count += 1
            else:
                failed_files.append(f"{file_path}: 删除失败")
        except Exception as e:
            failed_files.append(f"{file_path}: {str(e)}")

    return {
        "code": 0,
        "data": {
            "deleted": deleted_count,
            "failed": len(failed_files),
            "errors": failed_files,
            "storage": "minio"
        },
        "message": f"成功删除 {deleted_count} 个文件" + (f", {len(failed_files)} 个失败" if failed_files else "")
    }


@app.delete("/images/{image_id}")
async def delete_image(image_id: int, db: Session = Depends(get_db)):
    """删除图片（同时删除相关的推理结果记录）"""
    image = db.query(ImageDatabase).filter(ImageDatabase.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="图片不存在")

    # 删除相关的推理结果记录
    try:
        inference_results = db.query(InferenceResult).filter(
            InferenceResult.original_image == image.path
        ).all()

        deleted_inference_count = 0
        for result in inference_results:
            # 可选：同时删除推理结果图片
            if result.result_image and os.path.exists(result.result_image):
                try:
                    os.remove(result.result_image)
                    print(f"🗑️ 已删除推理结果图片: {result.result_image}")
                except Exception as e:
                    print(f"⚠️ 删除推理结果图片失败: {e}")

            db.delete(result)
            deleted_inference_count += 1

        if deleted_inference_count > 0:
            print(f"🗑️ 已删除 {deleted_inference_count} 条推理结果记录")

    except Exception as e:
        print(f"⚠️ 删除推理结果记录失败: {e}")

    # 删除原图文件
    try:
        if os.path.exists(image.path):
            os.remove(image.path)
    except Exception as e:
        print(f"删除文件失败: {e}")

    # 删除数据库记录
    db.delete(image)
    db.commit()

    return {"code": 0, "data": None, "message": "删除成功"}


@app.post("/images/batch-delete")
async def batch_delete_images(
    image_ids: List[int],
    db: Session = Depends(get_db)
):
    """批量删除图片（同时删除相关的推理结果记录）"""
    deleted_count = 0
    deleted_inference_count = 0

    for image_id in image_ids:
        image = db.query(ImageDatabase).filter(ImageDatabase.id == image_id).first()
        if image:
            # 删除相关的推理结果记录
            try:
                inference_results = db.query(InferenceResult).filter(
                    InferenceResult.original_image == image.path
                ).all()

                for result in inference_results:
                    # 可选：同时删除推理结果图片
                    if result.result_image and os.path.exists(result.result_image):
                        try:
                            os.remove(result.result_image)
                        except Exception as e:
                            print(f"⚠️ 删除推理结果图片失败: {e}")

                    db.delete(result)
                    deleted_inference_count += 1

            except Exception as e:
                print(f"⚠️ 删除推理结果记录失败: {e}")

            # 删除原图文件
            try:
                if os.path.exists(image.path):
                    os.remove(image.path)
            except Exception as e:
                print(f"删除文件失败 {image.filename}: {e}")

            # 删除数据库记录
            db.delete(image)
            deleted_count += 1

    db.commit()

    message = f"成功删除 {deleted_count} 张图片"
    if deleted_inference_count > 0:
        message += f"，同时删除 {deleted_inference_count} 条推理结果记录"

    return {"code": 0, "data": {"count": deleted_count, "inferenceCount": deleted_inference_count}, "message": message}


# ============ 视频数据库管理 ============
# 视频管理路由已移至 routers/video_database.py

# ============ 任务管理 ============
@app.get("/tasks", response_model=List[InferenceTaskResponse])
async def get_tasks(
    status: str = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取任务列表"""
    query = db.query(InferenceTask)
    if status:
        query = query.filter(InferenceTask.status == status)
    tasks = query.order_by(InferenceTask.created_at.desc()).limit(limit).all()
    return tasks


@app.get("/tasks/{task_id}", response_model=InferenceTaskResponse)
async def get_task(task_id: str, db: Session = Depends(get_db)):
    """获取任务详情"""
    task = db.query(InferenceTask).filter(InferenceTask.task_id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


# ============ 视频流式服务（支持 Range 请求）============
def range_requests_response(
    request: Request,
    file_path: str,
    content_type: str = "video/mp4"
):
    """支持 HTTP Range 请求的视频流式响应"""
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")

    if range_header:
        # 解析 Range 请求
        byte_range = range_header.replace("bytes=", "").split("-")
        start = int(byte_range[0]) if byte_range[0] else 0
        end = int(byte_range[1]) if byte_range[1] else file_size - 1
        end = min(end, file_size - 1)
        content_length = end - start + 1

        def file_iterator():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk_size = min(8192, remaining)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Type": content_type,
        }
        return StreamingResponse(
            file_iterator(),
            status_code=206,
            headers=headers,
            media_type=content_type
        )
    else:
        # 完整文件响应
        def file_iterator():
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk

        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": content_type,
        }
        return StreamingResponse(
            file_iterator(),
            headers=headers,
            media_type=content_type
        )


# 旧的本地磁盘视频路由已移除，统一使用 MinIO（见文件末尾的路由定义）


# ============ 推理结果管理 ============

@app.get("/inference-results/check-image")
async def check_image_inference_result(
    image_path: str,
    db: Session = Depends(get_db)
):
    """
    检查图片是否有推理结果

    参数:
        image_path: 图片路径（支持多种格式）

    返回:
        hasResult: bool - 是否有推理结果
        results: list - 推理结果列表（如果有）
    """
    try:
        print(f"\n🔍 检查图片推理结果: {image_path}", flush=True)

        # 提取相对路径（从 /uploads/images/... 或直接的相对路径）
        relative_path = image_path
        if image_path.startswith("/uploads/images/"):
            relative_path = image_path.replace("/uploads/images/", "")
        elif image_path.startswith("uploads/images/"):
            relative_path = image_path.replace("uploads/images/", "")
        elif image_path.startswith("/api/system/uploads/images/"):
            relative_path = image_path.replace("/api/system/uploads/images/", "")

        print(f"   相对路径: {relative_path}", flush=True)

        # 构建多种可能的路径格式进行查询
        # 1. MinIO 格式: minio://images/test/xxx.jpg
        minio_path = f"minio://{BUCKETS['images']}/{relative_path}"

        # 2. 本地绝对路径格式（兼容未迁移的数据）
        local_abs_path = os.path.join(UPLOAD_DIR, "images", relative_path)

        # 3. 相对路径格式
        rel_path = f"images/{relative_path}"

        print(f"   查询路径 1 (MinIO): {minio_path}", flush=True)
        print(f"   查询路径 2 (本地绝对): {local_abs_path}", flush=True)
        print(f"   查询路径 3 (相对): {rel_path}", flush=True)

        # 查询数据库（使用 OR 条件匹配多种格式）
        from sqlalchemy import or_
        results = db.query(InferenceResult).filter(
            or_(
                InferenceResult.original_image == minio_path,
                InferenceResult.original_image == local_abs_path,
                InferenceResult.original_image == rel_path,
                InferenceResult.original_image_rel == rel_path,
                InferenceResult.original_image_rel == relative_path
            )
        ).all()

        print(f"   ✅ 找到 {len(results)} 条推理结果", flush=True)

        return {
            "code": 0,
            "data": {
                "hasResult": len(results) > 0,
                "count": len(results),
                "results": [
                    {
                        "id": r.id,
                        "taskId": r.task_id,
                        "batchName": r.batch_name,
                        "resultImage": r.result_image,
                        "resultImageRel": r.result_image_rel,
                        "detectionCount": r.detection_count,
                        "avgConfidence": r.avg_confidence,
                        "severityLevel": r.severity_level,
                        "severityScore": r.severity_score,
                        "severityText": r.severity_text,
                        "severityColor": r.severity_color,
                        "imageWidth": r.image_width,
                        "imageHeight": r.image_height,
                        "createdAt": r.created_at.isoformat() if r.created_at else None
                    }
                    for r in results
                ]
            }
        }
    except Exception as e:
        print(f"❌ 查询推理结果失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@app.get("/inference-results/check-all")
async def check_all_images_inference_result(db: Session = Depends(get_db)):
    """
    批量查询所有图片的推理结果状态

    返回一个映射表：{ 图片路径: 是否有推理结果 }
    """
    try:
        print(f"\n📊 批量查询推理结果状态", flush=True)

        # 查询所有推理结果的原图路径（去重）
        results = db.query(InferenceResult.original_image, InferenceResult.original_image_rel).distinct().all()

        print(f"   数据库中有 {len(results)} 条不同的原图记录", flush=True)

        # 构建映射表（支持多种路径格式）
        image_map = {}
        for (original_image, original_image_rel) in results:
            # 1. 原始 MinIO 路径: minio://images/test3/xxx.jpg
            if original_image:
                image_map[original_image] = True

            # 2. 从 MinIO 路径提取相对路径
            if original_image and original_image.startswith("minio://"):
                # 提取 minio://images/ 之后的部分
                rel_path = original_image.replace(f"minio://{BUCKETS['images']}/", "")

                # 添加多种前端可能使用的格式
                image_map[f"/uploads/images/{rel_path}"] = True
                image_map[f"uploads/images/{rel_path}"] = True
                image_map[f"/api/system/uploads/images/{rel_path}"] = True
                image_map[rel_path] = True

            # 3. 使用 original_image_rel 字段
            if original_image_rel:
                image_map[original_image_rel] = True
                # 也添加带前缀的版本
                rel_without_images = original_image_rel.replace("images/", "")
                image_map[f"/uploads/images/{rel_without_images}"] = True
                image_map[f"uploads/images/{rel_without_images}"] = True

        print(f"   ✅ 构建映射表，支持 {len(image_map)} 种路径格式", flush=True)

        return {
            "code": 0,
            "data": {
                "total": len(results),
                "imageMap": image_map
            }
        }
    except Exception as e:
        print(f"❌ 批量查询推理结果失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@app.get("/inference-results/batches")
async def get_inference_batches(db: Session = Depends(get_db)):
    """
    获取所有推理批次列表（按 batch_name 分组）

    返回批次名称、图片数量、严重程度统计等
    """
    try:
        from sqlalchemy import func, distinct

        # 查询所有批次及其统计信息
        batches = db.query(
            InferenceResult.batch_name,
            func.count(InferenceResult.id).label('image_count'),
            func.avg(InferenceResult.severity_score).label('avg_severity_score'),
            func.min(InferenceResult.created_at).label('first_created'),
            func.max(InferenceResult.created_at).label('last_created')
        ).group_by(InferenceResult.batch_name).all()

        result = []
        for batch in batches:
            # 获取该批次的严重程度分布
            severity_dist = db.query(
                InferenceResult.severity_level,
                func.count(InferenceResult.id).label('count')
            ).filter(
                InferenceResult.batch_name == batch.batch_name
            ).group_by(InferenceResult.severity_level).all()

            severity_distribution = {
                str(level): count for level, count in severity_dist if level is not None
            }

            # 计算平均置信度：只统计有检测结果的图片（detection_count > 0）
            avg_conf_query = db.query(
                func.avg(InferenceResult.avg_confidence)
            ).filter(
                InferenceResult.batch_name == batch.batch_name,
                InferenceResult.detection_count > 0  # 只计算有检测到缺陷的图片
            ).scalar()

            result.append({
                "batchName": batch.batch_name,
                "imageCount": batch.image_count,
                "avgConfidence": round(avg_conf_query, 2) if avg_conf_query else 0,
                "avgSeverityScore": round(batch.avg_severity_score, 2) if batch.avg_severity_score else 0,
                "severityDistribution": severity_distribution,
                "firstCreated": batch.first_created.isoformat() if batch.first_created else None,
                "lastCreated": batch.last_created.isoformat() if batch.last_created else None
            })

        return {
            "code": 0,
            "data": {
                "total": len(result),
                "batches": result
            }
        }
    except Exception as e:
        print(f"❌ 获取批次列表失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@app.get("/inference-results/batch/{batch_name}")
async def get_batch_results(
    batch_name: str,
    db: Session = Depends(get_db)
):
    """
    获取指定批次的所有推理结果
    """
    try:
        results = db.query(InferenceResult).filter(
            InferenceResult.batch_name == batch_name
        ).order_by(InferenceResult.created_at.desc()).all()

        return {
            "code": 0,
            "data": {
                "batchName": batch_name,
                "total": len(results),
                "results": [
                    {
                        "id": r.id,
                        "taskId": r.task_id,
                        "batchName": r.batch_name,
                        "originalImage": r.original_image,
                        "resultImage": r.result_image,
                        "originalImageRel": r.original_image_rel,
                        "resultImageRel": r.result_image_rel,
                        "detections": r.detections,
                        "detectionCount": r.detection_count,
                        "avgConfidence": r.avg_confidence,
                        "severityLevel": r.severity_level,
                        "severityScore": r.severity_score,
                        "severityText": r.severity_text,
                        "severityColor": r.severity_color,
                        "imageWidth": r.image_width,
                        "imageHeight": r.image_height,
                        "processingTime": r.processing_time,
                        "createdAt": r.created_at.isoformat() if r.created_at else None
                    }
                    for r in results
                ]
            }
        }
    except Exception as e:
        print(f"❌ 获取批次结果失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")


@app.delete("/inference-results/{result_id}")
async def delete_inference_result(
    result_id: int,
    delete_files: bool = False,
    db: Session = Depends(get_db)
):
    """
    删除推理结果记录 - 支持 MinIO

    参数:
        result_id: 推理结果ID
        delete_files: 是否同时删除物理文件
    """
    try:
        result = db.query(InferenceResult).filter(InferenceResult.id == result_id).first()
        if not result:
            raise HTTPException(status_code=404, detail="推理结果不存在")

        # 如果需要删除物理文件 (从 MinIO)
        if delete_files and result.result_image and result.result_image.startswith("minio://"):
            parts = result.result_image.replace("minio://", "").split("/", 1)
            if len(parts) == 2:
                bucket_name, object_name = parts
                success = minio_client.delete_file(bucket_name, object_name)
                if success:
                    print(f"🗑️ 已从 MinIO 删除结果图片: {result.result_image}")
                else:
                    print(f"⚠️ MinIO 删除失败: {result.result_image}")

        # 删除数据库记录
        db.delete(result)
        db.commit()

        return {
            "code": 0,
            "message": "删除成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ 删除推理结果失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


class BatchDeleteRequest(BaseModel):
    """批量删除请求"""
    batch_names: List[str]  # 批次名称列表
    delete_files: bool = False  # 是否删除物理文件


@app.post("/inference-results/batch-delete")
async def batch_delete_inference_results(
    request: BatchDeleteRequest,
    db: Session = Depends(get_db)
):
    """
    批量删除推理结果（按批次）- 支持 MinIO

    参数:
        batch_names: 批次名称列表
        delete_files: 是否同时删除物理文件
    """
    try:
        deleted_count = 0
        deleted_files_count = 0
        failed_batches = []

        for batch_name in request.batch_names:
            try:
                # 查询该批次的所有推理结果
                results = db.query(InferenceResult).filter(
                    InferenceResult.batch_name == batch_name
                ).all()

                if not results:
                    failed_batches.append({
                        "batch_name": batch_name,
                        "reason": "批次不存在或已被删除"
                    })
                    continue

                # 如果需要删除物理文件
                if request.delete_files:
                    # 收集所有结果图片路径（去重）
                    result_images = set()
                    for result in results:
                        if result.result_image:
                            result_images.add(result.result_image)

                    # 从 MinIO 删除物理文件
                    for img_path in result_images:
                        try:
                            if img_path.startswith("minio://"):
                                # 解析 MinIO 路径
                                parts = img_path.replace("minio://", "").split("/", 1)
                                if len(parts) == 2:
                                    bucket_name, object_name = parts
                                    success = minio_client.delete_file(bucket_name, object_name)
                                    if success:
                                        deleted_files_count += 1
                                        print(f"🗑️ 已从 MinIO 删除: {img_path}")
                        except Exception as e:
                            print(f"⚠️ 删除文件失败 {img_path}: {e}")

                # 删除数据库记录
                batch_count = len(results)
                db.query(InferenceResult).filter(
                    InferenceResult.batch_name == batch_name
                ).delete()

                deleted_count += batch_count
                print(f"✅ 已删除批次 {batch_name}: {batch_count} 条记录")

            except Exception as e:
                failed_batches.append({
                    "batch_name": batch_name,
                    "reason": str(e)
                })
                print(f"❌ 删除批次 {batch_name} 失败: {e}")

        db.commit()

        return {
            "code": 0,
            "message": f"批量删除完成",
            "data": {
                "deleted_records": deleted_count,
                "deleted_files": deleted_files_count if request.delete_files else 0,
                "total_batches": len(request.batch_names),
                "failed_batches": failed_batches
            }
        }
    except Exception as e:
        db.rollback()
        print(f"❌ 批量删除失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"批量删除失败: {str(e)}")


# ============ 缺陷检测统计分析 ============
@app.get("/analytics/defect-statistics")
async def get_defect_statistics(db: Session = Depends(get_db)):
    """
    获取缺陷检测统计数据，用于分析页面
    返回:
    - 总检测次数
    - 总缺陷数量
    - 各等级缺陷数量
    - 各类别缺陷数量
    - 最近7天检测趋势
    """
    try:
        from sqlalchemy import func, cast, Float
        from datetime import datetime, timedelta
        import json

        # 1. 基础统计
        total_inspections = db.query(func.count(InferenceResult.id)).scalar() or 0
        total_defects = db.query(func.sum(InferenceResult.detection_count)).scalar() or 0
        avg_confidence = db.query(func.avg(InferenceResult.avg_confidence)).scalar() or 0

        # 2. 按严重程度等级统计
        severity_stats = db.query(
            InferenceResult.severity_level,
            InferenceResult.severity_text,
            func.count(InferenceResult.id).label('count'),
            func.sum(InferenceResult.detection_count).label('defect_count')
        ).filter(
            InferenceResult.severity_level.isnot(None)
        ).group_by(
            InferenceResult.severity_level,
            InferenceResult.severity_text
        ).order_by(
            InferenceResult.severity_level
        ).all()

        severity_distribution = []
        for stat in severity_stats:
            severity_distribution.append({
                "level": stat.severity_level,
                "text": stat.severity_text or f"等级{stat.severity_level}",
                "inspection_count": stat.count,
                "defect_count": stat.defect_count or 0
            })

        # 3. 按缺陷类别统计（从detections的JSONB字段中提取）
        # 获取所有包含检测结果的记录
        results_with_detections = db.query(InferenceResult.detections).filter(
            InferenceResult.detections.isnot(None),
            InferenceResult.detection_count > 0
        ).all()

        # 统计各类别数量
        class_counts = {}
        for result in results_with_detections:
            if result.detections:
                detections = result.detections if isinstance(result.detections, list) else json.loads(result.detections)
                for detection in detections:
                    class_name = detection.get('class', '未知')
                    class_counts[class_name] = class_counts.get(class_name, 0) + 1

        # 转换为列表并排序
        class_distribution = [
            {"class_name": k, "count": v}
            for k, v in sorted(class_counts.items(), key=lambda x: x[1], reverse=True)
        ]

        # 4. 最近7天检测趋势
        seven_days_ago = datetime.now() - timedelta(days=7)
        daily_stats = db.query(
            func.date(InferenceResult.created_at).label('date'),
            func.count(InferenceResult.id).label('inspection_count'),
            func.sum(InferenceResult.detection_count).label('defect_count')
        ).filter(
            InferenceResult.created_at >= seven_days_ago
        ).group_by(
            func.date(InferenceResult.created_at)
        ).order_by(
            func.date(InferenceResult.created_at)
        ).all()

        # 填充缺失的日期
        trends = []
        for i in range(7):
            date = (datetime.now() - timedelta(days=6-i)).date()
            stat = next((s for s in daily_stats if s.date == date), None)
            trends.append({
                "date": date.isoformat(),
                "inspection_count": stat.inspection_count if stat else 0,
                "defect_count": stat.defect_count if stat else 0
            })

        # 5. 按批次统计最近的检测任务
        recent_batches = db.query(
            InferenceResult.batch_name,
            func.count(InferenceResult.id).label('image_count'),
            func.sum(InferenceResult.detection_count).label('defect_count'),
            func.max(InferenceResult.created_at).label('latest_time')
        ).group_by(
            InferenceResult.batch_name
        ).order_by(
            func.max(InferenceResult.created_at).desc()
        ).limit(10).all()

        batch_stats = [
            {
                "batch_name": batch.batch_name,
                "image_count": batch.image_count,
                "defect_count": batch.defect_count or 0,
                "latest_time": batch.latest_time.isoformat() if batch.latest_time else None
            }
            for batch in recent_batches
        ]

        return {
            "code": 0,
            "data": {
                "overview": {
                    "total_inspections": int(total_inspections),
                    "total_defects": int(total_defects),
                    "avg_confidence": round(float(avg_confidence) * 100, 2) if avg_confidence else 0
                },
                "severity_distribution": severity_distribution,
                "class_distribution": class_distribution,
                "trends": trends,
                "recent_batches": batch_stats
            },
            "message": "统计数据获取成功"
        }
    except Exception as e:
        print(f"❌ 获取统计数据失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取统计数据失败: {str(e)}")


# ============ 访客统计分析 ============
from services.visitor_service import visitor_service

@app.get("/analytics/visitor-statistics")
async def get_visitor_statistics():
    """
    获取访客统计数据
    返回:
    - 总访问次数
    - 独立访客数
    - 今日访问
    - 本周访问
    - 按省份/城市统计
    - 地图数据
    - 每日趋势
    """
    try:
        stats = visitor_service.get_visit_statistics()
        return {
            "code": 0,
            "data": stats,
            "message": "访客统计数据获取成功"
        }
    except Exception as e:
        print(f"❌ 获取访客统计失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取访客统计失败: {str(e)}")


@app.get("/analytics/recent-visitors")
async def get_recent_visitors(limit: int = 50):
    """
    获取最近访客记录

    Args:
        limit: 返回数量,默认50
    """
    try:
        visitors = visitor_service.get_recent_visitors(limit)
        return {
            "code": 0,
            "data": visitors,
            "message": "最近访客记录获取成功"
        }
    except Exception as e:
        print(f"❌ 获取访客记录失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取访客记录失败: {str(e)}")


# ============ 文件访问路由 (MinIO 支持) ============

@app.get("/uploads/images/{file_path:path}")
async def get_image_file(file_path: str):
    """获取图片文件 - 从 MinIO 代理返回"""
    result = minio_client.get_file_stream(BUCKETS["images"], file_path)
    if not result:
        raise HTTPException(status_code=404, detail="图片不存在")
    response, content_type, content_length = result
    return StreamingResponse(
        response,
        media_type=content_type,
        headers={"Content-Length": str(content_length), "Cache-Control": "max-age=3600"}
    )


@app.get("/uploads/img_results/{file_path:path}")
async def get_inference_result_file(file_path: str):
    """获取推理结果图片 - 从 MinIO 代理返回"""
    print(f"\n📷 请求推理结果图片: {file_path}", flush=True)
    result = minio_client.get_file_stream(BUCKETS["img_results"], file_path)
    if not result:
        print(f"   ❌ 对象不存在: {file_path}", flush=True)
        raise HTTPException(status_code=404, detail="推理结果不存在")
    response, content_type, content_length = result
    print(f"   ✅ 代理返回成功", flush=True)
    return StreamingResponse(
        response,
        media_type=content_type,
        headers={"Content-Length": str(content_length), "Cache-Control": "max-age=3600"}
    )


@app.get("/uploads/videos/{file_path:path}")
async def get_video_file(file_path: str, request: Request):
    """获取视频文件 - 从 MinIO 代理返回，支持 Range 请求"""
    print(f"\n🎬 请求视频文件: {file_path}", flush=True)
    result = minio_client.get_file_stream(BUCKETS["videos"], file_path)
    if not result:
        print(f"   ❌ 视频不存在: {file_path}", flush=True)
        raise HTTPException(status_code=404, detail="视频不存在")
    response, content_type, content_length = result
    print(f"   ✅ 代理返回成功", flush=True)
    return StreamingResponse(
        response,
        media_type=content_type or "video/mp4",
        headers={"Content-Length": str(content_length), "Accept-Ranges": "bytes"}
    )


@app.get("/uploads/vid_results/{file_path:path}")
async def get_video_result_file(file_path: str):
    """获取视频推理结果 - 从 MinIO 代理返回"""
    print(f"\n🎥 请求推理结果视频: {file_path}", flush=True)
    result = minio_client.get_file_stream(BUCKETS["vid_results"], file_path)
    if not result:
        print(f"   ❌ 推理结果视频不存在: {file_path}", flush=True)
        raise HTTPException(status_code=404, detail="视频结果不存在")
    response, content_type, content_length = result
    print(f"   ✅ 代理返回成功", flush=True)
    return StreamingResponse(
        response,
        media_type=content_type or "video/mp4",
        headers={"Content-Length": str(content_length), "Accept-Ranges": "bytes"}
    )


if __name__ == "__main__":
    import uvicorn
    print("🚀 启动业务服务...")
    print("📍 访问地址: http://localhost:51032")
    print("📚 API 文档: http://localhost:51032/docs")
    uvicorn.run(app, host="0.0.0.0", port=51032)
