"""
系统初始化服务
负责创建默认数据: 超级管理员、默认角色、默认部门等
"""
from sqlalchemy.orm import Session
from models.system_models import User, Role, Department
import hashlib
import json


def hash_password(password: str) -> str:
    """加密密码 - 使用SHA256"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def init_system_data(db: Session):
    """初始化系统数据"""

    # 1. 检查是否已初始化
    existing_admin = db.query(User).filter(User.username == 'admin').first()
    if existing_admin:
        print('✅ 系统已初始化，跳过')
        return

    print('🚀 开始初始化系统数据...')

    # 2. 创建默认部门
    print('📁 创建默认部门...')
    root_dept = Department(
        name='总公司',
        code='ROOT',
        parent_id=None,
        leader='系统管理员',
        sort_order=0,
        status=True,
        description='顶级部门'
    )
    db.add(root_dept)
    db.flush()  # 获取ID

    tech_dept = Department(
        name='技术部',
        code='TECH',
        parent_id=root_dept.id,
        leader='技术负责人',
        sort_order=1,
        status=True,
        description='技术研发部门'
    )
    db.add(tech_dept)

    admin_dept = Department(
        name='行政部',
        code='ADMIN',
        parent_id=root_dept.id,
        leader='行政负责人',
        sort_order=2,
        status=True,
        description='行政管理部门'
    )
    db.add(admin_dept)
    db.flush()

    # 3. 创建默认角色
    print('👥 创建默认角色...')

    # 超级管理员角色(所有权限)
    admin_role = Role(
        name='超级管理员',
        code='SUPER_ADMIN',
        status=True,
        description='系统超级管理员，拥有所有权限',
        permissions=json.dumps({
            'system': ['user:view', 'user:add', 'user:edit', 'user:delete',
                      'role:view', 'role:add', 'role:edit', 'role:delete',
                      'dept:view', 'dept:add', 'dept:edit', 'dept:delete'],
            'defect': ['detect:view', 'detect:run', 'detect:delete',
                      'model:view', 'model:upload', 'model:delete'],
            'tracking': ['track:view', 'track:run', 'track:delete'],
            'database': ['image:view', 'image:upload', 'image:delete',
                        'video:view', 'video:upload', 'video:delete'],
        }),
        sort_order=0
    )
    db.add(admin_role)

    # 普通用户角色(只读权限)
    user_role = Role(
        name='普通用户',
        code='USER',
        status=True,
        description='普通用户，拥有查看权限',
        permissions=json.dumps({
            'defect': ['detect:view'],
            'tracking': ['track:view'],
            'database': ['image:view', 'video:view'],
        }),
        sort_order=1
    )
    db.add(user_role)

    # 技术员角色(操作权限)
    tech_role = Role(
        name='技术员',
        code='TECHNICIAN',
        status=True,
        description='技术员，拥有检测和追踪权限',
        permissions=json.dumps({
            'defect': ['detect:view', 'detect:run'],
            'tracking': ['track:view', 'track:run'],
            'database': ['image:view', 'image:upload', 'video:view', 'video:upload'],
        }),
        sort_order=2
    )
    db.add(tech_role)
    db.flush()

    # 4. 创建默认用户
    print('👤 创建默认用户...')

    # 超级管理员
    admin_user = User(
        username='admin',
        password=hash_password('admin123'),  # 默认密码
        real_name='系统管理员',
        email='admin@example.com',
        phone='13800138000',
        department_id=root_dept.id,
        position='超级管理员',
        status=True,
        is_admin=True
    )
    admin_user.roles.append(admin_role)
    db.add(admin_user)

    # 测试用户
    test_user = User(
        username='test',
        password=hash_password('test123'),
        real_name='测试用户',
        email='test@example.com',
        phone='13900139000',
        department_id=tech_dept.id,
        position='技术员',
        status=True,
        is_admin=False
    )
    test_user.roles.append(tech_role)
    db.add(test_user)

    # 5. 提交事务
    db.commit()

    print('✅ 系统数据初始化完成!')
    print('📝 默认账号:')
    print('   管理员 - 用户名: admin, 密码: admin123')
    print('   测试用户 - 用户名: test, 密码: test123')
