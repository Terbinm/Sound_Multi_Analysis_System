# a_sub_system/analysis_service/gridfs_handler.py - 分析服務的 GridFS 處理器

from gridfs import GridFS, GridFSBucket
from pymongo import MongoClient
from bson.objectid import ObjectId
from config import MONGODB_CONFIG
import logging
from typing import Optional, BinaryIO
import io

logger = logging.getLogger(__name__)


class AnalysisGridFSHandler:
    """分析服務專用的 GridFS 處理器（唯讀）"""

    def __init__(self, mongo_client: MongoClient = None):
        """
        初始化 GridFS 處理器

        Args:
            mongo_client: MongoDB 客戶端實例
        """
        if mongo_client is None:
            connection_string = (
                f"mongodb://{MONGODB_CONFIG['username']}:{MONGODB_CONFIG['password']}"
                f"@{MONGODB_CONFIG['host']}:{MONGODB_CONFIG['port']}/admin"
            )
            self.mongo_client = MongoClient(connection_string)
        else:
            self.mongo_client = mongo_client

        self.db = self.mongo_client[MONGODB_CONFIG['database']]
        self.fs = GridFS(self.db)
        self.fs_bucket = GridFSBucket(self.db)

        logger.info("分析服務 GridFS Handler 初始化成功")

    def download_file(self, file_id: ObjectId) -> Optional[bytes]:
        """
        從 GridFS 下載文件

        Args:
            file_id: 文件 ObjectId

        Returns:
            文件二進制數據或 None
        """
        try:
            if isinstance(file_id, str):
                file_id = ObjectId(file_id)

            grid_out = self.fs.get(file_id)
            file_data = grid_out.read()

            logger.debug(f"從 GridFS 下載文件成功 (ID: {file_id})")
            return file_data

        except Exception as e:
            logger.error(f"從 GridFS 下載文件失敗 (ID: {file_id}): {e}")
            return None

    def download_file_stream(self, file_id: ObjectId) -> Optional[io.BytesIO]:
        """
        從 GridFS 下載文件流

        Args:
            file_id: 文件 ObjectId

        Returns:
            BytesIO 對象或 None
        """
        try:
            if isinstance(file_id, str):
                file_id = ObjectId(file_id)

            file_data = self.download_file(file_id)
            if file_data:
                return io.BytesIO(file_data)
            return None

        except Exception as e:
            logger.error(f"從 GridFS 下載文件流失敗 (ID: {file_id}): {e}")
            return None

    def file_exists(self, file_id: ObjectId) -> bool:
        """
        檢查文件是否存在

        Args:
            file_id: 文件 ObjectId

        Returns:
            文件是否存在
        """
        try:
            if isinstance(file_id, str):
                file_id = ObjectId(file_id)

            return self.fs.exists(file_id)

        except Exception as e:
            logger.error(f"檢查文件存在失敗 (ID: {file_id}): {e}")
            return False

    def get_file_info(self, file_id: ObjectId) -> Optional[dict]:
        """
        獲取文件信息

        Args:
            file_id: 文件 ObjectId

        Returns:
            文件信息字典或 None
        """
        try:
            if isinstance(file_id, str):
                file_id = ObjectId(file_id)

            grid_out = self.fs.get(file_id)

            info = {
                'file_id': str(grid_out._id),
                'filename': grid_out.filename,
                'length': grid_out.length,
                'upload_date': grid_out.upload_date,
                'md5': grid_out.md5,
                'metadata': grid_out.metadata
            }

            return info

        except Exception as e:
            logger.error(f"獲取文件信息失敗 (ID: {file_id}): {e}")
            return None

    def close(self):
        """關閉連接"""
        if self.mongo_client:
            self.mongo_client.close()
            logger.info("分析服務 GridFS Handler 連接已關閉")