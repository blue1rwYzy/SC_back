# MinIO 修复：图片列表接口

## 🐛 问题

前端显示"数据库中暂无图片"，原因是 `/images/database` 接口仍在扫描本地磁盘目录，而不是从 MinIO 获取数据。

## ✅ 已修复

### 1. 修改 `/images/database` 接口

**文件**: `business-service/main.py`

**原实现**: 扫描本地 `uploads/images` 目录
```python
def build_tree(directory_path, parent_path=""):
    items = os.listdir(directory_path)  # ❌ 扫描本地磁盘
    ...
```

**新实现**: 从 MinIO 获取对象列表
```python
objects = minio_client.list_objects(
    bucket_name=BUCKETS["images"],
    prefix=folder if folder else None,
    recursive=True
)
```

### 2. 增强 MinIO 客户端

**文件**: `utils/minio_client.py`

修改 `list_objects()` 方法：
- **原**: 只返回对象名称字符串列表
- **新**: 返回完整对象信息 (包含 size, last_modified 等)

## 📋 返回的数据结构

```json
{
  "code": 0,
  "data": [
    {
      "id": "folder_test",
      "filename": "test",
      "path": "test",
      "relativePath": "test",
      "isFolder": true,
      "children": [
        {
          "id": "test/image1.jpg",
          "filename": "image1.jpg",
          "path": "/uploads/images/test/image1.jpg",
          "fullPath": "test/image1.jpg",
          "relativePath": "test/image1.jpg",
          "size": 123456,
          "uploadedAt": "2025-02-16T10:30:00",
          "isFolder": false
        }
      ]
    }
  ],
  "message": "success"
}
```

## 🔄 工作流程

1. **前端请求** `/images/database`
2. **后端查询** MinIO `images` bucket
3. **构建树形结构** 按文件夹组织
4. **返回数据** 包含访问路径 `/uploads/images/...`
5. **前端访问** 图片时自动获取预签名 URL

## 🧪 测试步骤

### 1. 上传测试图片

```bash
# 访问 http://localhost:8000/docs
# 找到 POST /images/upload
# 上传一张图片, folder 填写 "test"
```

### 2. 检查 MinIO

```bash
# 访问 MinIO Console: http://localhost:9000
# 登录 admin/admin123456
# 进入 images bucket
# 应该能看到 test/xxxxx.jpg
```

### 3. 获取图片列表

```bash
# 访问 http://localhost:8000/images/database
# 应该返回包含图片的 JSON 数据
```

### 4. 前端访问

刷新前端页面，应该能看到图片列表。

## ⚠️ 注意事项

### MinIO 必须运行

如果 MinIO 未运行，接口会返回错误：
```json
{
  "code": 500,
  "data": [],
  "message": "获取图片列表失败: ..."
}
```

### 空 Bucket 提示

如果 MinIO `images` bucket 为空：
```json
{
  "code": 0,
  "data": [],
  "message": "MinIO 中暂无图片"
}
```

### 前端路径格式

前端收到的 `path` 字段格式：
- `/uploads/images/folder/file.jpg`

访问时会自动重定向到 MinIO 预签名 URL。

## 📝 已同步的文件

- ✅ `business-service/main.py` - 修改接口
- ✅ `business-service/utils/minio_client.py` - 增强方法
- ✅ `inference-service/utils/minio_client.py` - 同步更新

## 🎯 完成！

现在图片列表完全从 MinIO 获取，不再依赖本地磁盘。
