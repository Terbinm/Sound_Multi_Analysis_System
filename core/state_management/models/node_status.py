"""
節點狀態模型
使用 MongoDB 存儲節點狀態，取代 Redis
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from utils.mongodb_handler import get_db
from config import get_config

logger = logging.getLogger(__name__)


@dataclass
class NodeRecord:
    """提供給視圖層使用的節點資料模型"""

    node_id: str
    status: str
    current_tasks: int = 0
    last_heartbeat: Optional[datetime] = None
    created_at: Optional[datetime] = None
    info: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.capabilities: List[str] = self.info.get('capabilities', [])
        self.version: str = self.info.get('version', 'unknown')
        self.max_concurrent_tasks: int = self.info.get('max_concurrent_tasks', 0)
        self.tags: List[str] = self.info.get('tags', [])

    def is_online(self) -> bool:
        return self.status == 'online'


class NodeStatus:
    """節點狀態類 - 使用 MongoDB 存儲"""

    @staticmethod
    def _get_collection_name():
        """從 config 獲取集合名稱"""
        config = get_config()
        return config.COLLECTIONS['node_status']

    @staticmethod
    def register_node(node_id: str, node_info: Dict[str, Any]) -> bool:
        """
        註冊節點

        Args:
            node_id: 節點 ID
            node_info: 節點信息

        Returns:
            是否成功
        """
        try:
            db = get_db()
            collection = db[NodeStatus._get_collection_name()]

            now = datetime.utcnow()

            # 使用 upsert 插入或更新
            result = collection.update_one(
                {'_id': node_id},
                {
                    '$set': {
                        'info': node_info,
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

            logger.info(f"節點已註冊: {node_id}")
            return True

        except Exception as e:
            logger.error(f"註冊節點失敗: {e}")
            return False

    @staticmethod
    def update_heartbeat(node_id: str, current_tasks: int = None) -> bool:
        """
        更新節點心跳

        Args:
            node_id: 節點 ID
            current_tasks: 當前任務數（可選）

        Returns:
            是否成功
        """
        try:
            db = get_db()
            collection = db[NodeStatus._get_collection_name()]

            update_data = {
                'last_heartbeat': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }

            if current_tasks is not None:
                update_data['current_tasks'] = current_tasks

            result = collection.update_one(
                {'_id': node_id},
                {'$set': update_data}
            )

            if result.modified_count > 0:
                logger.debug(f"心跳已更新: {node_id}")
                return True
            else:
                logger.warning(f"節點不存在或心跳未更新: {node_id}")
                return False

        except Exception as e:
            logger.error(f"更新心跳失敗 ({node_id}): {e}")
            return False

    @staticmethod
    def is_alive(node_id: str, timeout_seconds: Optional[int] = None) -> bool:
        """
        檢查節點是否存活

        Args:
            node_id: 節點 ID
            timeout_seconds: 超時時間（秒），若為 None 則使用配置值

        Returns:
            是否存活
        """
        try:
            db = get_db()
            collection = db[NodeStatus._get_collection_name()]
            config = get_config()
            timeout = timeout_seconds or config.NODE_HEARTBEAT_TIMEOUT

            node = collection.find_one({'_id': node_id})

            if not node:
                return False

            last_heartbeat = node.get('last_heartbeat')
            if not last_heartbeat:
                return False

            # 計算心跳時間差
            elapsed = (datetime.utcnow() - last_heartbeat).total_seconds()

            return elapsed <= timeout

        except Exception as e:
            logger.error(f"檢查節點狀態失敗 ({node_id}): {e}")
            return False

    @staticmethod
    def get_node_info(node_id: str) -> Optional[Dict[str, Any]]:
        """
        獲取節點信息

        Args:
            node_id: 節點 ID

        Returns:
            節點信息，失敗返回 None
        """
        try:
            db = get_db()
            collection = db[NodeStatus._get_collection_name()]

            node = collection.find_one({'_id': node_id})

            if not node:
                return None

            # 判斷狀態
            is_online = NodeStatus.is_alive(node_id)

            # 構建返回數據
            info = node.get('info', {})
            info['node_id'] = node_id
            info['status'] = 'online' if is_online else 'offline'
            info['current_tasks'] = node.get('current_tasks', 0)
            info['last_heartbeat'] = node.get('last_heartbeat')
            info['created_at'] = node.get('created_at')

            return info

        except Exception as e:
            logger.error(f"獲取節點信息失敗 ({node_id}): {e}")
            return None

    @staticmethod
    def get_all_nodes() -> List[Dict[str, Any]]:
        """
        獲取所有節點

        Returns:
            節點列表
        """
        try:
            db = get_db()
            collection = db[NodeStatus._get_collection_name()]

            nodes = []

            for node in collection.find():
                node_id = node.get('_id')

                # 判斷狀態
                is_online = NodeStatus.is_alive(node_id)

                # 構建節點數據
                info = node.get('info', {})
                info['node_id'] = node_id
                info['status'] = 'online' if is_online else 'offline'
                info['current_tasks'] = node.get('current_tasks', 0)
                info['last_heartbeat'] = node.get('last_heartbeat')
                info['created_at'] = node.get('created_at')

                nodes.append(info)

            return nodes

        except Exception as e:
            logger.error(f"獲取所有節點失敗: {e}")
            return []

    @staticmethod
    def unregister_node(node_id: str) -> bool:
        """
        註銷節點

        Args:
            node_id: 節點 ID

        Returns:
            是否成功
        """
        try:
            db = get_db()
            collection = db[NodeStatus._get_collection_name()]

            result = collection.delete_one({'_id': node_id})

            if result.deleted_count > 0:
                logger.info(f"節點已註銷: {node_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"註銷節點失敗 ({node_id}): {e}")
            return False

    @staticmethod
    def get_node_statistics() -> Dict[str, Any]:
        """
        獲取節點統計信息

        Returns:
            統計數據
        """
        try:
            nodes = NodeStatus.get_all_nodes()

            online_count = sum(1 for n in nodes if n.get('status') == 'online')
            offline_count = sum(1 for n in nodes if n.get('status') == 'offline')

            return {
                'total_nodes': len(nodes),
                'online_nodes': online_count,
                'offline_nodes': offline_count,
                'nodes': nodes
            }

        except Exception as e:
            logger.error(f"獲取節點統計失敗: {e}")
            return {
                'total_nodes': 0,
                'online_nodes': 0,
                'offline_nodes': 0,
                'nodes': []
            }

    @staticmethod
    def count_all() -> int:
        """統計節點總數"""
        try:
            db = get_db()
            collection = db[NodeStatus._get_collection_name()]
            return collection.count_documents({})
        except Exception as e:
            logger.error(f"統計節點總數失敗: {e}")
            return 0

    @staticmethod
    def count_online(timeout_seconds: Optional[int] = None) -> int:
        """統計在線節點數"""
        try:
            db = get_db()
            collection = db[NodeStatus._get_collection_name()]
            config = get_config()
            timeout = timeout_seconds or config.NODE_HEARTBEAT_TIMEOUT
            threshold = datetime.utcnow() - timedelta(seconds=timeout)

            return collection.count_documents({
                'last_heartbeat': {'$gte': threshold}
            })

        except Exception as e:
            logger.error(f"統計在線節點數失敗: {e}")
            return 0

    @staticmethod
    def get_online_nodes(limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """獲取在線節點清單"""
        try:
            db = get_db()
            collection = db[NodeStatus._get_collection_name()]
            config = get_config()
            threshold = datetime.utcnow() - timedelta(seconds=config.NODE_HEARTBEAT_TIMEOUT)

            cursor = collection.find({
                'last_heartbeat': {'$gte': threshold}
            }).sort('last_heartbeat', -1)

            if limit is not None:
                cursor = cursor.limit(limit)

            nodes = []
            for node in cursor:
                info = node.get('info', {})
                info['node_id'] = node.get('_id')
                info['status'] = 'online'
                info['current_tasks'] = node.get('current_tasks', 0)
                info['last_heartbeat'] = node.get('last_heartbeat')
                info['created_at'] = node.get('created_at')
                nodes.append(info)

            return nodes

        except Exception as e:
            logger.error(f"獲取在線節點列表失敗: {e}")
            return []

    # === 與舊視圖兼容的封裝方法 ===
    @staticmethod
    def _wrap_node(data: Optional[Dict[str, Any]]) -> Optional[NodeRecord]:
        if not data:
            return None
        return NodeRecord(
            node_id=data.get('node_id', ''),
            status=data.get('status', 'offline'),
            current_tasks=data.get('current_tasks', 0),
            last_heartbeat=data.get('last_heartbeat'),
            created_at=data.get('created_at'),
            info=data
        )

    @staticmethod
    def get_all() -> List[NodeRecord]:
        """兼容舊有視圖的節點列表"""
        nodes = NodeStatus.get_all_nodes()
        return [NodeStatus._wrap_node(node) for node in nodes if node]

    @staticmethod
    def get_by_id(node_id: str) -> Optional[NodeRecord]:
        """兼容舊有視圖的單一節點查詢"""
        node = NodeStatus.get_node_info(node_id)
        return NodeStatus._wrap_node(node)

    @staticmethod
    def delete(node_id: str) -> bool:
        """兼容舊有視圖的刪除操作"""
        return NodeStatus.unregister_node(node_id)
