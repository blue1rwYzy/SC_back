# MinIO 集成任务清单

## ✅ 已完成的任务

### 1. 基础设施
- [x] 创建 `utils/minio_client.py` - MinIO 客户端工具类
- [x] 创建 `config/minio_config.py` - MinIO 配置文件
- [x] 创建 `.env` - 环境变量配置
- [x] 修改 `main.py` - 添加 MinIO 导入和初始化

### 2. business-service 接口修改
- [x] 修改 `/images/upload` - 图片上传接口支持 MinIO

## 🔄 待完成的任务

### 3. business-service 继续修改

#### A. 图片相关接口
- [ ] `/images/upload-zip` - ZIP 批量上传
- [ ] `/images/{id}` - 图片查看/下载 (GET)
- [ ] `/images/{id}` - 图片删除 (DELETE)
- [ ] `/images/folder/{folder:path}` - 获取文件夹下的图片

#### B. 模型相关接口
- [ ] `/models` - 模型上传 (POST)
- [ ] `/models/{model_id}` - 模型下载 (GET)
- [ ] `/models/{model_id}` - 模型删除 (DELETE)

#### C. 视频相关接口
- [ ] `/api/videos/upload` - 视频上传
- [ ] `/uploads/videos/{filename:path}` - 视频访问
- [ ] 视频删除逻辑

#### D. 推理结果相关接口
- [ ] `/check-image-inference-result/{image_id}` - 查看推理结果
- [ ] `/delete-inference-result/{result_id}` - 删除推理结果
- [ ] `/batch-delete-inference-results` - 批量删除
- [ ] `/uploads/vid_results/{filename:path}` - 视频推理结果访问

### 4. inference-service 修改

#### A. 推理结果保存
- [ ] 修改 `run_inference` 函数 - 保存结果到 MinIO
- [ ] 修改 `yolo_inference_script.py` - 使用 MinIO 路径
- [ ] 更新 `IMG_RESULTS_DIR` 逻辑

### 5. 共享模块修改

#### A. 数据库模型
- [ ] 更新 `ImageDatabase` 模型 - 添加 `storage_type` 字段
- [ ] 更新 `InferenceResult` 模型 - 支持 MinIO 路径
- [ ] 更新 `VideoTrackingTask` 模型 - 支持 MinIO 路径

### 6. 前端适配 (可选)
- [ ] 更新前端 API 调用,处理预签名 URL
- [ ] 图片显示组件支持 MinIO URL

### 7. 测试验证
- [ ] 测试图片上传
- [ ] 测试图片查看
- [ ] 测试图片删除
- [ ] 测试推理功能
- [ ] 测试视频上传和追踪
- [ ] 性能测试

## 📝 关键注意事项

### 路径映射规则
本地目录 → MinIO Bucket:
- `uploads/images/` → `images/`
- `uploads/img_results/` → `img-results/` ⚠️ (注意连字符)
- `uploads/videos/` → `videos/`
- `uploads/vid_results/` → `vid-results/` ⚠️ (注意连字符)

### 代码修改模式

每个接口需要:
1. 检查 `USE_MINIO` 标志
2. MinIO 分支:
   - 上传: `minio_client.upload_file()` → 返回预签名 URL
   - 查看: `minio_client.get_presigned_url()` → 重定向
   - 删除: `minio_client.delete_file()`
3. 本地磁盘分支 (保持向后兼容)

### 预签名 URL 有效期
- 图片查看: 1 小时
- 上传返回: 7 天
- 视频播放: 2 小时

## 🚀 快速继续

要继续完成剩余任务,请告诉我:
1. 一次完成所有接口修改
2. 分步完成 (先图片,再视频,最后推理)
3. 只修改核心功能 (图片上传/查看/删除)

推荐选择: **选项 1 - 一次完成**,确保系统完整性。
