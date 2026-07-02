# 视频数据库接口修复

## 🐛 问题

前端"视频数据库"显示"暂无视频"，原因是**缺少视频列表接口**。

## ✅ 解决方案

添加了 `/videos/database` 接口，从 MinIO 获取视频列表。

---

## 📝 新增接口

### GET `/videos/database`

**功能**: 从 MinIO `videos` bucket 获取视频列表，返回树形结构

**参数**:
- `folder` (可选): 文件夹前缀过滤

**返回格式**:
```json
{
  "code": 0,
  "data": [
    {
      "id": "test1/M1303.mp4",
      "filename": "M1303.mp4",
      "path": "/uploads/videos/test1/M1303.mp4",
      "fullPath": "test1/M1303.mp4",
      "relativePath": "test1/M1303.mp4",
      "size": 12345678,
      "uploadedAt": "2026-02-15T15:07:55",
      "isFolder": false
    },
    {
      "id": "M0206.mp4",
      "filename": "M0206.mp4",
      "path": "/uploads/videos/M0206.mp4",
      "fullPath": "M0206.mp4",
      "relativePath": "M0206.mp4",
      "size": 8765432,
      "uploadedAt": "2026-02-13T13:18:53",
      "isFolder": false
    }
  ],
  "message": "success"
}
```

---

## 🎯 支持的视频格式

接口会自动过滤以下视频文件：
- `.mp4`
- `.avi`
- `.mov`
- `.mkv`
- `.flv`
- `.wmv`

---

## 🔄 工作流程

1. **前端请求** `/videos/database`
2. **后端查询** MinIO `videos` bucket
3. **过滤视频文件** 只返回视频格式
4. **构建树形结构** 按文件夹组织
5. **返回数据** 包含访问路径 `/uploads/videos/...`
6. **前端访问** 视频时自动获取预签名 URL

---

## 🧪 测试步骤

### 1. 检查 MinIO 中的视频

```bash
# 访问 MinIO Console
http://localhost:9000

# 登录
用户名: admin
密码: admin123456

# 查看 videos bucket
# 应该能看到已迁移的视频文件，如:
# - M0206.mp4
# - test1/M1303.mp4
```

### 2. 测试接口

```bash
# 方式 1: 浏览器访问
http://localhost:8000/videos/database

# 方式 2: API 文档测试
http://localhost:8000/docs
找到 GET /videos/database
点击 "Try it out"
点击 "Execute"

# 应该返回视频列表
```

### 3. 前端测试

1. 刷新前端页面
2. 进入"视频数据库"
3. 应该能看到视频列表
4. 点击视频应该能播放

---

## 📊 与图片接口对比

| 接口 | 功能 | Bucket | 文件格式 |
|------|------|--------|---------|
| `/images/database` | 图片列表 | `images` | jpg, png, bmp, gif, webp |
| `/videos/database` | 视频列表 | `videos` | mp4, avi, mov, mkv, flv, wmv |

两个接口的实现逻辑完全一致，只是：
- Bucket 名称不同
- 文件扩展名过滤不同

---

## 🔍 常见问题

### Q1: 接口返回空数组
**A**: 检查 MinIO `videos` bucket 是否有文件

```bash
# 使用 mc 命令检查
mc ls minio/videos/
```

### Q2: 前端仍显示"暂无视频"
**A**:
1. 确认后端已重启
2. 清除浏览器缓存
3. 检查前端是否调用了正确的接口

### Q3: 视频无法播放
**A**:
1. 检查 `/uploads/videos/{path}` 路由是否正常
2. 确认返回的是预签名 URL
3. 检查 MinIO 中的视频文件是否损坏

---

## ✅ 完成

- ✅ 添加 `/videos/database` 接口
- ✅ 从 MinIO 获取视频列表
- ✅ 支持树形结构
- ✅ 支持多种视频格式
- ✅ 与图片接口保持一致

---

## 🚀 下一步

**重启 business-service**:

```bash
# 停止当前服务 (Ctrl+C)

# 重新启动
cd G:\ShuangChuang\ShuangC\backend\business-service
conda activate backendJC
python main.py
```

**测试前端**:
刷新视频数据库页面，应该能看到视频列表了！
