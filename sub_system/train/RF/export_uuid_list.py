from pymongo import MongoClient

MONGO = {
    'host': 'localhost',
    'port': 55101,
    'username': 'web_ui',
    'password': 'hod2iddfsgsrl',
    'database': 'web_db',
    'collection': 'recordings'
}

MAX_RECORDS = 10

def main():
    print("連線 MongoDB...")
    uri = f"mongodb://{MONGO['username']}:{MONGO['password']}@{MONGO['host']}:{MONGO['port']}/admin"
    client = MongoClient(uri)
    col = client[MONGO['database']][MONGO['collection']]

    print("抓取 device_id=cpc006 的資料...")

    cursor = col.find(
        {"info_features.device_id": "cpc006"},
        {"AnalyzeUUID": 1, "runs": 1}
    )

    uuids = []

    for doc in cursor:

        runs = doc.get("runs", {})
        if not isinstance(runs, dict):
            continue

        for run_key, run_data in runs.items():

            steps = run_data.get("steps", {})
            leaf_step = steps.get("LEAF Features")

            # ← 這裡精準對應你的 screenshot
            if leaf_step and leaf_step.get("features_state") == "completed":
                uuids.append(doc["AnalyzeUUID"])
                print(f"找到 Step2 完成：{doc['AnalyzeUUID']}")
                break

        if MAX_RECORDS and len(uuids) >= MAX_RECORDS:
            break

    print(f"\n找到 {len(uuids)} 筆 UUID")

    with open("uuid_list.txt", "w", encoding="utf-8") as f:
        for u in uuids:
            f.write(u + "\n")

    print("已輸出 uuid_list.txt")


if __name__ == "__main__":
    main()
