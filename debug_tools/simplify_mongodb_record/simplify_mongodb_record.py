import os
import json
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId

# MongoDB 配置
MONGODB_CONFIG = {
    'host': os.getenv('MONGODB_HOST', 'localhost'),
    'port': int(os.getenv('MONGODB_PORT', '27021')),
    'username': os.getenv('MONGODB_USERNAME', 'web_ui'),
    'password': os.getenv('MONGODB_PASSWORD', 'hod2iddfsgsrl'),
    'database': 'web_db',
    'collection': 'recordings'
}


def connect_mongodb():
    """連線到 MongoDB"""
    client = MongoClient(
        host=MONGODB_CONFIG['host'],
        port=MONGODB_CONFIG['port'],
        username=MONGODB_CONFIG['username'],
        password=MONGODB_CONFIG['password']
    )
    db = client[MONGODB_CONFIG['database']]
    collection = db[MONGODB_CONFIG['collection']]
    return client, collection


def convert_mongo_types(obj):
    """轉換 MongoDB 特殊類型為可 JSON 序列化的格式"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: convert_mongo_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_mongo_types(item) for item in obj]
    return obj


def _trim_step_data(step):
    if 'features_data' in step and isinstance(step['features_data'], list):
        original_count = len(step['features_data'])
        step['features_data'] = step['features_data'][:2]
        print(
            f"  - {step.get('features_name', 'Unknown')}: {original_count} 筆 -> {len(step['features_data'])} 筆")


def simplify_features_data(record):
    """精簡 analyze_features 中的 features_data,僅保留前 2 筆"""
    if 'analyze_features' not in record:
        print("記錄中沒有 analyze_features 欄位")
        return record

    analyze_features = record['analyze_features']

    if isinstance(analyze_features, dict):
        for run in analyze_features.get('runs', []):
            for step in run.get('steps', []):
                _trim_step_data(step)
    elif isinstance(analyze_features, list):
        for feature in analyze_features:
            _trim_step_data(feature)

    return record


def main():
    print("=== MongoDB 資料提取與精簡工具 ===\n")

    # 連線到 MongoDB
    print("連線到 MongoDB...")
    client, collection = connect_mongodb()

    try:
        # 取得最新一筆記錄
        print("查詢最新一筆記錄...")
        latest_record = collection.find_one(
            sort=[('created_at', -1)]  # 依 created_at 降序排序
        )

        if not latest_record:
            print("資料庫中沒有任何記錄")
            return

        print(f"\n找到記錄:")
        print(f"  - AnalyzeUUID: {latest_record.get('AnalyzeUUID', 'N/A')}")
        print(f"  - 建立時間: {latest_record.get('created_at', 'N/A')}")
        print(f"  - 檔案名稱: {latest_record.get('files', {}).get('raw', {}).get('filename', 'N/A')}")

        # 精簡 features_data
        print("\n精簡 features_data...")
        simplified_record = simplify_features_data(latest_record)

        # 轉換 MongoDB 特殊類型
        json_record = convert_mongo_types(simplified_record)

        # 儲存成 JSON 檔案
        output_filename = f"output/simplified_record_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        print(f"\n儲存成 JSON 檔案: {output_filename}")

        # 確保 output 目錄存在
        output_dir = os.path.dirname(output_filename)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(json_record, f, ensure_ascii=False, indent=2)

        print(f"✓ 成功儲存至 {output_filename}")
        print(f"\n處理完成!")

    except Exception as e:
        print(f"\n❌ 錯誤: {str(e)}")

    finally:
        # 關閉連線
        client.close()
        print("\n已關閉 MongoDB 連線")


if __name__ == "__main__":
    main()
