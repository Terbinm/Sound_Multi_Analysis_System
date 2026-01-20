from __future__ import annotations

"""
RF.mongo_helpers

檢查 MongoDB 連線的預設及如何 query 函式，供 combine_cyclegan_rf CLI 或 export_uuid_list 使用。
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pymongo import MongoClient

# 嘗試載入 .env 文件
try:
    from dotenv import load_dotenv
    # 從此檔案向上找到專案根目錄的 .env
    _ROOT = Path(__file__).resolve().parents[3]
    _ENV_PATH = _ROOT / ".env"
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH, override=True)
        print(f"[mongo_helpers] 已載入 .env: {_ENV_PATH}")
except ImportError:
    print("[WARNING] python-dotenv 未安裝，無法自動載入 .env")

DEFAULT_MONGO = {
    'host': 'localhost',
    'port': 55101,
    'username': None,
    'password': None,
    'database': 'web_db',
    'collection': 'recordings',
    'auth_source': 'admin',
}


def load_default_mongo_config() -> Dict[str, Any]:
    """
    提供外部的 default config。
    優先從環境變數讀取（.env 已載入），若無則使用預設值。
    """
    config = {
        'host': os.getenv('MONGODB_HOST') or DEFAULT_MONGO['host'],
        'port': int(os.getenv('MONGODB_PORT') or DEFAULT_MONGO['port']),
        'username': os.getenv('MONGODB_USERNAME') or DEFAULT_MONGO['username'],
        'password': os.getenv('MONGODB_PASSWORD') or DEFAULT_MONGO['password'],
        'database': os.getenv('MONGODB_DATABASE') or DEFAULT_MONGO['database'],
        'collection': os.getenv('MONGODB_COLLECTION') or DEFAULT_MONGO['collection'],
        'auth_source': os.getenv('MONGODB_AUTH_SOURCE') or DEFAULT_MONGO['auth_source'],
    }
    return config


def merge_mongo_overrides(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """可以從 CLI args 或自訂的參數用來覆蓋原本的 Mongo config。"""
    merged = dict(base)
    for key, value in overrides.items():
        if value is not None:
            merged[key] = value
    return merged


def connect_mongo(config: Dict[str, Any]) -> Tuple[MongoClient, Any]:
    """如果 username/password 有設，自動建立帶有 authSource 連線，回傳使用者指定的 collection。"""
    host = config.get('host') or DEFAULT_MONGO['host']
    port = int(config.get('port') or DEFAULT_MONGO['port'])
    username = config.get('username') or None
    password = config.get('password') or None
    auth_source = config.get('auth_source') or config.get('authSource') or DEFAULT_MONGO['auth_source']

    # Debug: 顯示連線參數
    print(f"[DEBUG] host={host}, port={port}, username={username}, auth_source={auth_source}")

    # 只有在有 username 時才傳遞認證相關參數
    if username:
        client = MongoClient(
            host=host,
            port=port,
            username=username,
            password=password,
            authSource=auth_source,
        )
    else:
        client = MongoClient(
            host=host,
            port=port,
        )
    database_name = config.get('database') or DEFAULT_MONGO['database']
    collection_name = config.get('collection') or DEFAULT_MONGO['collection']
    collection = client[database_name][collection_name]
    return client, collection


def fetch_step2_completed_uuids(
    collection,
    max_records: int = 0,
    device_id: Optional[str] = None,
) -> List[str]:
    """
    取得所有 Step2 (LEAF) 且 features_state == completed 的 AnalyzeUUID 字串列表。
    device_id 可以指定 None 代表無 filter。
    """
    # Debug: 先看看總共有多少資料
    total_count = collection.count_documents({})
    print(f"[DEBUG] 資料庫總記錄數: {total_count}")

    # Debug: 看看有多少有 runs 的記錄
    has_runs_count = collection.count_documents({"analyze_features.runs": {"$exists": True, "$ne": {}}})
    print(f"[DEBUG] 有 runs 的記錄數: {has_runs_count}")

    # Debug: 如果有指定 device_id，看看有多少符合的
    if device_id:
        device_count = collection.count_documents({"info_features.device_id": device_id})
        print(f"[DEBUG] device_id={device_id} 的記錄數: {device_count}")

    query: Dict[str, Any] = {
        "$expr": {
            "$gt": [
                {
                    "$size": {
                        "$filter": {
                            "input": {"$objectToArray": "$analyze_features.runs"},
                            "as": "run",
                            "cond": {
                                "$eq": [
                                    {
                                        "$getField": {
                                            "field": "features_state",
                                            "input": {
                                                "$getField": {
                                                    "field": "LEAF Features",
                                                    "input": "$$run.v.steps",
                                                }
                                            },
                                        }
                                    },
                                    "completed",
                                ]
                            },
                        }
                    }
                },
                0,
            ]
        }
    }


    if device_id:
        query["info_features.device_id"] = device_id

    cursor = collection.find(query, {"AnalyzeUUID": 1})
    if max_records and max_records > 0:
        cursor = cursor.limit(max_records)
    return [doc["AnalyzeUUID"] for doc in cursor if "AnalyzeUUID" in doc]
