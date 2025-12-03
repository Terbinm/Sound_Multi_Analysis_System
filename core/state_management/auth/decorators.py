"""
權限裝飾器
用於控制路由的存取權限
"""
from functools import wraps
from flask import flash, redirect, url_for, abort
from flask_login import current_user
import logging

logger = logging.getLogger(__name__)


def login_required(f):
    """
    要求使用者登入的裝飾器
    Flask-Login 已提供，此處為自訂版本
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('請先登入', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    要求管理員權限的裝飾器
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('請先登入', 'warning')
            return redirect(url_for('auth.login'))

        if not current_user.is_admin():
            logger.warning(f"使用者 {current_user.username} 嘗試存取管理員頁面")
            flash('您沒有權限存取此頁面', 'danger')
            abort(403)

        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    """
    要求特定角色的裝飾器（工廠函式）

    Args:
        *roles: 允許的角色列表

    Usage:
        @role_required('admin', 'user')
        def some_view():
            pass
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('請先登入', 'warning')
                return redirect(url_for('auth.login'))

            if current_user.role not in roles:
                logger.warning(
                    f"使用者 {current_user.username} (角色: {current_user.role}) "
                    f"嘗試存取需要角色 {roles} 的頁面"
                )
                flash('您沒有權限存取此頁面', 'danger')
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def active_required(f):
    """
    要求使用者帳戶啟用狀態的裝飾器
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('請先登入', 'warning')
            return redirect(url_for('auth.login'))

        if not current_user.is_active:
            logger.warning(f"未啟用使用者 {current_user.username} 嘗試存取")
            flash('您的帳戶已被停用，請聯絡管理員', 'danger')
            return redirect(url_for('auth.login'))

        return f(*args, **kwargs)
    return decorated_function
