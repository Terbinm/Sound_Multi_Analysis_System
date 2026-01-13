import argparse
from pathlib import Path

from sub_system.train.RF.mongo_helpers import (
    load_default_mongo_config,
    merge_mongo_overrides,
    connect_mongo,
    fetch_step2_completed_uuids,
)

DEFAULT_MONGO = load_default_mongo_config()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="從 MongoDB 匯出 Step2 已完成的 AnalyzeUUID 至文字檔")
    parser.add_argument('--output', default='uuid_list.txt', help='輸出 txt 檔案名稱')
    parser.add_argument('--device', default='cpc006', help='過濾 info_features.device_id (預設 cpc006)')
    parser.add_argument('--limit', type=int, default=0, help='最多取出的數量 (0 代表無限 LIMIT)')
    parser.add_argument('--mongo_host', default=DEFAULT_MONGO.get('host'))
    parser.add_argument('--mongo_port', type=int, default=DEFAULT_MONGO.get('port'))
    parser.add_argument('--mongo_username', default=DEFAULT_MONGO.get('MONGODB_USERNAME'))
    parser.add_argument('--mongo_password', default=DEFAULT_MONGO.get('MONGODB_PASSWORD'))
    parser.add_argument('--mongo_db', default=DEFAULT_MONGO.get('database'))
    parser.add_argument('--mongo_collection', default=DEFAULT_MONGO.get('collection'))
    return parser.parse_args()


def main():
    args = parse_args()
    overrides = {
        'host': "127.0.0.1",
        'port': 55101,
        'username': "web_ui",
        'password': "hod2iddfsgsrl",
        'database': "web_db",
        'collection': "recordings",
    }
    mongo_cfg = merge_mongo_overrides(DEFAULT_MONGO, overrides)

    print("連線 MongoDB ...")
    client = None
    try:
        client, collection = connect_mongo(mongo_cfg)
        uuids = fetch_step2_completed_uuids(
            collection,
            max_records=args.limit,
            # device_id=args.device,
        )
    finally:
        if client:
            client.close()

    output_path = Path(args.output)
    output_path.write_text("\n".join(uuids), encoding='utf-8')
    print(f"取得 {len(uuids)} 筆的 AnalyzeUUID，寫入 {output_path.resolve()}")


if __name__ == "__main__":
    main()
