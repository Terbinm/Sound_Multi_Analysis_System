"""
狀態管理系統主應用
提供 REST API 和 Web UI 管理界面
"""
import os
import sys
import logging
import threading
from pathlib import Path

# 確保可以從任何入口載入 core/state_management 內的模組
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from flask import Flask, jsonify, redirect, url_for
from flask_cors import CORS
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from config import get_config
from services.websocket_manager import websocket_manager

csrf = CSRFProtect()

# 配置日誌
def setup_logging(config):
    """配置日誌系統"""
    import glob
    from datetime import datetime

    os.makedirs(config.LOG_DIR, exist_ok=True)

    # 如果啟用「啟動時清除日誌」功能（僅供 debug 使用）
    if config.CLEAR_LOGS_ON_STARTUP:
        log_files = glob.glob(os.path.join(config.LOG_DIR, 'SM_*.log'))
        for log_file in log_files:
            try:
                os.remove(log_file)
            except Exception as e:
                print(f"無法刪除日誌檔案 {log_file}: {e}", file=sys.stderr)
        print(f"已清除 {len(log_files)} 個日誌檔案（CLEAR_LOGS_ON_STARTUP=true）", file=sys.stdout)
    else:
        # 不清除日誌，但清理超過數量限制的舊日誌
        existing_logs = glob.glob(os.path.join(config.LOG_DIR, 'SM_*.log'))
        if len(existing_logs) >= config.LOG_BACKUP_COUNT:
            # 按修改時間排序
            existing_logs.sort(key=os.path.getmtime, reverse=True)
            # 刪除超過數量的舊日誌
            logs_to_delete = existing_logs[config.LOG_BACKUP_COUNT - 1:]  # 保留空間給新日誌
            for log_file in logs_to_delete:
                try:
                    os.remove(log_file)
                    print(f"刪除舊日誌: {os.path.basename(log_file)}", file=sys.stdout)
                except Exception as e:
                    print(f"無法刪除舊日誌 {log_file}: {e}", file=sys.stderr)

    # 每次啟動都建立新的日誌檔案
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file_path = os.path.join(config.LOG_DIR, f'SM_{timestamp}.log')
    print(f"建立新日誌檔案: {log_file_path}", file=sys.stdout)

    # 使用普通的 FileHandler（不自動輪替）
    file_handler = logging.FileHandler(
        filename=log_file_path,
        encoding='utf-8'
    )

    # 配置根日誌記錄器
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format=config.LOG_FORMAT,
        datefmt=config.LOG_DATE_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
            file_handler
        ]
    )


def create_app():
    """創建並配置 Flask 應用"""
    # 創建 Flask 應用
    app = Flask(__name__)

    # 加載配置
    config = get_config()
    app.config.from_object(config)

    # 設置日誌
    setup_logging(config)
    logger = logging.getLogger(__name__)
    logger.info(f"啟動狀態管理系統 (環境: {config.FLASK_ENV})")

    # 啟用 CORS（僅對 API 端點）
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # 初始化擴展
    bcrypt = Bcrypt(app)
    csrf.init_app(app)
    login_manager = LoginManager(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '請先登錄'
    login_manager.login_message_category = 'warning'

    # 初始化 WebSocket
    socketio = websocket_manager.init_socketio(app)
    # 將 socketio 存儲到 app 配置中，以便其他模組訪問
    app.config['SOCKETIO'] = socketio
    logger.info("WebSocket 服務已初始化")

    # 用戶加載器
    @login_manager.user_loader
    def load_user(username):
        from models.user import User
        return User.find_by_username(username)

    # 註冊 API 藍圖
    from api.config_api import config_bp
    from api.routing_api import routing_bp
    from api.node_api import node_bp
    from api.instance_api import instance_bp
    from api.upload_api import upload_bp

    app.register_blueprint(config_bp, url_prefix='/api/configs')
    app.register_blueprint(routing_bp, url_prefix='/api/routing')
    app.register_blueprint(node_bp, url_prefix='/api/nodes')
    app.register_blueprint(instance_bp, url_prefix='/api/instances')
    app.register_blueprint(upload_bp, url_prefix='/api/uploads')

    # API 僅透過 JSON 驗證，移除 CSRF 限制
    for bp in (config_bp, routing_bp, node_bp, instance_bp, upload_bp):
        csrf.exempt(bp)

    # 註冊 Web UI 藍圖
    from auth import auth_bp
    from views import views_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)

    # 健康檢查端點
    @app.route('/health', methods=['GET'])
    def health_check():
        """健康檢查"""
        return jsonify({
            'status': 'healthy',
            'service': config.SERVICE_NAME,
            'version': config.VERSION
        }), 200

    # 首頁 - 重定向到儀表板或登錄頁
    @app.route('/', methods=['GET'])
    def index():
        """首頁"""
        from flask_login import current_user
        if current_user.is_authenticated:
            return redirect(url_for('views.dashboard'))
        return redirect(url_for('auth.login'))

    # API 信息端點
    @app.route('/api', methods=['GET'])
    def api_info():
        """API 信息"""
        return jsonify({
            'service': '狀態管理系統',
            'version': config.VERSION,
            'endpoints': {
                'configs': '/api/configs',
                'routing': '/api/routing',
                'nodes': '/api/nodes',
                'instances': '/api/instances',
                'health': '/health'
            }
        }), 200

    # 錯誤處理
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal error: {error}")
        return jsonify({'error': 'Internal server error'}), 500

    # 啟動後台服務
    def start_background_services():
        """啟動後台服務（任務調度器、節點監控器）"""
        logger.info("啟動後台服務...")

        try:
            from services.task_scheduler import TaskScheduler
            from services.node_monitor import NodeMonitor

            # 啟動任務調度器
            scheduler = TaskScheduler()
            scheduler_thread = threading.Thread(
                target=scheduler.start,
                daemon=True,
                name='TaskScheduler'
            )
            scheduler_thread.start()
            logger.info("任務調度器已啟動")

            # 啟動節點監控器
            monitor = NodeMonitor()
            monitor_thread = threading.Thread(
                target=monitor.start,
                daemon=True,
                name='NodeMonitor'
            )
            monitor_thread.start()
            logger.info("節點監控器已啟動")

        except Exception as e:
            logger.error(f"啟動後台服務失敗: {e}", exc_info=True)

    # 在應用啟動後執行
    with app.app_context():
        # 初始化數據庫連接（檢查連接）
        try:
            from utils.mongodb_handler import get_db
            db = get_db()
            # 測試連接
            db.command('ping')
            logger.info("MongoDB 連接成功")
        except Exception as e:
            logger.warning(f"MongoDB 連接失敗: {e}")

        # 啟動後台服務
        start_background_services()

    return app, socketio


# 創建應用實例
app, socketio = create_app()

if __name__ == '__main__':
    config = get_config()
    run_kwargs = {
        'host': config.HOST,
        'port': config.PORT,  # 核心服務狀態管理端口
        'debug': config.DEBUG,
        'use_reloader': False,  # 避免重複啟動後台服務
    }

    async_mode = getattr(socketio, 'async_mode', None)
    if async_mode == 'threading':
        # Flask 3 / Werkzeug 3 需明確允許在非調試場合使用內建伺服器
        run_kwargs['allow_unsafe_werkzeug'] = True
        logging.getLogger(__name__).warning(
            "目前使用 Werkzeug (threading) 模式啟動 WebSocket，僅建議用於開發/測試。"
            "如需正式環境請安裝 eventlet 或 gevent。"
        )

    # 使用 socketio.run 而不是 app.run，以支持 WebSocket
    socketio.run(app, **run_kwargs)
