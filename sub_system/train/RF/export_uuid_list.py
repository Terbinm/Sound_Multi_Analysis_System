from pymongo import MongoClient



MONGO = {
    'host': 'localhost',
    'port': 55101,
    'username': 'web_ui',
    'password': 'hod2iddfsgsrl',
    'database': 'web_db',
    'collection': 'recordings'
}

MAX_RECORDS = 50

def main():
    print("連線 MongoDB...")
    uri = f"mongodb://{MONGO['username']}:{MONGO['password']}@{MONGO['host']}:{MONGO['port']}/admin"
    client = MongoClient(uri)

    col = client[MONGO['database']][MONGO['collection']]

    print("查詢 Step2 (LEAF Features) 已完成的紀錄...")

    query = {
        "info_features.device_id": "cpc006",
        "$expr": {
            "$gt": [
                {
                    "$size": {
                        "$filter": {
                            "input": {"$objectToArray": "$analyze_features.runs"},
                            "as": "run",
                            "cond": {
                                "$eq": [
                                    {"$getField": {
                                        "field": "features_state",
                                        "input": {
                                            "$getField": {
                                                "field": "LEAF Features",
                                                "input": "$$run.v.steps"
                                            }
                                        }
                                    }},
                                    "completed"
                                ]
                            }
                        }
                    }
                },
                0
            ]
        }
    }

    cursor = col.find(query, {"AnalyzeUUID": 1})

    if MAX_RECORDS > 0:
        cursor = cursor.limit(MAX_RECORDS)

    uuids = [doc["AnalyzeUUID"] for doc in cursor if "AnalyzeUUID" in doc]

    print(f"找到 {len(uuids)} 筆 UUID")

    with open("uuid_list.txt", "w", encoding="utf-8") as f:
        for u in uuids:
            f.write(u + "\n")

    print("已輸出 uuid_list.txt")

from pymongo import MongoClient

client = MongoClient("mongodb://web_ui:hod2iddfsgsrl@localhost:55101/admin")
col = client["web_db"]["recordings"]

docs = col.find(
    {
        "analyze_features.features_step": 2
    },
    {
        "AnalyzeUUID": 1,
        "info_features.device_id": 1
    }
)

print("=== Step2 資料 ===")
for d in docs:
    print(d)


if __name__ == "__main__":
    main()
