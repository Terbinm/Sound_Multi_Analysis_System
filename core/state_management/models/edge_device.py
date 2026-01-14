"""
邊緣設備模型

使用 MongoDB 存儲邊緣錄音設備的狀態與配置資訊
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from utils.mongodb_handler import get_db
from config import get_config

logger = logging.getLogger(__name__)


class OfflineReason:
    """離線原因常數"""
    NEVER_CONNECTED = 'never_connected'      # 從未連線
    HEARTBEAT_TIMEOUT = 'heartbeat_timeout'  # 心跳超時
    CONNECTION_LOST = 'connection_lost'      # 連線中斷（收到 disconnect 事件）

    # 離線原因對應的顯示文字
    DISPLAY_TEXT = {
        NEVER_CONNECTED: '從未連線',
        HEARTBEAT_TIMEOUT: '心跳超時',
        CONNECTION_LOST: '連線中斷',
    }

    @classmethod
    def get_display_text(cls, reason: Optional[str]) -> str:
        """取得離線原因的顯示文字"""
        if not reason:
            return '未知原因'
        return cls.DISPLAY_TEXT.get(reason, '未知原因')


# 視為「在線」的狀態值
ONLINE_STATUSES = ('IDLE', 'RECORDING')


@dataclass
class EdgeDeviceRecord:
    """提供給視圖層使用的邊緣設備資料模型"""

    device_id: str
    device_name: str
    status: str = "OFFLINE"  # IDLE / OFFLINE / RECORDING
    platform: str = "unknown"  # linux / win32 / darwin

    # 離線原因
    offline_reason: Optional[str] = None

    # 音訊配置
    audio_config: Dict[str, Any] = field(default_factory=dict)

    # 排程配置
    schedule_config: Dict[str, Any] = field(default_factory=dict)

    # 連線資訊
    connection_info: Dict[str, Any] = field(default_factory=dict)

    # 統計資訊
    statistics: Dict[str, Any] = field(default_factory=dict)

    # 路由配置 - 錄音完成後自動發送至指定路由分析
    assigned_router_ids: List[str] = field(default_factory=list)

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        # 設定預設的音訊配置
        if not self.audio_config:
            self.audio_config = {
                'default_device_index': 0,
                'channels': 1,
                'sample_rate': 16000,
                'bit_depth': 16,
                'available_devices': []
            }

        # 設定預設的排程配置
        if not self.schedule_config:
            self.schedule_config = {
                'enabled': False,
                'interval_seconds': 3600,
                'duration_seconds': 10,
                'start_time': None,
                'end_time': None,
                'max_success_count': None  # 錄製成功數量上限（累計），達到後自動停用排程
            }

        # 設定預設的統計資訊
        if not self.statistics:
            self.statistics = {
                'total_recordings': 0,
                'last_recording_at': None,
                'success_count': 0,
                'error_count': 0
            }

    def is_online(self) -> bool:
        """檢查設備是否在線"""
        return self.status in ('IDLE', 'RECORDING')

    def is_recording(self) -> bool:
        """檢查設備是否正在錄音"""
        return self.status == 'RECORDING'

    def get_offline_reason_display(self) -> str:
        """取得離線原因的顯示文字"""
        return OfflineReason.get_display_text(self.offline_reason)


class EdgeDevice:
    """邊緣設備類別 - 使用 MongoDB 存儲"""

    # 集合名稱（可透過環境變數配置）
    _COLLECTION_NAME = 'edge_devices'

    @staticmethod
    def _get_collection_name():
        """從 config 獲取集合名稱"""
        config = get_config()
        # 嘗試從 COLLECTIONS 獲取，若不存在則使用預設值
        return config.COLLECTIONS.get('edge_devices', EdgeDevice._COLLECTION_NAME)

    @staticmethod
    def _get_timeout() -> int:
        """獲取心跳逾時時間（秒）"""
        config = get_config()
        # 嘗試獲取 Edge Device 專用的逾時設定，否則使用節點逾時設定
        return getattr(config, 'EDGE_HEARTBEAT_TIMEOUT', config.NODE_HEARTBEAT_TIMEOUT)

    @staticmethod
    def generate_device_id() -> str:
        """生成新的設備 ID"""
        return str(uuid.uuid4())

    @staticmethod
    def register(
        device_id: Optional[str],
        device_name: str,
        platform: str,
        audio_devices: Optional[List[Dict[str, Any]]] = None,
        socket_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        註冊或重連邊緣設備

        處理三種情況：
        1. 有 device_id 且資料庫存在 → 重連（只更新連線資訊）
        2. 有 device_id 但資料庫不存在 → 自動恢復（用該 ID 創建新記錄）
        3. 無 device_id → 首次註冊（生成新 ID 並創建記錄）

        Args:
            device_id: 設備 ID（可選，為空則生成新 ID）
            device_name: 設備名稱
            platform: 平台（linux / win32 / darwin）
            audio_devices: 可用的音訊設備列表
            socket_id: WebSocket 連線 ID
            ip_address: 客戶端 IP 位址

        Returns:
            包含 device_id 和註冊結果的字典
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]
            now = datetime.now(timezone.utc)

            is_new_device = False

            # 情況 1 & 2：客戶端有 device_id，先檢查資料庫是否存在
            if device_id:
                existing_device = collection.find_one({'_id': device_id})
                if existing_device:
                    # 設備已存在，只更新連線資訊（重連流程）
                    update_data = {
                        'status': 'IDLE',
                        'connection_info.socket_id': socket_id,
                        'connection_info.ip_address': ip_address,
                        'connection_info.connected_at': now,
                        'connection_info.last_heartbeat': now,
                        'updated_at': now
                    }
                    # 更新音訊設備列表（如果有提供）
                    if audio_devices is not None:
                        update_data['audio_config.available_devices'] = audio_devices

                    collection.update_one({'_id': device_id}, {'$set': update_data})
                    logger.info(f"邊緣設備重連成功: {device_id} ({device_name})")
                    return {
                        'success': True,
                        'device_id': device_id,
                        'is_new': False
                    }
                else:
                    # 設備不存在但有 ID，使用該 ID 進行註冊（自動恢復）
                    is_new_device = True
            else:
                # 情況 3：無 device_id，生成新的（首次註冊）
                device_id = EdgeDevice.generate_device_id()
                is_new_device = True

            # 新設備：執行完整的初始化
            update_data = {
                '$set': {
                    'device_name': device_name,
                    'status': 'IDLE',
                    'platform': platform,
                    'connection_info.socket_id': socket_id,
                    'connection_info.ip_address': ip_address,
                    'connection_info.connected_at': now,
                    'connection_info.last_heartbeat': now,
                    'updated_at': now
                },
                '$setOnInsert': {
                    'audio_config': {
                        'default_device_index': 0,
                        'channels': 1,
                        'sample_rate': 16000,
                        'bit_depth': 16,
                        'available_devices': audio_devices or []
                    },
                    'schedule_config': {
                        'enabled': False,
                        'interval_seconds': 3600,
                        'duration_seconds': 10,
                        'start_time': None,
                        'end_time': None,
                        'max_success_count': None  # 錄製成功數量上限
                    },
                    'statistics': {
                        'total_recordings': 0,
                        'last_recording_at': None,
                        'success_count': 0,
                        'error_count': 0
                    },
                    'assigned_router_ids': [],
                    'created_at': now
                }
            }

            collection.update_one(
                {'_id': device_id},
                update_data,
                upsert=True
            )

            logger.info(f"邊緣設備已註冊: {device_id} ({device_name})")
            return {
                'success': True,
                'device_id': device_id,
                'is_new': is_new_device
            }

        except Exception as e:
            logger.error(f"註冊邊緣設備失敗: {e}")
            return {
                'success': False,
                'device_id': device_id,
                'error': str(e)
            }

    @staticmethod
    def update_heartbeat(device_id: str, status: str = None, current_recording: str = None) -> bool:
        """
        更新設備心跳

        Args:
            device_id: 設備 ID
            status: 當前狀態（可選）
            current_recording: 當前正在進行的錄音 UUID（可選）

        Returns:
            是否成功
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]

            update_data = {
                'connection_info.last_heartbeat': datetime.now(timezone.utc),
                'updated_at': datetime.now(timezone.utc)
            }

            if status:
                update_data['status'] = status

            if current_recording is not None:
                update_data['connection_info.current_recording'] = current_recording

            result = collection.update_one(
                {'_id': device_id},
                {'$set': update_data}
            )

            if result.modified_count > 0:
                logger.debug(f"邊緣設備心跳已更新: {device_id}")
                return True
            else:
                logger.warning(f"邊緣設備不存在或心跳未更新: {device_id}")
                return False

        except Exception as e:
            logger.error(f"更新邊緣設備心跳失敗 ({device_id}): {e}")
            return False

    @staticmethod
    def set_offline(device_id: str, reason: str = None) -> bool:
        """
        設定設備為離線狀態

        Args:
            device_id: 設備 ID
            reason: 離線原因（使用 OfflineReason 常數）

        Returns:
            是否成功
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]

            # 若未指定原因，預設為連線中斷
            if reason is None:
                reason = OfflineReason.CONNECTION_LOST

            result = collection.update_one(
                {'_id': device_id},
                {
                    '$set': {
                        'status': 'OFFLINE',
                        'offline_reason': reason,
                        'connection_info.socket_id': None,
                        'connection_info.current_recording': None,
                        'updated_at': datetime.now(timezone.utc)
                    }
                }
            )

            if result.modified_count > 0:
                reason_text = OfflineReason.get_display_text(reason)
                logger.info(f"邊緣設備已設為離線: {device_id}，原因: {reason_text}")
                return True
            return False

        except Exception as e:
            logger.error(f"設定邊緣設備離線失敗 ({device_id}): {e}")
            return False

    @staticmethod
    def update_status(device_id: str, status: str) -> bool:
        """
        更新設備狀態

        Args:
            device_id: 設備 ID
            status: 新狀態（IDLE / OFFLINE / RECORDING）

        Returns:
            是否成功
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]

            result = collection.update_one(
                {'_id': device_id},
                {
                    '$set': {
                        'status': status,
                        'updated_at': datetime.now(timezone.utc)
                    }
                }
            )

            if result.modified_count > 0:
                logger.info(f"邊緣設備狀態已更新: {device_id} -> {status}")
                return True
            return False

        except Exception as e:
            logger.error(f"更新邊緣設備狀態失敗 ({device_id}): {e}")
            return False

    @staticmethod
    def is_alive(device_id: str, timeout_seconds: Optional[int] = None) -> bool:
        """
        檢查設備是否存活（根據心跳時間）

        Args:
            device_id: 設備 ID
            timeout_seconds: 逾時秒數（若為 None 則使用配置值）

        Returns:
            是否存活
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]
            timeout = timeout_seconds or EdgeDevice._get_timeout()

            device = collection.find_one({'_id': device_id})
            if not device:
                return False

            last_heartbeat = device.get('connection_info', {}).get('last_heartbeat')
            if not last_heartbeat:
                return False

            # 確保 last_heartbeat 是時區感知的
            if last_heartbeat.tzinfo is None:
                last_heartbeat = last_heartbeat.replace(tzinfo=timezone.utc)

            elapsed = (datetime.now(timezone.utc) - last_heartbeat).total_seconds()
            return elapsed <= timeout

        except Exception as e:
            logger.error(f"檢查邊緣設備狀態失敗 ({device_id}): {e}")
            return False

    @staticmethod
    def _check_alive_from_device(device: Dict[str, Any], timeout_seconds: Optional[int] = None) -> tuple:
        """
        根據設備資料檢查是否存活（不再查詢 MongoDB）

        Args:
            device: 已查詢的設備資料字典
            timeout_seconds: 逾時秒數

        Returns:
            (is_alive: bool, elapsed_seconds: float, timeout: int)
        """
        timeout = timeout_seconds or EdgeDevice._get_timeout()

        last_heartbeat = device.get('connection_info', {}).get('last_heartbeat')
        if not last_heartbeat:
            return False, -1, timeout

        # 確保 last_heartbeat 是時區感知的（處理 MongoDB 可能返回的 offset-naive datetime）
        if last_heartbeat.tzinfo is None:
            last_heartbeat = last_heartbeat.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        elapsed = (now - last_heartbeat).total_seconds()

        # 偵錯日誌：記錄時間比較細節
        logger.debug(
            f"心跳檢查 - device_id={device.get('_id')}, "
            f"last_heartbeat={last_heartbeat}, now={now}, "
            f"elapsed={elapsed:.1f}s, timeout={timeout}s, "
            f"is_alive={elapsed <= timeout}"
        )

        return elapsed <= timeout, elapsed, timeout

    @staticmethod
    def get_by_id(device_id: str) -> Optional[Dict[str, Any]]:
        """
        根據 ID 獲取設備資訊

        Args:
            device_id: 設備 ID

        Returns:
            設備資訊字典，失敗返回 None
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]

            device = collection.find_one({'_id': device_id})
            if not device:
                return None

            # 判斷實際狀態（根據心跳）- 使用已查詢的 device 資料，避免重複查詢
            is_online, elapsed, timeout = EdgeDevice._check_alive_from_device(device)
            stored_status = device.get('status', 'offline')
            stored_offline_reason = device.get('offline_reason')

            # 判定實際狀態與離線原因
            if stored_status in ONLINE_STATUSES and not is_online:
                # 狀態為在線但心跳超時 → 視為離線，原因為心跳超時
                actual_status = 'OFFLINE'
                offline_reason = OfflineReason.HEARTBEAT_TIMEOUT
                logger.info(
                    f"設備 {device_id} 心跳超時判定為離線: "
                    f"stored_status={stored_status}, elapsed={elapsed:.1f}s > timeout={timeout}s"
                )
            elif stored_status == 'OFFLINE':
                # 狀態已為離線 → 判定離線原因
                actual_status = 'OFFLINE'
                offline_reason = EdgeDevice._determine_offline_reason(device, stored_offline_reason)
            else:
                # 在線狀態（IDLE / RECORDING）
                actual_status = stored_status
                offline_reason = None

            return {
                'device_id': device_id,
                'device_name': device.get('device_name', ''),
                'status': actual_status,
                'offline_reason': offline_reason,
                'platform': device.get('platform', 'unknown'),
                'audio_config': device.get('audio_config', {}),
                'schedule_config': device.get('schedule_config', {}),
                'connection_info': device.get('connection_info', {}),
                'statistics': device.get('statistics', {}),
                'assigned_router_ids': device.get('assigned_router_ids', []),
                'created_at': device.get('created_at'),
                'updated_at': device.get('updated_at')
            }

        except Exception as e:
            logger.error(f"獲取邊緣設備資訊失敗 ({device_id}): {e}")
            return None

    @staticmethod
    def _determine_offline_reason(device: Dict[str, Any], stored_reason: Optional[str]) -> str:
        """
        判定離線原因

        Args:
            device: 設備資料字典
            stored_reason: 資料庫中儲存的離線原因

        Returns:
            離線原因代碼
        """
        # 若有儲存的離線原因，優先使用
        if stored_reason:
            return stored_reason

        # 檢查是否從未連線
        last_heartbeat = device.get('connection_info', {}).get('last_heartbeat')
        if not last_heartbeat:
            return OfflineReason.NEVER_CONNECTED

        # 預設為連線中斷
        return OfflineReason.CONNECTION_LOST

    @staticmethod
    def get_all() -> List[Dict[str, Any]]:
        """
        獲取所有邊緣設備

        Returns:
            設備列表
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]

            devices = []
            for device in collection.find().sort('created_at', -1):
                device_id = device.get('_id')
                # 使用已查詢的 device 資料，避免重複查詢 MongoDB
                is_online, elapsed, timeout = EdgeDevice._check_alive_from_device(device)
                stored_status = device.get('status', 'offline')
                stored_offline_reason = device.get('offline_reason')

                # 判定實際狀態與離線原因
                if stored_status in ONLINE_STATUSES and not is_online:
                    # 狀態為在線但心跳超時 → 視為離線，原因為心跳超時
                    actual_status = 'OFFLINE'
                    offline_reason = OfflineReason.HEARTBEAT_TIMEOUT
                    logger.debug(
                        f"設備 {device_id} 心跳超時: elapsed={elapsed:.1f}s > timeout={timeout}s"
                    )
                elif stored_status == 'OFFLINE':
                    # 狀態已為離線 → 判定離線原因
                    actual_status = 'OFFLINE'
                    offline_reason = EdgeDevice._determine_offline_reason(device, stored_offline_reason)
                else:
                    # 在線狀態（IDLE / RECORDING）
                    actual_status = stored_status
                    offline_reason = None

                devices.append({
                    'device_id': device_id,
                    'device_name': device.get('device_name', ''),
                    'status': actual_status,
                    'offline_reason': offline_reason,
                    'platform': device.get('platform', 'unknown'),
                    'audio_config': device.get('audio_config', {}),
                    'schedule_config': device.get('schedule_config', {}),
                    'connection_info': device.get('connection_info', {}),
                    'statistics': device.get('statistics', {}),
                    'assigned_router_ids': device.get('assigned_router_ids', []),
                    'created_at': device.get('created_at'),
                    'updated_at': device.get('updated_at')
                })

            return devices

        except Exception as e:
            logger.error(f"獲取所有邊緣設備失敗: {e}")
            return []

    @staticmethod
    def get_online_devices() -> List[Dict[str, Any]]:
        """
        獲取所有在線的邊緣設備

        Returns:
            在線設備列表
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]
            timeout = EdgeDevice._get_timeout()
            threshold = datetime.now(timezone.utc) - timedelta(seconds=timeout)

            devices = []
            cursor = collection.find({
                'connection_info.last_heartbeat': {'$gte': threshold}
            }).sort('connection_info.last_heartbeat', -1)

            for device in cursor:
                devices.append({
                    'device_id': device.get('_id'),
                    'device_name': device.get('device_name', ''),
                    'status': device.get('status', 'IDLE'),
                    'platform': device.get('platform', 'unknown'),
                    'audio_config': device.get('audio_config', {}),
                    'schedule_config': device.get('schedule_config', {}),
                    'connection_info': device.get('connection_info', {}),
                    'statistics': device.get('statistics', {}),
                    'assigned_router_ids': device.get('assigned_router_ids', []),
                    'created_at': device.get('created_at'),
                    'updated_at': device.get('updated_at')
                })

            return devices

        except Exception as e:
            logger.error(f"獲取在線邊緣設備失敗: {e}")
            return []

    @staticmethod
    def get_by_socket_id(socket_id: str) -> Optional[Dict[str, Any]]:
        """
        根據 WebSocket ID 獲取設備

        Args:
            socket_id: WebSocket 連線 ID

        Returns:
            設備資訊字典，失敗返回 None
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]

            device = collection.find_one({'connection_info.socket_id': socket_id})
            if not device:
                return None

            device_id = device.get('_id')
            return EdgeDevice.get_by_id(device_id)

        except Exception as e:
            logger.error(f"根據 socket_id 獲取設備失敗 ({socket_id}): {e}")
            return None

    @staticmethod
    def update_device_name(device_id: str, device_name: str) -> bool:
        """
        更新設備名稱

        Args:
            device_id: 設備 ID
            device_name: 新名稱

        Returns:
            是否成功
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]

            result = collection.update_one(
                {'_id': device_id},
                {
                    '$set': {
                        'device_name': device_name,
                        'updated_at': datetime.now(timezone.utc)
                    }
                }
            )

            if result.modified_count > 0:
                logger.info(f"邊緣設備名稱已更新: {device_id} -> {device_name}")
                return True
            return False

        except Exception as e:
            logger.error(f"更新邊緣設備名稱失敗 ({device_id}): {e}")
            return False

    @staticmethod
    def update_audio_config(device_id: str, audio_config: Dict[str, Any]) -> bool:
        """
        更新設備音訊配置

        Args:
            device_id: 設備 ID
            audio_config: 音訊配置字典

        Returns:
            是否成功
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]

            # 只更新提供的欄位
            update_fields = {}
            for key, value in audio_config.items():
                update_fields[f'audio_config.{key}'] = value
            update_fields['updated_at'] = datetime.now(timezone.utc)

            result = collection.update_one(
                {'_id': device_id},
                {'$set': update_fields}
            )

            if result.modified_count > 0:
                logger.info(f"邊緣設備音訊配置已更新: {device_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"更新邊緣設備音訊配置失敗 ({device_id}): {e}")
            return False

    @staticmethod
    def update_available_audio_devices(device_id: str, devices: List[Dict[str, Any]]) -> bool:
        """
        更新設備的可用音訊設備列表

        Args:
            device_id: 設備 ID
            devices: 音訊設備列表

        Returns:
            是否成功
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]

            result = collection.update_one(
                {'_id': device_id},
                {
                    '$set': {
                        'audio_config.available_devices': devices,
                        'updated_at': datetime.now(timezone.utc)
                    }
                }
            )

            if result.modified_count > 0:
                logger.info(f"邊緣設備音訊設備列表已更新: {device_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"更新邊緣設備音訊設備列表失敗 ({device_id}): {e}")
            return False

    @staticmethod
    def update_schedule_config(device_id: str, schedule_config: Dict[str, Any]) -> bool:
        """
        更新設備排程配置

        Args:
            device_id: 設備 ID
            schedule_config: 排程配置字典

        Returns:
            是否成功
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]

            # 只更新提供的欄位
            update_fields = {}
            for key, value in schedule_config.items():
                update_fields[f'schedule_config.{key}'] = value
            update_fields['updated_at'] = datetime.now(timezone.utc)

            result = collection.update_one(
                {'_id': device_id},
                {'$set': update_fields}
            )

            if result.modified_count > 0:
                logger.info(f"邊緣設備排程配置已更新: {device_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"更新邊緣設備排程配置失敗 ({device_id}): {e}")
            return False

    @staticmethod
    def update_router_ids(device_id: str, router_ids: List[str]) -> bool:
        """
        更新設備的路由配置

        錄音完成後會自動發送至這些路由進行分析

        Args:
            device_id: 設備 ID
            router_ids: 路由 ID 列表

        Returns:
            是否成功
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]

            result = collection.update_one(
                {'_id': device_id},
                {
                    '$set': {
                        'assigned_router_ids': router_ids,
                        'updated_at': datetime.now(timezone.utc)
                    }
                }
            )

            if result.modified_count > 0:
                logger.info(f"邊緣設備路由配置已更新: {device_id}, routers={router_ids}")
                return True
            return False

        except Exception as e:
            logger.error(f"更新邊緣設備路由配置失敗 ({device_id}): {e}")
            return False

    @staticmethod
    def increment_recording_stats(device_id: str, success: bool = True) -> Dict[str, Any]:
        """
        增加錄音統計，並檢查是否達到排程上限

        Args:
            device_id: 設備 ID
            success: 是否成功

        Returns:
            結果字典，包含：
            - success: 是否更新成功
            - schedule_disabled: 是否因達到上限而停用排程
            - new_success_count: 更新後的成功計數
        """
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]

            update_data = {
                '$inc': {
                    'statistics.total_recordings': 1,
                    'statistics.success_count' if success else 'statistics.error_count': 1
                },
                '$set': {
                    'statistics.last_recording_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc)
                }
            }

            result = collection.update_one(
                {'_id': device_id},
                update_data
            )

            if result.modified_count == 0:
                return {'success': False, 'schedule_disabled': False}

            # 檢查是否達到排程錄音上限
            schedule_disabled = False
            new_success_count = 0

            if success:
                device = collection.find_one({'_id': device_id})
                if device:
                    schedule_config = device.get('schedule_config', {})
                    statistics = device.get('statistics', {})
                    max_success_count = schedule_config.get('max_success_count')
                    new_success_count = statistics.get('success_count', 0)

                    # 若設定了上限且已達到，自動停用排程
                    if (max_success_count is not None and
                        max_success_count > 0 and
                        new_success_count >= max_success_count and
                        schedule_config.get('enabled', False)):

                        collection.update_one(
                            {'_id': device_id},
                            {'$set': {
                                'schedule_config.enabled': False,
                                'updated_at': datetime.now(timezone.utc)
                            }}
                        )
                        schedule_disabled = True
                        logger.info(
                            f"設備 {device_id} 已達排程錄音上限 "
                            f"({new_success_count}/{max_success_count})，排程已自動停用"
                        )

            return {
                'success': True,
                'schedule_disabled': schedule_disabled,
                'new_success_count': new_success_count
            }

        except Exception as e:
            logger.error(f"更新邊緣設備錄音統計失敗 ({device_id}): {e}")
            return {'success': False, 'schedule_disabled': False}

    @staticmethod
    def delete(device_id: str, force: bool = False) -> bool:
        """
        刪除邊緣設備

        Args:
            device_id: 設備 ID
            force: 是否強制刪除（即使設備在線）

        Returns:
            是否成功
        """
        try:
            # 若非強制刪除，檢查設備是否在線
            if not force:
                device = EdgeDevice.get_by_id(device_id)
                if device and device.get('status') in ('IDLE', 'RECORDING'):
                    logger.warning(f"無法刪除在線的邊緣設備: {device_id}")
                    return False

            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]

            result = collection.delete_one({'_id': device_id})

            if result.deleted_count > 0:
                logger.info(f"邊緣設備已刪除: {device_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"刪除邊緣設備失敗 ({device_id}): {e}")
            return False

    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """
        獲取邊緣設備統計資訊

        Returns:
            統計數據字典
        """
        try:
            devices = EdgeDevice.get_all()

            online_count = sum(1 for d in devices if d.get('status') == 'IDLE')
            offline_count = sum(1 for d in devices if d.get('status') == 'OFFLINE')
            recording_count = sum(1 for d in devices if d.get('status') == 'RECORDING')

            return {
                'total_devices': len(devices),
                'online_devices': online_count,
                'offline_devices': offline_count,
                'recording_devices': recording_count,
                'devices': devices
            }

        except Exception as e:
            logger.error(f"獲取邊緣設備統計失敗: {e}")
            return {
                'total_devices': 0,
                'online_devices': 0,
                'offline_devices': 0,
                'recording_devices': 0,
                'devices': []
            }

    @staticmethod
    def count_all() -> int:
        """統計設備總數"""
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]
            return collection.count_documents({})
        except Exception as e:
            logger.error(f"統計邊緣設備總數失敗: {e}")
            return 0

    @staticmethod
    def count_online() -> int:
        """統計在線設備數"""
        try:
            db = get_db()
            collection = db[EdgeDevice._get_collection_name()]
            timeout = EdgeDevice._get_timeout()
            threshold = datetime.now(timezone.utc) - timedelta(seconds=timeout)

            return collection.count_documents({
                'connection_info.last_heartbeat': {'$gte': threshold}
            })

        except Exception as e:
            logger.error(f"統計在線邊緣設備數失敗: {e}")
            return 0

    # === 與視圖兼容的封裝方法 ===
    @staticmethod
    def _wrap_device(data: Optional[Dict[str, Any]]) -> Optional[EdgeDeviceRecord]:
        """將字典封裝為 EdgeDeviceRecord"""
        if not data:
            return None
        return EdgeDeviceRecord(
            device_id=data.get('device_id', ''),
            device_name=data.get('device_name', ''),
            status=data.get('status', 'OFFLINE'),
            platform=data.get('platform', 'unknown'),
            offline_reason=data.get('offline_reason'),
            audio_config=data.get('audio_config', {}),
            schedule_config=data.get('schedule_config', {}),
            connection_info=data.get('connection_info', {}),
            statistics=data.get('statistics', {}),
            assigned_router_ids=data.get('assigned_router_ids', []),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )

    @staticmethod
    def get_all_records() -> List[EdgeDeviceRecord]:
        """獲取所有設備（返回 EdgeDeviceRecord 列表）"""
        devices = EdgeDevice.get_all()
        return [EdgeDevice._wrap_device(d) for d in devices if d]

    @staticmethod
    def get_record_by_id(device_id: str) -> Optional[EdgeDeviceRecord]:
        """獲取單一設備（返回 EdgeDeviceRecord）"""
        device = EdgeDevice.get_by_id(device_id)
        return EdgeDevice._wrap_device(device)
