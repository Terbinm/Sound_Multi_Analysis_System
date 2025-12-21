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
    parser = argparse.ArgumentParser(description="�q MongoDB ��X Step2 ������� AnalyzeUUID ����r��")
    parser.add_argument('--output', default='uuid_list.txt', help='���X txt �ɮצW�٬�')
    parser.add_argument('--device', default='cpc006', help='��ܾ� info_features.device_id (�w�] cpc006)')
    parser.add_argument('--limit', type=int, default=50, help='�̦h�o�X���ƶq (0 �N�L�� LIMIT)')
    parser.add_argument('--mongo_host', default=DEFAULT_MONGO.get('host'))
    parser.add_argument('--mongo_port', type=int, default=DEFAULT_MONGO.get('port'))
    parser.add_argument('--mongo_username', default=DEFAULT_MONGO.get('username'))
    parser.add_argument('--mongo_password', default=DEFAULT_MONGO.get('password'))
    parser.add_argument('--mongo_db', default=DEFAULT_MONGO.get('database'))
    parser.add_argument('--mongo_collection', default=DEFAULT_MONGO.get('collection'))
    return parser.parse_args()


def main():
    args = parse_args()
    overrides = {
        'host': args.mongo_host,
        'port': args.mongo_port,
        'username': args.mongo_username,
        'password': args.mongo_password,
        'database': args.mongo_db,
        'collection': args.mongo_collection,
    }
    mongo_cfg = merge_mongo_overrides(DEFAULT_MONGO, overrides)

    print("���s MongoDB ...")
    client = None
    try:
        client, collection = connect_mongo(mongo_cfg)
        uuids = fetch_step2_completed_uuids(
            collection,
            max_records=args.limit,
            device_id=args.device,
        )
    finally:
        if client:
            client.close()

    output_path = Path(args.output)
    output_path.write_text("\n".join(uuids), encoding='utf-8')
    print(f"���o {len(uuids)} �쪺 AnalyzeUUID �A��J {output_path.resolve()}")


if __name__ == "__main__":
    main()
