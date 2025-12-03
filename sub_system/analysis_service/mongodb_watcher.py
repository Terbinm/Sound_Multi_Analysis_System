# mongodb_watcher.py - MongoDB Change Stream 監聽器

import time
from typing import Callable, Optional
from pymongo.errors import PyMongoError
from config import SERVICE_CONFIG
from utils.logger import logger, analyze_uuid_context
from utils.mongodb_handler import MongoDBHandler


class MongoDBWatcher:
    """MongoDB Change Stream 監聽器"""
    
    def __init__(self, mongodb_handler: MongoDBHandler, 
                 callback: Callable[[dict], None]):
        """
        初始化監聽器
        
        Args:
            mongodb_handler: MongoDB 處理器
            callback: 當收到新記錄時的回調函數
        """
        self.mongodb = mongodb_handler
        self.callback = callback
        self.config = SERVICE_CONFIG
        self.is_running = False
        
        logger.info("MongoDB 監聽器初始化完成")
    
    def start(self):
        """開始監聽"""
        self.is_running = True
        
        if self.config['use_change_stream']:
            logger.info("使用 Change Stream 模式監聽 MongoDB")
            self._watch_with_change_stream()
        else:
            logger.info("使用輪詢模式監聽 MongoDB")
            self._watch_with_polling()
    
    def stop(self):
        """停止監聽"""
        self.is_running = False
        logger.info("MongoDB 監聽器已停止")
    
    def _watch_with_change_stream(self):
        """使用 Change Stream 監聽"""
        retry_count = 0
        max_retries = self.config['retry_attempts']
        
        while self.is_running:
            try:
                logger.info("開始監聽 Change Stream...")
                
                for change in self.mongodb.watch_changes():
                    if not self.is_running:
                        break
                    
                    # 處理變更事件
                    self._handle_change(change)
                    retry_count = 0  # 重置重試計數
                
            except PyMongoError as e:
                retry_count += 1
                logger.error(f"Change Stream 錯誤 (重試 {retry_count}/{max_retries}): {e}")
                
                if retry_count >= max_retries:
                    logger.error("達到最大重試次數，切換到輪詢模式")
                    self._watch_with_polling()
                    break
                
                # 等待後重試
                time.sleep(self.config['retry_delay'])
                
            except KeyboardInterrupt:
                logger.info("收到中斷信號，停止監聽")
                self.stop()
                break
                
            except Exception as e:
                logger.error(f"監聽過程異常: {e}")
                time.sleep(self.config['retry_delay'])
    
    def _watch_with_polling(self):
        """使用輪詢方式監聽"""
        logger.info(f"開始輪詢模式，間隔: {self.config['polling_interval']} 秒")
        
        processed_ids = set()
        
        while self.is_running:
            try:
                # 查找待處理記錄
                pending_records = self.mongodb.find_pending_records(limit=10)
                
                for record in pending_records:
                    record_id = str(record.get('_id'))
                    
                    # 避免重複處理
                    if record_id in processed_ids:
                        continue
                    
                    # 處理記錄
                    self.callback(record)
                    processed_ids.add(record_id)
                    
                    # 限制 processed_ids 大小
                    if len(processed_ids) > 1000:
                        processed_ids.clear()
                
                # 等待下一次輪詢
                time.sleep(self.config['polling_interval'])
                
            except KeyboardInterrupt:
                logger.info("收到中斷信號，停止輪詢")
                self.stop()
                break
                
            except Exception as e:
                logger.error(f"輪詢過程異常: {e}")
                time.sleep(self.config['retry_delay'])
    
    def _handle_change(self, change: dict):
        """
        處理 Change Stream 事件
        
        Args:
            change: 變更事件
        """
        try:
            operation_type = change.get('operationType')
            
            if operation_type == 'insert':
                # 新增記錄
                full_document = change.get('fullDocument')
                
                if full_document:
                    analyze_uuid = full_document.get('AnalyzeUUID', 'UNKNOWN')
                    with analyze_uuid_context(analyze_uuid):
                        logger.info(f"偵測到新記錄: {analyze_uuid}")
                    self.callback(full_document)
            
            # 可以根據需要處理其他操作類型（update, delete 等）
            
        except Exception as e:
            logger.error(f"處理變更事件失敗: {e}")
    
    def process_existing_records(self):
        """處理現有的待處理記錄（啟動時執行一次）"""
        try:
            logger.info("檢查現有待處理記錄...")
            pending_records = self.mongodb.find_pending_records(limit=100)
            
            if pending_records:
                logger.info(f"找到 {len(pending_records)} 筆待處理記錄")
                
                for record in pending_records:
                    self.callback(record)
            else:
                logger.info("沒有待處理記錄")
                
        except Exception as e:
            logger.error(f"處理現有記錄失敗: {e}")
