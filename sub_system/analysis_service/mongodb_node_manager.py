"""
基於 MongoDB 的節點管理器
直接操作 MongoDB 進行節點註冊與心跳，無需 HTTP 連接
適用於多個 analysis_service_v2 實例並行運作的場景
"""
import logging
import time
from datetime import datetime
from threading import Thread, Event
from typing import Dict, Any, Optional
from pymongo.errors import PyMongoError
from config_schema import build_node_config_metadata

logger = logging.getLogger(__name__)


class MongoDBNodeManager:
    """
    基於 MongoDB 的節點管理器
    
    直接操作 MongoDB 的 nodes_status collection，
    不依賴 HTTP API，避免斷線後無法重連的問題
    """

    def __init__(
        self,
        mongodb_handler,
        node_id: str,
        node_info: Dict[str, Any],
        heartbeat_interval: int = 30
    ):
        """
        初始化

        Args:
            mongodb_handler: MongoDB 連接處理器
            node_id: 節點 ID
            node_info: 節點信息（capabilities, version, max_concurrent_tasks, tags）
            heartbeat_interval: 心跳間隔（秒）
        """
        self.mongodb_handler = mongodb_handler
        self.node_id = node_id
        self.node_info = node_info
        self.heartbeat_interval = heartbeat_interval
        # 將可配置資訊寫入 node_info，方便 state_management 提供表單
        self.node_info = {
            **self.node_info,
            **build_node_config_metadata()
        }
        
        self.running = False
        self._stop_event = Event()
        self._heartbeat_thread: Optional[Thread] = None
        self.current_tasks = 0

    def register_node(self) -> bool:
        """
        註冊節點到 MongoDB

        Returns:
            是否成功
        """
        try:
            collection = self.mongodb_handler.get_collection('node_status')
            
            now = datetime.utcnow()

            # 使用 upsert 插入或更新節點資訊
            result = collection.update_one(
                {'_id': self.node_id},
                {
                    '$set': {
                        'info': self.node_info,
                        'current_tasks': 0,
                        'last_heartbeat': now,
                        'updated_at': now
                    },
                    '$setOnInsert': {
                        'created_at': now
                    }
                },
                upsert=True
            )

            logger.info(f"節點已註冊到 MongoDB: {self.node_id}")
            return True

        except PyMongoError as e:
            logger.error(f"註冊節點到 MongoDB 失敗: {e}")
            return False
        except Exception as e:
            logger.error(f"註冊節點異常: {e}", exc_info=True)
            return False

    def unregister_node(self) -> bool:
        """
        從 MongoDB 註銷節點

        Returns:
            是否成功
        """
        try:
            collection = self.mongodb_handler.get_collection('node_status')

            result = collection.delete_one({'_id': self.node_id})

            if result.deleted_count > 0:
                logger.info(f"節點已從 MongoDB 註銷: {self.node_id}")
                return True
            else:
                logger.warning(f"節點不存在，無法註銷: {self.node_id}")
                return False

        except PyMongoError as e:
            logger.error(f"從 MongoDB 註銷節點失敗: {e}")
            return False
        except RuntimeError as e:
            # MongoDB 連接可能已關閉
            if "after close" in str(e).lower() or "尚未連線" in str(e):
                logger.warning(f"MongoDB 連接已關閉，無法註銷節點: {self.node_id}")
                return False
            logger.error(f"註銷節點異常: {e}", exc_info=True)
            return False
        except Exception as e:
            # 捕獲 AttributeError: 'MongoClient' object has no attribute 'xxx' after close
            if "after close" in str(e).lower() or "mongoclient" in str(e).lower():
                logger.warning(f"MongoDB 連接已關閉，無法註銷節點: {self.node_id}")
                return False
            logger.error(f"註銷節點異常: {e}", exc_info=True)
            return False

    def start_heartbeat(self):
        """啟動心跳發送（在新線程中）"""
        if self.running:
            logger.warning("心跳發送器已在運行")
            return

        logger.info(f"啟動心跳發送器 (間隔: {self.heartbeat_interval}秒)")
        self.running = True
        self._stop_event.clear()

        self._heartbeat_thread = Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name='MongoDBHeartbeat'
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self):
        """停止心跳發送"""
        logger.info("停止心跳發送器...")
        self.running = False
        self._stop_event.set()

        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)

        logger.info("心跳發送器已停止")

    def _heartbeat_loop(self):
        """心跳發送循環"""
        while self.running and not self._stop_event.is_set():
            try:
                self._send_heartbeat()
            except Exception as e:
                logger.error(f"發送心跳失敗: {e}")

            # 等待下一次心跳
            self._stop_event.wait(self.heartbeat_interval)

    def _send_heartbeat(self):
        """發送心跳到 MongoDB"""
        try:
            collection = self.mongodb_handler.get_collection('node_status')

            now = datetime.utcnow()

            update_data = {
                'last_heartbeat': now,
                'updated_at': now,
                'current_tasks': self.current_tasks
            }

            result = collection.update_one(
                {'_id': self.node_id},
                {'$set': update_data}
            )

            if result.modified_count > 0:
                logger.debug(f"心跳已發送: {self.node_id}, 當前任務數: {self.current_tasks}")
            elif result.matched_count == 0:
                # 節點可能被移除，嘗試重新註冊
                logger.warning(f"節點不存在於 MongoDB，嘗試重新註冊: {self.node_id}")
                self.register_node()
            else:
                logger.debug(f"心跳未更新（數據相同）: {self.node_id}")

        except PyMongoError as e:
            logger.error(f"發送心跳到 MongoDB 失敗: {e}")
        except Exception as e:
            logger.error(f"發送心跳異常: {e}")

    def update_task_count(self, count: int):
        """
        更新當前任務數

        Args:
            count: 當前任務數
        """
        self.current_tasks = count

    def is_registered(self) -> bool:
        """
        檢查節點是否已註冊

        Returns:
            是否已註冊
        """
        try:
            collection = self.mongodb_handler.get_collection('node_status')

            node = collection.find_one({'_id': self.node_id})
            return node is not None

        except Exception as e:
            logger.error(f"檢查節點註冊狀態失敗: {e}")
            return False

    def get_node_info(self) -> Optional[Dict[str, Any]]:
        """
        獲取節點信息

        Returns:
            節點信息，失敗返回 None
        """
        try:
            collection = self.mongodb_handler.get_collection('node_status')

            node = collection.find_one({'_id': self.node_id})
            return node

        except Exception as e:
            logger.error(f"獲取節點信息失敗: {e}")
            return None
