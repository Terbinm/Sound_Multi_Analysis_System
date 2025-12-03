# main.py - 分析服務主程式 (V2 - RabbitMQ 版本)

import signal
import sys
import uuid
import os
from pathlib import Path
from typing import Dict, Any, Optional
from threading import Lock
from datetime import datetime, timezone
import re

from config import (
    SERVICE_CONFIG,
    RABBITMQ_CONFIG,
    STATE_MANAGEMENT_CONFIG,
    BASE_DIR,
    AUDIO_CONFIG,
    CONVERSION_CONFIG,
    LEAF_CONFIG,
    CLASSIFICATION_CONFIG
)
from utils.logger import logger, analyze_uuid_context
from utils.mongodb_handler import MongoDBHandler
from analysis_pipeline import AnalysisPipeline
from rabbitmq_consumer import RetryableConsumer
from mongodb_node_manager import MongoDBNodeManager
from pymongo.collection import Collection

class AnalysisServiceV2:
    """分析服務主類別 (V2 - RabbitMQ 版本)"""

    def __init__(self):
        """初始化服務"""
        self.is_running = False
        self.node_id = self._load_or_create_node_id()

        # 核心組件
        self.mongodb_handler = None
        self.mongodb_connections = {}  # 多實例連接緩存
        self.pipeline = None
        self.rabbitmq_consumer = None
        self.node_manager = None  # MongoDB 節點管理器（取代 heartbeat_sender 和 state_client）
        self.node_registered = False
        self.analysis_configs_collection: Optional[Collection] = None

        # 任務追蹤
        self.processing_tasks = set()
        self.processing_lock = Lock()
        self.current_task_count = 0

        # 註冊信號處理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("=" * 60)
        logger.info(f"音訊分析服務 V2 初始化 (節點 ID: {self.node_id})")
        logger.info("=" * 60)

    def _load_or_create_node_id(self) -> str:
        """建立或載入節點 ID，確保重啟沿用同一 ID"""
        # 1) 先檢查常見環境變數
        for env_key in ('ANALYSIS_NODE_ID', 'NODE_ID', 'STATE_MANAGEMENT_NODE_ID'):
            env_value = os.getenv(env_key)
            if env_value:
                logger.info(f"使用環境變數 {env_key} 指定的節點 ID: {env_value}")
                return env_value

        # 2) 其次檢查設定檔提供的 node_id
        configured_id = STATE_MANAGEMENT_CONFIG.get('node_id')
        if configured_id:
            logger.info(f"使用設定檔指定的節點 ID: {configured_id}")
            return configured_id

        # 3) 最後嘗試從檔案載入，缺少時自動生成並寫回
        default_path = os.path.join(BASE_DIR, 'temp', 'analysis_node_id.txt')
        node_id_path = Path(
            STATE_MANAGEMENT_CONFIG.get('node_id_file')
            or os.getenv('ANALYSIS_NODE_ID_FILE')
            or default_path
        )

        try:
            if node_id_path.exists():
                stored_id = node_id_path.read_text(encoding='utf-8').strip()
                if stored_id:
                    logger.info(f"載入既有節點 ID: {stored_id}")
                    return stored_id
        except Exception as exc:  # 讀檔失敗僅警告，允許後續重新生成
            logger.warning(f"讀取節點 ID 檔案失敗 ({node_id_path}): {exc}")

        new_node_id = f"analysis_node_{uuid.uuid4().hex[:8]}"
        try:
            node_id_path.parent.mkdir(parents=True, exist_ok=True)
            node_id_path.write_text(new_node_id, encoding='utf-8')
            logger.info(f"產生新的節點 ID 並寫入 {node_id_path}: {new_node_id}")
        except Exception as exc:
            logger.warning(f"寫入節點 ID 檔案失敗 ({node_id_path}): {exc}")

        return new_node_id

    def _signal_handler(self, signum, frame):
        """處理終止信號"""
        logger.info(f"\n收到終止信號 ({signum})，正在關閉服務...")
        self.stop()
        sys.exit(0)

    def initialize(self):
        """初始化所有組件"""
        try:
            # 初始化默認 MongoDB 連接
            logger.info("初始化默認 MongoDB 連接...")
            self.mongodb_handler = MongoDBHandler()
            # 分析配置集合
            self.analysis_configs_collection = self.mongodb_handler.get_collection('analysis_configs')

            # 初始化分析流程
            logger.info("初始化分析流程...")
            self.pipeline = AnalysisPipeline(self.mongodb_handler)

            # 初始化 MongoDB 節點管理器（取代 HTTP 方式）
            logger.info("初始化 MongoDB 節點管理器...")
            node_info = {
                'capabilities': [SERVICE_CONFIG['analysis_Method_ID']],
                'version': 'v2.0',
                'max_concurrent_tasks': SERVICE_CONFIG['max_concurrent_tasks'],
                'tags': ['python', 'audio', 'leaf', 'rf']
            }

            self.node_manager = MongoDBNodeManager(
                mongodb_handler=self.mongodb_handler,
                node_id=self.node_id,
                node_info=node_info,
                heartbeat_interval=30
            )

            # 確保每個 capability 都有預設設定
            self._ensure_capability_defaults(node_info.get('capabilities', []))

            # 註冊節點到 MongoDB
            logger.info("註冊分析節點到 MongoDB...")
            if not self.node_manager.register_node():
                logger.error("節點註冊到 MongoDB 失敗")
                return False
            self.node_registered = True

            # 初始化 RabbitMQ 消費者
            logger.info("初始化 RabbitMQ 消費者...")
            self.rabbitmq_consumer = RetryableConsumer(
                RABBITMQ_CONFIG,
                self._process_task
            )

            logger.info("✓ 所有組件初始化完成")
            return True

        except Exception as e:
            logger.error(f"✗ 初始化失敗: {e}", exc_info=True)
            if self.node_manager and self.node_registered:
                self.node_manager.unregister_node()
                self.node_registered = False
            return False

    def start(self):
        """啟動服務"""
        if not self.initialize():
            logger.error("初始化失敗，服務無法啟動")
            return

        self.is_running = True

        try:
            # 啟動心跳發送（MongoDB 方式）
            logger.info("啟動心跳發送...")
            self.node_manager.start_heartbeat()

            # 開始監聽
            logger.info("=" * 60)
            logger.info("服務啟動成功，開始監聽任務隊列...")
            logger.info(f"節點 ID: {self.node_id}")
            logger.info("按 Ctrl+C 停止服務")
            logger.info("=" * 60)

            # 啟動 RabbitMQ 消費者（阻塞）
            self.rabbitmq_consumer.start()

        except KeyboardInterrupt:
            logger.info("\n收到中斷信號")
            self.stop()
        except Exception as e:
            logger.error(f"服務運行異常: {e}", exc_info=True)
            self.stop()

    def stop(self):
        """停止服務"""
        if not self.is_running and not self.node_registered:
            return

        logger.info("正在停止服務...")
        self.is_running = False

        # 1. 停止心跳發送
        if self.node_manager:
            self.node_manager.stop_heartbeat()

        # 2. 停止 RabbitMQ 消費者
        if self.rabbitmq_consumer:
            self.rabbitmq_consumer.stop()

        # 3. 從 MongoDB 註銷節點（必須在關閉連接之前）
        if self.node_manager and self.node_registered:
            try:
                if self.node_manager.unregister_node():
                    logger.info(f"節點 {self.node_id} 已從 MongoDB 註銷")
                else:
                    logger.warning(f"節點註銷失敗 ({self.node_id})")
            except Exception as e:
                logger.error(f"註銷節點時發生錯誤: {e}")
            self.node_registered = False

        # 4. 清理分析流程資源
        if self.pipeline:
            self.pipeline.cleanup()

        # 5. 關閉 MongoDB 連接
        if self.mongodb_handler:
            self.mongodb_handler.close()

        # 6. 清理多實例連接
        for instance_id, handler in self.mongodb_connections.items():
            try:
                handler.close()
            except:
                pass

        logger.info("服務已停止")

    def _process_task(self, task_data: Dict[str, Any]) -> bool:
        """
        處理任務

        Args:
            task_data: 任務數據

        Returns:
            是否成功
        """
        task_id = task_data.get('task_id', 'unknown')
        analyze_uuid = task_data.get('analyze_uuid')
        mongodb_instance = task_data.get('mongodb_instance')
        config_id = task_data.get('config_id')
        analysis_method_id = task_data.get('analysis_method_id') or (
            (self.node_manager.node_info.get('capabilities') or [None])[0] if self.node_manager else None
        )

        with analyze_uuid_context(analyze_uuid):
            try:
                logger.info(f"開始處理任務: {task_id}")
                logger.info(f"分析 UUID: {analyze_uuid}")
                logger.info(f"MongoDB 實例: {mongodb_instance}")
                logger.info(f"配置 ID: {config_id}")
                logger.info(f"分析方法 ID: {analysis_method_id}")

                # 任務狀態：processing
                self._update_task_status(task_id, 'processing')

                # 更新任務計數
                self._update_task_count(1)

                # 套用分析配置
                runtime_config = self._load_analysis_config(config_id, analysis_method_id)
                if not runtime_config:
                    logger.warning(
                        f"未找到啟用的配置 (config_id={config_id or 'None'} / capability={analysis_method_id})，使用預設值"
                    )
                self.pipeline.apply_runtime_config(runtime_config.get('parameters') if runtime_config else None)

                # 準備任務上下文，提供給 analyze_features.runs 記錄路由/配置/節點資訊
                metadata = task_data.get('metadata', {}) if isinstance(task_data, dict) else {}
                task_context = {
                    'task_id': task_id,
                    'analysis_method_id': analysis_method_id,
                    'analysis_method_name': runtime_config.get('analysis_method_id') if runtime_config else analysis_method_id,
                    'config_id': config_id,
                    'config_name': runtime_config.get('config_name') if runtime_config else None,
                    'router_id': metadata.get('router_id'),
                    'rule_id': metadata.get('rule_id'),
                    'rule_name': metadata.get('rule_name'),
                    'sequence_order': metadata.get('sequence_order'),
                    'mongodb_instance': mongodb_instance,
                    'metadata': metadata,
                    'node_id': self.node_id,
                    'node_info': self.node_manager.node_info if self.node_manager else {}
                }

                # 獲取 MongoDB 連接
                mongo_handler = self._get_mongodb_connection(mongodb_instance)
                if not mongo_handler:
                    err_msg = f"無法連接到 MongoDB 實例: {mongodb_instance}"
                    logger.error(err_msg)
                    self._update_task_status(task_id, 'failed', err_msg)
                    return False

                # 獲取記錄
                record = mongo_handler.get_collection('recordings').find_one({
                    'AnalyzeUUID': analyze_uuid
                })

                if not record:
                    err_msg = f"找不到記錄: {analyze_uuid}"
                    logger.error(err_msg)
                    self._update_task_status(task_id, 'failed', err_msg)
                    return False

                # 執行分析
                success = self.pipeline.process_record(record, task_context=task_context)

                if success:
                    logger.info(f"任務處理成功: {task_id}")
                    self._update_task_status(task_id, 'completed')
                else:
                    err_msg = f"任務處理失敗: {task_id}"
                    logger.error(err_msg)
                    self._update_task_status(task_id, 'failed', err_msg)

                return success

            except Exception as e:
                logger.error(f"處理任務異常: {e}", exc_info=True)
                self._update_task_status(task_id, 'failed', str(e))
                return False

            finally:
                # 更新任務計數
                self._update_task_count(-1)

    def _capability_slug(self, capability: str) -> str:
        return re.sub(r'[^a-zA-Z0-9]+', '_', str(capability)).strip('_').lower()

    def _ensure_capability_defaults(self, capabilities: list):
        """若缺少預設，為每個 capability 建立系統設定"""
        if self.analysis_configs_collection is None:
            return
        for cap in capabilities or []:
            if not cap:
                continue
            slug = self._capability_slug(cap)
            # 已有系統預設則跳過
            if self.analysis_configs_collection.find_one({
                'analysis_method_id': cap,
                'is_system': True
            }):
                continue
            config_id = f"default_{slug}"
            # 避免覆蓋任何現有設定
            if self.analysis_configs_collection.find_one({'config_id': config_id}):
                logger.info(f"略過建立預設，config_id 已存在: {config_id}")
                continue
            payload = {
                'analysis_method_id': cap,
                'config_id': config_id,
                'config_name': f"{cap} 系統預設",
                'description': f"依 capability {cap} 自動建立的系統預設",
                'parameters': {
                    'audio': dict(AUDIO_CONFIG),
                    'conversion': dict(CONVERSION_CONFIG),
                    'leaf': dict(LEAF_CONFIG),
                    'classification': dict(CLASSIFICATION_CONFIG)
                },
                'enabled': True,
                'is_system': True
            }
            try:
                self.analysis_configs_collection.insert_one(payload)
                logger.info(f"已為 {cap} 建立預設設定: {config_id}")
            except Exception as exc:
                logger.warning(f"建立預設設定失敗 ({cap}): {exc}")

    def _load_analysis_config(self, config_id: Optional[str], analysis_method_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        取得適用的分析配置：
        1) 有 config_id 則取該啟用設定
        2) 否則依 capability (analysis_method_id) 取啟用設定，優先 is_system
        """
        if self.analysis_configs_collection is None:
            return None
        # 明確指定 config_id
        if config_id:
            try:
                doc = self.analysis_configs_collection.find_one({
                    'config_id': config_id,
                    'enabled': True
                })
                if doc:
                    return doc
                logger.warning(f"找不到啟用的配置 config_id={config_id}")
            except Exception as exc:
                logger.error(f"載入分析配置失敗 ({config_id}): {exc}")

        # 依 capability 取預設/自訂
        if analysis_method_id:
            try:
                cursor = self.analysis_configs_collection.find({
                    'analysis_method_id': analysis_method_id,
                    'enabled': True
                }).sort([('is_system', -1), ('created_at', -1)])
                for doc in cursor:
                    return doc
            except Exception as exc:
                logger.error(f"依 capability 取得配置失敗 ({analysis_method_id}): {exc}")
        return None

    def _get_mongodb_connection(self, instance_id: str) -> MongoDBHandler:
        """獲取 MongoDB 連接"""
        # 如果是默認實例，使用默認連接
        if instance_id == 'default' or not instance_id:
            return self.mongodb_handler

        # 檢查緩存
        if instance_id in self.mongodb_connections:
            return self.mongodb_connections[instance_id]

        # 從 MongoDB 的 mongodb_instances collection 獲取實例配置
        try:
            collection = self.mongodb_handler.get_collection('mongodb_instances')
            instance_config = collection.find_one({'_id': instance_id})
            
            if not instance_config:
                logger.error(f"無法獲取實例配置: {instance_id}")
                return None

            # 創建新連接
            # TODO: 實現多實例 MongoDB 連接
            # 暫時使用默認連接
            logger.warning(f"暫時使用默認 MongoDB 連接: {instance_id}")
            return self.mongodb_handler

        except Exception as e:
            logger.error(f"獲取 MongoDB 連接失敗: {e}")
            return None

    def _update_task_status(self, task_id: str, status: str, error_message: Optional[str] = None) -> None:
        """更新 task_execution_logs 狀態，配合監控頁面顯示。"""
        if not self.mongodb_handler:
            return

        try:
            collection = self.mongodb_handler.get_collection('task_execution_logs')
        except Exception as exc:
            logger.error(f"任務狀態更新失敗（無法取得集合）: {exc}")
            return

        update_data = {'status': status}

        # 僅在 processing 時補寫 started_at
        try:
            existing = collection.find_one({'task_id': task_id}, {'started_at': 1})
        except Exception as exc:
            logger.error(f"查詢任務狀態失敗 ({task_id}): {exc}")
            return

        if status == 'processing':
            if not existing or not existing.get('started_at'):
                update_data['started_at'] = datetime.now(timezone.utc)

        if status in ('completed', 'failed'):
            update_data['completed_at'] = datetime.now(timezone.utc)

        if error_message:
            update_data['error_message'] = error_message

        # 紀錄處理節點，供前端顯示與排錯
        if self.node_id:
            update_data['node_id'] = self.node_id
            if self.node_manager:
                update_data['node_info'] = self.node_manager.node_info

        try:
            collection.update_one({'task_id': task_id}, {'$set': update_data})
            logger.debug(f"更新任務狀態: {task_id} -> {status}")
        except Exception as exc:
            logger.error(f"任務狀態更新失敗 ({task_id} -> {status}): {exc}")

    def _update_task_count(self, delta: int):
        """更新當前任務計數"""
        with self.processing_lock:
            self.current_task_count += delta

            # 更新節點管理器的任務計數
            if self.node_manager:
                self.node_manager.update_task_count(self.current_task_count)


def main():
    """主程式入口"""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║         音訊分析服務 - Analysis Service V2.0 (RabbitMQ)     ║
    ║                                                          ║
    ║  功能:                                                    ║
    ║  1. 從 RabbitMQ 消費分析任務                              ║
    ║  2. 支援多 MongoDB 實例                                   ║
    ║  3. 向狀態管理系統發送心跳                                 ║
    ║  4. 動態配置管理                                          ║
    ║                                                          ║
    ║  流程:                                                    ║
    ║  - 音訊轉檔 (Step 0)                                      ║
    ║  - 音訊切割 (Step 1)                                      ║
    ║  - LEAF 特徵提取 (Step 2)                                 ║
    ║  - 分類預測 (Step 3)                                      ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)

    # 建立並啟動服務
    service = AnalysisServiceV2()
    service.start()


if __name__ == '__main__':
    main()
