"""
用户管理服务
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from models.system_models import User, Role, Department
import hashlib
from typing import List, Optional, Dict, Tuple
from datetime import datetime


class UserService:
    """用户管理服务"""

    @staticmethod
    def hash_password(password: str) -> str:
        """加密密码 - 使用SHA256"""
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return UserService.hash_password(plain_password) == hashed_password

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_user_by_username(db: Session, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        return db.query(User).filter(User.username == username).first()

    @staticmethod
    def get_users_paginated(
        db: Session,
        page: int = 1,
        page_size: int = 10,
        keyword: str = None,
        department_id: int = None,
        status: bool = None
    ) -> Tuple[List[User], int]:
        """
        分页获取用户列表

        Returns:
            (users, total): 用户列表和总数
        """
        query = db.query(User)

        # 搜索条件
        if keyword:
            query = query.filter(
                or_(
                    User.username.like(f'%{keyword}%'),
                    User.real_name.like(f'%{keyword}%'),
                    User.email.like(f'%{keyword}%'),
                    User.phone.like(f'%{keyword}%')
                )
            )

        # 部门筛选
        if department_id is not None:
            query = query.filter(User.department_id == department_id)

        # 状态筛选
        if status is not None:
            query = query.filter(User.status == status)

        # 总数
        total = query.count()

        # 分页 - 按ID降序排列
        users = query.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

        return users, total

    @staticmethod
    def create_user(
        db: Session,
        username: str,
        password: str,
        real_name: str,
        email: str = None,
        phone: str = None,
        department_id: int = None,
        position: str = None,
        role_ids: List[int] = None
    ) -> User:
        """创建用户"""

        # 检查用户名是否存在
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            raise ValueError(f'用户名 {username} 已存在')

        # 检查邮箱是否存在
        if email:
            existing_email = db.query(User).filter(User.email == email).first()
            if existing_email:
                raise ValueError(f'邮箱 {email} 已被使用')

        # 创建用户
        user = User(
            username=username,
            password=UserService.hash_password(password),
            real_name=real_name,
            email=email,
            phone=phone,
            department_id=department_id,
            position=position,
            status=True,
            is_admin=False
        )

        # 分配角色
        if role_ids:
            roles = db.query(Role).filter(Role.id.in_(role_ids)).all()
            user.roles = roles

        db.add(user)
        db.commit()
        db.refresh(user)

        return user

    @staticmethod
    def update_user(
        db: Session,
        user_id: int,
        real_name: str = None,
        email: str = None,
        phone: str = None,
        department_id: int = None,
        position: str = None,
        status: bool = None,
        role_ids: List[int] = None
    ) -> User:
        """更新用户"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f'用户 ID {user_id} 不存在')

        # 更新字段
        if real_name is not None:
            user.real_name = real_name
        if email is not None:
            # 检查邮箱是否被其他用户使用
            if email != user.email:
                existing = db.query(User).filter(User.email == email, User.id != user_id).first()
                if existing:
                    raise ValueError(f'邮箱 {email} 已被其他用户使用')
            user.email = email
        if phone is not None:
            user.phone = phone
        if department_id is not None:
            user.department_id = department_id
        if position is not None:
            user.position = position
        if status is not None:
            user.status = status

        # 更新角色
        if role_ids is not None:
            roles = db.query(Role).filter(Role.id.in_(role_ids)).all()
            user.roles = roles

        db.commit()
        db.refresh(user)

        return user

    @staticmethod
    def reset_password(db: Session, user_id: int, new_password: str) -> User:
        """重置密码"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f'用户 ID {user_id} 不存在')

        user.password = UserService.hash_password(new_password)
        db.commit()
        db.refresh(user)

        return user

    @staticmethod
    def delete_user(db: Session, user_id: int) -> bool:
        """删除用户"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f'用户 ID {user_id} 不存在')

        # 禁止删除超级管理员
        if user.is_admin:
            raise ValueError('不能删除超级管理员')

        db.delete(user)
        db.commit()

        return True

    @staticmethod
    def update_login_info(db: Session, user_id: int, ip: str):
        """更新登录信息"""
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.last_login_at = datetime.now()
            user.last_login_ip = ip
            db.commit()
