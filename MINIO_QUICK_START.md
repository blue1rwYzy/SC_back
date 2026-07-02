# MinIO 集成快速启动指南

## 🎯 所有代码修改已完成！

所有 MinIO 集成代码已经完成，现在只需要启动服务即可使用。

## 📋 启动步骤

### 1. 确认 MinIO 正在运行

```powershell
# 检查 MinIO 是否在运行
# 浏览器访问: http://localhost:9000
# 用户名: admin
# 密码: admin123456
```

### 2. 激活后端环境并启动服务

#### 启动 business-service (端口 8000)

```bash
# 进入目录
cd G:\ShuangChuang\ShuangC\backend\business-service

# 激活 conda 环境
conda activate backendJC

# 启动服务
python main.py
```

#### 启动 inference-service (端口 8002)

**新开一个终端窗口**

```bash
# 进入目录
cd G:\ShuangChuang\ShuangC\backend\inference-service

# 激活 conda 环境
conda activate backendJC

# 启动服务
python main.py
```

### 3. 检查服务状态

- business-service: http://localhost:8000/docs
- inference-service: http://localhost:8002/docs

## 🧪 快速测试

### 测试 1: 图片上传

```bash
# 打开 http://localhost:8000/docs
# 找到 POST /images/upload 接口
# 上传一张图片，folder 填写 "test"
# 检查 MinIO Console (http://localhost:9000) 中 images bucket 是否有文件
```

### 测试 2: 图片访问

```bash
# 在浏览器中访问:
# http://localhost:8000/uploads/images/test/your_image.jpg
# 应该会重定向到 MinIO 预签名 URL
```

### 测试 3: 推理功能

```bash
# 1. 前端发起推理任务
# 2. 检查 MinIO Console 中 img-results bucket
# 3. 应该能看到推理结果图片自动上传
```

## ⚙️ 环境变量说明

### business-service/.env
```env
# MinIO 配置
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=admin123456
MINIO_SECURE=false

# 是否启用 MinIO (true/false)
USE_MINIO=true
```

### inference-service/.env
```env
# MinIO 配置 (与 business-service 相同)
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=admin123456
MINIO_SECURE=false

# 是否启用 MinIO (true/false)
USE_MINIO=true
```

## 🔄 切换存储模式

### 切换到本地存储
```bash
# 修改 .env 文件
USE_MINIO=false

# 重启服务
```

### 切换回 MinIO
```bash
# 修改 .env 文件
USE_MINIO=true

# 重启服务
```

## 📊 已修改的接口列表

### business-service (13个接口)
1. `POST /images/upload` - 图片上传
2. `POST /images/upload-zip` - ZIP 批量上传
3. `DELETE /images/file` - 图片删除
4. `POST /images/batch-delete-files` - 批量删除
5. `GET /uploads/images/{file_path:path}` - 图片访问 ⭐新增
6. `GET /uploads/img_results/{file_path:path}` - 推理结果访问 ⭐新增
7. `GET /uploads/videos/{file_path:path}` - 视频访问 ⭐新增
8. `GET /uploads/vid_results/{file_path:path}` - 视频结果访问 ⭐新增
9. `POST /models` - 模型上传
10. `DELETE /models/{model_id}` - 模型删除
11. `DELETE /inference-results/{result_id}` - 删除推理结果
12. `POST /inference-results/batch-delete` - 批量删除推理结果
13. `app.mount("/uploads", ...)` - 静态文件挂载 (条件挂载)

### inference-service (1个核心逻辑)
1. 推理结果保存逻辑 - 自动上传到 MinIO

## ⚠️ 重要提示

### 路径格式
- **MinIO 路径**: `minio://bucket-name/path/to/file`
- **本地路径**: `G:\ShuangChuang\ShuangC\backend\uploads\...`

### Bucket 命名
- 本地 `img_results` → MinIO `img-results` (下划线变连字符)
- 本地 `vid_results` → MinIO `vid-results` (下划线变连字符)

### 预签名 URL 有效期
- 图片: 1 小时
- 视频: 2 小时
- 上传返回: 7 天

## 🐛 常见问题

### Q1: 启动时报错 "No module named 'utils'"
**A**: 确认已复制 utils 和 config 文件夹到 inference-service

### Q2: MinIO 连接失败
**A**: 检查 MinIO 是否启动，检查 .env 配置

### Q3: 图片无法访问
**A**: 检查 USE_MINIO 配置，检查 bucket 是否存在

### Q4: 推理结果没有上传到 MinIO
**A**: 检查 inference-service 的 .env 文件是否正确配置

## 📚 详细文档

- 完整修改报告: `business-service/MINIO_INTEGRATION_COMPLETE.md`
- MinIO 客户端代码: `business-service/utils/minio_client.py`
- 配置文件: `business-service/config/minio_config.py`

## ✅ 检查清单

启动前确认：
- [ ] MinIO 服务运行中 (localhost:9000)
- [ ] 所有 bucket 已创建 (models, images, img-results, videos, vid-results)
- [ ] .env 文件已配置在两个服务中
- [ ] utils 和 config 已复制到 inference-service
- [ ] conda 环境 backendJC 已激活
- [ ] 依赖已安装 (python-dotenv, minio)

## 🚀 开始测试！

现在可以启动服务并开始测试了。所有代码修改已经完成，只需要：

1. 启动 MinIO (如果还没启动)
2. 启动 business-service
3. 启动 inference-service
4. 运行测试用例

祝测试顺利！🎉
