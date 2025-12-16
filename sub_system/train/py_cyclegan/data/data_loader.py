"""Data loading utilities for LEAF features."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from utils.mongo_helpers import collect_feature_vectors, find_step_across_runs

logger = logging.getLogger(__name__)


class MongoDBLEAFLoader:
    """Load dual-domain LEAF features directly from MongoDB."""

    def __init__(
        self,
        mongo_config: Dict[str, Any],
        *,
        step_name: str = 'LEAF Features',
        step_order: int = 2,
        timeout_ms: int = 5000
    ):
        self.config = mongo_config
        self.step_name = step_name
        self.step_order = step_order
        self.timeout_ms = timeout_ms
        self.client: Optional[MongoClient] = None
        self.collection: Optional[Collection] = None
        self._connect()

    def _build_uri(self) -> str:
        uri = self.config.get('uri')
        if uri:
            return uri

        username = self.config.get('username')
        password = self.config.get('password', '')
        host = self.config.get('host', 'localhost')
        port = self.config.get('port', 27017)

        if username:
            return f"mongodb://{username}:{password}@{host}:{port}/admin"
        return f"mongodb://{host}:{port}/admin"

    def _connect(self) -> None:
        """建立 MongoDB 連線。"""
        try:
            uri = self._build_uri()
            self.client = MongoClient(uri, serverSelectionTimeoutMS=self.timeout_ms)
            self.client.admin.command('ping')
            self.collection = self.client[self.config['database']][self.config['collection']]
            logger.info(
                "MongoDBLEAFLoader 已連線到 %s/%s",
                self.config['database'],
                self.config['collection'],
            )
        except PyMongoError as exc:
            logger.error("連線 MongoDB 失敗: %s", exc)
            raise

    def close(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
            self.collection = None
            logger.info("MongoDBLEAFLoader 已關閉連線")

    def _extract_leaf_features(self, record: Dict[str, Any]) -> Optional[np.ndarray]:
        """從記錄中提取完成的 LEAF features。"""
        step, _ = find_step_across_runs(
            record,
            step_name=self.step_name,
            step_order=self.step_order,
            require_completed=True,
        )
        if not step:
            return None

        vectors = collect_feature_vectors(step)
        if not vectors:
            return None

        return np.asarray(vectors, dtype=np.float32)

    def _fetch_records(self, query: Dict[str, Any], limit: Optional[int]) -> List[Dict[str, Any]]:
        if not self.collection:
            raise RuntimeError("MongoDBLEAFLoader 尚未連線")

        cursor = self.collection.find(query).sort('created_at', -1)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def load_domain(
        self,
        query: Dict[str, Any],
        *,
        max_records: Optional[int] = None,
    ) -> List[np.ndarray]:
        """根據查詢條件載入單一 Domain 的 features。"""
        features: List[np.ndarray] = []
        documents = self._fetch_records(query, max_records)
        for record in documents:
            feat = self._extract_leaf_features(record)
            if feat is not None:
                features.append(feat)
            else:
                logger.debug(
                    "AnalyzeUUID=%s 缺少 Step %s 或數據為空",
                    record.get('AnalyzeUUID'),
                    self.step_order,
                )

        return features

    def load_dual_domain(
        self,
        *,
        domain_a_query: Dict[str, Any],
        domain_b_query: Dict[str, Any],
        max_samples_a: Optional[int] = None,
        max_samples_b: Optional[int] = None,
    ) -> Dict[str, List[np.ndarray]]:
        """同時載入 Domain A/B 的資料。"""
        domain_a = self.load_domain(domain_a_query, max_records=max_samples_a)
        domain_b = self.load_domain(domain_b_query, max_records=max_samples_b)

        if not domain_a or not domain_b:
            raise ValueError(
                f"MongoDB 資料不足：Domain A={len(domain_a)}，Domain B={len(domain_b)}"
            )

        return {'domain_a': domain_a, 'domain_b': domain_b}


class FileLEAFLoader:
    """Load/save LEAF features from filesystem."""

    @staticmethod
    def load_from_json(path: str) -> List[np.ndarray]:
        with open(path, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        return [np.asarray(sample, dtype=np.float32) for sample in data]

    @staticmethod
    def load_from_npy(path: str) -> List[np.ndarray]:
        arr = np.load(path, allow_pickle=True)
        return [np.asarray(sample, dtype=np.float32) for sample in arr]

    @staticmethod
    def save_to_npy(features: List[np.ndarray], path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        np.save(path, np.array(features, dtype=object), allow_pickle=True)
