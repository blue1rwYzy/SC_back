# 🚀 快速上手指南

## 📋 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      当前阶段 (Phase 1)                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  前端 (Vue 3 + Vben Admin)                                 │
│  http://localhost:5173                                     │
│                    │                                        │
│                    ↓                                        │
│  ┌─────────────────────────────────────┐                  │
│  │  Python FastAPI 微服务               │                  │
│  ├─────────────────────────────────────┤                  │
│  │  • 业务服务 (8001)                   │                  │
│  │    - 模型管理                        │                  │
│  │    - 图片库管理                      │                  │
│  │    - 任务管理                        │                  │
│  │                                      │                  │
│  │  • 推理服务 (8002)                   │                  │
│  │    - YOLO 模型推理                   │                  │
│  │    - 图片处理                        │                  │
│  │    - 批量任务                        │                  │
│  └─────────────────────────────────────┘                  │
│                    │                                        │
│                    ↓                                        │
│  PostgreSQL (5432) + 本地文件系统                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      后续阶段 (Phase 2)                      │
├─────────────────────────────────────────────────────────────┤
│  将添加 Spring Boot 服务:                                    │
│  • 用户认证授权 (JWT)                                        │
│  • 权限管理 (RBAC)                                           │
│  • 系统日志                                                  │
│  • 统计报表                                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 第一步：安装 Python 依赖

### 1. 进入后端目录
```bash
cd G:\ShuangChuang\ShuangC\backend
```

### 2. 安装依赖（双击运行）
```bash
install_dependencies.bat
```

**或者手动安装：**
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**预计时间：** 5-10 分钟（取决于网络速度）

---

## 🗄️ 第二步：初始化数据库

### 1. 确保 PostgreSQL 正在运行
- 端口：5432
- 用户：postgres
- 密码：mm

### 2. 运行初始化脚本（双击运行）
```bash
cd config
init_database.bat
```

**或者手动执行：**
```bash
cd config
set PGPASSWORD=mm
"G:\ShuangChuang\ShuangC\postgresql\bin\psql.exe" -U postgres -h localhost -p 5432 -f database_init.sql
```

**期望输出：**
```
CREATE DATABASE
\c defect_detection
CREATE TABLE
CREATE TABLE
CREATE TABLE
CREATE TABLE
INSERT 0 1
INSERT 0 3
Database initialization completed successfully!
```

---

## 🧪 第三步：测试环境

### 运行测试脚本
```bash
python test_connection.py
```

**期望输出：**
```
==================================================
测试数据库连接
==================================================
✅ 数据库连接成功！
✅ 查询成功！共有 1 个模型
   - best.pt (v2.0)

==================================================
测试 YOLO 模型
==================================================
📦 加载模型: G:\ShuangChuang\ShuangC\ultralytics-main\runs\detect\train4_highrpd_v2\weights\best.pt
✅ 模型加载成功！
   - 模型类型: <class 'ultralytics.models.yolo.detect.detect.DetectionModel'>
   - 类别数量: X
   - 类别列表: [...]

==================================================
测试目录结构
==================================================
✅ 上传目录: G:\ShuangChuang\ShuangC\backend\uploads
✅ 图片目录: G:\ShuangChuang\ShuangC\backend\uploads\images
✅ 结果目录: G:\ShuangChuang\ShuangC\backend\uploads\results

==================================================
检测结果
==================================================
数据库连接: ✅ 通过
YOLO 模型: ✅ 通过
目录结构: ✅ 通过

🎉 所有检测通过！系统可以正常运行
```

---

## 🚀 第四步：启动后端服务

### 方式 1：一键启动（推荐）
双击运行：
```bash
start_all.bat
```

会打开两个窗口：
- **窗口 1:** 业务服务 (端口 8001)
- **窗口 2:** 推理服务 (端口 8002)

### 方式 2：手动启动
```bash
# 终端 1: 业务服务
cd business-service
python main.py

# 终端 2: 推理服务
cd inference-service
python main.py
```

**期望输出：**
```
业务服务:
🚀 启动业务服务...
📍 访问地址: http://localhost:8001
📚 API 文档: http://localhost:8001/docs
INFO:     Uvicorn running on http://0.0.0.0:8001

推理服务:
🚀 启动推理服务...
📍 访问地址: http://localhost:8002
📚 API 文档: http://localhost:8002/docs
INFO:     Uvicorn running on http://0.0.0.0:8002
```

---

## 🌐 第五步：验证服务

### 1. 访问 API 文档
打开浏览器：
- **业务服务文档:** http://localhost:8001/docs
- **推理服务文档:** http://localhost:8002/docs

### 2. 测试获取模型列表
打开浏览器：http://localhost:8001/models

**期望返回：**
```json
[
  {
    "id": 1,
    "name": "best.pt",
    "path": "G:\\ShuangChuang\\ShuangC\\ultralytics-main\\runs\\detect\\train4_highrpd_v2\\weights\\best.pt",
    "version": "v2.0",
    "description": "高速公路缺陷检测模型 - 最佳权重",
    "model_type": "detection",
    "is_active": true,
    "created_at": "2024-02-07T...",
    "updated_at": "2024-02-07T..."
  }
]
```

### 3. 测试图片库
http://localhost:8001/images/database

### 4. 测试健康检查
- http://localhost:8001/health
- http://localhost:8002/health

---

## 🖥️ 第六步：启动前端

### 1. 启动 Mock 后端（可选，用于其他功能）
```bash
cd G:\ShuangChuang\ShuangC\UI\vue-vben-admin-main\apps\backend-mock
pnpm dev
```

### 2. 启动前端
```bash
cd G:\ShuangChuang\ShuangC\UI\vue-vben-admin-main\apps\web-antd
pnpm dev
```

### 3. 访问系统
打开浏览器：http://localhost:5173

**登录信息：**
- 用户名：`vben`
- 密码：`123456`

---

## 🎨 第七步：测试缺陷检测功能

### 1. 进入功能页面
登录后，点击左侧菜单：
```
系统管理 → 路面缺陷检测推理
```

### 2. 测试单张图片推理
1. **选择模型：** best.pt (v2.0)
2. **点击"上传单张图片"**
3. **选择一张图片**（从数据集或本地）
4. **点击"开始推理"**
5. **等待 2-5 秒**
6. **查看结果：**
   - 推理后的图片（带检测框）
   - 检测详情表格
   - 置信度和严重程度

### 3. 测试数据库图片推理
1. **点击"从图片库选择"**
2. **浏览文件夹**
3. **勾选 2-3 张图片**
4. **点击"确定"**
5. **点击"开始推理"**
6. **等待任务完成**
7. **查看结果并翻页**

### 4. 测试批量推理
1. **准备一个包含多张图片的 ZIP 文件**
2. **点击"上传文件夹压缩包"**
3. **选择 ZIP 文件**
4. **点击"开始推理"**
5. **系统会每 5 秒轮询任务状态**
6. **任务完成后显示所有结果**
7. **点击"下载结果"下载压缩包**

---

## 📊 完整的系统测试流程

### 测试场景 1：单张图片快速检测
```
目的：验证模型推理功能
步骤：
1. 上传测试图片
2. 立即获得推理结果
3. 查看检测框和置信度
预期时间：2-5 秒
```

### 测试场景 2：批量图片处理
```
目的：验证异步任务处理
步骤：
1. 上传包含 10 张图片的 ZIP
2. 创建后台任务
3. 轮询任务进度
4. 查看所有结果
5. 下载结果压缩包
预期时间：30-60 秒
```

### 测试场景 3：数据库图片管理
```
目的：验证图片库功能
步骤：
1. 浏览图片库
2. 选择已有图片
3. 直接推理
4. 无需重复上传
预期时间：即时
```

---

## 🔍 API 调用示例

### 使用 curl 测试

#### 1. 获取模型列表
```bash
curl http://localhost:8001/models
```

#### 2. 单张图片推理
```bash
curl -X POST "http://localhost:8002/inference/single" \
  -F "model_id=1" \
  -F "image=@G:\ShuangChuang\ShuangC\backend\uploads\images\test_001.jpg"
```

#### 3. 获取图片库
```bash
curl http://localhost:8001/images/database
```

#### 4. 获取任务列表
```bash
curl http://localhost:8001/tasks
```

### 使用 Python 测试
```python
import requests

# 1. 获取模型
response = requests.get("http://localhost:8001/models")
models = response.json()
print(f"共有 {len(models)} 个模型")

# 2. 上传图片推理
with open("test.jpg", "rb") as f:
    files = {"image": f}
    data = {"model_id": 1}
    response = requests.post(
        "http://localhost:8002/inference/single",
        files=files,
        data=data
    )
    result = response.json()
    print(f"检测到 {len(result['data']['detections'])} 个目标")
```

---

## 📁 项目文件快速导航

### 后端代码
```
G:\ShuangChuang\ShuangC\backend\
├── business-service\main.py      # 业务服务入口
├── inference-service\main.py     # 推理服务入口
├── shared\                        # 共享模块
│   ├── database.py               # 数据库连接
│   ├── models.py                 # ORM 模型
│   └── schemas.py                # 数据验证
└── config\database_init.sql      # 数据库初始化
```

### 前端代码
```
G:\ShuangChuang\ShuangC\UI\vue-vben-admin-main\apps\web-antd\
├── src\router\routes\modules\system.ts                    # 路由配置
├── src\views\system\defect-detection\index.vue            # 主页面
├── src\views\system\defect-detection\components\
│   └── ImageDatabaseModal.vue                             # 图片库选择器
└── src\api\system\defect-detection.ts                     # API 接口
```

### 数据存储
```
G:\ShuangChuang\ShuangC\backend\uploads\
├── images\        # 上传的原始图片
├── results\       # 推理结果图片
│   ├── task_xxx\  # 批量任务结果
│   └── task_xxx.zip  # 结果压缩包
└── videos\        # 视频文件（预留）
```

---

## 🐛 常见问题排查

### 问题 1: 依赖安装失败
```
错误: ERROR: Could not find a version that satisfies the requirement...
```

**解决：**
```bash
# 使用清华源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或者升级 pip
python -m pip install --upgrade pip
```

### 问题 2: 数据库连接失败
```
错误: could not connect to server
```

**检查清单：**
- [ ] PostgreSQL 是否运行？
- [ ] 端口 5432 是否正确？
- [ ] 密码是否为 `mm`？
- [ ] 防火墙是否阻止？

**解决：**
修改 `shared/database.py` 中的连接字符串

### 问题 3: 模型加载失败
```
错误: FileNotFoundError: best.pt
```

**解决：**
1. 检查模型路径是否正确
2. 更新数据库中的模型路径：
```sql
UPDATE models SET path = '新的路径' WHERE id = 1;
```

### 问题 4: 端口被占用
```
错误: [Errno 10048] Only one usage of each socket address
```

**解决：**
```bash
# 查找占用端口的进程
netstat -ano | findstr :8001

# 杀死进程（替换 <PID>）
taskkill /PID <PID> /F
```

### 问题 5: 前端无法连接后端
```
错误: CORS Error / Network Error
```

**检查清单：**
- [ ] 后端服务是否启动？
- [ ] API 地址是否正确？
- [ ] 浏览器控制台有什么错误？

**解决：**
1. 确认后端运行在 8001/8002 端口
2. 检查前端 `.env.development` 配置
3. 查看浏览器控制台的具体错误

---

## 📊 性能优化建议

### 1. GPU 加速
如果有 NVIDIA GPU：
```bash
# 安装 CUDA 版本的 PyTorch
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

推理速度可提升 5-10 倍！

### 2. 模型预热
启动后首次推理会较慢（加载模型），后续推理会很快（模型已缓存）。

### 3. 批量推理优化
对于大量图片，使用批量推理接口比单张推理快得多。

---

## 🎯 下一步计划

### Phase 1: 当前功能（已完成 ✅）
- [x] 路面缺陷检测推理
- [x] 图片管理
- [x] 任务管理
- [x] 结果下载

### Phase 2: 视频追踪功能（待开发）
- [ ] 实时视频流接入
- [ ] 车辆目标追踪
- [ ] 轨迹绘制
- [ ] 视频结果导出

### Phase 3: Spring Boot 服务（待开发）
- [ ] 用户认证授权 (JWT)
- [ ] 角色权限管理 (RBAC)
- [ ] 系统日志
- [ ] 统计报表
- [ ] 告警系统

---

## 📞 技术支持

### 文档
- 后端详细文档: `README.md`
- 前后端集成: `FRONTEND_INTEGRATION.md`
- 数据库脚本: `config/database_init.sql`

### 日志
- 业务服务日志: 终端输出
- 推理服务日志: 终端输出
- 数据库日志: PostgreSQL 日志目录

### 调试
- API 文档: http://localhost:8001/docs
- Swagger UI: 可直接测试所有接口

---

## ✅ 检查清单

启动前请确认：

- [ ] Python 3.8+ 已安装
- [ ] PostgreSQL 正在运行（端口 5432）
- [ ] 依赖已安装 (`pip list`)
- [ ] 数据库已初始化（可以连接）
- [ ] 模型文件存在
- [ ] 目录结构正确

启动后请确认：

- [ ] 业务服务运行在 8001 端口
- [ ] 推理服务运行在 8002 端口
- [ ] 可以访问 API 文档
- [ ] 模型列表 API 返回正常
- [ ] 前端可以连接后端

---

**准备好了吗？现在就开始测试吧！** 🚀

如有任何问题，随时查看文档或询问我！
