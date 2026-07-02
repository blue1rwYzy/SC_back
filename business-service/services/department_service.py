"""
部门管理服务
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_
from models.system_models import Department
from typing import List, Optional, Tuple, Dict


class DepartmentService:
    """部门管理服务"""

    @staticmethod
    def get_department_by_id(db: Session, dept_id: int) -> Optional[Department]:
        """根据ID获取部门"""
        return db.query(Department).filter(Department.id == dept_id).first()

    @staticmethod
    def get_department_by_code(db: Session, code: str) -> Optional[Department]:
        """根据编码获取部门"""
        return db.query(Department).filter(Department.code == code).first()

    @staticmethod
    def get_all_departments(db: Session, status: bool = None) -> List[Department]:
        """获取所有部门(平铺列表)"""
        query = db.query(Department)

        if status is not None:
            query = query.filter(Department.status == status)

        return query.order_by(Department.sort_order.asc()).all()

    @staticmethod
    def get_department_tree(db: Session, status: bool = None) -> List[Dict]:
        """
        获取部门树形结构

        Returns:
            树形结构的部门列表
        """
        query = db.query(Department)

        if status is not None:
            query = query.filter(Department.status == status)

        all_depts = query.order_by(Department.sort_order.asc()).all()

        # 构建树形结构
        def build_tree(parent_id=None):
            children = []
            for dept in all_depts:
                if dept.parent_id == parent_id:
                    dept_dict = dept.to_dict()
                    dept_dict['children'] = build_tree(dept.id)
                    # 统计用户数
                    dept_dict['user_count'] = len(dept.users)
                    children.append(dept_dict)
            return children

        return build_tree()

    @staticmethod
    def get_departments_paginated(
        db: Session,
        page: int = 1,
        page_size: int = 10,
        keyword: str = None,
        status: bool = None
    ) -> Tuple[List[Department], int]:
        """
        分页获取部门列表(平铺)

        Returns:
            (departments, total): 部门列表和总数
        """
        query = db.query(Department)

        # 搜索条件
        if keyword:
            query = query.filter(
                or_(
                    Department.name.like(f'%{keyword}%'),
                    Department.code.like(f'%{keyword}%'),
                    Department.leader.like(f'%{keyword}%')
                )
            )

        # 状态筛选
        if status is not None:
            query = query.filter(Department.status == status)

        # 总数
        total = query.count()

        # 分页
        departments = query.order_by(Department.sort_order.asc()).offset((page - 1) * page_size).limit(page_size).all()

        return departments, total

    @staticmethod
    def create_department(
        db: Session,
        name: str,
        code: str,
        parent_id: int = None,
        leader: str = None,
        phone: str = None,
        email: str = None,
        sort_order: int = 0,
        description: str = None
    ) -> Department:
        """创建部门"""

        # 检查编码是否存在
        existing = db.query(Department).filter(Department.code == code).first()
        if existing:
            raise ValueError(f'部门编码 {code} 已存在')

        # 检查父部门是否存在
        if parent_id is not None:
            parent = db.query(Department).filter(Department.id == parent_id).first()
            if not parent:
                raise ValueError(f'父部门 ID {parent_id} 不存在')

        # 创建部门
        department = Department(
            name=name,
            code=code,
            parent_id=parent_id,
            leader=leader,
            phone=phone,
            email=email,
            sort_order=sort_order,
            status=True,
            description=description
        )

        db.add(department)
        db.commit()
        db.refresh(department)

        return department

    @staticmethod
    def update_department(
        db: Session,
        dept_id: int,
        name: str = None,
        code: str = None,
        parent_id: int = None,
        leader: str = None,
        phone: str = None,
        email: str = None,
        sort_order: int = None,
        status: bool = None,
        description: str = None
    ) -> Department:
        """更新部门"""
        department = db.query(Department).filter(Department.id == dept_id).first()
        if not department:
            raise ValueError(f'部门 ID {dept_id} 不存在')

        # 更新字段
        if name is not None:
            department.name = name

        if code is not None:
            # 检查编码是否被其他部门使用
            if code != department.code:
                existing = db.query(Department).filter(Department.code == code, Department.id != dept_id).first()
                if existing:
                    raise ValueError(f'部门编码 {code} 已被其他部门使用')
            department.code = code

        if parent_id is not None:
            # 检查父部门是否存在
            if parent_id != department.id:  # 不能设置自己为父部门
                parent = db.query(Department).filter(Department.id == parent_id).first()
                if not parent:
                    raise ValueError(f'父部门 ID {parent_id} 不存在')
                department.parent_id = parent_id
            else:
                raise ValueError('不能将部门设置为自己的父部门')

        if leader is not None:
            department.leader = leader

        if phone is not None:
            department.phone = phone

        if email is not None:
            department.email = email

        if sort_order is not None:
            department.sort_order = sort_order

        if status is not None:
            department.status = status

        if description is not None:
            department.description = description

        db.commit()
        db.refresh(department)

        return department

    @staticmethod
    def delete_department(db: Session, dept_id: int) -> bool:
        """删除部门"""
        department = db.query(Department).filter(Department.id == dept_id).first()
        if not department:
            raise ValueError(f'部门 ID {dept_id} 不存在')

        # 检查是否有子部门
        children = db.query(Department).filter(Department.parent_id == dept_id).count()
        if children > 0:
            raise ValueError(f'部门 {department.name} 下还有 {children} 个子部门，无法删除')

        # 检查是否有用户
        if department.users:
            raise ValueError(f'部门 {department.name} 下还有 {len(department.users)} 个用户，无法删除')

        db.delete(department)
        db.commit()

        return True

    @staticmethod
    def get_department_users(db: Session, dept_id: int, include_children: bool = False):
        """
        获取部门下的用户

        Args:
            dept_id: 部门ID
            include_children: 是否包含子部门的用户
        """
        department = db.query(Department).filter(Department.id == dept_id).first()
        if not department:
            raise ValueError(f'部门 ID {dept_id} 不存在')

        if not include_children:
            return [user.to_dict() for user in department.users]

        # 包含子部门的用户
        def get_all_dept_ids(dept):
            ids = [dept.id]
            for child in dept.children:
                ids.extend(get_all_dept_ids(child))
            return ids

        dept_ids = get_all_dept_ids(department)
        users = []
        for dept_id in dept_ids:
            dept = db.query(Department).filter(Department.id == dept_id).first()
            if dept:
                users.extend([user.to_dict() for user in dept.users])

        return users
