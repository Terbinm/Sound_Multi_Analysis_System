from __future__ import annotations

"""
RF.mongo_helpers

�ˬd MongoDB �����w�]�Φp�� query �禡�A�ϥέp combine_cyclegan_rf CLI �γ~ export_uuid_list�C
"""

from typing import Any, Dict, List, Optional, Tuple
from pymongo import MongoClient

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
    """���ѥ���� default config�A�[�J analysis_service.config �w�]�ѼơC"""
    config = dict(DEFAULT_MONGO)
    try:
        from sub_system.analysis_service.config import MONGODB_CONFIG  # type: ignore

        for key, value in (MONGODB_CONFIG or {}).items():
            if value is not None:
                config[key] = value
    except Exception:
        pass
    if not config.get('collection'):
        config['collection'] = 'recordings'
    if not config.get('database'):
        config['database'] = 'web_db'
    return config


def merge_mongo_overrides(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """�i�H�q CLI args �ΦۦP���ѼƥΦ��ܩ����w Mongo config�C"""
    merged = dict(base)
    for key, value in overrides.items():
        if value is not None:
            merged[key] = value
    return merged


def connect_mongo(config: Dict[str, Any]) -> Tuple[MongoClient, Any]:
    """�p�G username/password ���w�A�۰ʥإ߼ƥ� authSource �s�u�A�^�ǨϥΪ̲��ޤ@�P collection�C"""
    host = config.get('host') or DEFAULT_MONGO['host']
    port = int(config.get('port') or DEFAULT_MONGO['port'])
    username = config.get('username') or None
    password = config.get('password') or None
    auth_source = config.get('auth_source') or config.get('authSource') or DEFAULT_MONGO['auth_source']

    client = MongoClient(
        host=host,
        port=port,
        username=username,
        password=password,
        authSource=auth_source if username else None,
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
    ��⥦ Step2 (LEAF) �� features_state == completed ���� AnalyzeUUID ��Ƨ�u�C
    device_id �i�H���w None �N���L filter�C
    """
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
