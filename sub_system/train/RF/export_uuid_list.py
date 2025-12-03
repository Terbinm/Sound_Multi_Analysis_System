from pymongo import MongoClient

# 修改成你的 MongoDB 設定
MONGO = {
    'host': 'localhost',
    'port': 27025,
    'username': 'web_ui',
    'password': 'hod2iddfsgsrl',
    'database': 'web_db',
    'collection': 'recordings'
}

# ====== 可自行設定最多抓多少筆 ======
MAX_RECORDS = 10   # 想抓幾筆就改這個（0 或 None = 不限制）

def main():
    print("連線 MongoDB...")
    uri = f"mongodb://{MONGO['username']}:{MONGO['password']}@{MONGO['host']}:{MONGO['port']}/admin"
    client = MongoClient(uri)

    col = client[MONGO['database']][MONGO['collection']]

    print("查詢 Step2 (LEAF) 已完成的紀錄...")

    query = {
        'info_features.device_id': 'cpc006',
        #'info_features.device_id': 'BATCH_UPLOAD_NORMAL',
        #'info_features.device_id': 'BATCH_UPLOAD_ABNORMAL',
        'analyze_features': {
            '$elemMatch': {
                'features_step': 2,
                'features_state': 'completed'
            }
        }
    }

    cursor = col.find(query, {'AnalyzeUUID': 1})

    # ====== 若有設定限制筆數，套用 limit() ======
    if MAX_RECORDS and MAX_RECORDS > 0:
        cursor = cursor.limit(MAX_RECORDS)

    # ====== 收集 UUID ======
    uuids = [doc['AnalyzeUUID'] for doc in cursor if 'AnalyzeUUID' in doc]

    print(f"找到 {len(uuids)} 筆 UUID（限制 = {MAX_RECORDS}）")

    # ====== 輸出 ======
    with open("uuid_list.txt", "w", encoding="utf-8") as f:
        for u in uuids:
            f.write(u + "\n")

    print("已輸出 → uuid_list.txt")

if __name__ == "__main__":
    main()
