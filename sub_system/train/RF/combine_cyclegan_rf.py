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
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus
import warnings
import os

import numpy as np
import torch
import pickle
from pymongo import MongoClient
from sklearn.preprocessing import StandardScaler

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
DEFAULT_CKPT = (CHECKPOINT_DIR / "last.ckpt").resolve()
DEFAULT_RF = (Path(ROOT) / "sub_system/train/RF/models/mimii_fan_rf_classifier.pkl").resolve()
#DEFAULT_SCALER = (Path(ROOT) / "a_sub_system/train/RF/models/feature_scaler.pkl").resolve()
DEFAULT_UUID_FILE = (Path(ROOT) / "sub_system/train/RF/uuid_list.txt").resolve()

# 嘗試從 train_rf_model import DataLoader（優先使用）
DataLoader = None
ModelConfig = None
try:
    from sub_system.train.RF.train_rf_model import DataLoader as TF_DataLoader, ModelConfig as TF_ModelConfig
    DataLoader = TF_DataLoader
    ModelConfig = TF_ModelConfig
    _USE_EXTERNAL_DATALOADER = True
    print("[DEBUG] Using DataLoader from train_rf_model.py")
except Exception:
    DataLoader = None
    ModelConfig = None
    _USE_EXTERNAL_DATALOADER = False
    print("[DEBUG] train_rf_model.DataLoader not importable -> fallback to internal fetch")

# 嘗試 import CycleGANModule（project path）
try:
    from sub_system.train.py_cyclegan.models.cyclegan_module import CycleGANModule
except Exception:
    CycleGANModule = None

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

def load_cyclegan(ckpt_path: Path):
    ckpt = ckpt_path
    if not ckpt.exists():
        raise FileNotFoundError(f"找不到 CycleGAN checkpoint: {ckpt}")
    if CycleGANModule is None:
        raise RuntimeError("CycleGANModule not importable. 確認專案路徑或改用可 import 的路徑。")
    model = CycleGANModule.load_from_checkpoint(str(ckpt), map_location="cpu")
    model.eval()
    return model

def load_rf_and_scaler(rf_path: str, scaler_path: Optional[str] = None):
    rf_file = Path(rf_path)
    print(f"models:{rf_file}")
    if not rf_file.exists():
        raise FileNotFoundError(f"找不到 RF 模型: {rf_file}")
    with open(rf_file, "rb") as f:
        rf = pickle.load(f)
    scaler = None
    if scaler_path and Path(scaler_path).exists():
        with open(scaler_path, "rb") as f:
            scaler = pickle.load(f)
    return rf, scaler

# -----------------------------------------------------------------------------
# MongoDB helper (same as previous)
# -----------------------------------------------------------------------------
def build_mongo_config(args, default_cfg: Dict) -> Dict:
    cfg = default_cfg.copy()
    if args.mongo_host:
        cfg['host'] = args.mongo_host
    if args.mongo_port:
        cfg['port'] = args.mongo_port
    if args.mongo_username is not None:
        cfg['username'] = args.mongo_username
    if args.mongo_password is not None:
        cfg['password'] = args.mongo_password
    if args.mongo_db:
        cfg['database'] = args.mongo_db
    if args.mongo_collection:
        cfg['collection'] = args.mongo_collection
    return cfg

def connect_mongo(cfg: Dict):
    username = cfg.get('username')
    password = cfg.get('password')
    host = cfg.get('host', 'localhost')
    port = cfg.get('port', 27017)
    if username:
        uri = f"mongodb://{quote_plus(username)}:{quote_plus(password or '')}@{host}:{port}/admin"
    else:
        uri = f"mongodb://{host}:{port}/admin"
    client = MongoClient(uri)
    client.admin.command('ping')
    collection = client[cfg['database']][cfg['collection']]
    return client, collection

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


# -----------------------------------------------------------------------------
# process_record - 主要推論流程（per AnalyzeUUID）
# -----------------------------------------------------------------------------
def process_record(
        analyze_uuid: str,
        cyclegan,
        rf_model,
        scaler: Optional[StandardScaler],
        collection,
        direction: str,
        external_loader=None
):
    feats, record = fetch_leaf_features(collection, analyze_uuid, external_loader=external_loader)
    T = feats.shape[0]

    # --- 1. CycleGAN 轉換特徵 ---
    x = torch.tensor(feats, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        if direction == "AB":
            # CPC -> Mimii
            converted = cyclegan.convert_A_to_B(x)
        else:
            # Mimii -> CPC
            converted = cyclegan.convert_B_to_A(x)

    converted_np = converted.squeeze(0).cpu().numpy()

    # === 反標準化（必做！）===
    norm_path = CHECKPOINT_DIR / "normalization_params.json"
    if norm_path.exists():
        import json
        with open(norm_path, "r", encoding="utf-8") as f:
            norm = json.load(f)

        if direction == "AB":
            # CycleGAN 輸出的是 domain B 的 normalized features
            mean = np.array(norm["mean_b"])
            std = np.array(norm["std_b"])
        else:
            mean = np.array(norm["mean_a"])
            std = np.array(norm["std_a"])

        # 反標準化
        converted_np = converted_np * std + mean

        print("[DEBUG] 反標準化後 mean/std =", converted_np.mean(), converted_np.std())
    else:
        print("[WARNING] 沒找到 normalization_params.json，無法反標準化")

    print(f"[DEBUG] 原始 CPC mean/std = {feats.mean():.4f} / {feats.std():.4f}")
    print(f"[DEBUG] G_AB 後 mean/std = {converted_np.mean():.4f} / {converted_np.std():.4f}")

    # 如果你有 scaler，就印出 scaler 轉換後
    if scaler is not None:
        X_target = scaler.transform(converted_np)
        print(f"[DEBUG] G_AB + scaler mean/std = {X_target.mean():.4f} / {X_target.std():.4f}")

    # --- 2. 準備 RF 輸入特徵 ---
    X_target = converted_np
    X_raw_40d = feats
    print("[TEST] no-scaler mean/std =", X_target.mean(), X_target.std())

    # 檢查維度是否一致 (確保是 T x 40)
    try:
        rf_expected_features = rf_model.n_features_in_
    except AttributeError:
        rf_expected_features = rf_model.n_features_

    if X_target.shape[1] != rf_expected_features:
        raise ValueError(
            f"RF 特徵維度不符！ RF 訓練時預期: {rf_expected_features} 維，"
            f"但實際輸入為: {X_target.shape[1]} 維。請檢查 LEAF 特徵維度 (N_MELS=40)。"
        )

    # --- 3. 執行預測與標籤翻轉 ---

    # a. 原始特徵預測 (RF 訓練領域，預期 0=Normal, 1=Abnormal)
    preds_raw = rf_model.predict(X_raw_40d)

    preds_final = rf_model.predict(X_target)



    source_name = record.get('files', {}).get('raw', {}).get('filename', analyze_uuid)

    rows = []
    for idx in range(T):
        rows.append({
            "AnalyzeUUID": analyze_uuid,
            "來源檔名": source_name,
            "片段索引": idx,
            "原始預測": int(preds_raw[idx]),
            "轉換後預測": int(preds_final[idx]),
        })

    summary = {
        "AnalyzeUUID": analyze_uuid,
        "來源檔名": source_name,
        "片段數": int(T),
        "原始投票": int(np.round(preds_raw.mean())),
        "轉換後投票": int(np.round(preds_final.mean())),
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
    parser.add_argument('--rf', default=str(DEFAULT_RF))
    parser.add_argument('--scaler', default=None)

    parser.add_argument('--out_csv', default='cpc_normal.csv')
    parser.add_argument('--out_summary', default='cpc_normal_summary.csv')

    # parser.add_argument('--out_csv', default='cpc_abnormal.csv')
    # parser.add_argument('--out_summary', default='cpc_abnormal_summary.csv')


    # MongoDB arguments (可覆蓋 DEFAULT)
    # try to import default config
    try:
        from sub_system.analysis_service.config import MONGODB_CONFIG as DEFAULT_MONGO_CONFIG
    except Exception:
        DEFAULT_MONGO_CONFIG = {'host': 'localhost', 'port': 27017, 'username': None, 'password': None, 'database': 'web_db', 'collection': 'recordings'}

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

    print("載入模型...")
    ckpt_path = resolve_checkpoint_path(args.cyclegan)
    cyclegan = load_cyclegan(ckpt_path)
    rf_model, scaler = load_rf_and_scaler(args.rf, args.scaler if args.scaler else None)

    mongo_cfg = build_mongo_config(args, DEFAULT_MONGO_CONFIG)
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
                rows, summary = process_record(uid, cyclegan, rf_model, scaler, collection, args.direction, external_loader=external_loader)
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
