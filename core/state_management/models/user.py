"""
用户模型
支持基于角色的访问控制 (RBAC)
"""
from datetime import datetime
from typing import Optional, Dict, Any
from flask_login import UserMixin
from utils.mongodb_handler import MongoDBHandler
import logging

logger = logging.getLogger(__name__)


class User(UserMixin):
    """
    用户模型类
    使用 MongoDB 存储用户信息
    集成 Flask-Login 的 UserMixin 提供会话管理
    """

    # 用户角色常量
    ROLE_ADMIN = 'admin'
    ROLE_USER = 'user'
    VALID_ROLES = [ROLE_ADMIN, ROLE_USER]

    def __init__(self, user_data: Dict[str, Any]):
        """
        初始化用户对象

        Args:
            user_data: 用户数据字典
        """
        self.username = user_data.get('username')
        self.email = user_data.get('email')
        self.password_hash = user_data.get('password_hash')
        self.role = user_data.get('role', self.ROLE_USER)
        self.is_active = user_data.get('is_active', True)
        self.created_at = user_data.get('created_at')
        self.updated_at = user_data.get('updated_at')
        self.last_login = user_data.get('last_login')

    def get_id(self) -> str:
        """
        Flask-Login 要求的方法
        返回用户的唯一标识符
        """
        return self.username

    def is_admin(self) -> bool:
        """检查用户是否为管理员"""
        return self.role == self.ROLE_ADMIN

    @property
    def is_active(self) -> bool:
        """Flask-Login uses this to check if the user account is active."""
        return getattr(self, '_is_active', True)

    @is_active.setter
    def is_active(self, value: bool) -> None:
        self._is_active = bool(value)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（不包含密码哈希）"""
        return {
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'is_active': self.is_active,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'last_login': self.last_login
        }

    @staticmethod
    def get_collection():
        """获取用户集合"""
        db_handler = MongoDBHandler()
        return db_handler.get_collection('users')

    @classmethod
    def find_by_username(cls, username: str) -> Optional['User']:
        """
        根据用户名查找用户

        Args:
            username: 用户名

        Returns:
            User 对象或 None
        """
        try:
            collection = cls.get_collection()
            user_data = collection.find_one({'username': username})

            if user_data:
                return cls(user_data)
            return None
        except Exception as e:
            logger.error(f"查找用户失败: {str(e)}")
            return None

    @classmethod
    def find_by_email(cls, email: str) -> Optional['User']:
        """
        根据邮箱查找用户

        Args:
            email: 邮箱地址

        Returns:
            User 对象或 None
        """
        try:
            collection = cls.get_collection()
            user_data = collection.find_one({'email': email})

            if user_data:
                return cls(user_data)
            return None
        except Exception as e:
            logger.error(f"查找用户失败: {str(e)}")
            return None

    @classmethod
    def create(cls, username: str, email: str, password_hash: str,
               role: str = ROLE_USER) -> Optional['User']:
        """
        创建新用户

        Args:
            username: 用户名
            email: 邮箱
            password_hash: 密码哈希
            role: 用户角色

        Returns:
            User 对象或 None
        """
        try:
            # 验证角色
            if role not in cls.VALID_ROLES:
                logger.error(f"无效的角色: {role}")
                return None

            # 检查用户名是否已存在
            if cls.find_by_username(username):
                logger.error(f"用户名已存在: {username}")
                return None

            # 检查邮箱是否已存在
            if cls.find_by_email(email):
                logger.error(f"邮箱已存在: {email}")
                return None

            # 创建用户文档
            now = datetime.utcnow()
            user_data = {
                'username': username,
                'email': email,
                'password_hash': password_hash,
                'role': role,
                'is_active': True,
                'created_at': now,
                'updated_at': now,
                'last_login': None
            }

            collection = cls.get_collection()
            result = collection.insert_one(user_data)

            if result.inserted_id:
                logger.info(f"用户创建成功: {username}")
                return cls(user_data)

            return None
        except Exception as e:
            logger.error(f"创建用户失败: {str(e)}")
            return None

    @classmethod
    def get_all(cls, include_inactive: bool = False) -> list:
        """
        获取所有用户

        Args:
            include_inactive: 是否包含未激活的用户

        Returns:
            User 对象列表
        """
        try:
            collection = cls.get_collection()
            query = {} if include_inactive else {'is_active': True}

            users = []
            for user_data in collection.find(query):
                users.append(cls(user_data))

            return users
        except Exception as e:
            logger.error(f"获取用户列表失败: {str(e)}")
            return []

    def update(self, **kwargs) -> bool:
        """
        更新用户信息

        Args:
            **kwargs: 要更新的字段

        Returns:
            是否更新成功
        """
        try:
            # 允许更新的字段
            allowed_fields = ['email', 'password_hash', 'role', 'is_active']
            update_data = {}

            for key, value in kwargs.items():
                if key in allowed_fields:
                    if key == 'role' and value not in self.VALID_ROLES:
                        logger.error(f"无效的角色: {value}")
                        return False
                    update_data[key] = value

            if not update_data:
                return True

            # 添加更新时间
            update_data['updated_at'] = datetime.utcnow()

            collection = self.get_collection()
            result = collection.update_one(
                {'username': self.username},
                {'$set': update_data}
            )

            if result.modified_count > 0:
                # 更新当前对象的属性
                for key, value in update_data.items():
                    setattr(self, key, value)
                logger.info(f"用户信息更新成功: {self.username}")
                return True

            return False
        except Exception as e:
            logger.error(f"更新用户失败: {str(e)}")
            return False

    def update_last_login(self) -> bool:
        """更新最后登录时间"""
        try:
            now = datetime.utcnow()
            collection = self.get_collection()
            result = collection.update_one(
                {'username': self.username},
                {'$set': {'last_login': now}}
            )

            if result.modified_count > 0:
                self.last_login = now
                return True
            return False
        except Exception as e:
            logger.error(f"更新登录时间失败: {str(e)}")
            return False

    def delete(self) -> bool:
        """
        删除用户（软删除，设置 is_active 为 False）

        Returns:
            是否删除成功
        """
        return self.update(is_active=False)

    @classmethod
    def delete_permanently(cls, username: str) -> bool:
        """
        永久删除用户

        Args:
            username: 用户名

        Returns:
            是否删除成功
        """
        try:
            collection = cls.get_collection()
            result = collection.delete_one({'username': username})

            if result.deleted_count > 0:
                logger.info(f"用户永久删除成功: {username}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除用户失败: {str(e)}")
            return False

    @classmethod
    def create_indexes(cls):
        """创建索引"""
        try:
            collection = cls.get_collection()

            # 用户名唯一索引
            collection.create_index('username', unique=True)

            # 邮箱唯一索引
            collection.create_index('email', unique=True)

            # 角色索引
            collection.create_index('role')

            # 激活状态索引
            collection.create_index('is_active')

            logger.info("用户索引创建成功")
            return True
        except Exception as e:
            logger.error(f"创建索引失败: {str(e)}")
            return False
