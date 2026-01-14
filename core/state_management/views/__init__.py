"""
視圖模組初始化
"""
from flask import Blueprint

# 建立視圖藍圖
views_bp = Blueprint('views', __name__)

# 匯入所有視圖路由
from . import dashboard
from . import config_views
from . import routing_views
from . import instance_views
from . import node_views
from . import user_views
from . import data_views
from . import upload_views
from . import analysis_dashboard
from . import device_views
from . import edge_device_views
