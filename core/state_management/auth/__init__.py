"""
認證模組初始化
"""
from flask import Blueprint

# 建立認證藍圖
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# 匯入路由
from . import routes
