"""
共用函數模組
提供檔案雜湊計算、JSON序列化、分析容器建立等共用功能
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from bson.objectid import ObjectId


def build_analysis_container() -> Dict[str, Any]:
    """
    建立分析容器的標準結構

    Returns:
        包含分析狀態的字典
    """
    return {
        "active_analysis_id": None,
        "latest_analysis_id": None,
        "latest_summary_index": None,
        "total_runs": 0,
        "last_requested_at": None,
        "last_started_at": None,
        "last_completed_at": None,
        "runs": []
    }


def calculate_file_hash(file_path: Path) -> str:
    """
    計算檔案的 SHA-256 雜湊值

    Args:
        file_path: 檔案路徑

    Returns:
        SHA-256 雜湊值（十六進位字串）
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, 'rb') as handle:
        for block in iter(lambda: handle.read(4096), b""):
            sha256_hash.update(block)
    return sha256_hash.hexdigest()


def to_json_serializable(data: Any) -> Any:
    """
    將資料轉換為 JSON 可序列化格式
    遞迴處理字典、列表，並轉換特殊類型（datetime、ObjectId）

    Args:
        data: 要轉換的資料

    Returns:
        JSON 可序列化的資料
    """
    if isinstance(data, dict):
        return {k: to_json_serializable(v) for k, v in data.items()}
    if isinstance(data, list):
        return [to_json_serializable(item) for item in data]
    if isinstance(data, datetime):
        return data.isoformat()
    if isinstance(data, ObjectId):
        return str(data)
    return data
