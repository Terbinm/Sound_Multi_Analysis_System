#!/usr/bin/env python3
r"""
combine_cyclegan_rf.py

用途：
- 從 MongoDB 直接載入指定裝置 (device_id) 已完成 Step 2 (LEAF) 的特徵
- 逐筆套用 CycleGAN 轉換，再交由 RF 模型推論，用來比較轉換前後的分類結果
- 將片段層級結果與整體摘要輸出成 CSV

使用範例：
python combine_cyclegan_rf.py --device_id cpc006 --direction AB
python combine_cyclegan_rf.py --device_id Mimii_NORMAL --direction BA
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import warnings

import numpy as np

# Ensure the repo root is available before importing project modules
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sub_system.train.py_cyclegan.inference import CycleGANConverter
from sub_system.train.RF.inference import RFClassifier
from sub_system.train.RF.mongo_helpers import (
    load_default_mongo_config,
    merge_mongo_overrides,
    connect_mongo,
    build_leaf_completed_expr,
)

# -----------------------------------------------------------------------------
# 常數
# -----------------------------------------------------------------------------
N_MELS = 40
MAX_RECORDS = 0  # 最多一次處理多少筆 AnalyzeUUID
DEFAULT_DEVICE_ID = "cpc006"
CHECKPOINT_DIR = (Path(ROOT) / "sub_system/train/py_cyclegan/checkpoints").resolve()

# --- 路徑預設值，可透過參數覆寫 ---
DEFAULT_CKPT = (CHECKPOINT_DIR / "cycle_A=0.4930.ckpt").resolve()
DEFAULT_RF = (Path(ROOT) / "sub_system/train/RF/models").resolve()
#DEFAULT_SCALER = (Path(ROOT) / "a_sub_system/train/RF/models/feature_scaler.pkl").resolve()
DEFAULT_MONGO_CONFIG = load_default_mongo_config()

# 嘗試動態匯入 train_rf_model.DataLoader，方便沿用同一份資料讀取邏輯
# 為了避免未定義，先給預設 None
TF_DataLoader = None  # type: ignore
DataLoader = None
ModelConfig = None
try:
    from sub_system.train.RF.train_rf_model import (
        DataLoader as TF_DataLoader,
        ModelConfig as TF_ModelConfig,
    )

    DataLoader = TF_DataLoader
    ModelConfig = TF_ModelConfig
    _USE_EXTERNAL_DATALOADER = True
    print("[DEBUG] Using DataLoader from train_rf_model.py")
except Exception:
    DataLoader = None
    ModelConfig = None
    _USE_EXTERNAL_DATALOADER = False
    print("[DEBUG] train_rf_model.DataLoader not importable -> fallback to internal fetch")


# -----------------------------------------------------------------------------
# 輔助函式：解析模型路徑
# -----------------------------------------------------------------------------
def resolve_checkpoint_path(path_str: str) -> Path:
    if not path_str:
        return DEFAULT_CKPT

    candidate = Path(path_str).expanduser()
    tried: List[Path] = []

    if candidate.is_dir():
        ckpts = sorted(candidate.glob("*.ckpt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if ckpts:
            return ckpts[0].resolve()
        tried.append(candidate)
    elif candidate.exists():
        return candidate.resolve()
    else:
        tried.append(candidate)

    # 允許只輸入檔名，預設去 checkpoints 目錄找
    if not candidate.is_absolute():
        alt = (CHECKPOINT_DIR / candidate).resolve()
        if alt.exists():
            return alt
        tried.append(alt)

        # 補齊 .ckpt 副檔名
        if candidate.suffix != ".ckpt":
            alt_with_suffix = (CHECKPOINT_DIR / f"{candidate.name}.ckpt").resolve()
            if alt_with_suffix.exists():
                return alt_with_suffix
            tried.append(alt_with_suffix)

    raise FileNotFoundError(
        f"找不到指定的 CycleGAN checkpoint ({path_str})。已搜尋：{', '.join(str(p) for p in tried)}"
    )


def resolve_rf_model_dir(path_str: str) -> Path:
    """RF 模型參數可能是檔案也可能是資料夾，這裡統一回傳資料夾路徑。"""
    candidate = Path(path_str).expanduser()
    if candidate.is_file():
        return candidate.parent.resolve()
    return candidate.resolve()


# -----------------------------------------------------------------------------
# MongoDB Helper
# -----------------------------------------------------------------------------
def build_mongo_config(args) -> Dict[str, Any]:
    overrides = {
        "host": args.mongo_host,
        "port": args.mongo_port,
        "username": args.mongo_username,
        "password": args.mongo_password,
        "database": args.mongo_db,
        "collection": args.mongo_collection,
    }
    return merge_mongo_overrides(DEFAULT_MONGO_CONFIG, overrides)


def fetch_records_by_device(
    collection,
    device_id: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """依 device_id 取得最新 Analyze 記錄，只保留 Step2 (LEAF) 已完成者。"""
    query = {
        "info_features.device_id": device_id,
        "analyze_features.runs": {"$exists": True},
        "$expr": build_leaf_completed_expr(),
    }
    projection = {
        "_id": 0,
        "AnalyzeUUID": 1,
        "info_features": 1,
        "files": 1,
        "analyze_features": 1,
    }
    cursor = collection.find(query, projection).sort("created_at", -1)
    if limit:
        cursor = cursor.limit(limit)
    return list(cursor)


# -----------------------------------------------------------------------------
# 讀取 LEAF 特徵
# -----------------------------------------------------------------------------
def fetch_leaf_features_internal(
    collection,
    analyze_uuid: str,
    record: Optional[Dict] = None,
) -> Tuple[np.ndarray, Dict]:
    """
    使用 analyze_features.runs.<run_id>.steps["LEAF Features"] 的新結構。
    record 可預先提供，避免重複查詢。
    """

    if record is None:
        record = collection.find_one({"AnalyzeUUID": analyze_uuid})
        if not record:
            raise ValueError(f"找不到 AnalyzeUUID={analyze_uuid}")

    runs = record.get("analyze_features", {}).get("runs")
    if not isinstance(runs, dict):
        raise ValueError("資料不包含 analyze_features.runs（新結構）")

    leaf_step = None
    for _, run_data in runs.items():
        steps = run_data.get("steps", {})
        step_obj = steps.get("LEAF Features")
        if step_obj and step_obj.get("features_state") == "completed":
            leaf_step = step_obj
            break

    if leaf_step is None:
        raise ValueError("找不到完成的 Step2: LEAF Features (features_state='completed')")

    features_data = leaf_step.get("features_data")
    if not features_data:
        raise ValueError("LEAF Features: features_data 為空")

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


def fetch_leaf_features(
    collection,
    analyze_uuid: str,
    external_loader=None,
    record: Optional[Dict] = None,
) -> Tuple[np.ndarray, Dict]:
    """
    若可使用 training DataLoader，優先交給外部 loader 讀取；否則 fallback 到內建流程。
    """
    if external_loader is not None:
        try:
            loader = (
                external_loader(ModelConfig.MONGODB_CONFIG)
                if ModelConfig is not None
                else external_loader()
            )
            if hasattr(loader, "fetch_leaf_features"):
                feats, record_data = loader.fetch_leaf_features(analyze_uuid)
                return feats, record_data
        except Exception:
            pass

    return fetch_leaf_features_internal(collection, analyze_uuid, record=record)


LABEL_TO_INT = {"normal": 0, "abnormal": 1}


def _pad_predictions(predictions: List[Dict[str, Any]], total_segments: int) -> List[Dict[str, Any]]:
    padded = list(predictions or [])
    unknown = {"prediction": "unknown", "prediction_index": None, "confidence": 0.0}
    if len(padded) < total_segments:
        padded.extend([unknown.copy() for _ in range(total_segments - len(padded))])
    return padded[:total_segments]


def _prediction_to_int(pred: Optional[Dict[str, Any]]) -> int:
    if not pred:
        return -1
    idx = pred.get("prediction_index")
    if idx in (0, 1):
        return int(idx)
    label = pred.get("prediction")
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
# 主要流程：處理單一 AnalyzeUUID
# -----------------------------------------------------------------------------
def process_record(
    analyze_uuid: str,
    converter: CycleGANConverter,
    classifier: RFClassifier,
    collection,
    aggregation: Optional[str] = None,
    external_loader=None,
    record: Optional[Dict] = None,
):
    feats, record_data = fetch_leaf_features(
        collection,
        analyze_uuid,
        external_loader=external_loader,
        record=record,
    )
    record = record_data
    total_segments = feats.shape[0]

    converted_np = converter.convert(feats)
    converted = classifier.predict(converted_np, aggregation=aggregation)
    raw = classifier.predict(feats, aggregation=aggregation)

    raw_predictions = _pad_predictions(raw.get("predictions") or [], total_segments)
    converted_predictions = _pad_predictions(converted.get("predictions") or [], total_segments)

    print(f"[DEBUG] 原始特徵 mean/std = {feats.mean():.4f} / {feats.std():.4f}")
    print(f"[DEBUG] CycleGAN 特徵 mean/std = {converted_np.mean():.4f} / {converted_np.std():.4f}")

    source_name = record.get("files", {}).get("raw", {}).get("filename", analyze_uuid)

    rows = []
    for idx in range(total_segments):
        rows.append(
            {
                "AnalyzeUUID": analyze_uuid,
                "來源檔名": source_name,
                "片段索引": idx,
                "原始預測": _prediction_to_int(raw_predictions[idx]),
                "轉換後預測": _prediction_to_int(converted_predictions[idx]),
            }
        )

    summary = {
        "AnalyzeUUID": analyze_uuid,
        "來源檔名": source_name,
        "片段數": int(total_segments),
        "原始投票": _majority_vote(raw_predictions),
        "轉換後投票": _majority_vote(converted_predictions),
    }

    return rows, summary


# -----------------------------------------------------------------------------
# CLI 與主程式
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="CycleGAN + RF 整合 (使用 MongoDB Step2 特徵 - segments)")
    parser.add_argument("--direction", choices=["AB", "BA"], default="AB")
    parser.add_argument("--cyclegan", default=str(DEFAULT_CKPT), help="CycleGAN checkpoint 路徑/檔名/資料夾")
    parser.add_argument(
        "--normalization",
        default=None,
        help="Normalization 參數檔 (預設為 checkpoint 目錄下的 normalization_params.json)",
    )
    parser.add_argument("--skip_normalization", action="store_true", help="不要在轉換後套回 normalization 參數")
    parser.add_argument("--rf", default=str(DEFAULT_RF), help="RF 模型目錄或 pkl 檔")
    parser.add_argument("--scaler", default=None, help="可選的 scaler pkl")
    parser.add_argument("--rf_aggregation", default=None, help="覆寫 RF metadata aggregator (segments/mean/...)")
    parser.add_argument("--device_id", default=DEFAULT_DEVICE_ID, help="只處理指定 device 的資料 (預設 cpc006)")

    parser.add_argument("--out_csv", default=r"D:\D_PycharmProjects\Sound_Multi_Analysis_System\sub_system\train\RF\outputs\cpc_normal.csv")
    parser.add_argument("--out_summary", default=r"D:\D_PycharmProjects\Sound_Multi_Analysis_System\sub_system\train\RF\outputs\cpc_normal_summary.csv")

    parser.add_argument("--mongo_host", default=DEFAULT_MONGO_CONFIG.get("host"))
    parser.add_argument("--mongo_port", type=int, default=DEFAULT_MONGO_CONFIG.get("port"))
    parser.add_argument("--mongo_username", default=DEFAULT_MONGO_CONFIG.get("username"))
    parser.add_argument("--mongo_password", default=DEFAULT_MONGO_CONFIG.get("password"))
    parser.add_argument("--mongo_db", default=DEFAULT_MONGO_CONFIG.get("database"))
    parser.add_argument("--mongo_collection", default=DEFAULT_MONGO_CONFIG.get("collection"))

    args = parser.parse_args()
    record_limit = MAX_RECORDS

    print("準備載入模型...")
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
        records = fetch_records_by_device(collection, args.device_id, record_limit)
        if not records:
            raise SystemExit(f"查無符合 device_id={args.device_id} 的 Analyze 記錄")
        print(f"取得 {len(records)} 筆 device_id={args.device_id} 的資料，開始處理...")
        segment_rows: List[Dict[str, Any]] = []
        summary_rows: List[Dict[str, Any]] = []

        external_loader = TF_DataLoader if _USE_EXTERNAL_DATALOADER else None

        for doc in records:
            uid = doc.get("AnalyzeUUID")
            if not uid:
                warnings.warn("略過一筆缺少 AnalyzeUUID 的資料")
                continue
            print(f"處理 {uid} ...")
            try:
                rows, summary = process_record(
                    uid,
                    converter,
                    classifier,
                    collection,
                    aggregation=args.rf_aggregation,
                    external_loader=external_loader,
                    record=doc,
                )
                segment_rows.extend(rows)
                summary_rows.append(summary)
                print(
                    f" -> 完成: {summary['片段數']} 片段，原始投票={summary['原始投票']} "
                    f"轉換後投票={summary['轉換後投票']}"
                )
            except Exception as exc:
                warnings.warn(f"處理 {uid} 失敗: {exc}")

    finally:
        if client:
            client.close()

    if not segment_rows:
        raise SystemExit("沒有任何成功記錄，請檢查 device_id 與 Step2/Step6 特徵狀態。")

    out_csv_path = Path(args.out_csv)
    out_summary_path = Path(args.out_summary)
    out_csv_path.parent.mkdir(parents=True, exist_ok=True)
    out_summary_path.parent.mkdir(parents=True, exist_ok=True)

    with out_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["AnalyzeUUID", "來源檔名", "片段索引", "原始預測", "轉換後預測"],
        )
        writer.writeheader()
        writer.writerows(segment_rows)

    with out_summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["AnalyzeUUID", "來源檔名", "片段數", "原始投票", "轉換後投票"],
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    print("完成！")
    print("片段 CSV:", out_csv_path.resolve())
    print("摘要 CSV:", out_summary_path.resolve())


if __name__ == "__main__":
    main()
