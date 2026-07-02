# 高速公路缺陷检测系统 - 后端微服务

## 📋 项目概述

基于微服务架构的高速公路缺陷检测系统后端，支持 YOLO 模型推理、图片管理、任务调度等功能。

### 技术栈
- **Python 3.8+**
- **FastAPI** - Web 框架
- **PostgreSQL** - 数据库
- **Ultralytics YOLO** - 深度学习模型
- **Nginx** - API 网关（可选）

### 微服务架构
```
┌─────────────────────────────────────────────────┐
│          Nginx API 网关 (8000)                  │
└──────────┬──────────────────┬───────────────────┘
           │                  │
    ┌──────▼──────┐    ┌──────▼──────┐
    │ 业务服务     │    │ 推理服务     │
    │ (8001)      │    │ (8002)      │
    └──────┬──────┘    └──────┬──────┘
           │                  │
           └────────┬─────────┘
                    │
         ┌──────────▼───────────┐
         │  PostgreSQL (5432)  │
         └─────────────────────┘
```

---

## 🚀 快速开始

### 环境要求
- Python 3.8 或更高版本
- PostgreSQL 数据库
- CUDA（如果使用 GPU）

### 安装步骤

#### 1. 安装 Python 依赖
```bash
# 双击运行
install_dependencies.bat

# 或者手动安装
pip install -r requirements.txt
```

#### 2. 初始化数据库
```bash
# 双击运行
cd config
init_database.bat

# 或者手动执行
psql -U postgres -h localhost -p 5432 -f database_init.sql
```

**数据库配置：**
- 主机: localhost
- 端口: 5432
- 用户: postgres
- 密码: mm
- 数据库: defect_detection

#### 3. 测试环境
```bash
python test_connection.py
```

应该看到：
```
✅ 数据库连接成功！
✅ YOLO 模型加载成功！
✅ 所有检测通过！
```

#### 4. 启动服务
```bash
# 双击运行（启动所有服务）
start_all.bat

# 或者手动启动
# 终端 1: 业务服务
cd business-service
python main.py

# 终端 2: 推理服务
cd inference-service
python main.py
```

#### 5. 验证服务
访问以下地址：
- 业务服务: http://localhost:8001/docs
- 推理服务: http://localhost:8002/docs
- API 网关: http://localhost:8000 (需要 Nginx)

---

## 📁 目录结构

```
backend/
├── business-service/          # 业务服务
│   └── main.py               # 主入口
├── inference-service/         # 推理服务
│   ├── main.py               # 主入口
│   └── yolo_inference.py     # YOLO 推理引擎
├── shared/                    # 共享模块
│   ├── database.py           # 数据库连接
│   ├── models.py             # ORM 模型
│   └── schemas.py            # Pydantic 模型
├── config/                    # 配置文件
│   ├── database_init.sql     # 数据库初始化脚本
│   └── init_database.bat     # 初始化脚本
├── nginx/                     # Nginx 配置
│   └── nginx.conf            # API 网关配置
├── uploads/                   # 文件存储
│   ├── images/               # 原始图片
│   ├── results/              # 推理结果
│   └── videos/               # 视频文件（预留）
├── requirements.txt           # Python 依赖
├── install_dependencies.bat   # 安装脚本
├── start_all.bat             # 启动脚本
├── test_connection.py        # 测试脚本
└── README.md                 # 本文件
```

---

## 🔧 服务详细说明

### 业务服务 (8001)

**负责：** 模型管理、图片库管理、任务管理

**API 端点：**
- `GET /models` - 获取模型列表
- `GET /models/{id}` - 获取模型详情
- `GET /images/database` - 获取图片库
- `POST /images/upload` - 上传图片
- `GET /tasks` - 获取任务列表
- `GET /tasks/{id}` - 获取任务详情

### 推理服务 (8002)

**负责：** YOLO 模型推理、图片处理

**API 端点：**
- `POST /inference/single` - 单张图片推理
- `POST /inference/batch` - 批量图片推理
- `POST /inference/from-database` - 数据库图片推理
- `GET /inference/results/{task_id}` - 获取推理结果
- `GET /inference/download/{task_id}` - 下载结果压缩包

---

## 📊 数据库表结构

### models - 模型管理
```sql
id, name, path, version, description, model_type, is_active, created_at, updated_at
```

### image_database - 图片库
```sql
id, filename, path, url, folder, size, mime_type, width, height, is_folder, uploaded_at
```

### inference_tasks - 推理任务
```sql
id, task_id, model_id, image_count, status, source_type, result_path, error_message, progress, created_at, started_at, completed_at
```

### inference_results - 推理结果
```sql
id, task_id, original_image, result_image, detections(JSONB), confidence, processing_time, created_at
```

---

## 🧪 API 测试示例

### 1. 获取模型列表
```bash
curl http://localhost:8001/models
```

### 2. 单张图片推理
```bash
curl -X POST "http://localhost:8002/inference/single" \
  -F "model_id=1" \
  -F "image=@test.jpg"
```

### 3. 批量推理
```bash
curl -X POST "http://localhost:8002/inference/batch" \
  -F "model_id=1" \
  -F "archive=@images.zip"
```

### 4. 获取任务状态
```bash
curl http://localhost:8001/tasks/{task_id}
```

### 5. 获取推理结果
```bash
curl http://localhost:8002/inference/results/{task_id}
```

---

## 🔍 故障排查

### 问题 1: 数据库连接失败
**错误：** `could not connect to server`

**解决：**
1. 检查 PostgreSQL 是否运行
2. 检查端口 5432 是否开放
3. 检查密码是否正确（默认：mm）
4. 修改 `shared/database.py` 中的连接字符串

### 问题 2: YOLO 模型加载失败
**错误：** `FileNotFoundError: best.pt`

**解决：**
1. 检查模型路径是否正确
2. 确认模型文件存在
3. 更新数据库中的模型路径

### 问题 3: 推理服务启动失败
**错误：** `ModuleNotFoundError: No module named 'ultralytics'`

**解决：**
```bash
pip install ultralytics torch torchvision opencv-python
```

### 问题 4: 端口被占用
**错误：** `[Errno 10048] Only one usage of each socket address`

**解决：**
```bash
# 查找占用端口的进程
netstat -ano | findstr :8001

# 杀死进程
taskkill /PID <进程ID> /F
```

---

## 🌐 Nginx 配置（可选）

如果使用 Nginx 作为 API 网关：

### 1. 安装 Nginx
下载: http://nginx.org/en/download.html

### 2. 替换配置文件
将 `nginx/nginx.conf` 复制到 Nginx 安装目录的 `conf` 文件夹

### 3. 启动 Nginx
```bash
cd <nginx安装目录>
nginx.exe
```

### 4. 访问
http://localhost:8000

### 5. 重载配置
```bash
nginx.exe -s reload
```

---

## 📈 性能优化

### GPU 加速
如果有 NVIDIA GPU，安装 CUDA 版本的 PyTorch：
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### 模型缓存
推理服务会自动缓存已加载的模型，无需重复加载。

### 批量推理
对于大量图片，使用批量推理接口可以显著提高效率。

---

## 🔐 安全建议

1. **修改数据库密码**
   - 修改 PostgreSQL 密码
   - 更新 `shared/database.py` 中的连接字符串

2. **添加认证**
   - 使用 JWT Token
   - 限制 API 访问权限

3. **文件上传限制**
   - 限制文件大小
   - 验证文件类型
   - 防止路径遍历

---

## 🚀 部署到生产环境

### 1. 使用 Gunicorn (Linux)
```bash
gunicorn business-service.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

### 2. 使用 Supervisor 守护进程
```ini
[program:business-service]
command=python main.py
directory=/path/to/business-service
autostart=true
autorestart=true
```

### 3. 使用 Docker
```bash
# 构建镜像
docker build -t defect-detection-backend .

# 运行容器
docker-compose up -d
```

---

## 📞 技术支持

- 项目文档: `DEFECT_DETECTION_README.md`
- 前端文档: `QUICK_START.md`
- 数据库脚本: `config/database_init.sql`

---

**开发日期:** 2024-02-07
**版本:** v1.0.0
**技术栈:** Python + FastAPI + PostgreSQL + YOLO
