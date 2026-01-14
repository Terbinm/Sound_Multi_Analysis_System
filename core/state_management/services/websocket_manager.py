"""
WebSocket 管理器
用於管理 WebSocket 連接和事件推送
"""
import logging
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import request
from typing import Dict, Any, Optional, Literal

logger = logging.getLogger(__name__)

class WebSocketManager:
    """WebSocket 管理器"""

    def __init__(self):
        """初始化 WebSocket 管理器"""
        self.socketio: Optional[SocketIO] = None
        self.connected_clients: Dict[str, Dict[str, Any]] = {}
        logger.info("WebSocket 管理器初始化")

    def init_socketio(self, app):
        """
        初始化 SocketIO

        Args:
            app: Flask 應用實例

        Returns:
            SocketIO: SocketIO 實例
        """
        preferred_async_mode = app.config.get('WEBSOCKET_ASYNC_MODE', 'threading')
        async_mode = self._resolve_async_mode(preferred_async_mode)
        ping_timeout = app.config.get('WEBSOCKET_PING_TIMEOUT', 6)  # 與 config.py 一致
        ping_interval = app.config.get('WEBSOCKET_PING_INTERVAL', 2)  # 與 config.py 一致
        cors_allowed_origins = app.config.get('WEBSOCKET_CORS_ALLOWED_ORIGINS', "*")

        self.socketio = SocketIO(
            app,
            cors_allowed_origins=cors_allowed_origins,
            async_mode=async_mode,
            logger=True,
            engineio_logger=False,
            ping_timeout=ping_timeout,
            ping_interval=ping_interval
        )

        # 註冊事件處理器
        self._register_handlers()

        logger.info(
            "SocketIO 初始化完成 (async_mode=%s, ping_timeout=%s, ping_interval=%s)",
            async_mode,
            ping_timeout,
            ping_interval
        )
        return self.socketio

    def _resolve_async_mode(self, preferred: Optional[str]) -> Literal['threading', 'eventlet', 'gevent']:
        """
        驗證並決定 SocketIO async_mode，若指定模式無法使用則回退到 threading。
        """
        normalized = (preferred or 'threading').strip().lower()

        if normalized == 'eventlet':
            try:
                import eventlet  # type: ignore  # noqa: F401
                return 'eventlet'
            except Exception as exc:
                logger.warning(
                    "Eventlet async_mode 無法使用，原因: %s。將自動回退到 threading。",
                    exc,
                    exc_info=True
                )
                return 'threading'
        elif normalized == 'gevent':
            try:
                import gevent  # type: ignore  # noqa: F401
                return 'gevent'
            except Exception as exc:
                logger.warning(
                    "Gevent async_mode 無法使用，原因: %s。將自動回退到 threading。",
                    exc,
                    exc_info=True
                )
                return 'threading'
        elif normalized == 'threading':
            return 'threading'
        else:
            logger.warning("未知的 async_mode '%s'，將改用 threading。", normalized)
            return 'threading'

    def _register_handlers(self):
        """註冊 WebSocket 事件處理器"""
        assert self.socketio is not None, "socketio must be initialized before registering handlers"

        @self.socketio.on('connect')
        def handle_connect():
            """處理客戶端連接"""
            client_id = request.sid
            self.connected_clients[client_id] = {
                'connected_at': None,
                'rooms': set()
            }
            logger.info(f"客戶端連接: {client_id}, 當前連接數: {len(self.connected_clients)}")
            emit('connection_established', {'client_id': client_id})

        @self.socketio.on('disconnect')
        def handle_disconnect():
            """處理客戶端斷開"""
            client_id = request.sid
            if client_id in self.connected_clients:
                del self.connected_clients[client_id]
            logger.info(f"客戶端斷開: {client_id}, 當前連接數: {len(self.connected_clients)}")

        @self.socketio.on('subscribe')
        def handle_subscribe(data):
            """
            處理訂閱房間請求

            Args:
                data: {'room': 'room_name'}
            """
            room = data.get('room')
            if room:
                client_id = request.sid
                join_room(room)
                if client_id in self.connected_clients:
                    self.connected_clients[client_id]['rooms'].add(room)
                logger.info(f"客戶端 {client_id} 訂閱房間: {room}")
                emit('subscribed', {'room': room})

        @self.socketio.on('unsubscribe')
        def handle_unsubscribe(data):
            """
            處理取消訂閱房間請求

            Args:
                data: {'room': 'room_name'}
            """
            room = data.get('room')
            if room:
                client_id = request.sid
                leave_room(room)
                if client_id in self.connected_clients:
                    self.connected_clients[client_id]['rooms'].discard(room)
                logger.info(f"客戶端 {client_id} 取消訂閱房間: {room}")
                emit('unsubscribed', {'room': room})

    # ==================== 節點相關事件 ====================

    def emit_node_registered(self, node_data: Dict[str, Any]):
        """
        推送節點註冊事件

        Args:
            node_data: 節點數據
        """
        self._emit('node.registered', node_data, room='nodes')
        logger.info(f"推送節點註冊事件: {node_data.get('node_id')}")

    def emit_node_heartbeat(self, node_data: Dict[str, Any]):
        """
        推送節點心跳事件

        Args:
            node_data: 節點數據（包含 node_id, status, current_tasks, load_ratio 等）
        """
        self._emit('node.heartbeat', node_data, room='nodes')
        logger.debug(f"推送節點心跳事件: {node_data.get('node_id')}")

    def emit_node_offline(self, node_data: Dict[str, Any]):
        """
        推送節點離線事件

        Args:
            node_data: 節點數據
        """
        self._emit('node.offline', node_data, room='nodes')
        logger.info(f"推送節點離線事件: {node_data.get('node_id')}")

    def emit_node_online(self, node_data: Dict[str, Any]):
        """
        推送節點重新上線事件

        Args:
            node_data: 節點數據
        """
        self._emit('node.online', node_data, room='nodes')
        logger.info(f"推送節點上線事件: {node_data.get('node_id')}")

    def emit_node_status_changed(self, node_data: Dict[str, Any]):
        """
        推送節點狀態變更事件

        Args:
            node_data: 節點數據
        """
        self._emit('node.status_changed', node_data, room='nodes')
        logger.info(f"推送節點狀態變更事件: {node_data.get('node_id')} -> {node_data.get('status')}")

    # ==================== 任務相關事件 ====================

    def emit_task_created(self, task_data: Dict[str, Any]):
        """
        推送任務創建事件

        Args:
            task_data: 任務數據（包含 task_id, rule_id 等）
        """
        rule_id = task_data.get('rule_id')
        # 推送到任務房間
        self._emit('task.created', task_data, room='tasks')
        # 推送到特定規則房間
        if rule_id:
            self._emit('task.created', task_data, room=f'rule_{rule_id}')
        logger.debug(f"推送任務創建事件: {task_data.get('task_id')}")

    def emit_task_status_changed(self, task_data: Dict[str, Any]):
        """
        推送任務狀態變更事件

        Args:
            task_data: 任務數據（包含 task_id, status, rule_id 等）
        """
        rule_id = task_data.get('rule_id')
        # 推送到任務房間
        self._emit('task.status_changed', task_data, room='tasks')
        # 推送到特定規則房間
        if rule_id:
            self._emit('task.status_changed', task_data, room=f'rule_{rule_id}')
        logger.debug(f"推送任務狀態變更事件: {task_data.get('task_id')} -> {task_data.get('status')}")

    # ==================== 統計相關事件 ====================

    def emit_stats_updated(self, stats_data: Dict[str, Any]):
        """
        推送統計數據更新事件

        Args:
            stats_data: 統計數據
        """
        self._emit('stats.updated', stats_data, room='dashboard')
        # 同時推送到 nodes 房間，確保節點列表頁面也能收到
        self._emit('stats.updated', stats_data, room='nodes')
        logger.info(f"推送統計數據更新事件: 總數={stats_data.get('total_nodes')}, 在線={stats_data.get('online_nodes')}")

    def emit_rule_stats_updated(self, rule_id: str, stats_data: Dict[str, Any]):
        """
        推送路由規則統計更新事件

        Args:
            rule_id: 規則 ID
            stats_data: 統計數據
        """
        self._emit('rule.stats_updated', stats_data, room=f'rule_{rule_id}')
        logger.debug(f"推送規則統計更新事件: {rule_id}")

    # ==================== 配置相關事件 ====================

    def emit_config_updated(self, config_data: Dict[str, Any]):
        """
        推送配置更新事件

        Args:
            config_data: 配置數據
        """
        self._emit('config.updated', config_data, room='configs')
        logger.info(f"推送配置更新事件: {config_data.get('config_id')}")

    # ==================== Edge Device 相關事件 ====================

    def emit_edge_device_registered(self, device_data: Dict[str, Any]):
        """
        推送邊緣設備註冊事件

        Args:
            device_data: 設備數據
        """
        self._emit('edge_device.registered', device_data, room='edge_devices')
        logger.info(f"推送邊緣設備註冊事件: {device_data.get('device_id')}")

    def emit_edge_device_offline(self, device_data: Dict[str, Any]):
        """
        推送邊緣設備離線事件

        Args:
            device_data: 設備數據
        """
        self._emit('edge_device.offline', device_data, room='edge_devices')
        logger.info(f"推送邊緣設備離線事件: {device_data.get('device_id')}")

    def emit_edge_device_online(self, device_data: Dict[str, Any]):
        """
        推送邊緣設備上線事件

        Args:
            device_data: 設備數據
        """
        self._emit('edge_device.online', device_data, room='edge_devices')
        logger.info(f"推送邊緣設備上線事件: {device_data.get('device_id')}")

    def emit_edge_device_status_changed(self, device_data: Dict[str, Any]):
        """
        推送邊緣設備狀態變更事件

        Args:
            device_data: 設備數據（包含 device_id, status）
        """
        self._emit('edge_device.status_changed', device_data, room='edge_devices')
        logger.info(f"推送邊緣設備狀態變更事件: {device_data.get('device_id')} -> {device_data.get('status')}")

    def emit_edge_device_heartbeat(self, device_data: Dict[str, Any]):
        """
        推送邊緣設備心跳事件

        Args:
            device_data: 設備數據
        """
        self._emit('edge_device.heartbeat', device_data, room='edge_devices')
        logger.debug(f"推送邊緣設備心跳事件: {device_data.get('device_id')}")

    def emit_edge_device_recording_started(self, data: Dict[str, Any]):
        """
        推送邊緣設備錄音開始事件

        Args:
            data: 錄音數據（包含 device_id, recording_uuid）
        """
        self._emit('edge_device.recording_started', data, room='edge_devices')
        logger.info(f"推送邊緣設備錄音開始事件: {data.get('device_id')}, recording: {data.get('recording_uuid')}")

    def emit_edge_device_recording_progress(self, data: Dict[str, Any]):
        """
        推送邊緣設備錄音進度事件

        Args:
            data: 進度數據（包含 device_id, recording_uuid, progress_percent）
        """
        self._emit('edge_device.recording_progress', data, room='edge_devices')
        logger.debug(f"推送邊緣設備錄音進度事件: {data.get('device_id')}, progress: {data.get('progress_percent')}%")

    def emit_edge_device_recording_completed(self, data: Dict[str, Any]):
        """
        推送邊緣設備錄音完成事件

        Args:
            data: 完成數據（包含 device_id, recording_uuid, result）
        """
        self._emit('edge_device.recording_completed', data, room='edge_devices')
        logger.info(f"推送邊緣設備錄音完成事件: {data.get('device_id')}, recording: {data.get('recording_uuid')}")

    def emit_edge_device_recording_failed(self, data: Dict[str, Any]):
        """
        推送邊緣設備錄音失敗事件

        Args:
            data: 失敗數據（包含 device_id, recording_uuid, error）
        """
        self._emit('edge_device.recording_failed', data, room='edge_devices')
        logger.error(f"推送邊緣設備錄音失敗事件: {data.get('device_id')}, error: {data.get('error')}")

    def emit_edge_device_stats_updated(self, stats_data: Dict[str, Any]):
        """
        推送邊緣設備統計更新事件

        Args:
            stats_data: 統計數據
        """
        self._emit('edge_device.stats_updated', stats_data, room='edge_devices')
        logger.info(f"推送邊緣設備統計更新事件: 總數={stats_data.get('total_devices')}, 在線={stats_data.get('online_devices')}")

    def emit_instance_updated(self, instance_data: Dict[str, Any]):
        """
        推送實例更新事件

        Args:
            instance_data: 實例數據
        """
        self._emit('instance.updated', instance_data, room='instances')
        logger.info(f"推送實例更新事件: {instance_data.get('instance_id')}")

    # ==================== 通用方法 ====================

    def broadcast(self, event: str, data: Dict[str, Any], room: Optional[str] = None):
        """
        廣播事件

        Args:
            event: 事件名稱
            data: 數據
            room: 房間名稱（可選）
        """
        if room:
            self._emit(event, data, room=room)
        else:
            self._emit(event, data, broadcast=True)
        logger.debug(f"廣播事件: {event} 到房間: {room if room else '全部'}")

    def get_connected_clients_count(self) -> int:
        """獲取當前連接的客戶端數量"""
        return len(self.connected_clients)


# ==================== 輔助方法 ====================

    def _emit(self, event: str, data: Any, **kwargs):
        """封裝 emit，確保資料可被 JSON 序列化"""
        if not self.socketio:
            logger.warning(f"WebSocket 未初始化，無法推送事件: {event}")
            return

        payload = self._prepare_payload(data)
        
        # 記錄推送詳情（僅在 DEBUG 模式）
        room = kwargs.get('room')
        if room:
            logger.debug(f"推送事件 {event} 到房間 {room}")
        else:
            logger.debug(f"廣播事件 {event}")
        
        self.socketio.emit(event, payload, **kwargs)

    def _prepare_payload(self, data: Any):
        if data is None:
            return None
        return self._normalize_value(data)

    def _normalize_value(self, value: Any):
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Mapping):
            return {k: self._normalize_value(v) for k, v in value.items()}
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self._normalize_value(v) for v in value]
        return value


# 全局 WebSocket 管理器實例
websocket_manager = WebSocketManager()
