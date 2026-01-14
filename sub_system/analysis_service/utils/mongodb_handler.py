# utils/mongodb_handler.py - MongoDB 操作工具（加入 Step 0 支援）

from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
from uuid import uuid4
from copy import deepcopy
from config import MONGODB_CONFIG, DATABASE_INDEXES
from utils.logger import logger


class StepNames:
    """分析步驟名稱常數"""
    AUDIO_CONVERSION = "Audio Conversion"
    AUDIO_SLICING = "Audio Slicing"
    LEAF_FEATURES = "LEAF Features"
    CLASSIFICATION = "Classification"


def build_analysis_container() -> Dict[str, Any]:
    """建立 analyze_features 預設結構"""
    return {
        'active_analysis_id': None,
        'latest_analysis_id': None,
        'total_runs': 0,
        'last_requested_at': None,
        'last_started_at': None,
        'last_completed_at': None,
        'runs': {}  # 改為 dict，以 analysis_id 為 key
    }


class MongoDBHandler:
    """MongoDB 操作處理器"""

    def __init__(self):
        """初始化 MongoDB 連接"""
        self.config = MONGODB_CONFIG
        self.mongo_client = None
        self.db = None
        self.collection = None
        self._connect()

    def _connect(self):
        """建立 MongoDB 連接"""
        try:
            connection_string = (
                f"mongodb://{self.config['username']}:{self.config['password']}"
                f"@{self.config['host']}:{self.config['port']}/admin"
            )
            self.mongo_client = MongoClient(connection_string)
            self.db = self.mongo_client[self.config['database']]
            self.collection = self.db[self.config['collection']]

            # 測試連接
            self.mongo_client.admin.command('ping')
            logger.info("✓ MongoDB 連接成功")

            # 建立索引
            self._create_indexes()

        except Exception as e:
            logger.error(f"✗ MongoDB 連接失敗: {e}")
            raise

    def _create_indexes(self):
        """建立資料庫索引"""
        for index_field in DATABASE_INDEXES:
            try:
                self.collection.create_index([(index_field, ASCENDING)])
                logger.debug(f"索引建立成功: {index_field}")
            except Exception as e:
                logger.warning(f"索引建立失敗 {index_field}: {e}")

    def get_collection(self, collection_name: Optional[str] = None):
        """
        取得指定集合，預設回傳初始化時的主集合

        Args:
            collection_name: 集合名稱，若為 None 則回傳 self.collection
        """
        if self.db is None:
            raise RuntimeError("MongoDB 尚未連線")

        if collection_name:
            return self.db[collection_name]

        if self.collection is None:
            raise RuntimeError("預設集合尚未設置")

        return self.collection

    def _merge_container_defaults(self, container: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], bool]:
        """
        將既有 analyze_features 容器補齊必要欄位

        Returns:
            (補齊後容器, 是否需要回寫資料庫)
        """
        merged = build_analysis_container()
        needs_update = False

        if not isinstance(container, dict):
            return merged, True

        # 複製基本欄位（移除 latest_summary_index）
        for key in ['active_analysis_id', 'latest_analysis_id']:
            if key in container:
                merged[key] = container.get(key)
            else:
                needs_update = True

        # 處理 metadata（舊版相容）
        legacy_metadata = container.get('metadata')
        if isinstance(legacy_metadata, dict):
            merged['total_runs'] = legacy_metadata.get('total_runs', merged['total_runs'])
            merged['last_requested_at'] = legacy_metadata.get('last_requested_at')
            merged['last_started_at'] = legacy_metadata.get('last_started_at')
            merged['last_completed_at'] = legacy_metadata.get('last_completed_at')
            needs_update = True
        else:
            for key in ['total_runs', 'last_requested_at', 'last_started_at', 'last_completed_at']:
                if key in container:
                    merged[key] = container.get(key)
                else:
                    needs_update = True

        # 處理 runs：從 list 轉為 dict
        runs = container.get('runs')
        if isinstance(runs, dict):
            # 已經是 dict 格式
            merged['runs'] = runs
        elif isinstance(runs, list):
            # 舊的 list 格式，轉換為 dict
            runs_dict = {}
            for run in runs:
                if isinstance(run, dict):
                    analysis_id = run.get('analysis_id')
                    if analysis_id:
                        runs_dict[analysis_id] = run
            merged['runs'] = runs_dict
            needs_update = True
        else:
            merged['runs'] = {}
            needs_update = True

        # 更新 total_runs
        if merged['total_runs'] == 0 and merged['runs']:
            merged['total_runs'] = len(merged['runs'])
            needs_update = True

        return merged, needs_update

    def _wrap_legacy_analyze_features(self, record: Dict[str, Any], legacy_value: Any) -> Dict[str, Any]:
        """
        將舊版 list 結構包裝成多 run 容器
        """
        container = build_analysis_container()
        if isinstance(legacy_value, list) and legacy_value:
            legacy_id = f"legacy-{record.get('AnalyzeUUID', uuid4().hex)}"
            summary = record.get('analysis_summary', {}) or {}

            # 轉換舊的 steps list 為新的 dict 格式
            steps_dict = {}
            for step in legacy_value:
                if isinstance(step, dict):
                    step_name = step.get('features_name', f"Step {step.get('features_step', 'unknown')}")
                    steps_dict[step_name] = {
                        'display_order': step.get('features_step', 0),
                        'features_state': step.get('features_state', 'unknown'),
                        'features_data': step.get('features_data', []),
                        'processor_metadata': step.get('processor_metadata', {}),
                        'error_message': step.get('error_message'),
                        'started_at': step.get('started_at'),
                        'completed_at': step.get('completed_at')
                    }

            legacy_run = {
                'analysis_id': legacy_id,
                'analysis_summary': summary,
                'analysis_context': {'imported_from': 'legacy'},
                'steps': steps_dict,
                'requested_at': record.get('created_at'),
                'started_at': record.get('processing_started_at') or record.get('created_at'),
                'completed_at': record.get('updated_at'),
                'error_message': record.get('error_message')
            }

            # 使用 dict 格式存儲 runs
            container['runs'] = {legacy_id: legacy_run}
            container['active_analysis_id'] = None
            container['latest_analysis_id'] = legacy_id
            container['total_runs'] = 1
            container['last_requested_at'] = legacy_run.get('requested_at')
            container['last_started_at'] = legacy_run.get('started_at')
            container['last_completed_at'] = legacy_run.get('completed_at')

        return container

    def ensure_analysis_container(self, analyze_uuid: str,
                                  record: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        確保 analyze_features 採用最新結構

        Returns:
            正常化後的容器
        """
        if record is None:
            record = self.get_record_by_uuid(analyze_uuid)

        if not record:
            raise ValueError(f"找不到記錄: {analyze_uuid}")

        raw_value = record.get('analyze_features')
        needs_update = False

        if isinstance(raw_value, dict) and 'runs' in raw_value:
            container, needs_update = self._merge_container_defaults(raw_value)
        else:
            container = self._wrap_legacy_analyze_features(record, raw_value)
            needs_update = True

        # 總是移除頂層的 analysis_summary（避免與 analyze_features 不同步）
        has_top_level_summary = record.get('analysis_summary') is not None

        if needs_update or has_top_level_summary:
            update_doc: Dict[str, Any] = {}
            if needs_update:
                update_doc['$set'] = {'analyze_features': container}
            if has_top_level_summary:
                update_doc.setdefault('$unset', {})['analysis_summary'] = ""

            if update_doc:
                self.collection.update_one({'AnalyzeUUID': analyze_uuid}, update_doc)
                record['analyze_features'] = container

        return container

    def start_analysis_run(self, analyze_uuid: str,
                           request_context: Optional[Dict[str, Any]] = None,
                           record: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        建立新的分析 run, 以支援多次完整分析
        """
        request_context = deepcopy(request_context or {})
        if record is None:
            record = self.get_record_by_uuid(analyze_uuid)

        if not record:
            logger.error(f"建立分析 run 失敗，找不到記錄: {analyze_uuid}")
            return None

        container = self.ensure_analysis_container(analyze_uuid, record)
        existing_runs = container.get('runs', {})

        analysis_id = request_context.get('analysis_id') or f"run_{uuid4().hex}"
        current_time = datetime.now(timezone.utc)
        requested_at = request_context.get('requested_at', current_time)
        routing_ctx = request_context.get('routing_rule', {}) if isinstance(request_context, dict) else {}
        config_ctx = request_context.get('analysis_config', {}) if isinstance(request_context, dict) else {}
        node_ctx = request_context.get('node', {}) if isinstance(request_context, dict) else {}

        run_doc = {
            'analysis_id': analysis_id,
            'analysis_summary': {},
            'analysis_context': request_context,
            'routing_rule_id': routing_ctx.get('rule_id'),
            'router_id': routing_ctx.get('router_id'),
            'analysis_config_id': config_ctx.get('config_id'),
            'analysis_method_id': config_ctx.get('analysis_method_id'),
            'node_id': node_ctx.get('node_id'),
            'steps': {},  # 改為 dict
            'requested_at': requested_at,
            'started_at': current_time,
            'completed_at': None,
            'error_message': None
        }

        # 使用 $set 而非 $push（dict 格式）
        update_doc = {
            '$set': {
                f'analyze_features.runs.{analysis_id}': run_doc,
                'updated_at': current_time,
                'analyze_features.active_analysis_id': analysis_id,
                'analyze_features.latest_analysis_id': analysis_id,
                'analyze_features.last_requested_at': requested_at,
                'analyze_features.last_started_at': current_time,
                'analyze_features.total_runs': len(existing_runs) + 1
            }
        }

        result = self.collection.update_one({'AnalyzeUUID': analyze_uuid}, update_doc)

        if result.modified_count == 0:
            logger.error(f"建立分析 run 失敗: {analyze_uuid}")
            return None

        return {'analysis_id': analysis_id}

    def try_claim_record(self, analyze_uuid: str) -> bool:
        """
        嘗試認領記錄進行處理(原子操作)

        使用 analyze_features.active_analysis_id 來判斷是否可以認領

        Returns:
            True: 認領成功,可以處理
            False: 已被其他 Worker 認領或正在處理中
        """
        try:
            # 注意：實際的認領邏輯已移至 start_analysis_run()
            # 這裡只是檢查是否有正在進行的分析
            result = self.collection.update_one(
                {
                    'AnalyzeUUID': analyze_uuid,
                    '$or': [
                        {'analyze_features.active_analysis_id': None},
                        {'analyze_features.active_analysis_id': {'$exists': False}}
                    ]
                },
                {
                    '$set': {
                        'processing_started_at': datetime.now(timezone.utc),
                        'updated_at': datetime.now(timezone.utc)
                    }
                }
            )

            # modified_count > 0 表示成功認領
            return result.modified_count > 0

        except Exception as e:
            logger.error(f"認領記錄失敗 {analyze_uuid}: {e}")
            return False

    def find_pending_records(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        查找待處理的記錄（沒有正在進行的分析）

        Args:
            limit: 最大返回數量

        Returns:
            待處理記錄列表
        """
        try:
            query = {
                '$or': [
                    {'analyze_features.active_analysis_id': None},
                    {'analyze_features.active_analysis_id': {'$exists': False}},
                    {'analyze_features': {'$exists': False}}  # 舊記錄
                ]
            }
            records = list(self.collection.find(query).limit(limit))
            logger.debug(f"找到 {len(records)} 筆待處理記錄")
            return records
        except Exception as e:
            logger.error(f"查詢待處理記錄失敗: {e}")
            return []

    def save_conversion_results(self, analyze_uuid: str, conversion_info: Dict,
                                analysis_id: str,
                                conversion_state: str = 'completed') -> bool:
        """
        儲存轉檔結果（Step 0: Audio Conversion）

        Args:
            analyze_uuid: 記錄 UUID
            conversion_info: 轉檔資訊
            analysis_id: 分析 run ID（必要）
            conversion_state: 轉檔狀態

        Returns:
            是否儲存成功
        """
        try:
            current_time = datetime.now(timezone.utc)

            conversion_step = {
                'display_order': 0,
                'features_state': conversion_state,
                'features_data': [],  # 轉檔步驟無特徵資料
                'error_message': None,
                'started_at': current_time,
                'completed_at': current_time,
                'processor_metadata': conversion_info
            }

            result = self.collection.update_one(
                {'AnalyzeUUID': analyze_uuid},
                {
                    '$set': {
                        f'analyze_features.runs.{analysis_id}.steps.{StepNames.AUDIO_CONVERSION}': conversion_step,
                        'updated_at': current_time,
                        'analyze_features.last_started_at': conversion_info.get('started_at', current_time)
                    }
                }
            )

            return result.modified_count > 0

        except Exception as e:
            logger.error(f"儲存轉檔結果失敗 {analyze_uuid}: {e}")
            return False

    def save_slice_results(self, analyze_uuid: str, features_data: List[Dict],
                           analysis_id: str) -> bool:
        """
        儲存切割結果（Step 1: Audio Slicing）

        Args:
            analyze_uuid: 記錄 UUID
            features_data: 切割特徵資料
            analysis_id: 分析 run ID（必要）

        Returns:
            是否儲存成功
        """
        try:
            current_time = datetime.now(timezone.utc)

            slice_step = {
                'display_order': 1,
                'features_state': 'completed',
                'features_data': features_data,
                'error_message': None,
                'started_at': current_time,
                'completed_at': current_time,
                'processor_metadata': {
                    'segments_count': len(features_data),
                    'total_duration': round(sum(fd['end'] - fd['start'] for fd in features_data), 3)
                }
            }

            result = self.collection.update_one(
                {'AnalyzeUUID': analyze_uuid},
                {
                    '$set': {
                        f'analyze_features.runs.{analysis_id}.steps.{StepNames.AUDIO_SLICING}': slice_step,
                        'updated_at': current_time
                    }
                }
            )

            return result.modified_count > 0

        except Exception as e:
            logger.error(f"儲存切割結果失敗 {analyze_uuid}: {e}")
            return False

    def save_leaf_features(self, analyze_uuid: str, features_data: List[Dict],
                           processor_metadata: Dict,
                           analysis_id: str) -> bool:
        """
        儲存 LEAF 特徵（Step 2: LEAF Features）

        Args:
            analyze_uuid: 記錄 UUID
            features_data: LEAF 特徵資料
            processor_metadata: 提取資訊
            analysis_id: 分析 run ID（必要）

        Returns:
            是否儲存成功
        """
        try:
            current_time = datetime.now(timezone.utc)

            leaf_step = {
                'display_order': 2,
                'features_state': 'completed',
                'features_data': features_data,
                'processor_metadata': processor_metadata,
                'error_message': None,
                'started_at': current_time,
                'completed_at': current_time
            }

            result = self.collection.update_one(
                {'AnalyzeUUID': analyze_uuid},
                {
                    '$set': {
                        f'analyze_features.runs.{analysis_id}.steps.{StepNames.LEAF_FEATURES}': leaf_step,
                        'updated_at': current_time
                    }
                }
            )

            return result.modified_count > 0

        except Exception as e:
            logger.error(f"儲存 LEAF 特徵失敗 {analyze_uuid}: {e}")
            return False

    def save_classification_results(self, analyze_uuid: str,
                                    classification_results: Dict,
                                    analysis_id: str) -> bool:
        """
        儲存分類結果（Step 3: Classification）

        Args:
            analyze_uuid: 記錄 UUID
            classification_results: 分類結果 (包含 features_data 和 processor_metadata)
            analysis_id: 分析 run ID（必要）

        Returns:
            是否儲存成功
        """
        try:
            current_time = datetime.now(timezone.utc)

            # 統一格式：與其他步驟一致
            classify_step = {
                'display_order': 3,
                'features_state': 'completed',
                'features_data': classification_results.get('features_data', []),
                'processor_metadata': classification_results.get('processor_metadata', {}),
                'error_message': None,
                'started_at': current_time,
                'completed_at': current_time
            }

            # 從 processor_metadata 提取摘要資訊
            processor_metadata = classification_results.get('processor_metadata', {})

            summary = {
                'final_prediction': processor_metadata.get('final_prediction', 'unknown'),
                'total_segments': processor_metadata.get('total_segments', 0),
                'normal_count': processor_metadata.get('normal_count', 0),
                'abnormal_count': processor_metadata.get('abnormal_count', 0),
                'unknown_count': processor_metadata.get('unknown_count', 0),
                'average_confidence': processor_metadata.get('average_confidence', 0.0),
                'method': processor_metadata.get('method', 'unknown')
            }

            result = self.collection.update_one(
                {'AnalyzeUUID': analyze_uuid},
                {
                    '$set': {
                        f'analyze_features.runs.{analysis_id}.steps.{StepNames.CLASSIFICATION}': classify_step,
                        f'analyze_features.runs.{analysis_id}.analysis_summary': summary,
                        f'analyze_features.runs.{analysis_id}.completed_at': current_time,
                        f'analyze_features.runs.{analysis_id}.error_message': None,
                        'analyze_features.last_completed_at': current_time,
                        'analyze_features.active_analysis_id': None,  # 完成後釋放
                        'updated_at': current_time
                    }
                }
            )

            return result.modified_count > 0

        except Exception as e:
            logger.error(f"儲存分類結果失敗 {analyze_uuid}: {e}")
            return False

    def get_record_by_uuid(self, analyze_uuid: str) -> Optional[Dict]:
        """
        根據 UUID 獲取記錄

        Args:
            analyze_uuid: 記錄 UUID

        Returns:
            記錄資料或 None
        """
        try:
            return self.collection.find_one({'AnalyzeUUID': analyze_uuid})
        except Exception as e:
            logger.error(f"獲取記錄失敗 {analyze_uuid}: {e}")
            return None

    def watch_changes(self):
        """
        監聽 MongoDB Change Stream

        Yields:
            變更事件
        """
        try:
            logger.info("開始監聽 MongoDB Change Stream...")

            # 只監聽插入事件
            pipeline = [
                {'$match': {'operationType': 'insert'}}
            ]

            with self.collection.watch(pipeline) as stream:
                for change in stream:
                    yield change

        except Exception as e:
            logger.error(f"Change Stream 監聽失敗: {e}")
            raise

    def close(self):
        """關閉連接"""
        if self.mongo_client:
            self.mongo_client.close()
            logger.info("MongoDB 連接已關閉")
