"""
角色管理服务
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_
from models.system_models import Role
from typing import List, Optional, Tuple


class RoleService:
    """角色管理服务"""

    @staticmethod
    def get_role_by_id(db: Session, role_id: int) -> Optional[Role]:
        """根据ID获取角色"""
        return db.query(Role).filter(Role.id == role_id).first()

    @staticmethod
    def get_role_by_code(db: Session, code: str) -> Optional[Role]:
        """根据编码获取角色"""
        return db.query(Role).filter(Role.code == code).first()

    @staticmethod
    def get_all_roles(db: Session, status: bool = None) -> List[Role]:
        """获取所有角色"""
        query = db.query(Role)

        if status is not None:
            query = query.filter(Role.status == status)

        return query.order_by(Role.sort_order.asc(), Role.created_at.desc()).all()

    @staticmethod
    def get_roles_paginated(
        db: Session,
        page: int = 1,
        page_size: int = 10,
        keyword: str = None,
        status: bool = None
    ) -> Tuple[List[Role], int]:
        """
        分页获取角色列表

        Returns:
            (roles, total): 角色列表和总数
        """
        query = db.query(Role)

        # 搜索条件
        if keyword:
            query = query.filter(
                or_(
                    Role.name.like(f'%{keyword}%'),
                    Role.code.like(f'%{keyword}%'),
                    Role.description.like(f'%{keyword}%')
                )
            )

        # 状态筛选
        if status is not None:
            query = query.filter(Role.status == status)

        # 总数
        total = query.count()

        # 分页
        roles = query.order_by(Role.sort_order.asc(), Role.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

        return roles, total

    @staticmethod
    def create_role(
        db: Session,
        name: str,
        code: str,
        description: str = None,
        permissions: str = None,
        sort_order: int = 0
    ) -> Role:
        """创建角色"""

        # 检查名称是否存在
        existing_name = db.query(Role).filter(Role.name == name).first()
        if existing_name:
            raise ValueError(f'角色名称 {name} 已存在')

        # 检查编码是否存在
        existing_code = db.query(Role).filter(Role.code == code).first()
        if existing_code:
            raise ValueError(f'角色编码 {code} 已存在')

        # 创建角色
        role = Role(
            name=name,
            code=code,
            description=description,
            permissions=permissions,
            status=True,
            sort_order=sort_order
        )

        db.add(role)
        db.commit()
        db.refresh(role)

        return role

    @staticmethod
    def update_role(
        db: Session,
        role_id: int,
        name: str = None,
        code: str = None,
        description: str = None,
        permissions: str = None,
        status: bool = None,
        sort_order: int = None
    ) -> Role:
        """更新角色"""
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise ValueError(f'角色 ID {role_id} 不存在')

        # 更新字段
        if name is not None:
            # 检查名称是否被其他角色使用
            if name != role.name:
                existing = db.query(Role).filter(Role.name == name, Role.id != role_id).first()
                if existing:
                    raise ValueError(f'角色名称 {name} 已被其他角色使用')
            role.name = name

        if code is not None:
            # 检查编码是否被其他角色使用
            if code != role.code:
                existing = db.query(Role).filter(Role.code == code, Role.id != role_id).first()
                if existing:
                    raise ValueError(f'角色编码 {code} 已被其他角色使用')
            role.code = code

        if description is not None:
            role.description = description

        if permissions is not None:
            role.permissions = permissions

        if status is not None:
            role.status = status

        if sort_order is not None:
            role.sort_order = sort_order

        db.commit()
        db.refresh(role)

        return role

    @staticmethod
    def delete_role(db: Session, role_id: int) -> bool:
        """删除角色"""
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise ValueError(f'角色 ID {role_id} 不存在')

        # 检查是否有用户使用该角色
        if role.users:
            raise ValueError(f'角色 {role.name} 正在被 {len(role.users)} 个用户使用，无法删除')

        db.delete(role)
        db.commit()

        return True

    @staticmethod
    def get_role_users(db: Session, role_id: int):
        """获取角色关联的用户"""
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise ValueError(f'角色 ID {role_id} 不存在')

        return [user.to_dict() for user in role.users]
