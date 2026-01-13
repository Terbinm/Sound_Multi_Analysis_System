#!/usr/bin/env python3
r"""
combine_cyclegan_rf.py

用途：
- 從 MongoDB 讀取已存在的 Step2 (LEAF) 特徵（segments 模式）
- 對每筆 AnalyzeUUID 分別進行 CycleGAN 轉換前/後的 RF 推論
- 產出片段層級與記錄摘要兩份 CSV

使用：
python combine_cyclegan_rf.py --uuid_file uuid_list.txt --direction AB
python combine_cyclegan_rf.py --uuid 1111-2222 --uuid 3333-4444
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import warnings
import os

import numpy as np

from sub_system.train.py_cyclegan.inference import CycleGANConverter
from sub_system.train.RF.inference import RFClassifier
from sub_system.train.RF.mongo_helpers import (
    load_default_mongo_config,
    merge_mongo_overrides,
    connect_mongo,
)

# -----------------------------------------------------------------------------
# 常數
# -----------------------------------------------------------------------------
N_MELS = 40
MAX_RECORDS = 400  # 最多一次處理多少筆 AnalyzeUUID

# -----------------------------------------------------------------------------
# 嘗試加入專案 root（以便 import train_rf_model.DataLoader）
# -----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[3]  # 假設此檔放在 a_sub_system/train/RF
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CHECKPOINT_DIR = (Path(ROOT) / "sub_system/train/py_cyclegan/checkpoints").resolve()

# --- 預設檔案路徑設定（確保不用額外傳參數也能執行） ---
DEFAULT_CKPT = (CHECKPOINT_DIR / "cycle_A=0.5531.ckpt").resolve()
DEFAULT_RF = (Path(ROOT) / "sub_system/train/RF/models").resolve()
#DEFAULT_SCALER = (Path(ROOT) / "a_sub_system/train/RF/models/feature_scaler.pkl").resolve()
DEFAULT_UUID_FILE = (Path(ROOT) / "sub_system/train/RF/uuid_list.txt").resolve()
DEFAULT_MONGO_CONFIG = load_default_mongo_config()

# ���ձq train_rf_model import DataLoader�]�u���ϥΡ^
DataLoader = None
ModelConfig = None
try:
    from sub_system.train.RF.train_rf_model import DataLoader as TF_DataLoader, ModelConfig as TF_ModelConfig
    DataLoader = TF_DataLoader
    ModelConfig = TF_ModelConfig
    _USE_EXTERNAL_DATALOADER = True
    print('[DEBUG] Using DataLoader from train_rf_model.py')
except Exception:
    DataLoader = None
    ModelConfig = None
    _USE_EXTERNAL_DATALOADER = False
    print('[DEBUG] train_rf_model.DataLoader not importable -> fallback to internal fetch')

# -----------------------------------------------------------------------------
# Helpers: load models
# -----------------------------------------------------------------------------
def resolve_checkpoint_path(path_str: str) -> Path:

    if not path_str:
        return DEFAULT_CKPT

    candidate = Path(path_str).expanduser()
    tried = []

    if candidate.is_dir():
        ckpts = sorted(candidate.glob("*.ckpt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if ckpts:
            return ckpts[0].resolve()
        tried.append(candidate)
    elif candidate.exists():
        return candidate.resolve()
    else:
        tried.append(candidate)

    # 嘗試加上 checkpoints 目錄
    if not candidate.is_absolute():
        alt = (CHECKPOINT_DIR / candidate).resolve()
        if alt.exists():
            return alt
        tried.append(alt)

        # 若沒有副檔名，自動補 .ckpt
        if candidate.suffix != ".ckpt":
            alt_with_suffix = (CHECKPOINT_DIR / f"{candidate.name}.ckpt").resolve()
            if alt_with_suffix.exists():
                return alt_with_suffix
            tried.append(alt_with_suffix)

    raise FileNotFoundError(
        f"找不到指定的 CycleGAN checkpoint ({path_str})。嘗試過: {', '.join(str(p) for p in tried)}"
    )


def resolve_rf_model_dir(path_str: str) -> Path:
    """RF 模型參數可以是檔案或資料夾，統一回傳資料夾路徑。"""
    candidate = Path(path_str).expanduser()
    if candidate.is_file():
        return candidate.parent.resolve()
    return candidate.resolve()


# -----------------------------------------------------------------------------
# MongoDB helper (same as previous)
# -----------------------------------------------------------------------------
def build_mongo_config(args) -> Dict[str, Any]:
    overrides = {
        'host': args.mongo_host,
        'port': args.mongo_port,
        'username': args.mongo_username,
        'password': args.mongo_password,
        'database': args.mongo_db,
        'collection': args.mongo_collection,
    }
    return merge_mongo_overrides(DEFAULT_MONGO_CONFIG, overrides)

# -----------------------------------------------------------------------------
# Fetch features: 優先使用 external DataLoader 的 load_data（若可用）；
# 否則使用內建 fetch_leaf_features（會嚴格檢查 Step2 完成且為 segments）
# -----------------------------------------------------------------------------
def fetch_leaf_features_internal(collection, analyze_uuid: str) -> Tuple[np.ndarray, Dict]:
    """
    專門讀新版 MongoDB 結構：
    analyze_features.runs.<run_id>.steps["LEAF Features"]
    """

    record = collection.find_one({'AnalyzeUUID': analyze_uuid})
    if not record:
        raise ValueError(f"找不到 AnalyzeUUID={analyze_uuid}")

    runs = record.get("analyze_features", {}).get("runs")
    if not isinstance(runs, dict):
        raise ValueError("資料無 analyze_features.runs（新格式）")

    leaf_step = None

    # 逐一檢查每個 run
    for run_id, run_data in runs.items():
        steps = run_data.get("steps", {})
        if "LEAF Features" in steps:
            step_obj = steps["LEAF Features"]
            if step_obj.get("features_state") == "completed":
                leaf_step = step_obj
                break

    if leaf_step is None:
        raise ValueError("找不到完成的 Step2: LEAF Features (features_state='completed')")

    features_data = leaf_step.get("features_data")
    if not features_data:
        raise ValueError("LEAF Features: features_data 為空")

    # === 建立特徵矩陣 ===
    segment_list = []
    for idx, seg in enumerate(features_data):
        if seg is None:
            raise ValueError(f"第 {idx} 段為 None")

        if isinstance(seg, (list, tuple)):
            vec = np.array(seg, dtype=np.float32)
        else:
            raise ValueError(f"不支援的特徵格式：{type(seg)}")

        if vec.ndim != 1 or vec.shape[0] != N_MELS:
            raise ValueError(f"特徵維度錯誤 index={idx}: {vec.shape}, 預期 {N_MELS}")

        segment_list.append(vec)

    feats = np.vstack(segment_list)  # (T, 40)

    return feats, record


def fetch_leaf_features(collection, analyze_uuid: str, external_loader=None) -> Tuple[np.ndarray, Dict]:
    """
    wrapper: 若 external_loader（DataLoader）可用且支援單一 uuid 讀取 -> 使用它（若提供 load_data_by_uuid）
    否則使用 internal fetch。
    """
    # 如果外部 DataLoader 可用，且提供 fetch/single-record 功能，我們可以優先使用。
    if external_loader is not None:
        try:
            # external_loader 可能是 class DataLoader (需要先建立 instance)
            # 我們嘗試呼叫 .fetch_leaf_features 或 .load_data_by_uuid 這類 API（若存在）
            loader = external_loader(ModelConfig.MONGODB_CONFIG) if ModelConfig is not None else external_loader()
            if hasattr(loader, 'fetch_leaf_features'):
                feats, record = loader.fetch_leaf_features(analyze_uuid)
                return feats, record
            # 退回到 internal
        except Exception:
            # 忽略並退回 internal
            pass

    # internal fetch
    return fetch_leaf_features_internal(collection, analyze_uuid)


LABEL_TO_INT = {'normal': 0, 'abnormal': 1}


def _pad_predictions(predictions: List[Dict[str, Any]], total_segments: int) -> List[Dict[str, Any]]:
    padded = list(predictions or [])
    unknown = {'prediction': 'unknown', 'prediction_index': None, 'confidence': 0.0}
    if len(padded) < total_segments:
        padded.extend([unknown.copy() for _ in range(total_segments - len(padded))])
    return padded[:total_segments]


def _prediction_to_int(prediction: Optional[Dict[str, Any]]) -> int:
    if not prediction:
        return -1
    idx = prediction.get('prediction_index')
    if idx is not None and idx in (0, 1):
        return int(idx)
    label = prediction.get('prediction')
    if label in LABEL_TO_INT:
        return LABEL_TO_INT[label]
    return -1


def _majority_vote(predictions: List[Dict[str, Any]]) -> int:
    values = [_prediction_to_int(p) for p in predictions]
    valid = [v for v in values if v in (0, 1)]
    if not valid:
        return -1
    return int(np.round(float(np.mean(valid))))

# -----------------------------------------------------------------------------
# process_record - 主要推論流程（per AnalyzeUUID）
# -----------------------------------------------------------------------------
def process_record(
        analyze_uuid: str,
        converter: CycleGANConverter,
        classifier: RFClassifier,
        collection,
        aggregation: Optional[str] = None,
        external_loader=None
):
    feats, record = fetch_leaf_features(collection, analyze_uuid, external_loader=external_loader)
    T = feats.shape[0]

    converted_np = converter.convert(feats)
    converted = classifier.predict(converted_np, aggregation=aggregation)
    raw = classifier.predict(feats, aggregation=aggregation)

    raw_predictions = _pad_predictions(raw.get('predictions') or [], T)
    converted_predictions = _pad_predictions(converted.get('predictions') or [], T)

    print(f"[DEBUG] 原始 mean/std = {feats.mean():.4f} / {feats.std():.4f}")
    print(f"[DEBUG] CycleGAN mean/std = {converted_np.mean():.4f} / {converted_np.std():.4f}")

    source_name = record.get('files', {}).get('raw', {}).get('filename', analyze_uuid)

    rows = []
    for idx in range(T):
        rows.append({
            "AnalyzeUUID": analyze_uuid,
            "來源檔名": source_name,
            "片段索引": idx,
            "原始預測": _prediction_to_int(raw_predictions[idx]),
            "轉換後預測": _prediction_to_int(converted_predictions[idx]),
        })

    summary = {
        "AnalyzeUUID": analyze_uuid,
        "來源檔名": source_name,
        "片段數": int(T),
        "原始投票": _majority_vote(raw_predictions),
        "轉換後投票": _majority_vote(converted_predictions),
    }

    return rows, summary

# -----------------------------------------------------------------------------
# CLI + main
# -----------------------------------------------------------------------------
def load_uuid_list_from_args(args) -> List[str]:
    uuid_set = set()
    if args.uuid:
        for u in args.uuid:
            text = u.strip()
            if text:
                uuid_set.add(text)

    # 若未指定 uuid_file 參數就使用預設清單檔，確保可以自動批次處理
    uuid_file = Path(args.uuid_file) if args.uuid_file else DEFAULT_UUID_FILE
    if not uuid_file.exists():
        raise FileNotFoundError(f"找不到 UUID 清單檔：{uuid_file}")

    with uuid_file.open('r', encoding='utf-8') as f:
        for line in f:
            text = line.strip()
            if text:
                uuid_set.add(text)
    return sorted(uuid_set)

def main():
    parser = argparse.ArgumentParser(description="CycleGAN + RF 整合 (使用 MongoDB Step2 特徵 - segments)")
    parser.add_argument('--uuid', action='append', help='指定 AnalyzeUUID (可多個)')
    parser.add_argument('--uuid_file', default=str(DEFAULT_UUID_FILE), help='列有 AnalyzeUUID 的文字檔 (一行一筆)')
    parser.add_argument('--direction', choices=['AB', 'BA'], default='AB')
    parser.add_argument('--cyclegan', default=str(DEFAULT_CKPT), help='CycleGAN checkpoint 路徑/檔名/資料夾')
    parser.add_argument('--normalization', default=None, help='Normalization 參數檔 (預設為 checkpoint 目錄下的 normalization_params.json)')
    parser.add_argument('--skip_normalization', action='store_true', help='不要在轉換後套回 normalization 參數')
    parser.add_argument('--rf', default=str(DEFAULT_RF), help='RF 模型目錄或 pkl 檔')
    parser.add_argument('--scaler', default=None, help='可選的 scaler pkl')
    parser.add_argument('--rf_aggregation', default=None, help='覆寫 RF metadata aggregator (segments/mean/...)')

    parser.add_argument('--out_csv', default='cpc_normal.csv')
    parser.add_argument('--out_summary', default='cpc_normal_summary.csv')

    # parser.add_argument('--out_csv', default='cpc_abnormal.csv')
    # parser.add_argument('--out_summary', default='cpc_abnormal_summary.csv')


    parser.add_argument('--mongo_host', default=DEFAULT_MONGO_CONFIG.get('host'))
    parser.add_argument('--mongo_port', type=int, default=DEFAULT_MONGO_CONFIG.get('port'))
    parser.add_argument('--mongo_username', default=DEFAULT_MONGO_CONFIG.get('username'))
    parser.add_argument('--mongo_password', default=DEFAULT_MONGO_CONFIG.get('password'))
    parser.add_argument('--mongo_db', default=DEFAULT_MONGO_CONFIG.get('database'))
    parser.add_argument('--mongo_collection', default=DEFAULT_MONGO_CONFIG.get('collection'))


    args = parser.parse_args()

    uuid_list = load_uuid_list_from_args(args)
    if not uuid_list:
        raise SystemExit("請至少提供一個 AnalyzeUUID (--uuid 或 --uuid_file)")

    if len(uuid_list) > MAX_RECORDS:
        warnings.warn(f"收到 {len(uuid_list)} 筆 UUID，僅處理前 {MAX_RECORDS} 筆")
        uuid_list = uuid_list[:MAX_RECORDS]

    print("���J�ҫ�...")
    ckpt_path = resolve_checkpoint_path(args.cyclegan)
    rf_model_dir = resolve_rf_model_dir(args.rf)
    converter = CycleGANConverter(
        checkpoint_path=str(ckpt_path),
        direction=args.direction,
        normalization_path=args.normalization,
        apply_normalization=not args.skip_normalization,
    )
    classifier = RFClassifier(model_dir=rf_model_dir, scaler_path=args.scaler)

    mongo_cfg = build_mongo_config(args)
    client = None
    try:
        client, collection = connect_mongo(mongo_cfg)
        print("MongoDB 連線成功")
        segment_rows = []
        summary_rows = []

        # 如果我們能用外部 DataLoader，傳入以便 fetch 使用（會優先嘗試）
        external_loader = TF_DataLoader if _USE_EXTERNAL_DATALOADER else None

        for uid in uuid_list:
            print(f"處理 {uid} ...")
            try:
                rows, summary = process_record(
                    uid,
                    converter,
                    classifier,
                    collection,
                    aggregation=args.rf_aggregation,
                    external_loader=external_loader,
                )
                segment_rows.extend(rows)
                summary_rows.append(summary)
                print(f" -> 完成: {summary['片段數']} 片段， 原始投票={summary['原始投票']} 轉換後投票={summary['轉換後投票']}")
            except Exception as e:
                warnings.warn(f"處理 {uid} 失敗: {e}")

    finally:
        if client:
            client.close()

    if not segment_rows:
        raise SystemExit("沒有任何成功紀錄，請檢查 AnalyzeUUID 與 Step2/Step6 特徵狀態。")

    # write CSVs
    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["AnalyzeUUID", "來源檔名", "片段索引", "原始預測", "轉換後預測"])
        writer.writeheader()
        writer.writerows(segment_rows)

    with open(args.out_summary, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["AnalyzeUUID", "來源檔名", "片段數", "原始投票", "轉換後投票"])
        writer.writeheader()
        writer.writerows(summary_rows)

    print("完成！")
    print("片段 CSV:", Path(args.out_csv).resolve())
    print("摘要 CSV:", Path(args.out_summary).resolve())


if __name__ == "__main__":
    main()
