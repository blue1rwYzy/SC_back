# 数据库路径迁移 - 预期结果示例

根据您提供的实际数据，以下是迁移脚本的预期转换结果：

---

## 1. Models 表 (2条记录)

### 迁移前

```
ID | Name       | Path
3  | best_ZZ.pt | G:\ShuangChuang\ShuangC\backend\uploads\model\ZZ\best.pt
5  | best_JC.pt | G:\ShuangChuang\ShuangC\backend\uploads\model\JC\best.pt
```

### 迁移后 ✅

```
ID | Name       | Path
3  | best_ZZ.pt | minio://models/ZZ/best.pt
5  | best_JC.pt | minio://models/JC/best.pt
```

**变化说明**:
- 移除: `G:\ShuangChuang\ShuangC\backend\uploads\model\`
- 添加: `minio://models/`
- 保留: `ZZ/best.pt` 或 `JC/best.pt`

---

## 2. InferenceResults 表 (示例记录 ID 439)

### 迁移前

```
ID: 439
task_id: 08dde969-116b-4677-93bd-9dd32b69f885
batch_name: predict0

original_image:
  G:\ShuangChuang\ShuangC\backend\uploads\images\test\lr_00022_bottom_left.jpg

result_image:
  G:\ShuangChuang\ShuangC\backend\uploads\img_results\predict0\lr_00022_bottom_left.jpg

original_image_rel: images/test/lr_00022_bottom_left.jpg
result_image_rel: img_results/predict0/lr_00022_bottom_left.jpg
```

### 迁移后 ✅

```
ID: 439
task_id: 08dde969-116b-4677-93bd-9dd32b69f885
batch_name: predict0

original_image:
  minio://images/test/lr_00022_bottom_left.jpg

result_image:
  minio://img-results/predict0/lr_00022_bottom_left.jpg

original_image_rel: images/test/lr_00022_bottom_left.jpg  (保持不变)
result_image_rel: img_results/predict0/lr_00022_bottom_left.jpg  (保持不变)
```

**变化说明**:

**original_image**:
- 移除: `G:\ShuangChuang\ShuangC\backend\uploads\images\`
- 添加: `minio://images/`
- 保留: `test/lr_00022_bottom_left.jpg`

**result_image**:
- 移除: `G:\ShuangChuang\ShuangC\backend\uploads\img_results\`
- 添加: `minio://img-results/` ⚠️ 注意连字符
- 保留: `predict0/lr_00022_bottom_left.jpg`

**relative 字段**:
- `original_image_rel` 和 `result_image_rel` **保持不变**
- 这些字段已经是相对路径格式

---

## 3. InferenceResults 表 (示例记录 ID 464)

### 迁移前

```
ID: 464
task_id: 2176ebcd-e92e-431f-baaa-6b9399bd075e
batch_name: predict2

original_image:
  G:\ShuangChuang\ShuangC\backend\uploads\images\test3\r180_00405_bottom_right.jpg

result_image:
  G:\ShuangChuang\ShuangC\backend\uploads\img_results\predict2\r180_00405_bottom_right.jpg
```

### 迁移后 ✅

```
ID: 464
task_id: 2176ebcd-e92e-431f-baaa-6b9399bd075e
batch_name: predict2

original_image:
  minio://images/test3/r180_00405_bottom_right.jpg

result_image:
  minio://img-results/predict2/r180_00405_bottom_right.jpg
```

---

## 4. VideoTrackingTasks 表 (记录 ID 1)

### 迁移前

```
ID: 1
task_id: 45dee3a1-1258-4040-83be-6954c54f0e21
model_id: 3

original_video_path:
  G:\ShuangChuang\ShuangC\backend\uploads\videos\M0206.mp4

original_video_name: M0206.mp4

original_video_relative_path: videos\M0206.mp4

result_video_path:
  G:\ShuangChuang\ShuangC\backend\uploads\vid_results\tracked_M0206.mp4

result_video_name: tracked_M0206.mp4

result_video_relative_path: vid_results/tracked_M0206.mp4
```

### 迁移后 ✅

```
ID: 1
task_id: 45dee3a1-1258-4040-83be-6954c54f0e21
model_id: 3

original_video_path:
  minio://videos/M0206.mp4

original_video_name: M0206.mp4  (保持不变)

original_video_relative_path: videos/M0206.mp4  (统一为 /)

result_video_path:
  minio://vid-results/tracked_M0206.mp4  ⚠️ 注意连字符

result_video_name: tracked_M0206.mp4  (保持不变)

result_video_relative_path: vid_results/tracked_M0206.mp4  (保持不变)
```

**变化说明**:

**original_video_path**:
- 移除: `G:\ShuangChuang\ShuangC\backend\uploads\videos\`
- 添加: `minio://videos/`
- 保留: `M0206.mp4`

**result_video_path**:
- 移除: `G:\ShuangChuang\ShuangC\backend\uploads\vid_results\`
- 添加: `minio://vid-results/` ⚠️ 注意连字符
- 保留: `tracked_M0206.mp4`

**relative_path 字段**:
- `original_video_relative_path`: `videos\M0206.mp4` → `videos/M0206.mp4` (统一分隔符)
- `result_video_relative_path`: 保持 `vid_results/tracked_M0206.mp4`

---

## 5. VideoTrackingTasks 表 (记录 ID 2)

### 迁移前

```
ID: 2
task_id: 40d57833-80a1-41c3-b6ac-0034632fe184

original_video_path:
  G:\ShuangChuang\ShuangC\backend\uploads\videos\test1\M1303.mp4

original_video_relative_path: videos\test1\M1303.mp4

result_video_path:
  G:\ShuangChuang\ShuangC\backend\uploads\vid_results\tracked_M1303.mp4

result_video_relative_path: vid_results/tracked_M1303.mp4
```

### 迁移后 ✅

```
ID: 2
task_id: 40d57833-80a1-41c3-b6ac-0034632fe184

original_video_path:
  minio://videos/test1/M1303.mp4

original_video_relative_path: videos/test1/M1303.mp4  (统一为 /)

result_video_path:
  minio://vid-results/tracked_M1303.mp4

result_video_relative_path: vid_results/tracked_M1303.mp4  (保持不变)
```

---

## ⚠️ 关键注意事项

### 1. Bucket 名称映射

| 本地目录 | MinIO Bucket |
|---------|-------------|
| `uploads/images/` | `images` |
| `uploads/img_results/` | `img-results` ⚠️ 连字符 |
| `uploads/videos/` | `videos` |
| `uploads/vid_results/` | `vid-results` ⚠️ 连字符 |
| `uploads/model/` | `models` |

### 2. 路径格式统一

- Windows 分隔符 `\` → Unix 分隔符 `/`
- 所有 MinIO 路径使用 `/`

### 3. 字段处理

**完整路径字段** (需要迁移):
- `models.path`
- `inference_results.original_image`
- `inference_results.result_image`
- `video_tracking_tasks.original_video_path`
- `video_tracking_tasks.result_video_path`

**相对路径字段** (不需要迁移，只统一分隔符):
- `inference_results.original_image_rel`
- `inference_results.result_image_rel`
- `video_tracking_tasks.original_video_relative_path`
- `video_tracking_tasks.result_video_relative_path`

---

## ✅ 验证脚本执行后的结果

### SQL 查询验证

```sql
-- 1. 检查 Models 表
SELECT id, name, path FROM models;
-- 所有 path 应该以 minio:// 开头

-- 2. 检查 InferenceResults 表 (前10条)
SELECT id, batch_name,
       original_image,
       result_image
FROM inference_results
ORDER BY id DESC
LIMIT 10;
-- 所有路径应该以 minio:// 开头

-- 3. 检查 VideoTrackingTasks 表
SELECT id, task_id,
       original_video_path,
       result_video_path
FROM video_tracking_tasks;
-- 所有路径应该以 minio:// 开头
```

---

## 🚀 执行迁移

```bash
# 1. 备份数据库
pg_dump -U postgres -d defect_detection > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. 执行迁移
conda activate backendJC
cd G:\ShuangChuang\ShuangC\backend\business-service
python migrate_paths_to_minio.py

# 脚本会先显示预览，然后等待你输入 yes 确认
```

---

**脚本已经过优化，能够正确处理您的数据格式！** ✅
