# main.py - 分析服務主程式

import signal
import sys
import threading
from queue import Queue
from typing import Dict, Any

from config import SERVICE_CONFIG
from utils.logger import logger, analyze_uuid_context
from utils.mongodb_handler import MongoDBHandler
from mongodb_watcher import MongoDBWatcher
from analysis_pipeline import AnalysisPipeline
from threading import Lock

import torchaudio
if not hasattr(torchaudio, "list_audio_backends"):
    torchaudio.list_audio_backends = lambda: ["sox_io"]



class AnalysisService:
    """分析服務主類別"""
    
    def __init__(self):
        """初始化服務"""
        self.is_running = False
        self.mongodb_handler = None
        self.watcher = None
        self.pipeline = None
        self.task_queue = Queue()
        self.worker_threads = []
        self.processing_records = set()  # 正在處理的記錄
        self.processing_lock = Lock()
        
        # 註冊信號處理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("=" * 60)
        logger.info("音訊分析服務初始化")
        logger.info("=" * 60)
    
    def _signal_handler(self, signum, frame):
        """處理終止信號"""
        logger.info(f"\n收到終止信號 ({signum})，正在關閉服務...")
        self.stop()
        sys.exit(0)
    
    def initialize(self):
        """初始化所有組件"""
        try:
            # 初始化 MongoDB
            logger.info("初始化 MongoDB 連接...")
            self.mongodb_handler = MongoDBHandler()
            
            # 初始化分析流程
            logger.info("初始化分析流程...")
            self.pipeline = AnalysisPipeline(self.mongodb_handler)
            
            # 初始化監聽器
            logger.info("初始化 MongoDB 監聽器...")
            self.watcher = MongoDBWatcher(
                self.mongodb_handler,
                self._on_new_record
            )
            
            logger.info("✓ 所有組件初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"✗ 初始化失敗: {e}")
            return False
    
    def start(self):
        """啟動服務"""
        if not self.initialize():
            logger.error("初始化失敗，服務無法啟動")
            return
        
        self.is_running = True
        
        try:
            # 啟動工作執行緒
            self._start_workers()
            
            # 處理現有記錄
            logger.info("處理現有待處理記錄...")
            self.watcher.process_existing_records()
            
            # 開始監聽
            logger.info("=" * 60)
            logger.info("服務啟動成功，開始監聽新記錄...")
            logger.info("按 Ctrl+C 停止服務")
            logger.info("=" * 60)
            
            self.watcher.start()
            
        except KeyboardInterrupt:
            logger.info("\n收到中斷信號")
            self.stop()
        except Exception as e:
            logger.error(f"服務運行異常: {e}")
            self.stop()
    
    def stop(self):
        """停止服務"""
        if not self.is_running:
            return
        
        logger.info("正在停止服務...")
        self.is_running = False
        
        # 停止監聽器
        if self.watcher:
            self.watcher.stop()
        
        # 等待工作執行緒完成
        logger.info("等待工作執行緒完成...")
        for thread in self.worker_threads:
            thread.join(timeout=5)
        
        # 清理資源
        if self.pipeline:
            self.pipeline.cleanup()
        
        if self.mongodb_handler:
            self.mongodb_handler.close()
        
        logger.info("服務已停止")
    
    def _on_new_record(self, record: Dict[str, Any]):
        """
        當收到新記錄時的回調
        
        Args:
            record: MongoDB 記錄
        """
        analyze_uuid = record.get('AnalyzeUUID', 'UNKNOWN')
        with analyze_uuid_context(analyze_uuid):
            try:
                logger.info(f"收到新記錄: {analyze_uuid}")
                
                # 將任務加入佇列
                self.task_queue.put(record)
                
            except Exception as e:
                logger.error(f"處理新記錄回調失敗: {e}")
    
    def _start_workers(self):
        """啟動工作執行緒"""
        max_workers = SERVICE_CONFIG['max_concurrent_tasks']
        
        logger.info(f"啟動 {max_workers} 個工作執行緒...")
        
        for i in range(max_workers):
            thread = threading.Thread(
                target=self._worker,
                name=f"Worker-{i+1}",
                daemon=True
            )
            thread.start()
            self.worker_threads.append(thread)

    def _worker(self):
        thread_name = threading.current_thread().name
        logger.info(f"{thread_name} 已啟動")

        while self.is_running:
            try:
                record = self.task_queue.get(timeout=1)
            except Exception:
                if self.is_running:  # 避免在關閉時記錄錯誤
                    continue  # Queue.Empty 是正常的，不需要記錄
                break

            analyze_uuid = record.get('AnalyzeUUID', 'UNKNOWN')

            with analyze_uuid_context(analyze_uuid):
                # ✅ 檢查是否已在處理
                with self.processing_lock:
                    if analyze_uuid in self.processing_records:
                        logger.info(f"{thread_name} 跳過重複記錄: {analyze_uuid}")
                        self.task_queue.task_done()
                        continue

                    self.processing_records.add(analyze_uuid)

                try:
                    logger.info(f"{thread_name} 開始處理: {analyze_uuid}")
                    success = self.pipeline.process_record(record)

                    if success:
                        logger.info(f"{thread_name} 處理成功: {analyze_uuid}")
                    else:
                        logger.error(f"{thread_name} 處理失敗: {analyze_uuid}")
                finally:
                    # ✅ 處理完成後移除
                    with self.processing_lock:
                        self.processing_records.discard(analyze_uuid)

                    self.task_queue.task_done()

        logger.info(f"{thread_name} 已停止")


def main():
    """主程式入口"""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║         音訊分析服務 - Analysis Service v1.1               ║
    ║                                                          ║
    ║  功能:                                                    ║
    ║  1. 監聽 MongoDB 新記錄                                    ║
    ║  2. 音訊切割 (Step 1)                                      ║
    ║  3. LEAF 特徵提取 (Step 2)                                 ║
    ║  4. 分類預測 (Step 3)                                      ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # 建立並啟動服務
    service = AnalysisService()
    service.start()


if __name__ == '__main__':
    main()
