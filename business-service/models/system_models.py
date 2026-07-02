"""
系统管理模块数据模型
包括: 用户(User)、角色(Role)、部门(Department)
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Table, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# 用户-角色关联表(多对多)
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('created_at', DateTime, server_default=func.now())
)


class Department(Base):
    """部门表"""
    __tablename__ = 'departments'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment='部门名称')
    code = Column(String(50), unique=True, nullable=False, comment='部门编码')
    parent_id = Column(Integer, ForeignKey('departments.id', ondelete='CASCADE'), nullable=True, comment='父部门ID')
    leader = Column(String(50), nullable=True, comment='部门负责人')
    phone = Column(String(20), nullable=True, comment='联系电话')
    email = Column(String(100), nullable=True, comment='邮箱')
    sort_order = Column(Integer, default=0, comment='排序')
    status = Column(Boolean, default=True, comment='状态: True=启用, False=禁用')
    description = Column(Text, nullable=True, comment='描述')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')

    # 关系
    parent = relationship('Department', remote_side=[id], backref='children')
    users = relationship('User', back_populates='department')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'parent_id': self.parent_id,
            'leader': self.leader,
            'phone': self.phone,
            'email': self.email,
            'sort_order': self.sort_order,
            'status': self.status,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Role(Base):
    """角色表"""
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, comment='角色名称')
    code = Column(String(50), unique=True, nullable=False, comment='角色编码')
    status = Column(Boolean, default=True, comment='状态: True=启用, False=禁用')
    description = Column(Text, nullable=True, comment='描述')
    permissions = Column(Text, nullable=True, comment='权限列表(JSON格式)')
    sort_order = Column(Integer, default=0, comment='排序')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')

    # 关系
    users = relationship('User', secondary=user_roles, back_populates='roles')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'status': self.status,
            'description': self.description,
            'permissions': self.permissions,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class User(Base):
    """用户表"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True, comment='用户名')
    password = Column(String(255), nullable=False, comment='密码(加密)')
    real_name = Column(String(50), nullable=False, comment='真实姓名')
    email = Column(String(100), unique=True, nullable=True, comment='邮箱')
    phone = Column(String(20), nullable=True, comment='手机号')
    avatar = Column(String(255), nullable=True, comment='头像URL')
    department_id = Column(Integer, ForeignKey('departments.id', ondelete='SET NULL'), nullable=True, comment='部门ID')
    position = Column(String(50), nullable=True, comment='职位')
    status = Column(Boolean, default=True, comment='状态: True=启用, False=禁用')
    is_admin = Column(Boolean, default=False, comment='是否超级管理员')
    last_login_at = Column(DateTime, nullable=True, comment='最后登录时间')
    last_login_ip = Column(String(50), nullable=True, comment='最后登录IP')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')

    # 关系
    department = relationship('Department', back_populates='users')
    roles = relationship('Role', secondary=user_roles, back_populates='users')

    def to_dict(self, include_password=False):
        data = {
            'id': self.id,
            'username': self.username,
            'real_name': self.real_name,
            'email': self.email,
            'phone': self.phone,
            'avatar': self.avatar,
            'department_id': self.department_id,
            'department_name': self.department.name if self.department else None,
            'position': self.position,
            'status': self.status,
            'is_admin': self.is_admin,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
            'last_login_ip': self.last_login_ip,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'roles': [{'id': r.id, 'name': r.name, 'code': r.code} for r in self.roles],
        }
        if include_password:
            data['password'] = self.password
        return data
