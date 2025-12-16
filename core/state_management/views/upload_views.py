"""
檔案上傳視圖
處理檔案上傳與管理的 Web 介面
"""
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from views import views_bp
from models.routing_rule import RoutingRule
from models.task_execution_log import TaskExecutionLog
from utils.mongodb_handler import get_db
import logging

logger = logging.getLogger(__name__)


@views_bp.route('/uploads')
@login_required
def upload_list():
    """
    上傳記錄列表頁面
    """
    try:
        return render_template('uploads/list.html')
    except Exception as e:
        logger.error(f"載入上傳列表失敗: {str(e)}")
        flash('載入上傳列表失敗', 'danger')
        return redirect(url_for('views.dashboard'))


@views_bp.route('/uploads/create')
@login_required
def upload_create():
    """
    檔案上傳頁面
    """
    try:
        # 取得所有啟用的路由規則供選擇
        rules = RoutingRule.get_all(enabled_only=True)
        
        return render_template(
            'uploads/create.html',
            rules=rules
        )
    except Exception as e:
        logger.error(f"載入上傳頁面失敗: {str(e)}")
        flash('載入上傳頁面失敗', 'danger')
        return redirect(url_for('views.dashboard'))


@views_bp.route('/uploads/<analyze_uuid>')
@login_required
def upload_detail(analyze_uuid):
    """
    上傳詳情頁面（重導向至資料詳情頁）
    """
    return redirect(url_for('views.data_detail', analyze_uuid=analyze_uuid))
