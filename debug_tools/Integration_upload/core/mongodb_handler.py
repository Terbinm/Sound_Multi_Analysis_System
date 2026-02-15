"""
MongoDB 和 GridFS 操作模組
提供資料庫連接和檔案上傳功能
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Optional

from bson.objectid import ObjectId
from gridfs import GridFS
from pymongo import MongoClient

from .utils import build_analysis_container


class MongoDBUploader:
    """封裝 MongoDB 與 GridFS 操作的類別"""

    def __init__(
        self,
        mongodb_config: Dict[str, Any],
        use_gridfs: bool,
        logger: logging.Logger
    ) -> None:
        """
        初始化 MongoDB 上傳器

        Args:
            mongodb_config: MongoDB 配置字典，包含 host, port, username, password, database, collection
            use_gridfs: 是否使用 GridFS 儲存檔案
            logger: 日誌記錄器
        """
        self.config = mongodb_config
        self.use_gridfs = use_gridfs
        self.logger = logger
        self.mongo_client: Optional[MongoClient] = None
        self.db = None
        self.collection = None
        self.fs: Optional[GridFS] = None
        self._connect()

    def _connect(self) -> None:
        """建立 MongoDB 連接"""
        try:
            connection_string = (
                f"mongodb://{self.config['username']}:{self.config['password']}"
                f"@{self.config['host']}:{self.config['port']}/admin"
            )
            self.mongo_client = MongoClient(connection_string)
            self.db = self.mongo_client[self.config['database']]
            self.collection = self.db[self.config['collection']]

            if self.use_gridfs:
                self.fs = GridFS(self.db)

            self.mongo_client.admin.command("ping")
            self.logger.info("成功連線至 MongoDB。")
        except Exception as exc:
            self.logger.error("無法連線至 MongoDB：%s", exc)
            raise

    def file_exists(self, file_hash: str, check_duplicates: bool = True) -> bool:
        """
        檢查檔案是否已存在

        Args:
            file_hash: 檔案雜湊值
            check_duplicates: 是否檢查重複

        Returns:
            檔案是否存在
        """
        if not check_duplicates:
            return False
        existing = self.collection.find_one({'info_features.file_hash': file_hash})
        return existing is not None

    def upload_file(
        self,
        file_path: Path,
        label: str,
        file_hash: str,
        info_features: Dict[str, Any],
        gridfs_metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        上傳檔案到 MongoDB/GridFS

        Args:
            file_path: 檔案路徑
            label: 標籤
            file_hash: 檔案雜湊值
            info_features: 資訊特徵字典
            gridfs_metadata: GridFS 元數據（可選）

        Returns:
            AnalyzeUUID，如果失敗則為 None
        """
        analyze_uuid = str(uuid.uuid4())

        try:
            with open(file_path, 'rb') as handle:
                file_data = handle.read()

            file_id = None
            if self.fs:
                metadata = gridfs_metadata or {
                    'file_hash': file_hash,
                    'label': label,
                }
                file_id = self.fs.put(
                    file_data,
                    filename=file_path.name,
                    metadata=metadata,
                )
                self.logger.debug("檔案已寫入 GridFS：%s", file_id)

            document = self._create_document(
                analyze_uuid=analyze_uuid,
                filename=file_path.name,
                file_id=file_id,
                info_features=info_features,
            )

            self.collection.insert_one(document)
            self.logger.debug("已新增 MongoDB 文件：%s", analyze_uuid)
            return analyze_uuid

        except Exception as exc:
            self.logger.error("上傳檔案 %s 時發生錯誤：%s", file_path.name, exc)
            return None

    def _create_document(
        self,
        analyze_uuid: str,
        filename: str,
        file_id: Optional[ObjectId],
        info_features: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        建立 MongoDB 文檔

        Args:
            analyze_uuid: 分析 UUID
            filename: 檔案名稱
            file_id: GridFS 檔案 ID
            info_features: 資訊特徵字典

        Returns:
            MongoDB 文檔
        """
        current_time = datetime.now(UTC)
        file_type = Path(filename).suffix.lstrip('.').lower()

        document = {
            "AnalyzeUUID": analyze_uuid,
            # "current_step": 0,
            "created_at": current_time,
            "updated_at": current_time,
            "files": {
                "raw": {
                    "fileId": file_id,
                    "filename": filename,
                    "type": file_type,
                }
            },
            # 預先建立 analyze_features 容器，方便後續寫入多 run 與動態欄位
            "analyze_features": build_analysis_container(),
            "info_features": info_features,
        }

        return document

    def count_records(self) -> int:
        """
        計算 collection 中的記錄總數

        Returns:
            記錄總數
        """
        try:
            count = self.collection.count_documents({})
            return count
        except Exception as exc:
            self.logger.error("計算記錄數時發生錯誤：%s", exc)
            return 0

    def get_database_info(self) -> Dict[str, Any]:
        """
        取得資料庫詳細資訊

        Returns:
            包含資料庫資訊的字典
        """
        try:
            info = {
                'host': self.config['host'],
                'port': self.config['port'],
                'database': self.config['database'],
                'collection': self.config['collection'],
                'username': self.config['username'],
                'record_count': self.count_records(),
                'connected': True
            }

            # 取得資料庫統計資訊
            try:
                stats = self.db.command('collStats', self.config['collection'])
                info['size_bytes'] = stats.get('size', 0)
                info['storage_size_bytes'] = stats.get('storageSize', 0)
            except Exception:
                info['size_bytes'] = 0
                info['storage_size_bytes'] = 0

            # 取得最後更新時間
            try:
                latest_record = self.collection.find_one(
                    {},
                    sort=[('updated_at', -1)]
                )
                if latest_record and 'updated_at' in latest_record:
                    info['last_updated'] = latest_record['updated_at']
                else:
                    info['last_updated'] = None
            except Exception:
                info['last_updated'] = None

            return info

        except Exception as exc:
            self.logger.error("取得資料庫資訊時發生錯誤：%s", exc)
            return {
                'host': self.config.get('host', 'N/A'),
                'port': self.config.get('port', 'N/A'),
                'database': self.config.get('database', 'N/A'),
                'collection': self.config.get('collection', 'N/A'),
                'username': self.config.get('username', 'N/A'),
                'record_count': 0,
                'connected': False,
                'error': str(exc)
            }

    def backup_all_records(self, backup_file: Path) -> bool:
        """
        備份所有記錄至 JSON 檔案

        Args:
            backup_file: 備份檔案路徑

        Returns:
            備份是否成功
        """
        import json

        try:
            self.logger.info("開始備份資料庫記錄...")
            records = list(self.collection.find({}))

            # 轉換 ObjectId 為字串
            for record in records:
                if '_id' in record:
                    record['_id'] = str(record['_id'])
                if 'files' in record and 'raw' in record['files']:
                    if 'fileId' in record['files']['raw'] and record['files']['raw']['fileId']:
                        record['files']['raw']['fileId'] = str(record['files']['raw']['fileId'])
                # 轉換 datetime 物件
                if 'created_at' in record:
                    record['created_at'] = str(record['created_at'])
                if 'updated_at' in record:
                    record['updated_at'] = str(record['updated_at'])

            # 確保備份目錄存在
            backup_file.parent.mkdir(parents=True, exist_ok=True)

            # 寫入 JSON 檔案
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(records, f, indent=2, ensure_ascii=False, default=str)

            self.logger.info(f"✓ 備份完成：{backup_file} ({len(records)} 筆記錄)")
            return True

        except Exception as exc:
            self.logger.error(f"✗ 備份失敗：{exc}")
            return False

    def delete_all_records(self) -> int:
        """
        刪除所有記錄

        Returns:
            刪除的記錄數量
        """
        try:
            result = self.collection.delete_many({})
            deleted_count = result.deleted_count
            self.logger.info(f"✓ 已刪除 {deleted_count} 筆記錄")
            return deleted_count

        except Exception as exc:
            self.logger.error(f"✗ 刪除記錄失敗：{exc}")
            return 0

    def count_records_by_dataset(self, dataset_uuid: str) -> int:
        """
        計算指定 dataset_UUID 的記錄數

        Args:
            dataset_uuid: 資料集 UUID

        Returns:
            記錄數量
        """
        try:
            query = {'info_features.dataset_UUID': dataset_uuid}
            return self.collection.count_documents(query)
        except Exception as exc:
            self.logger.error(f"計算 {dataset_uuid} 記錄數時發生錯誤：{exc}")
            return 0

    def delete_records_by_dataset(self, dataset_uuid: str, with_backup: bool = True) -> Dict[str, Any]:
        """
        刪除指定 dataset_UUID 的記錄

        Args:
            dataset_uuid: 要刪除的資料集 UUID
            with_backup: 是否先備份

        Returns:
            包含 deleted_count 和 backup_file 的字典
        """
        import json
        from datetime import datetime
        from pathlib import Path

        result = {
            'deleted_count': 0,
            'backup_file': None,
            'success': False
        }

        try:
            # 查詢符合條件的記錄數
            query = {'info_features.dataset_UUID': dataset_uuid}
            count = self.collection.count_documents(query)

            if count == 0:
                self.logger.info(f"沒有找到 dataset_UUID={dataset_uuid} 的記錄")
                result['success'] = True
                return result

            self.logger.info(f"找到 {count} 筆 dataset_UUID={dataset_uuid} 的記錄")

            # 備份（如果需要）
            if with_backup:
                records = list(self.collection.find(query))

                # 轉換 ObjectId 為字串
                for record in records:
                    if '_id' in record:
                        record['_id'] = str(record['_id'])
                    if 'files' in record and 'raw' in record['files']:
                        if 'fileId' in record['files']['raw'] and record['files']['raw']['fileId']:
                            record['files']['raw']['fileId'] = str(record['files']['raw']['fileId'])
                    if 'created_at' in record:
                        record['created_at'] = str(record['created_at'])
                    if 'updated_at' in record:
                        record['updated_at'] = str(record['updated_at'])

                # 備份檔案
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_dir = Path('reports/backups')
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_file = backup_dir / f"backup_{dataset_uuid}_{timestamp}.json"

                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(records, f, indent=2, ensure_ascii=False, default=str)

                self.logger.info(f"✓ 已備份 {len(records)} 筆記錄至 {backup_file}")
                result['backup_file'] = str(backup_file)

            # 刪除記錄
            delete_result = self.collection.delete_many(query)
            result['deleted_count'] = delete_result.deleted_count
            result['success'] = True

            self.logger.info(f"✓ 已刪除 {result['deleted_count']} 筆 {dataset_uuid} 記錄")
            return result

        except Exception as exc:
            self.logger.error(f"✗ 刪除 {dataset_uuid} 記錄失敗：{exc}")
            return result

    def restore_from_backup(self, backup_file: Path) -> Dict[str, int]:
        """
        從備份檔還原記錄

        Args:
            backup_file: 備份檔案路徑

        Returns:
            包含 inserted 和 skipped 數量的字典
        """
        import json

        try:
            self.logger.info(f"開始從備份檔還原：{backup_file}")

            # 讀取備份檔案
            with open(backup_file, 'r', encoding='utf-8') as f:
                records = json.load(f)

            inserted_count = 0
            skipped_count = 0

            for record in records:
                try:
                    # 轉換字串 ID 回 ObjectId
                    if '_id' in record and isinstance(record['_id'], str):
                        try:
                            record['_id'] = ObjectId(record['_id'])
                        except Exception:
                            # 如果轉換失敗，移除 _id 讓 MongoDB 自動生成
                            del record['_id']

                    if 'files' in record and 'raw' in record['files']:
                        if 'fileId' in record['files']['raw'] and isinstance(record['files']['raw']['fileId'], str):
                            try:
                                record['files']['raw']['fileId'] = ObjectId(record['files']['raw']['fileId'])
                            except Exception:
                                # GridFS 檔案 ID 轉換失敗，保持為 None
                                record['files']['raw']['fileId'] = None

                    # 轉換日期字串回 datetime（如果是字串格式）
                    # 注意：這裡簡化處理，實際可能需要更複雜的日期解析

                    # 插入記錄
                    self.collection.insert_one(record)
                    inserted_count += 1

                except Exception as e:
                    # 如果是重複 _id，跳過
                    if 'duplicate key error' in str(e).lower():
                        skipped_count += 1
                        self.logger.debug(f"跳過重複記錄：{record.get('AnalyzeUUID', 'unknown')}")
                    else:
                        skipped_count += 1
                        self.logger.warning(f"還原記錄失敗：{e}")

            self.logger.info(f"✓ 還原完成：插入 {inserted_count} 筆，跳過 {skipped_count} 筆")
            return {'inserted': inserted_count, 'skipped': skipped_count}

        except Exception as exc:
            self.logger.error(f"✗ 從備份檔還原失敗：{exc}")
            return {'inserted': 0, 'skipped': 0}

    def close(self) -> None:
        """關閉 MongoDB 連接"""
        if self.mongo_client:
            self.mongo_client.close()
            self.logger.info("已關閉 MongoDB 連線。")
