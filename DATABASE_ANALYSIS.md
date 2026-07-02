# 数据库使用分析：PostgreSQL 的作用

## 📊 当前系统架构

```
存储层:
├── MinIO (对象存储) ← 存储文件 (图片、视频、模型、推理结果)
└── PostgreSQL (关系数据库) ← 存储元数据和业务数据
```

---

## ✅ PostgreSQL 仍然**非常重要**！

### 核心作用总结

MinIO 只负责**存储文件**，PostgreSQL 负责**存储和管理业务逻辑、元数据、关系数据**。

---

## 📋 PostgreSQL 中的数据表

### 1. **Model 表** (模型管理) ✅ 必需

```python
class Model(Base):
    id              # 模型ID
    name            # 模型名称 (唯一)
    path            # MinIO 路径: minio://models/JC/yolov8n.pt
    version         # 版本号
    description     # 描述
    model_type      # 类型: detection/tracking
    is_active       # 是否激活
    created_at      # 创建时间
    updated_at      # 更新时间
```

**作用**:
- 管理模型元数据 (名称、版本、类型)
- 记录模型在 MinIO 中的位置
- 支持模型启用/禁用
- 关联推理任务

**为什么需要**:
- ❌ MinIO 不能存储模型的业务属性 (版本、类型、状态)
- ❌ MinIO 不能建立模型与任务的关系
- ✅ 需要快速查询"所有激活的检测模型"

---

### 2. **ImageDatabase 表** (图片元数据) ⚠️ 可选优化

```python
class ImageDatabase(Base):
    id              # 图片ID
    filename        # 文件名
    path            # MinIO 路径或本地路径
    url             # 访问URL
    folder          # 文件夹
    size            # 文件大小
    width/height    # 图片尺寸
    uploaded_at     # 上传时间
```

**当前状态**:
- 目前 `/images/database` 接口**直接从 MinIO 获取列表**
- 这个表可能**未被充分使用**

**优化建议**:
1. **方案 A (推荐)**: 保留表，用于快速查询和统计
   - 上传时同步写入数据库
   - 支持复杂查询 (按时间、大小、文件夹过滤)
   - 支持统计分析 (总大小、总数量)

2. **方案 B**: 删除表，完全依赖 MinIO
   - 简化系统
   - 每次都从 MinIO 查询
   - 无法做复杂统计

---

### 3. **InferenceTask 表** (推理任务) ✅ 必需

```python
class InferenceTask(Base):
    id              # 任务ID
    task_id         # 任务UUID
    model_id        # 关联模型 (外键)
    image_count     # 图片数量
    status          # 状态: pending/processing/completed/failed
    source_type     # 来源类型
    result_path     # 结果路径
    progress        # 进度 0-100
    created_at      # 创建时间
    started_at      # 开始时间
    completed_at    # 完成时间
```

**作用**:
- 管理推理任务的生命周期
- 追踪任务状态和进度
- 记录任务元数据
- 关联使用的模型

**为什么需要**:
- ❌ MinIO 不能管理任务状态
- ❌ MinIO 不能建立任务与模型的关系
- ✅ 需要查询"所有失败的任务"
- ✅ 需要实时更新任务进度

---

### 4. **InferenceResult 表** (推理结果) ✅ 核心！

```python
class InferenceResult(Base):
    id                      # 结果ID
    task_id                 # 关联任务
    batch_name              # 批次名称

    # 文件路径
    original_image          # 原图: minio://images/folder/img.jpg
    result_image            # 结果: minio://img-results/batch/img.jpg
    original_image_rel      # 相对路径
    result_image_rel        # 相对路径

    # 检测详情
    detections              # JSONB: 检测框详情
    detection_count         # 检测数量
    avg_confidence          # 平均置信度

    # 严重程度分析
    severity_level          # 等级 1-5
    severity_score          # 分数 0-100
    severity_text           # 文字描述
    severity_color          # 颜色标识

    # 图像信息
    image_width             # 宽度
    image_height            # 高度
    processing_time         # 处理时间
    created_at              # 创建时间
```

**作用** (⭐ 最重要的表):
- 存储每张图片的推理结果
- 使用 JSONB 存储检测框详情 (坐标、类别、置信度)
- 计算和存储严重程度评级
- 关联原图和结果图的 MinIO 路径
- 支持复杂查询和统计分析

**为什么需要**:
- ❌ MinIO 只能存储图片，**不能存储检测结果数据**
- ✅ 需要查询"所有严重缺陷的图片"
- ✅ 需要统计"各批次的平均置信度"
- ✅ 需要分析"缺陷分布趋势"
- ✅ 前端展示需要检测框坐标和置信度

**示例查询**:
```sql
-- 查询所有严重缺陷 (severity_level >= 4)
SELECT * FROM inference_results WHERE severity_level >= 4;

-- 统计各批次的缺陷数量
SELECT batch_name, COUNT(*), AVG(detection_count)
FROM inference_results
GROUP BY batch_name;

-- 查询某张原图的所有推理结果
SELECT * FROM inference_results WHERE original_image = 'minio://images/test/img.jpg';
```

---

### 5. **VideoTrackingTask 表** (视频追踪任务) ✅ 必需

```python
class VideoTrackingTask(Base):
    id                      # 任务ID
    task_id                 # 任务UUID
    model_id                # 关联模型

    # 视频路径
    original_video_path     # 原视频: minio://videos/xxx.mp4
    result_video_path       # 结果: minio://vid-results/xxx.mp4

    # 任务状态
    status                  # pending/processing/completed/failed
    progress                # 进度

    # 统计信息
    total_frames            # 总帧数
    processed_frames        # 已处理帧数
    fps                     # 帧率
    duration                # 时长

    created_at              # 创建时间
    started_at              # 开始时间
    completed_at            # 完成时间
```

**作用**:
- 管理视频处理任务
- 追踪处理进度 (帧级别)
- 记录视频元数据
- 关联视频文件在 MinIO 的位置

---

## 🎯 PostgreSQL vs MinIO 职责划分

| 数据类型 | 存储位置 | 示例 |
|---------|---------|------|
| **文件本身** | MinIO | 图片、视频、模型文件、推理结果图片 |
| **文件元数据** | PostgreSQL | 文件名、大小、上传时间、宽高 |
| **业务数据** | PostgreSQL | 模型配置、任务状态、推理结果、检测框 |
| **关系数据** | PostgreSQL | 模型↔任务、任务↔结果 |
| **结构化数据** | PostgreSQL | JSONB 检测详情、严重程度评级 |
| **统计分析** | PostgreSQL | 聚合查询、分组统计、趋势分析 |

---

## 📈 实际应用场景

### 场景 1: 用户查看推理结果

```
1. 前端请求: GET /inference-results/batch/batch_20250216
2. PostgreSQL 查询:
   - 获取该批次所有结果记录
   - 包含检测框、置信度、严重程度
3. 返回数据包含:
   - result_image: minio://img-results/batch_20250216/img1.jpg
   - detections: [{class: "裂缝", confidence: 0.95, bbox: [x,y,w,h]}]
   - severity_level: 4
4. 前端根据 result_image 访问 /uploads/img_results/...
5. 后端生成 MinIO 预签名 URL
6. 前端显示图片 + 检测框
```

**分析**:
- ✅ PostgreSQL 提供检测框数据
- ✅ MinIO 提供图片文件
- ❌ 如果没有数据库，前端无法绘制检测框

---

### 场景 2: 分析缺陷趋势

```sql
-- 按天统计缺陷数量
SELECT
    DATE(created_at) as date,
    COUNT(*) as total_images,
    SUM(detection_count) as total_defects,
    AVG(avg_confidence) as avg_conf
FROM inference_results
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY date;
```

**分析**:
- ✅ PostgreSQL 支持复杂 SQL 查询
- ❌ MinIO 不支持这种分析

---

### 场景 3: 查找特定模型的所有任务

```sql
-- 查询使用 yolov8n 模型的所有任务
SELECT t.*, m.name as model_name
FROM inference_tasks t
JOIN models m ON t.model_id = m.id
WHERE m.name = 'yolov8n'
ORDER BY t.created_at DESC;
```

**分析**:
- ✅ PostgreSQL 支持表关联 (JOIN)
- ❌ MinIO 不支持关系查询

---

## 🔧 优化建议

### 1. ImageDatabase 表的处理

**当前问题**:
- 图片上传时**未写入数据库**
- `/images/database` 接口直接从 MinIO 读取

**建议方案 A (推荐)**: 同步写入数据库
```python
@app.post("/images/upload")
async def upload_image(...):
    # 1. 上传到 MinIO
    minio_client.upload_file(...)

    # 2. 写入数据库
    image_record = ImageDatabase(
        filename=new_filename,
        path=f"minio://images/{object_name}",
        folder=folder,
        size=file_size,
        width=width,
        height=height
    )
    db.add(image_record)
    db.commit()
```

**好处**:
- ✅ 支持快速查询 (WHERE folder = 'test')
- ✅ 支持统计 (总大小、总数量)
- ✅ 支持关联查询 (哪些图片有推理结果)

**建议方案 B**: 删除表，完全依赖 MinIO
- 简化系统
- 减少维护成本
- 但失去复杂查询能力

---

### 2. 系统管理相关表 (SQLite)

**System Management 模块**使用单独的 SQLite 数据库:
- User (用户)
- Role (角色)
- Department (部门)
- Permission (权限)

这些表与 MinIO 无关，是纯业务数据。

---

## ✅ 结论

### PostgreSQL **必须保留**！

**核心原因**:
1. ✅ **存储业务逻辑** - 任务状态、推理结果、检测框
2. ✅ **存储关系数据** - 模型↔任务、任务↔结果
3. ✅ **支持复杂查询** - JOIN、聚合、统计
4. ✅ **存储 JSONB** - 检测详情、配置信息
5. ✅ **支持事务** - 数据一致性保证

### MinIO 的职责

1. ✅ **存储文件** - 图片、视频、模型
2. ✅ **提供访问** - 预签名 URL
3. ❌ **不能替代数据库** - 不支持结构化查询

---

## 📊 数据流示意图

```
上传图片:
用户 → business-service → MinIO (存储文件)
                        → PostgreSQL (存储元数据) ← 可选

推理任务:
用户 → business-service → PostgreSQL (创建任务)
     → inference-service → YOLO 推理
                        → MinIO (上传结果图)
                        → PostgreSQL (保存检测结果) ← 必需

查看结果:
用户 → business-service → PostgreSQL (查询检测框)
                        → 返回 MinIO 路径
     → 前端访问图片 → MinIO (预签名 URL)
     → 前端绘制检测框 ← 来自 PostgreSQL
```

---

## 🎯 最终答案

**PostgreSQL 仍然非常重要！**

- ✅ **Model 表**: 管理模型元数据和关系
- ✅ **InferenceTask 表**: 追踪任务状态和进度
- ✅ **InferenceResult 表**: 存储检测结果和分析 (⭐ 最核心)
- ✅ **VideoTrackingTask 表**: 管理视频处理任务
- ⚠️ **ImageDatabase 表**: 可优化 (建议同步写入或删除)

**系统架构**:
```
MinIO (文件存储) + PostgreSQL (数据管理) = 完整的对象存储系统
```

这是**标准的云原生架构**，类似于：
- AWS: S3 + RDS
- 阿里云: OSS + RDS
- 腾讯云: COS + CDB

**不能删除 PostgreSQL！** 🚫
