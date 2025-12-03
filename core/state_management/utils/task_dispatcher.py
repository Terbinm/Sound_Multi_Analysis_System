"""
任務派送工具
負責根據 router_id 為後續處理建立任務記錄
"""
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from models.routing_rule import RoutingRule
from models.analysis_config import AnalysisConfig
from models.task_execution_log import TaskExecutionLog
from utils.mongodb_handler import get_db, MultiMongoDBHandler
from utils.rabbitmq_handler import RabbitMQPublisher
from config import get_config

logger = logging.getLogger(__name__)


class TaskDispatcher:
    """任務派送器"""

    def __init__(self):
        """初始化"""
        self.config = get_config()
        self.mongo_handler = MultiMongoDBHandler()
        self.rabbitmq_publisher = RabbitMQPublisher(self.config.RABBITMQ_CONFIG)

    def dispatch_by_router_ids(
        self,
        analyze_uuid: str,
        router_ids: List[str],
        sequential: bool = True
    ) -> Dict[str, Any]:
        """
        根據 router_ids 列表派送任務

        Args:
            analyze_uuid: 分析資料的 UUID
            router_ids: routerID 列表
            sequential: 是否依序執行（True: 串行，False: 並行）

        Returns:
            派送結果
        """
        results = {
            'success': True,
            'analyze_uuid': analyze_uuid,
            'router_ids': router_ids,
            'tasks_created': [],
            'errors': []
        }

        try:
            for index, router_id in enumerate(router_ids):
                # 派送單個 router_id 的任務
                result = self.dispatch_by_router_id(
                    analyze_uuid=analyze_uuid,
                    router_id=router_id,
                    sequence_order=index if sequential else None
                )

                if result['success']:
                    results['tasks_created'].extend(result['tasks_created'])
                else:
                    results['errors'].append({
                        'router_id': router_id,
                        'error': result.get('error', '未知錯誤')
                    })

            # 如果有任何錯誤，標記整體為失敗
            if results['errors']:
                results['success'] = False

        except Exception as e:
            logger.error(f"批量派送任務失敗: {e}", exc_info=True)
            results['success'] = False
            results['errors'].append({
                'error': str(e)
            })

        return results

    def dispatch_by_router_id(
        self,
        analyze_uuid: str,
        router_id: str,
        sequence_order: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        根據單個 router_id 派送任務

        Args:
            analyze_uuid: 分析資料的 UUID
            router_id: routerID
            sequence_order: 序列順序（用於串行執行時設定優先級）

        Returns:
            派送結果
        """
        result = {
            'success': False,
            'router_id': router_id,
            'analyze_uuid': analyze_uuid,
            'tasks_created': [],
            'error': None
        }

        try:
            # 1. 根據 router_id 查找規則
            rule = RoutingRule.get_by_router_id(router_id)
            if not rule:
                result['error'] = f'找不到 router_id: {router_id}'
                logger.warning(result['error'])
                return result

            if not rule.enabled:
                result['error'] = f'規則已禁用: {rule.rule_name}'
                logger.warning(result['error'])
                return result

            # 2. 查找 MongoDB 中的記錄
            db = get_db()
            collection = db[self.config.COLLECTIONS['recordings']]

            record = collection.find_one({'AnalyzeUUID': analyze_uuid})
            if not record:
                result['error'] = f'找不到記錄: {analyze_uuid}'
                logger.warning(result['error'])
                return result

            # 3. 檢查是否已經處理過此 router_id
            assigned_router_ids = record.get('assigned_router_ids', [])
            if router_id in assigned_router_ids:
                result['error'] = f'此記錄已被 router_id 處理過: {router_id}'
                logger.info(result['error'])
                return result

            # 4. 為規則的每個 action 創建任務
            tasks_created, publish_failures = self._create_tasks_for_rule(
                rule=rule,
                router_id=router_id,
                analyze_uuid=analyze_uuid,
                sequence_order=sequence_order
            )

            if tasks_created:
                # 5. 更新記錄，標記此 router_id 已處理
                collection.update_one(
                    {'AnalyzeUUID': analyze_uuid},
                    {
                        '$addToSet': {'assigned_router_ids': router_id},
                        '$set': {'last_router_dispatch': datetime.utcnow()}
                    }
                )

                result['success'] = True
                result['tasks_created'] = tasks_created
                logger.info(
                    f"成功派送 {len(tasks_created)} 個任務 "
                    f"(router_id: {router_id}, analyze_uuid: {analyze_uuid})"
                )
            else:
                error_hint = '未能創建任何任務'
                if publish_failures:
                    error_hint += '（RabbitMQ 發布失敗）'
                result['error'] = error_hint

        except Exception as e:
            logger.error(f"派送任務失敗: {e}", exc_info=True)
            result['error'] = str(e)

        return result

    def backfill_by_router_id(
        self,
        router_id: str,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        追溯歷史資料，為符合規則條件的所有記錄派送任務

        Args:
            router_id: routerID
            limit: 限制處理數量（None 表示全部）

        Returns:
            追溯結果
        """
        result = {
            'success': False,
            'router_id': router_id,
            'total_matched': 0,
            'tasks_created': 0,
            'errors': []
        }

        try:
            # 1. 根據 router_id 查找規則
            rule = RoutingRule.get_by_router_id(router_id)
            if not rule:
                result['error'] = f'找不到 router_id: {router_id}'
                return result

            # 2. 使用規則的 conditions 查詢符合條件的記錄
            db = get_db()
            collection = db[self.config.COLLECTIONS['recordings']]

            # 構建 MongoDB query
            query = rule.build_mongodb_query()

            # 排除已經被此 router_id 處理過的記錄
            query['assigned_router_ids'] = {'$ne': router_id}

            # 統計總數
            total_matched = collection.count_documents(query)
            result['total_matched'] = total_matched

            logger.info(f"追溯任務: 找到 {total_matched} 條符合條件的記錄 (router_id: {router_id})")

            if total_matched == 0:
                result['success'] = True
                return result

            # 3. 查詢記錄並派送任務
            cursor = collection.find(query)
            if limit:
                cursor = cursor.limit(limit)

            tasks_count = 0
            for record in cursor:
                analyze_uuid = record.get('AnalyzeUUID')
                if not analyze_uuid:
                    continue

                # 派送任務
                dispatch_result = self.dispatch_by_router_id(
                    analyze_uuid=analyze_uuid,
                    router_id=router_id
                )

                if dispatch_result['success']:
                    tasks_count += len(dispatch_result['tasks_created'])
                else:
                    result['errors'].append({
                        'analyze_uuid': analyze_uuid,
                        'error': dispatch_result.get('error')
                    })

            result['tasks_created'] = tasks_count
            result['success'] = True

            logger.info(
                f"追溯完成: 創建 {tasks_count} 個任務 "
                f"(router_id: {router_id}, 符合條件: {total_matched})"
            )

        except Exception as e:
            logger.error(f"追溯歷史資料失敗: {e}", exc_info=True)
            result['error'] = str(e)

        return result

    def preview_matching_records(
        self,
        conditions: Dict[str, Any],
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        預覽符合條件的記錄

        Args:
            conditions: 匹配條件
            limit: 返回數量限制

        Returns:
            預覽結果
        """
        result = {
            'success': False,
            'total': 0,
            'records': [],
            'sample': []
        }

        try:
            db = get_db()
            collection = db[self.config.COLLECTIONS['recordings']]

            # 創建臨時規則對象以使用 build_mongodb_query
            temp_rule = RoutingRule()
            temp_rule.conditions = conditions
            query = temp_rule.build_mongodb_query()

            # 統計總數
            total = collection.count_documents(query)
            result['total'] = total

            # 獲取樣本記錄
            records = []
            for record in collection.find(query).limit(limit):
                # 只返回必要欄位
                records.append({
                    'AnalyzeUUID': record.get('AnalyzeUUID'),
                    'info_features': record.get('info_features', {}),
                    'assigned_router_ids': record.get('assigned_router_ids', []),
                    '_id': str(record.get('_id'))
                })

            result['records'] = records
            result['sample'] = records[:10]  # 前 10 筆作為樣本
            result['success'] = True

        except Exception as e:
            logger.error(f"預覽符合條件的記錄失敗: {e}", exc_info=True)
            result['error'] = str(e)

        return result

    def _build_routing_key(self, analysis_method_id: str) -> str:
        """組合 RabbitMQ routing key，例如 analysis.<method>"""
        prefix = self.config.RABBITMQ_CONFIG.get('routing_key_prefix', 'analysis')
        safe_method = analysis_method_id or 'unknown'
        return f"{prefix}.{safe_method}"

    def _publish_task_message(
        self,
        task_data: Dict[str, Any],
        analysis_method_id: str
    ) -> bool:
        """將任務發布到 RabbitMQ"""
        routing_key = self._build_routing_key(analysis_method_id)
        return self.rabbitmq_publisher.publish_task(
            task_data=task_data,
            routing_key=routing_key
        )

    def _create_tasks_for_rule(
        self,
        rule: RoutingRule,
        router_id: str,
        analyze_uuid: str,
        sequence_order: Optional[int] = None
    ) -> Tuple[List[str], List[str]]:
        """
        為規則創建任務

        Args:
            rule: 路由規則
            router_id: routerID
            analyze_uuid: 分析資料 UUID
            sequence_order: 序列順序

        Returns:
            創建的任務 ID 列表
        """
        task_ids: List[str] = []
        publish_failures: List[str] = []

        try:
            # 遍歷規則的所有 actions
            for action in rule.actions:
                analysis_method_id = action['analysis_method_id']
                config_id = action['config_id']
                target_instance = action.get('mongodb_instance', 'default')

                # 獲取配置
                config = AnalysisConfig.get_by_id(config_id)
                if not config:
                    logger.warning(f"配置不存在: {config_id}")
                    continue

                if not config.enabled:
                    logger.info(f"配置已禁用: {config_id}")
                    continue

                # 創建任務
                task_id = str(uuid.uuid4())

                task_data = {
                    'task_id': task_id,
                    'mongodb_instance': target_instance,
                    'analyze_uuid': analyze_uuid,
                    'analysis_method_id': analysis_method_id,
                    'config_id': config_id,
                    'created_at': datetime.utcnow().isoformat(),
                    'retry_count': 0,
                    'metadata': {
                        'rule_id': rule.rule_id,
                        'rule_name': rule.rule_name,
                        'router_id': router_id,
                        'config_name': config.config_name,
                        'analysis_method_name': config.analysis_method_id,
                        'sequence_order': sequence_order
                    }
                }

                TaskExecutionLog.create({
                    'task_id': task_id,
                    'router_id': router_id,
                    'rule_id': rule.rule_id,
                    'analyze_uuid': analyze_uuid,
                    'analysis_method_id': analysis_method_id,
                    'config_id': config_id,
                    'mongodb_instance': target_instance,
                    'status': 'pending',
                    'metadata': {
                        'rule_name': rule.rule_name,
                        'config_name': config.config_name,
                        'sequence_order': sequence_order
                    }
                })

                # 發布到 RabbitMQ
                published = self._publish_task_message(
                    task_data=task_data,
                    analysis_method_id=analysis_method_id
                )

                if not published:
                    publish_failures.append(task_id)
                    TaskExecutionLog.update_status(
                        task_id=task_id,
                        status='failed',
                        error_message='RabbitMQ publish failed'
                    )
                    continue

                task_ids.append(task_id)

                logger.info(
                    f"任務已建立並發布: {task_id} "
                    f"(方法: {analysis_method_id}, 配置: {config_id})"
                )

        except Exception as e:
            logger.error(f"創建任務失敗: {e}", exc_info=True)

        if publish_failures:
            logger.warning(
                f"以下任務發布到 RabbitMQ 失敗（已標記為 failed）: {publish_failures}"
            )

        return task_ids, publish_failures
