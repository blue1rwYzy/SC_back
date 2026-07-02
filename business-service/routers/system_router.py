"""
系统管理路由
包括: 用户管理、角色管理、部门管理
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel, Field
from database import get_db
from services.user_service import UserService
from services.role_service import RoleService
from services.department_service import DepartmentService

router = APIRouter(prefix="/system", tags=["系统管理"])


# ============ Pydantic 模型 ============

# 用户相关
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, description="密码")
    real_name: str = Field(..., min_length=2, max_length=50, description="真实姓名")
    email: Optional[str] = Field(None, max_length=100, description="邮箱")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    department_id: Optional[int] = Field(None, description="部门ID")
    position: Optional[str] = Field(None, max_length=50, description="职位")
    role_ids: Optional[List[int]] = Field(None, description="角色ID列表")


class UserUpdate(BaseModel):
    real_name: Optional[str] = Field(None, min_length=2, max_length=50)
    email: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    department_id: Optional[int] = None
    position: Optional[str] = Field(None, max_length=50)
    status: Optional[bool] = None
    role_ids: Optional[List[int]] = None


class PasswordReset(BaseModel):
    new_password: str = Field(..., min_length=6, description="新密码")


# 角色相关
class RoleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50, description="角色名称")
    code: str = Field(..., min_length=2, max_length=50, description="角色编码")
    description: Optional[str] = Field(None, description="描述")
    permissions: Optional[str] = Field(None, description="权限(JSON)")
    sort_order: Optional[int] = Field(0, description="排序")


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=50)
    code: Optional[str] = Field(None, min_length=2, max_length=50)
    description: Optional[str] = None
    permissions: Optional[str] = None
    status: Optional[bool] = None
    sort_order: Optional[int] = None


# 部门相关
class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="部门名称")
    code: str = Field(..., min_length=2, max_length=50, description="部门编码")
    parent_id: Optional[int] = Field(None, description="父部门ID")
    leader: Optional[str] = Field(None, max_length=50, description="负责人")
    phone: Optional[str] = Field(None, max_length=20, description="电话")
    email: Optional[str] = Field(None, max_length=100, description="邮箱")
    sort_order: Optional[int] = Field(0, description="排序")
    description: Optional[str] = Field(None, description="描述")


class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    code: Optional[str] = Field(None, min_length=2, max_length=50)
    parent_id: Optional[int] = None
    leader: Optional[str] = Field(None, max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    sort_order: Optional[int] = None
    status: Optional[bool] = None
    description: Optional[str] = None


# ============ 用户管理接口 ============

@router.get("/users")
async def get_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    department_id: Optional[int] = Query(None, description="部门ID"),
    status: Optional[bool] = Query(None, description="状态"),
    db: Session = Depends(get_db)
):
    """获取用户列表(分页)"""
    try:
        users, total = UserService.get_users_paginated(
            db, page, page_size, keyword, department_id, status
        )

        return {
            "code": 0,
            "message": "success",
            "data": {
                "list": [user.to_dict() for user in users],
                "total": total,
                "page": page,
                "page_size": page_size
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    """获取用户详情"""
    user = UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return {
        "code": 0,
        "message": "success",
        "data": user.to_dict()
    }


@router.post("/users")
async def create_user(user_data: UserCreate, db: Session = Depends(get_db)):
    """创建用户"""
    try:
        user = UserService.create_user(
            db,
            username=user_data.username,
            password=user_data.password,
            real_name=user_data.real_name,
            email=user_data.email,
            phone=user_data.phone,
            department_id=user_data.department_id,
            position=user_data.position,
            role_ids=user_data.role_ids
        )

        return {
            "code": 0,
            "message": "用户创建成功",
            "data": user.to_dict()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate, db: Session = Depends(get_db)):
    """更新用户"""
    try:
        user = UserService.update_user(
            db,
            user_id=user_id,
            real_name=user_data.real_name,
            email=user_data.email,
            phone=user_data.phone,
            department_id=user_data.department_id,
            position=user_data.position,
            status=user_data.status,
            role_ids=user_data.role_ids
        )

        return {
            "code": 0,
            "message": "用户更新成功",
            "data": user.to_dict()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{user_id}/password")
async def reset_user_password(user_id: int, password_data: PasswordReset, db: Session = Depends(get_db)):
    """重置用户密码"""
    try:
        user = UserService.reset_password(db, user_id, password_data.new_password)

        return {
            "code": 0,
            "message": "密码重置成功",
            "data": {"id": user.id, "username": user.username}
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    """删除用户"""
    try:
        UserService.delete_user(db, user_id)

        return {
            "code": 0,
            "message": "用户删除成功"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 角色管理接口 ============

@router.get("/roles")
async def get_roles(
    page: Optional[int] = Query(None, ge=1, description="页码(不传则返回所有)"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    status: Optional[bool] = Query(None, description="状态"),
    db: Session = Depends(get_db)
):
    """获取角色列表"""
    try:
        if page is None:
            # 返回所有角色
            roles = RoleService.get_all_roles(db, status)
            return {
                "code": 0,
                "message": "success",
                "data": [role.to_dict() for role in roles]
            }
        else:
            # 分页返回
            roles, total = RoleService.get_roles_paginated(db, page, page_size, keyword, status)
            return {
                "code": 0,
                "message": "success",
                "data": {
                    "list": [role.to_dict() for role in roles],
                    "total": total,
                    "page": page,
                    "page_size": page_size
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/roles/{role_id}")
async def get_role(role_id: int, db: Session = Depends(get_db)):
    """获取角色详情"""
    role = RoleService.get_role_by_id(db, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    return {
        "code": 0,
        "message": "success",
        "data": role.to_dict()
    }


@router.post("/roles")
async def create_role(role_data: RoleCreate, db: Session = Depends(get_db)):
    """创建角色"""
    try:
        role = RoleService.create_role(
            db,
            name=role_data.name,
            code=role_data.code,
            description=role_data.description,
            permissions=role_data.permissions,
            sort_order=role_data.sort_order
        )

        return {
            "code": 0,
            "message": "角色创建成功",
            "data": role.to_dict()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/roles/{role_id}")
async def update_role(role_id: int, role_data: RoleUpdate, db: Session = Depends(get_db)):
    """更新角色"""
    try:
        role = RoleService.update_role(
            db,
            role_id=role_id,
            name=role_data.name,
            code=role_data.code,
            description=role_data.description,
            permissions=role_data.permissions,
            status=role_data.status,
            sort_order=role_data.sort_order
        )

        return {
            "code": 0,
            "message": "角色更新成功",
            "data": role.to_dict()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/roles/{role_id}")
async def delete_role(role_id: int, db: Session = Depends(get_db)):
    """删除角色"""
    try:
        RoleService.delete_role(db, role_id)

        return {
            "code": 0,
            "message": "角色删除成功"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/roles/{role_id}/users")
async def get_role_users(role_id: int, db: Session = Depends(get_db)):
    """获取角色关联的用户"""
    try:
        users = RoleService.get_role_users(db, role_id)
        return {
            "code": 0,
            "message": "success",
            "data": users
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 部门管理接口 ============

@router.get("/departments/tree")
async def get_department_tree(
    status: Optional[bool] = Query(None, description="状态"),
    db: Session = Depends(get_db)
):
    """获取部门树形结构"""
    try:
        tree = DepartmentService.get_department_tree(db, status)
        return {
            "code": 0,
            "message": "success",
            "data": tree
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/departments")
async def get_departments(
    page: Optional[int] = Query(None, ge=1, description="页码(不传则返回所有)"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    status: Optional[bool] = Query(None, description="状态"),
    db: Session = Depends(get_db)
):
    """获取部门列表(平铺)"""
    try:
        if page is None:
            # 返回所有部门
            departments = DepartmentService.get_all_departments(db, status)
            return {
                "code": 0,
                "message": "success",
                "data": [dept.to_dict() for dept in departments]
            }
        else:
            # 分页返回
            departments, total = DepartmentService.get_departments_paginated(
                db, page, page_size, keyword, status
            )
            return {
                "code": 0,
                "message": "success",
                "data": {
                    "list": [dept.to_dict() for dept in departments],
                    "total": total,
                    "page": page,
                    "page_size": page_size
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/departments/{dept_id}")
async def get_department(dept_id: int, db: Session = Depends(get_db)):
    """获取部门详情"""
    dept = DepartmentService.get_department_by_id(db, dept_id)
    if not dept:
        raise HTTPException(status_code=404, detail="部门不存在")

    return {
        "code": 0,
        "message": "success",
        "data": dept.to_dict()
    }


@router.post("/departments")
async def create_department(dept_data: DepartmentCreate, db: Session = Depends(get_db)):
    """创建部门"""
    try:
        dept = DepartmentService.create_department(
            db,
            name=dept_data.name,
            code=dept_data.code,
            parent_id=dept_data.parent_id,
            leader=dept_data.leader,
            phone=dept_data.phone,
            email=dept_data.email,
            sort_order=dept_data.sort_order,
            description=dept_data.description
        )

        return {
            "code": 0,
            "message": "部门创建成功",
            "data": dept.to_dict()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/departments/{dept_id}")
async def update_department(dept_id: int, dept_data: DepartmentUpdate, db: Session = Depends(get_db)):
    """更新部门"""
    try:
        dept = DepartmentService.update_department(
            db,
            dept_id=dept_id,
            name=dept_data.name,
            code=dept_data.code,
            parent_id=dept_data.parent_id,
            leader=dept_data.leader,
            phone=dept_data.phone,
            email=dept_data.email,
            sort_order=dept_data.sort_order,
            status=dept_data.status,
            description=dept_data.description
        )

        return {
            "code": 0,
            "message": "部门更新成功",
            "data": dept.to_dict()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/departments/{dept_id}")
async def delete_department(dept_id: int, db: Session = Depends(get_db)):
    """删除部门"""
    try:
        DepartmentService.delete_department(db, dept_id)

        return {
            "code": 0,
            "message": "部门删除成功"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/departments/{dept_id}/users")
async def get_department_users(
    dept_id: int,
    include_children: bool = Query(False, description="是否包含子部门用户"),
    db: Session = Depends(get_db)
):
    """获取部门下的用户"""
    try:
        users = DepartmentService.get_department_users(db, dept_id, include_children)
        return {
            "code": 0,
            "message": "success",
            "data": users
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
