"""
批次 CycleGAN 域轉換腳本
=======================

自動針對 MongoDB 中符合 Domain B 查詢條件的所有分析任務，將 Step 2
(Mafaulda) 特徵批次轉換為 Step 6 (CPC) 並寫回資料庫。
"""

from __future__ import annotations

import argparse
import copy
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import torch
from pymongo import MongoClient
from pymongo.collection import Collection

# 確保可以匯入專案模組
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models import CycleGANModule
from utils import (  # noqa: E402
    get_data_config,
    get_inference_config,
    get_mongodb_config,
    setup_logger,
)
from utils.mongo_helpers import (  # noqa: E402
    build_step_update_path,
    find_step_across_runs,
    find_step_in_run,
    get_run_by_id,
)

# 預設設定，可透過環境變數覆寫
DEFAULT_CHECKPOINT = Path(
    os.getenv("BATCH_CONVERSION_CHECKPOINT", "a_sub_system/train/py_cyclegan/checkpoints/last-v3.ckpt")
)
DEFAULT_INPUT_STEP = int(os.getenv("BATCH_CONVERSION_INPUT_STEP", "2"))
DEFAULT_OUTPUT_STEP = int(os.getenv("BATCH_CONVERSION_OUTPUT_STEP", "6"))
DEFAULT_DEVICE = os.getenv("BATCH_CONVERSION_DEVICE", get_inference_config()["device"])

logger = setup_logger("batch_conversion")


def load_model(checkpoint: Path, device_name: str) -> Tuple[CycleGANModule, torch.device, Dict[str, np.ndarray]]:
    """載入 CycleGAN 檢查點並返回模型、裝置與正規化參數。"""
    if device_name == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA 不可用，自動改用 CPU")
        device_name = "cpu"

    device = torch.device(device_name)
    logger.info("載入模型檢查點 %s 至裝置 %s", checkpoint, device)

    model = CycleGANModule.load_from_checkpoint(str(checkpoint))
    model.to(device)
    model.eval()

    # 載入正規化參數
    import json
    normalization_path = checkpoint.parent / 'normalization_params.json'
    normalization_params = {}

    if normalization_path.exists():
        logger.info("載入正規化參數 %s", normalization_path)
        with open(normalization_path, 'r', encoding='utf-8') as f:
            params = json.load(f)

        # 轉換為 numpy array
        for key, value in params.items():
            normalization_params[key] = np.array(value, dtype=np.float32)

        # 注意：使用統一歸一化時，mean_a = mean_b, std_a = std_b
        # 但為了向後兼容性，我們仍然保留所有參數
        logger.info(
            "正規化參數已載入 - Domain A: mean=%.4f, std=%.4f | Domain B: mean=%.4f, std=%.4f",
            normalization_params['mean_a'].mean(),
            normalization_params['std_a'].mean(),
            normalization_params['mean_b'].mean(),
            normalization_params['std_b'].mean(),
        )
    else:
        logger.warning("⚠ 未找到正規化參數檔案 %s，將不進行正規化（可能導致轉換結果不佳）", normalization_path)

    return model, device, normalization_params


def get_collection() -> Tuple[MongoClient, Collection]:
    """�إ� MongoDB �s�u�è��o�ؼж��X�C"""
    cfg = get_mongodb_config()
    client = MongoClient(cfg["uri"])
    return client, client[cfg["database"]][cfg["collection"]]


def build_query(base_query: Dict[str, Any], input_step: int) -> Dict[str, Any]:
    """組合 MongoDB 查詢條件（Step 條件改為程式層過濾）"""
    if base_query:
        return copy.deepcopy(base_query)
    return {}

def iter_documents(
    collection: Collection,
    query: Dict[str, Any],
    limit: Optional[int],
) -> Iterable[Dict[str, Any]]:
    """
    遍歷符合條件的分析任務。

    Args:
        collection: MongoDB 集合。
        query: 完整查詢條件。
        limit: 最大處理數量（None 表示不限制）。
    """
    cursor = collection.find(
        query,
        {
            "_id": 0,
            "AnalyzeUUID": 1,
            "analyze_features": 1,
        },
    )

    if limit:
        cursor = cursor.limit(limit)

    return cursor


def extract_step(data: Dict[str, Any], step: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """從 analyze_features.runs 中取得指定步驟資料。"""
    return find_step_across_runs(
        data,
        step_order=step,
        require_completed=True,
    )

def parse_features(step_data: Dict[str, Any]) -> List[np.ndarray]:
    """將步驟中的 features_data 轉換為 numpy 陣列列表並驗證形狀。"""
    features_raw = step_data.get("features_data")
    if not features_raw:
        raise ValueError("features_data 為空")

    features_list: List[np.ndarray] = []
    for idx, sample in enumerate(features_raw):
        array = np.asarray(sample, dtype=np.float32)
        if array.ndim == 1 and array.shape[0] == 40:
            array = array.reshape(1, 40)
        if array.ndim != 2 or array.shape[1] != 40:
            raise ValueError(f"第 {idx} 筆樣本形狀為 {array.shape}，應為 (seq_len, 40)")
        features_list.append(array)

    return features_list


def convert_features(
    model: CycleGANModule,
    device: torch.device,
    features_list: List[np.ndarray],
    normalization_params: Dict[str, np.ndarray],
) -> List[List[List[float]]]:
    """執行 Domain B → Domain A 轉換。"""
    converted: List[List[List[float]]] = []

    # 取得正規化參數（B→A 方向：輸入用 B，輸出用 A）
    has_norm = bool(normalization_params)
    if has_norm:
        mean_input = normalization_params['mean_b']
        std_input = normalization_params['std_b']
        mean_output = normalization_params['mean_a']
        std_output = normalization_params['std_a']

    with torch.no_grad():
        for sample in features_list:
            # 正規化輸入
            if has_norm:
                sample_normalized = (sample - mean_input) / std_input
            else:
                sample_normalized = sample

            tensor = torch.tensor(sample_normalized, dtype=torch.float32, device=device).unsqueeze(0)
            translated = model.convert_B_to_A(tensor)
            translated_np = translated.squeeze(0).cpu().numpy()

            # 反正規化輸出
            if has_norm:
                translated_np = translated_np * std_output + mean_output

            converted.append(translated_np.tolist())

    return converted


def upsert_step(
    collection: Collection,
    analyze_uuid: str,
    run_id: str,
    step_id: int,
    step_label: str,
    converted: List[List[List[float]]],
    metadata: Dict[str, Any],
) -> None:
    """將轉換結果寫入指定 run 的步驟。"""
    now = datetime.utcnow()
    step_doc = {
        "display_order": step_id,
        "step_name": step_label,
        "features_state": "completed",
        "features_data": converted,
        "processor_metadata": metadata,
        "error_message": None,
        "started_at": now,
        "completed_at": now,
    }
    update_path = build_step_update_path(run_id, step_label)
    result = collection.update_one(
        {"AnalyzeUUID": analyze_uuid},
        {"": {update_path: step_doc}},
    )
    if not result.matched_count:
        raise RuntimeError(f"無法更新 AnalyzeUUID={analyze_uuid}")

def main() -> None:
    data_cfg = get_data_config()
    domain_b_cfg = copy.deepcopy(data_cfg["domain_b"])

    parser = argparse.ArgumentParser(description="批次將 Domain B 特徵轉換為 Domain A")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT, help="CycleGAN 檢查點路徑")
    parser.add_argument("--device", type=str, default=DEFAULT_DEVICE, choices=["cpu", "cuda"], help="推論裝置")
    parser.add_argument("--input-step", type=int, default=DEFAULT_INPUT_STEP, help="來源步驟編號（預設 2）")
    parser.add_argument("--output-step", type=int, default=DEFAULT_OUTPUT_STEP, help="輸出步驟編號（預設 6）")
    parser.add_argument("--limit", type=int, default=domain_b_cfg.get("max_samples"), help="最大處理筆數（預設使用 config 中的 max_samples）")
    parser.add_argument("--device-id", type=str, help="覆寫 domain_b 設備 ID 查詢")
    parser.add_argument("--overwrite", action="store_true", help="若目標步驟已存在則覆寫")
    parser.add_argument("--dry-run", action="store_true", help="僅顯示將處理的任務，不寫回資料庫")
    args = parser.parse_args()

    if args.device_id:
        domain_b_cfg["mongo_query"]["info_features.device_id"] = args.device_id

    mongo_query = build_query(domain_b_cfg['mongo_query'], args.input_step)
    client, collection = get_collection()
    model, device, normalization_params = load_model(args.checkpoint, args.device)

    total = converted = skipped = failures = 0
    last_uuid: Optional[str] = None

    try:
        for doc in iter_documents(collection, mongo_query, args.limit):
            total += 1
            analyze_uuid = doc.get('AnalyzeUUID')
            last_uuid = analyze_uuid

            input_step_data, run_id = extract_step(doc, args.input_step)
            if not input_step_data or not run_id:
                logger.warning(
                    '記錄 %s 缺少步驟 %s，略過',
                    analyze_uuid,
                    args.input_step,
                )
                skipped += 1
                continue

            run_doc = get_run_by_id(doc, run_id)
            if not run_doc:
                logger.warning('記錄 %s 缺少 runs 結構，略過', analyze_uuid)
                skipped += 1
                continue

            step_label = f"CycleGAN Step {args.output_step}"
            existing_output = find_step_in_run(
                run_doc,
                step_name=step_label,
                step_order=args.output_step,
                require_completed=False,
            )
            if existing_output and not args.overwrite:
                logger.info(
                    '記錄 %s 已存在步驟 %s，使用 --overwrite 才會覆寫',
                    analyze_uuid,
                    args.output_step,
                )
                skipped += 1
                continue

            try:
                features_list = parse_features(input_step_data)
                converted_features = convert_features(
                    model, device, features_list, normalization_params
                )
            except Exception as exc:
                logger.exception('記錄 %s 轉換失敗: %s', analyze_uuid, exc)
                failures += 1
                continue

            metadata = {
                'source_step': args.input_step,
                'direction': 'B->A',
                'checkpoint': str(args.checkpoint),
                'device': str(device),
                'converted_at': datetime.utcnow(),
                'num_samples': len(converted_features),
                'analysis_run_id': run_id,
            }

            if args.dry_run:
                logger.info(
                    '[DRY RUN] 記錄 %s 將寫入步驟 %s，共 %s 筆樣本',
                    analyze_uuid,
                    args.output_step,
                    len(converted_features),
                )
                converted += 1
                continue

            upsert_step(
                collection,
                analyze_uuid,
                run_id,
                args.output_step,
                step_label,
                converted_features,
                metadata,
            )
            logger.info(
                '記錄 %s 已寫入步驟 %s，共 %s 筆樣本',
                analyze_uuid,
                args.output_step,
                len(converted_features),
            )
            converted += 1
    finally:
        client.close()

    logger.info(
        "批次轉換完成：處理 %s 筆，成功 %s，跳過 %s，失敗 %s。最後處理 UUID：%s",
        total or 0,
        converted or 0,
        skipped or 0,
        failures or 0,
        last_uuid or "N/A",
    )


if __name__ == "__main__":
    main()
