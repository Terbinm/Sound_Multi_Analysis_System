"""
節點監控器
監控分析節點的健康狀態
"""
import logging
import time
from typing import List, Dict, Any

from models.node_status import NodeStatus
from config import get_config
from services.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)


class NodeMonitor:
    """節點監控器類"""

    def __init__(self):
        """初始化"""
        self.config = get_config()
        self.running = False
        self.previous_node_status = {}  # 記錄上次節點狀態，用於檢測狀態變化
        self.known_nodes = set()  # 記錄已知節點 ID，用於檢測新節點

    def start(self):
        """啟動監控器"""
        try:
            logger.info("啟動節點監控器...")
            self.running = True

            while self.running:
                # 檢查所有節點
                self._check_all_nodes()

                # 等待下一次檢查
                time.sleep(self.config.NODE_HEARTBEAT_INTERVAL)

        except KeyboardInterrupt:
            logger.info("節點監控器收到停止信號")
            self.stop()
        except Exception as e:
            logger.error(f"節點監控器錯誤: {e}", exc_info=True)
            self.stop()

    def stop(self):
        """停止監控器"""
        logger.info("停止節點監控器...")
        self.running = False
        logger.info("節點監控器已停止")

    def _check_all_nodes(self):
        """檢查所有節點的狀態"""
        try:
            # 獲取所有節點
            nodes = NodeStatus.get_all_nodes()
            current_node_ids = set()  # 當前存在的節點 ID

            online_count = 0
            offline_count = 0

            for node in nodes:
                node_id = node.get('node_id')
                current_node_ids.add(node_id)  # 記錄當前存在的節點
                current_status = node.get('status', 'unknown')
                previous_status = self.previous_node_status.get(node_id)

                # 檢測新節點註冊（從 MongoDB 直接註冊）
                if node_id not in self.known_nodes:
                    logger.info(f"檢測到新節點註冊: {node_id}")
                    self.known_nodes.add(node_id)
                    # 推送節點註冊事件
                    node_info = node.get('info', {})
                    websocket_manager.emit_node_registered({
                        'node_id': node_id,
                        'status': current_status,
                        'capabilities': node_info.get('capabilities', []),
                        'version': node_info.get('version', 'unknown'),
                        'max_concurrent_tasks': node_info.get('max_concurrent_tasks', 1),
                        'tags': node_info.get('tags', [])
                    })

                if current_status == 'online':
                    online_count += 1

                    # 檢測節點從離線變為在線
                    if previous_status and previous_status != 'online':
                        logger.info(f"節點重新上線: {node_id}")
                        # 推送節點上線事件
                        websocket_manager.emit_node_online({
                            'node_id': node_id,
                            'status': current_status,
                            'timestamp': node.get('last_heartbeat'),
                            'current_tasks': node.get('current_tasks', 0),
                            'capability': node.get('capability', 'unknown')
                        })
                else:
                    offline_count += 1

                    # 檢測節點從在線變為離線
                    if previous_status == 'online':
                        logger.warning(f"節點離線: {node_id}")
                        # 推送節點離線事件
                        websocket_manager.emit_node_offline({
                            'node_id': node_id,
                            'status': current_status,
                            'timestamp': node.get('last_heartbeat'),
                            'capability': node.get('capability', 'unknown')
                        })

                # 更新節點狀態記錄
                self.previous_node_status[node_id] = current_status

            # 檢測已刪除的節點（主動註銷）
            removed_nodes = self.known_nodes - current_node_ids
            for node_id in removed_nodes:
                logger.info(f"檢測到節點已註銷: {node_id}")
                self.known_nodes.remove(node_id)
                
                # 從狀態記錄中移除
                if node_id in self.previous_node_status:
                    del self.previous_node_status[node_id]
                
                # 推送節點移除事件
                websocket_manager.emit_node_offline({
                    'node_id': node_id,
                    'status': 'removed',
                    'timestamp': None,
                    'capability': 'unknown'
                })

            # 定期記錄統計信息並推送更新（無論是否有節點）
            logger.debug(
                f"節點狀態: 總數={len(nodes)}, "
                f"在線={online_count}, 離線={offline_count}"
            )

            # 推送統計數據更新（每次檢查都推送，即使沒有節點）
            stats_data = {
                'total_nodes': len(nodes),
                'online_nodes': online_count,
                'offline_nodes': offline_count,
                'timestamp': time.time()
            }
            websocket_manager.emit_stats_updated(stats_data)

        except Exception as e:
            logger.error(f"檢查節點狀態失敗: {e}")

    def get_healthy_nodes(self) -> List[Dict[str, Any]]:
        """獲取所有健康節點"""
        try:
            nodes = NodeStatus.get_all_nodes()
            return [node for node in nodes if node.get('status') == 'online']

        except Exception as e:
            logger.error(f"獲取健康節點失敗: {e}")
            return []

    def get_node_statistics(self) -> Dict[str, Any]:
        """獲取節點統計信息"""
        try:
            return NodeStatus.get_node_statistics()

        except Exception as e:
            logger.error(f"獲取節點統計失敗: {e}")
            return {
                'total_nodes': 0,
                'online_nodes': 0,
                'offline_nodes': 0,
                'nodes': []
            }
