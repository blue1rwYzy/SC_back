# 系统管理模块 - 安装和使用指南

## 📋 功能概述

系统管理模块实现了完整的RBAC(基于角色的访问控制)系统,包括:

- **用户管理**: 用户CRUD、分页查询、密码重置、角色分配
- **角色管理**: 角色CRUD、权限配置、用户关联
- **部门管理**: 部门CRUD、树形结构、用户关联

## 🔧 后端安装

### 1. 安装依赖

所有依赖已包含在标准库中,无需额外安装。

```bash
cd G:\ShuangChuang\ShuangC\backend\business-service
conda activate backendJC
```

### 2. 启动服务

```bash
python main.py
```

启动后会自动:
1. 创建数据库文件: `G:\ShuangChuang\ShuangC\backend\system_management.db`
2. 初始化数据表(users, roles, departments, user_roles)
3. 创建默认数据

### 3. 默认账号

系统自动创建以下默认账号:

| 用户名 | 密码 | 角色 | 说明 |
|--------|------|------|------|
| admin | admin123 | 超级管理员 | 拥有所有权限 |
| test | test123 | 技术员 | 拥有检测和追踪权限 |

### 4. 默认部门结构

```
总公司 (ROOT)
├── 技术部 (TECH)
└── 行政部 (ADMIN)
```

### 5. 默认角色

- **超级管理员** (SUPER_ADMIN): 所有权限
- **普通用户** (USER): 只读权限
- **技术员** (TECHNICIAN): 检测和追踪权限

## 📡 API接口

### 用户管理

```bash
GET    /system/users              # 获取用户列表(分页)
GET    /system/users/{id}         # 获取用户详情
POST   /system/users              # 创建用户
PUT    /system/users/{id}         # 更新用户
DELETE /system/users/{id}         # 删除用户
PUT    /system/users/{id}/password # 重置密码
```

### 角色管理

```bash
GET    /system/roles              # 获取角色列表
GET    /system/roles/{id}         # 获取角色详情
POST   /system/roles              # 创建角色
PUT    /system/roles/{id}         # 更新角色
DELETE /system/roles/{id}         # 删除角色
GET    /system/roles/{id}/users   # 获取角色用户
```

### 部门管理

```bash
GET    /system/departments/tree         # 获取部门树
GET    /system/departments              # 获取部门列表
GET    /system/departments/{id}         # 获取部门详情
POST   /system/departments              # 创建部门
PUT    /system/departments/{id}         # 更新部门
DELETE /system/departments/{id}         # 删除部门
GET    /system/departments/{id}/users   # 获取部门用户
```

## 🎨 前端使用

### 访问路径

- 用户管理: `/system-management/users`
- 角色管理: `/system-management/roles`
- 部门管理: `/system-management/departments`

### 功能特性

#### 用户管理
- ✅ 分页查询、搜索(用户名/姓名/邮箱/手机号)
- ✅ 按部门筛选、按状态筛选
- ✅ 新增/编辑用户
- ✅ 重置密码
- ✅ 删除用户(禁止删除超级管理员)
- ✅ 角色分配(多选)
- ✅ 状态启用/禁用

#### 角色管理
- ✅ 分页查询、搜索(角色名称/编码)
- ✅ 新增/编辑角色
- ✅ 权限配置(JSON格式)
- ✅ 查看角色关联的用户
- ✅ 删除角色(有用户时不可删除)
- ✅ 状态启用/禁用

#### 部门管理
- ✅ 树形展示部门层级
- ✅ 新增顶级部门/子部门
- ✅ 编辑部门
- ✅ 查看部门用户(可选包含子部门)
- ✅ 删除部门(有子部门或用户时不可删除)
- ✅ 状态启用/禁用

## 🗂️ 文件结构

### 后端

```
backend/business-service/
├── database.py                          # 数据库配置
├── models/
│   └── system_models.py                 # 数据模型(User, Role, Department)
├── services/
│   ├── user_service.py                  # 用户服务
│   ├── role_service.py                  # 角色服务
│   ├── department_service.py            # 部门服务
│   └── system_init_service.py           # 初始化服务
├── routers/
│   └── system_router.py                 # API路由
└── main.py                              # 主程序(已注册路由)
```

### 前端

```
frontend/vue-vben-admin-main/apps/web-antd/src/
├── router/routes/modules/
│   └── system-management.ts             # 路由配置
├── views/system-management/
│   ├── users/index.vue                  # 用户管理页面
│   ├── roles/index.vue                  # 角色管理页面
│   └── departments/index.vue            # 部门管理页面
├── api/system/
│   └── system-management.ts             # API接口
└── locales/langs/
    ├── zh-CN/page.json                  # 中文翻译
    └── en-US/page.json                  # 英文翻译
```

## 🧪 测试步骤

### 1. 测试后端API

```bash
# 1. 启动服务
python main.py

# 2. 访问API文档
# 浏览器打开: http://localhost:8002/docs

# 3. 测试用户列表接口
curl http://localhost:8002/system/users?page=1&page_size=10

# 4. 测试部门树接口
curl http://localhost:8002/system/departments/tree
```

### 2. 测试前端页面

```bash
# 1. 启动前端
cd G:\ShuangChuang\ShuangC\frontend\vue-vben-admin-main
pnpm dev

# 2. 浏览器访问
http://localhost:5173

# 3. 点击导航菜单
系统管理 -> 用户管理
系统管理 -> 角色管理
系统管理 -> 部门管理
```

## 🔐 权限配置说明

权限使用JSON格式存储,格式如下:

```json
{
  "system": [
    "user:view", "user:add", "user:edit", "user:delete",
    "role:view", "role:add", "role:edit", "role:delete",
    "dept:view", "dept:add", "dept:edit", "dept:delete"
  ],
  "defect": [
    "detect:view", "detect:run", "detect:delete"
  ],
  "tracking": [
    "track:view", "track:run", "track:delete"
  ],
  "database": [
    "image:view", "image:upload", "image:delete",
    "video:view", "video:upload", "video:delete"
  ]
}
```

## ⚠️ 注意事项

1. **数据库文件位置**:
   - 存储在 `G:\ShuangChuang\ShuangC\backend\system_management.db`
   - 使用相对路径,部署时会自动创建

2. **密码安全**:
   - 使用SHA256加密
   - 默认密码仅供测试,生产环境请修改

3. **删除限制**:
   - 不能删除超级管理员
   - 不能删除有用户的角色
   - 不能删除有子部门或用户的部门

4. **编码规范**:
   - 角色编码: 大写字母+下划线 (如: SUPER_ADMIN)
   - 部门编码: 大写字母+下划线 (如: TECH)

## 🐛 常见问题

### 1. 密码加密方式

系统使用 Python 内置的 SHA256 进行密码加密,无需安装额外依赖。

### 2. 前端报错: Cannot find module '#/api/system/system-management'

**解决**: 检查API文件是否创建,路径是否正确

### 3. 数据库文件权限错误

**解决**: 确保backend目录有写权限

## 📚 扩展开发

### 添加新权限

编辑 `services/system_init_service.py`,在角色的permissions字段添加新权限。

### 添加新字段

1. 修改 `models/system_models.py` 添加字段
2. 删除数据库文件重新初始化,或使用Alembic迁移
3. 更新对应的Service和API

### 自定义初始数据

修改 `services/system_init_service.py` 的 `init_system_data` 函数。

## ✅ 开发清单

- [x] 后端数据模型
- [x] 后端服务层
- [x] 后端API接口
- [x] 前端路由配置
- [x] 前端页面组件
- [x] 前端API对接
- [x] 国际化配置
- [x] 文档说明

---

**开发完成时间**: 2026-02-16
**开发者**: Claude Sonnet 4.5
