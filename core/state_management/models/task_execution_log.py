"""
任務執行日誌模型
記錄路由規則觸發的任務執行歷史
"""
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
from utils.mongodb_handler import get_db
from config import get_config

logger = logging.getLogger(__name__)


class TaskExecutionLog:
    """任務執行日誌類"""

    @staticmethod
    def _get_collection():
        config = get_config()
        db = get_db()
        return db[config.COLLECTIONS.get('task_execution_logs', 'task_execution_logs')]

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        """初始化"""
        if data:
            self.from_dict(data)
        else:
            # 默認值
            self.log_id = ""
            self.task_id = ""
            self.router_id = ""
            self.rule_id = ""
            self.analyze_uuid = ""
            self.analysis_method_id = ""
            self.config_id = ""
            self.mongodb_instance = ""
            self.priority = None  # 優先級已移除，保留欄位供舊資料相容
            self.node_id = None
            self.node_info = {}
            self.status = "pending"  # pending, processing, completed, failed
            self.created_at = datetime.utcnow()
            self.started_at = None
            self.completed_at = None
            self.error_message = None
            self.metadata = {}

    def from_dict(self, data: Dict[str, Any]):
        """從字典加載"""
        self.log_id = data.get('log_id', '')
        self.task_id = data.get('task_id', '')
        self.router_id = data.get('router_id', '')
        self.rule_id = data.get('rule_id', '')
        self.analyze_uuid = data.get('analyze_uuid', '')
        self.analysis_method_id = data.get('analysis_method_id', '')
        self.config_id = data.get('config_id', '')
        self.mongodb_instance = data.get('mongodb_instance', '')
        self.priority = data.get('priority')
        self.node_id = data.get('node_id')
        self.node_info = data.get('node_info', {})
        self.status = data.get('status', 'pending')
        self.created_at = data.get('created_at', datetime.utcnow())
        self.started_at = data.get('started_at')
        self.completed_at = data.get('completed_at')
        self.error_message = data.get('error_message')
        self.metadata = data.get('metadata', {})
        return self

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        data = {
            'log_id': self.log_id,
            'task_id': self.task_id,
            'router_id': self.router_id,
            'rule_id': self.rule_id,
            'analyze_uuid': self.analyze_uuid,
            'analysis_method_id': self.analysis_method_id,
            'config_id': self.config_id,
            'mongodb_instance': self.mongodb_instance,
            'status': self.status,
            'node_id': self.node_id,
            'node_info': self.node_info,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'error_message': self.error_message,
            'metadata': self.metadata
        }

        if self.priority is not None:
            data['priority'] = self.priority

        return data

    @staticmethod
    def create(log_data: Dict[str, Any]) -> Optional['TaskExecutionLog']:
        """創建新日誌"""
        try:
            collection = TaskExecutionLog._get_collection()

            # 創建日誌對象
            log = TaskExecutionLog()
            log.log_id = log_data.get('log_id', str(uuid.uuid4()))
            log.task_id = log_data['task_id']
            log.router_id = log_data.get('router_id', '')
            log.rule_id = log_data.get('rule_id', '')
            log.analyze_uuid = log_data.get('analyze_uuid', '')
            log.analysis_method_id = log_data.get('analysis_method_id', '')
            log.config_id = log_data.get('config_id', '')
            log.mongodb_instance = log_data.get('mongodb_instance', '')
            log.priority = log_data.get('priority')
            log.node_id = log_data.get('node_id')
            log.node_info = log_data.get('node_info', {})
            log.status = log_data.get('status', 'pending')
            log.created_at = datetime.utcnow()
            log.started_at = log_data.get('started_at')
            log.completed_at = log_data.get('completed_at')
            log.error_message = log_data.get('error_message')
            log.metadata = log_data.get('metadata', {})

            # 插入資料庫
            result = collection.insert_one(log.to_dict())

            if result.inserted_id:
                logger.debug(f"任務執行日誌已創建: {log.log_id}")
                return log

            return None

        except Exception as e:
            logger.error(f"創建任務執行日誌失敗: {e}", exc_info=True)
            return None

    @staticmethod
    def get_by_task_id(task_id: str) -> Optional['TaskExecutionLog']:
        """根據 task_id 獲取日誌"""
        try:
            collection = TaskExecutionLog._get_collection()
            data = collection.find_one({'task_id': task_id})
            if data:
                return TaskExecutionLog(data)
            return None
        except Exception as e:
            logger.error(f"獲取任務執行日誌失敗: {e}")
            return None

    @staticmethod
    def get_by_router_id(router_id: str, limit: int = 100, skip: int = 0) -> List['TaskExecutionLog']:
        """
        根據 router_id 獲取日誌列表

        Args:
            router_id: routerID
            limit: 返回數量限制
            skip: 跳過數量

        Returns:
            日誌列表（按創建時間倒序）
        """
        try:
            collection = TaskExecutionLog._get_collection()
            logs = []

            for data in collection.find({'router_id': router_id}) \
                    .sort('created_at', -1) \
                    .skip(skip) \
                    .limit(limit):
                logs.append(TaskExecutionLog(data))

            return logs

        except Exception as e:
            logger.error(f"獲取 router_id 日誌列表失敗: {e}")
            return []

    @staticmethod
    def update_status(task_id: str, status: str, error_message: Optional[str] = None) -> bool:
        """
        更新任務狀態

        Args:
            task_id: 任務 ID
            status: 新狀態（pending, processing, completed, failed）
            error_message: 錯誤訊息（狀態為 failed 時使用）

        Returns:
            是否更新成功
        """
        try:
            collection = TaskExecutionLog._get_collection()

            update_data = {'status': status}

            if status == 'processing' and not collection.find_one({'task_id': task_id, 'started_at': {'$ne': None}}):
                update_data['started_at'] = datetime.utcnow()

            if status in ['completed', 'failed']:
                update_data['completed_at'] = datetime.utcnow()

            if error_message:
                update_data['error_message'] = error_message

            result = collection.update_one(
                {'task_id': task_id},
                {'$set': update_data}
            )

            return result.modified_count > 0

        except Exception as e:
            logger.error(f"更新任務狀態失敗: {e}")
            return False

    @staticmethod
    def get_statistics(router_id: str) -> Dict[str, Any]:
        """
        獲取 router_id 的統計資訊

        Args:
            router_id: routerID

        Returns:
            統計資訊字典
        """
        try:
            collection = TaskExecutionLog._get_collection()

            status_counts: Dict[str, int] = {
                'pending': 0,
                'processing': 0,
                'completed': 0,
                'failed': 0
            }
            unknown_status_count = 0

            # 直接迭代指定 router_id 的所有紀錄，避免聚合遺漏自訂狀態
            cursor = collection.find({'router_id': router_id}, {'status': 1})
            for doc in cursor:
                status_value = doc.get('status') or 'unknown'
                normalized = str(status_value).strip().lower()
                if normalized in status_counts:
                    status_counts[normalized] += 1
                else:
                    unknown_status_count += 1

            if unknown_status_count:
                status_counts['unknown'] = unknown_status_count

            total = sum(status_counts.values())

            # 最後執行時間
            last_log = collection.find_one(
                {'router_id': router_id},
                sort=[('created_at', -1)]
            )

            last_execution = last_log['created_at'] if last_log else None

            # 計算平均處理時間（僅針對已完成的任務）
            avg_time_pipeline = [
                {
                    '$match': {
                        'router_id': router_id,
                        'status': 'completed',
                        'started_at': {'$ne': None},
                        'completed_at': {'$ne': None}
                    }
                },
                {
                    '$project': {
                        'duration': {
                            '$subtract': ['$completed_at', '$started_at']
                        }
                    }
                },
                {
                    '$group': {
                        '_id': None,
                        'avg_duration': {'$avg': '$duration'}
                    }
                }
            ]

            avg_duration = None
            for doc in collection.aggregate(avg_time_pipeline):
                avg_duration = doc.get('avg_duration')
                if avg_duration:
                    # 轉換為秒
                    avg_duration = avg_duration / 1000.0

            return {
                'total': total,
                'status_counts': status_counts,
                'success_count': status_counts.get('completed', 0),
                'failed_count': status_counts.get('failed', 0),
                'pending_count': status_counts.get('pending', 0),
                'processing_count': status_counts.get('processing', 0),
                'success_rate': (status_counts.get('completed', 0) / total * 100) if total > 0 else 0,
                'last_execution': last_execution,
                'avg_processing_time': avg_duration
            }

        except Exception as e:
            logger.error(f"獲取統計資訊失敗: {e}", exc_info=True)
            return {
                'total': 0,
                'status_counts': {},
                'success_count': 0,
                'failed_count': 0,
                'pending_count': 0,
                'processing_count': 0,
                'success_rate': 0,
                'last_execution': None,
                'avg_processing_time': None
            }

    @staticmethod
    def count_by_router_id(router_id: str) -> int:
        """統計指定 router_id 的日誌總數"""
        try:
            collection = TaskExecutionLog._get_collection()
            return collection.count_documents({'router_id': router_id})
        except Exception as e:
            logger.error(f"統計日誌總數失敗: {e}")
            return 0
