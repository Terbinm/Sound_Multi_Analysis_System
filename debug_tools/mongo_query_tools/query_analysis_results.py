"""
MongoDB Analysis Query Tool
查詢分析結果並輸出 CSV 與視覺化圖表

用途：
1. 查詢所有 Rule ID
2. 查詢特定 Router ID 的分析結果
3. 輸出 CSV (聲音檔案名稱/結果/average_confidence)
4. 繪製時間與結果/信心度關係圖
"""

import os
import sys
import re
import csv
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

# 專案根目錄
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# 載入環境變數
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)

from pymongo import MongoClient


# ============================================================
# MongoDB 連接設定
# ============================================================
def get_mongo_config() -> Dict[str, Any]:
    """從環境變數取得 MongoDB 連線設定"""
    return {
        'host': os.getenv('MONGODB_HOST', 'localhost'),
        'port': int(os.getenv('MONGODB_PORT', 55101)),
        'username': os.getenv('MONGODB_USERNAME'),
        'password': os.getenv('MONGODB_PASSWORD'),
        'database': os.getenv('MONGODB_DATABASE', 'web_db'),
        'auth_source': os.getenv('MONGODB_AUTH_SOURCE', 'admin'),
    }


def connect_mongodb() -> Tuple[MongoClient, Any]:
    """連接 MongoDB 並返回 client 和 database"""
    config = get_mongo_config()
    print(f"[INFO] 連接 MongoDB: {config['host']}:{config['port']}")

    if config['username']:
        client = MongoClient(
            host=config['host'],
            port=config['port'],
            username=config['username'],
            password=config['password'],
            authSource=config['auth_source'],
        )
    else:
        client = MongoClient(
            host=config['host'],
            port=config['port'],
        )

    db = client[config['database']]
    return client, db


# ============================================================
# 查詢函式
# ============================================================
def get_all_rule_ids(db) -> List[Dict[str, Any]]:
    """
    查詢所有 Rule ID

    Returns:
        List of dicts with rule_id, rule_name, router_ids, enabled
    """
    collection = db['routing_rules']
    rules = []

    for doc in collection.find({}, {
        'rule_id': 1,
        'rule_name': 1,
        'router_ids': 1,
        'enabled': 1,
        'description': 1
    }):
        rules.append({
            'rule_id': doc.get('rule_id'),
            'rule_name': doc.get('rule_name'),
            'router_ids': doc.get('router_ids', []),
            'enabled': doc.get('enabled', False),
            'description': doc.get('description', '')
        })

    return rules


def parse_filename_datetime(filename: str) -> Optional[datetime]:
    """
    從檔案名稱解析時間戳記

    支援格式:
    - CPC_006_20241223_163138.wav -> 2024-12-23 16:31:38
    - 其他格式嘗試解析
    """
    if not filename:
        return None

    # 嘗試 CPC 格式: CPC_XXX_YYYYMMDD_HHMMSS.wav
    match = re.search(r'(\d{8})_(\d{6})', filename)
    if match:
        date_str = match.group(1)
        time_str = match.group(2)
        try:
            return datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
        except ValueError:
            pass

    # 嘗試其他常見格式
    patterns = [
        r'(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})',  # 2024-12-23_16-31-38
        r'(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})',       # 20241223163138
    ]

    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            groups = match.groups()
            try:
                return datetime(
                    int(groups[0]), int(groups[1]), int(groups[2]),
                    int(groups[3]), int(groups[4]), int(groups[5])
                )
            except (ValueError, IndexError):
                continue

    return None


def resolve_router_id(db, identifier: str) -> Tuple[str, str]:
    """
    解析 Rule Name 或 Router ID，返回實際的 Router ID

    Args:
        db: MongoDB database
        identifier: Rule Name 或 Router ID

    Returns:
        (router_id, rule_name) 元組
    """
    rules_col = db['routing_rules']

    # 先嘗試用 rule_name 查詢
    rule = rules_col.find_one({'rule_name': identifier})
    if rule:
        router_ids = rule.get('router_ids', [])
        router_id = router_ids[0] if router_ids else rule.get('rule_id', identifier)
        return router_id, rule.get('rule_name', identifier)

    # 再嘗試用 rule_id 查詢
    rule = rules_col.find_one({'rule_id': identifier})
    if rule:
        router_ids = rule.get('router_ids', [])
        router_id = router_ids[0] if router_ids else identifier
        return router_id, rule.get('rule_name', identifier)

    # 嘗試用 router_ids 查詢
    rule = rules_col.find_one({'router_ids': identifier})
    if rule:
        return identifier, rule.get('rule_name', identifier)

    # 找不到就直接返回輸入值
    return identifier, identifier


def get_analysis_results_by_router_id(
    db,
    router_id: str
) -> List[Dict[str, Any]]:
    """
    查詢特定 Router ID 的所有分析結果

    Args:
        db: MongoDB database
        router_id: 路由 ID

    Returns:
        List of analysis results
    """
    logs_col = db['task_execution_logs']
    recordings_col = db['recordings']

    # 方法1: 透過 task_execution_logs 查詢
    print(f"[INFO] 查詢 router_id = '{router_id}' 的分析結果...")

    # 取得所有符合的 analyze_uuid
    log_docs = list(logs_col.find(
        {'router_id': router_id},
        {'analyze_uuid': 1, 'router_id': 1, 'status': 1}
    ))

    print(f"[INFO] 在 task_execution_logs 中找到 {len(log_docs)} 筆記錄")

    analyze_uuids = list(set(doc.get('analyze_uuid') for doc in log_docs if doc.get('analyze_uuid')))

    results = []

    for uuid in analyze_uuids:
        recording = recordings_col.find_one({'AnalyzeUUID': uuid})
        if not recording:
            continue

        filename = recording.get('files', {}).get('raw', {}).get('filename', '')
        file_datetime = parse_filename_datetime(filename)

        # 解析 runs
        analyze_features = recording.get('analyze_features', {}) or {}
        runs = analyze_features.get('runs', {})

        if isinstance(runs, dict):
            for run_id, run_data in runs.items():
                run_router_id = run_data.get('router_id', '')

                # 只取符合 router_id 的 run
                if run_router_id != router_id:
                    # 也檢查 analysis_context
                    ctx = run_data.get('analysis_context', {}) or {}
                    routing_ctx = ctx.get('routing_rule', {}) if isinstance(ctx, dict) else {}
                    if routing_ctx.get('router_id') != router_id:
                        continue

                summary = run_data.get('analysis_summary', {}) or {}
                final_prediction = summary.get('final_prediction', 'unknown')
                avg_confidence = summary.get('average_confidence', 0.0)

                # 如果 summary 沒有，嘗試從 steps 取得
                if final_prediction == 'unknown' or avg_confidence == 0.0:
                    steps = run_data.get('steps', {})
                    if isinstance(steps, dict):
                        for step_name, step_data in steps.items():
                            if isinstance(step_data, dict):
                                proc_meta = step_data.get('processor_metadata', {})
                                if proc_meta:
                                    if final_prediction == 'unknown':
                                        final_prediction = proc_meta.get('final_prediction', final_prediction)
                                    if avg_confidence == 0.0:
                                        avg_confidence = proc_meta.get('average_confidence', avg_confidence)

                results.append({
                    'analyze_uuid': uuid,
                    'filename': filename,
                    'file_datetime': file_datetime,
                    'run_id': run_id,
                    'router_id': run_router_id or router_id,
                    'final_prediction': final_prediction,
                    'average_confidence': float(avg_confidence) if avg_confidence else 0.0,
                    'completed_at': run_data.get('completed_at'),
                })
        elif isinstance(runs, list):
            for idx, run_data in enumerate(runs):
                run_router_id = run_data.get('router_id', '')
                if run_router_id != router_id:
                    continue

                summary = run_data.get('analysis_summary', {}) or {}
                results.append({
                    'analyze_uuid': uuid,
                    'filename': filename,
                    'file_datetime': file_datetime,
                    'run_id': f"run_{idx}",
                    'router_id': run_router_id,
                    'final_prediction': summary.get('final_prediction', 'unknown'),
                    'average_confidence': float(summary.get('average_confidence', 0.0)),
                    'completed_at': run_data.get('completed_at'),
                })

    # 按時間排序
    results.sort(key=lambda x: x.get('file_datetime') or datetime.min)

    print(f"[INFO] 共找到 {len(results)} 筆分析結果")
    return results


def export_to_csv(
    results: List[Dict[str, Any]],
    output_path: Path
) -> None:
    """
    輸出分析結果為 CSV

    Args:
        results: 分析結果列表
        output_path: 輸出路徑
    """
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['filename', 'file_datetime', 'final_prediction', 'average_confidence'])

        for r in results:
            dt_str = r['file_datetime'].strftime('%Y-%m-%d %H:%M:%S') if r['file_datetime'] else ''
            writer.writerow([
                r['filename'],
                dt_str,
                r['final_prediction'],
                f"{r['average_confidence']:.4f}"
            ])

    print(f"[INFO] CSV 已儲存至: {output_path}")


def plot_time_series(
    results: List[Dict[str, Any]],
    output_path: Path
) -> None:
    """
    繪製時間與結果/信心度關係圖

    Args:
        results: 分析結果列表
        output_path: 輸出路徑
    """
    # 過濾有效的時間資料
    valid_results = [r for r in results if r.get('file_datetime')]

    if not valid_results:
        print("[WARNING] 沒有有效的時間資料，無法繪製圖表")
        return

    # 準備資料
    times = [r['file_datetime'] for r in valid_results]
    predictions = [r['final_prediction'] for r in valid_results]
    confidences = [r['average_confidence'] for r in valid_results]

    # 將預測結果轉換為數值
    pred_map = {'normal': 0, 'abnormal': 1, 'unknown': 0.5, 'uncertain': 0.5}
    pred_values = [pred_map.get(p, 0.5) for p in predictions]

    # 設定顏色
    colors = []
    for p in predictions:
        if p == 'normal':
            colors.append('green')
        elif p == 'abnormal':
            colors.append('red')
        else:
            colors.append('gray')

    # 建立圖表 (比例 1:3，寬度更長方便觀察時間序列)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(24, 8), sharex=True)
    fig.suptitle(f'Analysis Results Over Time (n={len(valid_results)})', fontsize=14)

    # 子圖1: 預測結果
    ax1.scatter(times, pred_values, c=colors, alpha=0.7, s=50)
    ax1.set_ylabel('Prediction (0=normal, 1=abnormal)')
    ax1.set_ylim(-0.1, 1.1)
    ax1.axhline(y=0.5, color='orange', linestyle='--', alpha=0.5, label='Threshold')
    ax1.set_yticks([0, 0.5, 1])
    ax1.set_yticklabels(['normal', 'uncertain', 'abnormal'])
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # 子圖2: 信心度
    ax2.scatter(times, confidences, c=colors, alpha=0.7, s=50)
    ax2.plot(times, confidences, 'b-', alpha=0.3, linewidth=1)
    ax2.set_ylabel('Average Confidence')
    ax2.set_ylim(0, 1.05)
    ax2.set_xlabel('Time')
    ax2.grid(True, alpha=0.3)

    # 格式化 X 軸
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
    ax2.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.xticks(rotation=45)

    # 添加統計資訊
    normal_count = sum(1 for p in predictions if p == 'normal')
    abnormal_count = sum(1 for p in predictions if p == 'abnormal')
    avg_conf = np.mean(confidences)

    stats_text = f'Normal: {normal_count} | Abnormal: {abnormal_count} | Avg Confidence: {avg_conf:.3f}'
    fig.text(0.5, 0.02, stats_text, ha='center', fontsize=11,
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.tight_layout(rect=[0, 0.05, 1, 0.96])
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"[INFO] 圖表已儲存至: {output_path}")


# ============================================================
# 主程式
# ============================================================
def main():
    """主程式"""
    # 設定輸出目錄
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    # 連接 MongoDB
    client, db = connect_mongodb()

    try:
        # 1. 查詢所有 Rule ID
        print("\n" + "=" * 60)
        print("查詢所有 Rule ID")
        print("=" * 60)

        rules = get_all_rule_ids(db)

        if not rules:
            print("[WARNING] 未找到任何 Rule")
        else:
            print(f"\n找到 {len(rules)} 個 Rule:\n")
            for i, rule in enumerate(rules, 1):
                status = "enabled" if rule['enabled'] else "disabled"
                print(f"  {i}. Rule ID: {rule['rule_id']}")
                print(f"     Rule Name: {rule['rule_name']}")
                print(f"     Router IDs: {rule['router_ids']}")
                print(f"     Status: {status}")
                if rule['description']:
                    print(f"     Description: {rule['description'][:50]}...")
                print()

        # 2. 查詢特定 Router ID 的分析結果
        target_identifier = "HGJKJKGH"  # 可以是 Rule Name 或 Router ID

        # 解析實際的 Router ID
        actual_router_id, rule_name = resolve_router_id(db, target_identifier)

        print("\n" + "=" * 60)
        print(f"查詢 Rule = '{rule_name}' 的分析結果")
        print(f"(Router ID: {actual_router_id})")
        print("=" * 60)

        results = get_analysis_results_by_router_id(db, actual_router_id)

        if not results:
            print(f"[WARNING] 未找到 Rule = '{rule_name}' 的分析結果")
            print("\n可能的原因：")
            print("  1. 此規則尚未有任何分析任務")
            print("  2. Rule Name 或 Router ID 拼寫錯誤")
            print("\n建議：請從上方列表中選擇正確的規則")
        else:
            # 顯示結果摘要
            print(f"\n找到 {len(results)} 筆分析結果:\n")

            normal_count = sum(1 for r in results if r['final_prediction'] == 'normal')
            abnormal_count = sum(1 for r in results if r['final_prediction'] == 'abnormal')
            unknown_count = len(results) - normal_count - abnormal_count

            print(f"  - Normal: {normal_count}")
            print(f"  - Abnormal: {abnormal_count}")
            print(f"  - Unknown/Other: {unknown_count}")

            confidences = [r['average_confidence'] for r in results if r['average_confidence'] > 0]
            if confidences:
                print(f"  - Average Confidence: {np.mean(confidences):.4f}")

            # 顯示前 10 筆
            print(f"\n前 10 筆資料:")
            for i, r in enumerate(results[:10], 1):
                dt_str = r['file_datetime'].strftime('%Y-%m-%d %H:%M:%S') if r['file_datetime'] else 'N/A'
                print(f"  {i}. {r['filename'][:40]:<40} | {dt_str} | {r['final_prediction']:10} | {r['average_confidence']:.4f}")

            # 3. 輸出 CSV
            csv_path = output_dir / f"analysis_results_{rule_name}.csv"
            export_to_csv(results, csv_path)

            # 4. 繪製圖表
            plot_path = output_dir / f"analysis_results_{rule_name}.png"
            plot_time_series(results, plot_path)

    finally:
        client.close()
        print("\n[INFO] MongoDB 連線已關閉")


if __name__ == "__main__":
    main()
