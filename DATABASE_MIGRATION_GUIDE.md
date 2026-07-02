# 数据库路径迁移指南

## 📋 问题说明

当前数据库中有**本地文件路径**，需要迁移为 **MinIO 路径格式**：

### 当前数据（需要修改）

```sql
-- models 表
id | name       | path
3  | best_ZZ.pt | G:\ShuangChuang\ShuangC\backend\uploads\model\ZZ\best.pt
5  | best_JC.pt | G:\ShuangChuang\ShuangC\backend\uploads\model\JC\best.pt

-- inference_results 表
original_image: G:\ShuangChuang\ShuangC\backend\uploads\images\test\img1.jpg
result_image:   G:\ShuangChuang\ShuangC\backend\uploads\img_results\batch_xxx\img1.jpg

-- video_tracking_tasks 表
original_video_path: G:\ShuangChuang\ShuangC\backend\uploads\videos\test.mp4
result_video_path:   G:\ShuangChuang\ShuangC\backend\uploads\vid_results\test_tracked.mp4
```

### 目标格式（MinIO 路径）

```sql
-- models 表
path: minio://models/ZZ/best.pt
path: minio://models/JC/best.pt

-- inference_results 表
original_image: minio://images/test/img1.jpg
result_image:   minio://img-results/batch_xxx/img1.jpg

-- video_tracking_tasks 表
original_video_path: minio://videos/test.mp4
result_video_path:   minio://vid-results/test_tracked.mp4
```

---

## ⚠️ 迁移前准备

### 1. 备份数据库

```bash
# PostgreSQL 备份
pg_dump -U postgres -d defect_detection > backup_$(date +%Y%m%d_%H%M%S).sql

# 或使用 pgAdmin 图形界面备份
```

### 2. 确认文件已迁移到 MinIO

访问 MinIO Console (http://localhost:9000)，确认以下 bucket 中有文件：

- ✅ `models` - 模型文件
- ✅ `images` - 原始图片
- ✅ `img-results` - 推理结果
- ✅ `videos` - 视频文件（如果有）
- ✅ `vid-results` - 视频结果（如果有）

### 3. 确认 MinIO 服务运行

```bash
# 访问 MinIO
http://localhost:9000
用户名: admin
密码: admin123456
```

---

## 🚀 执行迁移

### 方式 1: 使用自动迁移脚本（推荐）

```bash
# 1. 激活环境
cd G:\ShuangChuang\ShuangC\backend\business-service
conda activate backendJC

# 2. 执行迁移脚本
python migrate_paths_to_minio.py

# 3. 按提示确认
# 输入 yes 开始迁移
```

**脚本会自动：**
- ✅ 检测本地路径
- ✅ 转换为 MinIO 格式
- ✅ 更新数据库
- ✅ 显示迁移进度
- ✅ 错误自动回滚

---

### 方式 2: 手动 SQL 迁移

如果自动脚本失败，可以手动执行 SQL：

#### 1. 更新 models 表

```sql
-- 检测模型
UPDATE models
SET path = REPLACE(
    REPLACE(path, 'G:\ShuangChuang\ShuangC\backend\uploads\model\JC\', 'minio://models/JC/'),
    '\', '/'
)
WHERE path LIKE '%\model\JC\%';

-- 追踪模型
UPDATE models
SET path = REPLACE(
    REPLACE(path, 'G:\ShuangChuang\ShuangC\backend\uploads\model\ZZ\', 'minio://models/ZZ/'),
    '\', '/'
)
WHERE path LIKE '%\model\ZZ\%';

-- 验证
SELECT id, name, path FROM models;
```

#### 2. 更新 inference_results 表

```sql
-- 更新原图路径
UPDATE inference_results
SET original_image = 'minio://images/' ||
    REPLACE(
        SUBSTRING(original_image FROM POSITION('uploads\images\' IN original_image) + 15),
        '\', '/'
    )
WHERE original_image LIKE '%uploads\images\%'
  AND original_image NOT LIKE 'minio://%';

-- 更新结果图路径
UPDATE inference_results
SET result_image = 'minio://img-results/' ||
    REPLACE(
        SUBSTRING(result_image FROM POSITION('uploads\img_results\' IN result_image) + 19),
        '\', '/'
    )
WHERE result_image LIKE '%uploads\img_results\%'
  AND result_image NOT LIKE 'minio://%';

-- 验证
SELECT id, batch_name,
       LEFT(original_image, 50) as original,
       LEFT(result_image, 50) as result
FROM inference_results
LIMIT 5;
```

#### 3. 更新 video_tracking_tasks 表

```sql
-- 更新原视频路径
UPDATE video_tracking_tasks
SET original_video_path = 'minio://videos/' ||
    REPLACE(
        SUBSTRING(original_video_path FROM POSITION('uploads\videos\' IN original_video_path) + 15),
        '\', '/'
    )
WHERE original_video_path LIKE '%uploads\videos\%'
  AND original_video_path NOT LIKE 'minio://%';

-- 更新结果视频路径
UPDATE video_tracking_tasks
SET result_video_path = 'minio://vid-results/' ||
    REPLACE(
        SUBSTRING(result_video_path FROM POSITION('uploads\vid_results\' IN result_video_path) + 19),
        '\', '/'
    )
WHERE result_video_path LIKE '%uploads\vid_results\%'
  AND result_video_path NOT LIKE 'minio://%';

-- 验证
SELECT task_id,
       original_video_path,
       result_video_path
FROM video_tracking_tasks;
```

---

## ✅ 验证迁移结果

### 1. 检查数据库

```sql
-- 检查 models 表
SELECT * FROM models;
-- 所有 path 应该以 minio:// 开头

-- 检查 inference_results 表（最近10条）
SELECT id, batch_name, original_image, result_image
FROM inference_results
ORDER BY id DESC
LIMIT 10;
-- 所有路径应该以 minio:// 开头

-- 检查 video_tracking_tasks 表
SELECT * FROM video_tracking_tasks;
-- 所有路径应该以 minio:// 开头
```

### 2. 测试前端访问

1. **启动服务**
   ```bash
   # 终端 1
   cd G:\ShuangChuang\ShuangC\backend\business-service
   conda activate backendJC
   python main.py

   # 终端 2
   cd G:\ShuangChuang\ShuangC\backend\inference-service
   conda activate backendJC
   python main.py
   ```

2. **访问前端**
   - 查看图片列表
   - 点击图片应该能正常显示
   - 查看推理结果应该能正常显示

3. **检查日志**
   - 后端日志应该显示 MinIO 预签名 URL
   - 不应该有本地路径错误

---

## 🔄 回滚迁移

如果迁移出现问题，可以回滚：

### 方式 1: 从备份恢复

```bash
# 恢复数据库备份
psql -U postgres -d defect_detection < backup_20260216_123456.sql
```

### 方式 2: 手动恢复（如果记得原路径）

```sql
-- 示例：恢复 models 表
UPDATE models
SET path = 'G:\ShuangChuang\ShuangC\backend\uploads\model\JC\' ||
           REPLACE(SUBSTRING(path FROM POSITION('/JC/' IN path) + 4), '/', '\')
WHERE path LIKE 'minio://models/JC/%';
```

---

## 📊 迁移总结

### 需要迁移的表

| 表名 | 字段 | 记录数（你的数据库） | 状态 |
|------|------|---------------------|------|
| `models` | `path` | 2条 (best_ZZ.pt, best_JC.pt) | ⚠️ 需要迁移 |
| `inference_results` | `original_image`, `result_image` | 未知 | ⚠️ 需要迁移 |
| `video_tracking_tasks` | `original_video_path`, `result_video_path` | 未知 | ⚠️ 需要迁移 |

### 不需要迁移的表

| 表名 | 原因 |
|------|------|
| `image_database` | 目前未使用（接口直接从 MinIO 获取） |
| `inference_tasks` | 只存储任务元数据，无文件路径 |

---

## 🎯 迁移后的好处

### 1. 系统一致性
- ✅ 所有路径格式统一
- ✅ 代码逻辑简化
- ✅ 便于维护

### 2. 兼容性
- ✅ 新旧接口都能正常工作
- ✅ 前端无需修改
- ✅ 数据可追溯

### 3. 可扩展性
- ✅ 便于未来切换到云端 MinIO
- ✅ 便于数据备份和恢复
- ✅ 便于多节点部署

---

## ⚠️ 注意事项

### 1. 路径格式
- Windows 路径: `\` → MinIO: `/`
- 本地: `uploads\img_results\` → MinIO: `img-results/` (注意连字符)

### 2. 批量迁移
- 如果数据量大（>1000条），建议分批处理
- 可以先迁移最近的数据测试

### 3. 测试环境
- 建议先在测试环境执行
- 验证无误后再在生产环境执行

---

## 🚀 快速执行（推荐）

```bash
# 1. 备份数据库
pg_dump -U postgres -d defect_detection > backup.sql

# 2. 激活环境
conda activate backendJC

# 3. 执行迁移
cd G:\ShuangChuang\ShuangC\backend\business-service
python migrate_paths_to_minio.py

# 4. 验证结果
psql -U postgres -d defect_detection -c "SELECT * FROM models;"

# 5. 测试前端
# 启动服务并访问前端，确认功能正常
```

---

## 📞 如遇问题

如果迁移过程中遇到问题：

1. **查看错误日志**
2. **检查 MinIO 连接**
3. **验证数据备份**
4. **从备份恢复**
5. **联系开发人员**

---

**准备好执行迁移了吗？** 🚀
