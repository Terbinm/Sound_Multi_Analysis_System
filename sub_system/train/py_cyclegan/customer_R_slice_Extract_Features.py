# customer_R_Extract_Features_app.py
import logging
import os
import json
import shutil
import sys
import threading
import datetime
import time

import numpy
from flask import Flask, jsonify
import pika
from pymongo import MongoClient
from gridfs import GridFS
from bson import ObjectId
import rpy2.robjects as robjects
from rpy2.robjects.conversion import localconverter
from rpy2.robjects import default_converter,vectors
from rpy2.robjects import r as r_base
import config
app = Flask(__name__)

# MongoDB 連接
client = MongoClient(config.MONGO_URI)
db = client[config.MONGO_DB]


class AudioProcessor:
    def __init__(self, analyze_uuid):
        self.analyze_uuid = analyze_uuid
        self.temp_dir = None
        self.chunk_size = config.ANALYZE_CHUNK_SIZE
        self.max_retries = config.ANALYZE_MAX_RETRIES
        self.timeout = config.ANALYZE_TIMEOUT


    def setup_directories(self):
        """設置必要的目錄結構"""
        self.temp_dir = str(os.path.join(config.TEMP_DIR, self.analyze_uuid))
        directories = {
            'raw_wav': os.path.join(self.temp_dir, "raw_wav"),
            'csv_transform': os.path.join(self.temp_dir, "csv_transform"),
            'input_features': os.path.join(self.temp_dir, "input_features"),
            'raw_features': os.path.join(self.temp_dir, "raw_features")
        }

        for directory in directories.values():
            os.makedirs(directory, exist_ok=True)
        return directories

    def download_files(self, directories,download_file_type):
        """從 GridFS 下載所需文件"""
        analysis = db.analyses.find_one({"AnalyzeUUID": self.analyze_uuid})

        if not analysis or "files" not in analysis or download_file_type not in analysis["files"]:
            raise ValueError(f"No {download_file_type} audio file found")

        fs = GridFS(db)
        download_file_db = analysis["files"][download_file_type]

        # 讀取 GridFS 檔案資訊
        grid_file = fs.get(download_file_db["fileId"])
        file_size = grid_file.length

        # 檢查檔案大小
        if file_size > config.FILE_UPLOAD_MAX_SIZE:
            raise ValueError(f"File too large: {file_size} bytes")

        # 檢查副檔名
        file_ext = os.path.splitext(download_file_db['filename'])[1][1:].lower()
        if file_ext not in config.ALLOWED_EXTENSIONS:
            raise ValueError(f"Invalid file type: {file_ext}")

        logger.debug(f"File info - Name: {download_file_db['filename']}, Size: {file_size} bytes")

        # 下載檔案
        with open(os.path.join(directories[download_file_type], download_file_db['filename']), 'wb') as f:
            f.write(grid_file.read())

    def setup_r_environment(self, directories):
        """配置R環境和參數"""
        try:
            with localconverter(default_converter):
                # 從 MongoDB 獲取之前的 Function.Step3.2 數據
                analysis = db.analyses.find_one({"AnalyzeUUID": self.analyze_uuid})
                step1_data = next((step for step in analysis.get("analyze_features", [])
                                   if step["features_step"] == 1), None)

                if not step1_data or not step1_data.get("features_data"):
                    raise ValueError("Previous step data not found")

                # 拿長度
                # data_length = len(step1_data["features_data"])

                data_vectors = {
                    "equID": vectors.FloatVector([row["equID"] for row in step1_data["features_data"]]),
                    "faultID": vectors.StrVector([row["faultID"] for row in step1_data["features_data"]]),
                    "faultValue": vectors.FloatVector([row["faultValue"] for row in step1_data["features_data"]]),
                    "sound.files": vectors.StrVector([row["sound.files"] for row in step1_data["features_data"]]),
                    "channel": vectors.FloatVector([row["channel"] for row in step1_data["features_data"]]),
                    "selec": vectors.IntVector([row["selec"] for row in step1_data["features_data"]]),
                    "start": vectors.FloatVector([row["start"] for row in step1_data["features_data"]]),
                    "end": vectors.FloatVector([row["end"] for row in step1_data["features_data"]]),
                    "bottom.freq": vectors.FloatVector([row["bottom.freq"] for row in step1_data["features_data"]]),
                    "top.freq": vectors.FloatVector([row["top.freq"] for row in step1_data["features_data"]])
                }

                # 建立 data.frame
                r_df = robjects.DataFrame({
                    "equID": data_vectors["equID"],
                    "faultID": data_vectors["faultID"],
                    "faultValue": data_vectors["faultValue"],
                    "sound.files": data_vectors["sound.files"],
                    "channel": data_vectors["channel"],
                    "selec": data_vectors["selec"],
                    "start": data_vectors["start"],
                    "end": data_vectors["end"],
                    "bottom.freq": data_vectors["bottom.freq"],
                    "top.freq": data_vectors["top.freq"]
                })

                # 将 DataFrame 送給 R
                robjects.r.assign("flt_table1", r_df)

                # 將數據填入 data.frame
                for col_name, values in data_vectors.items():
                    robjects.r.assign(f"temp_{col_name}", values)
                    robjects.r(f'flt_table1${col_name} <- temp_{col_name}')


                ### 必要區域
                # 設置其他 R 選項
                motor_options = robjects.ListVector({
                    'work.case': 3,
                    'max.records': 50,
                    'curr.frame.dur': 60,
                    'curr.skip.dur': 40,
                    'curr.frame.start': 1
                })

                analyze_options = robjects.ListVector({
                    'analyze.data.root': self.temp_dir,
                    'raw.wav.dir': directories['raw_wav'],
                    'transformed.wav.dir': directories['csv_transform'],
                    'raw.features.dir': directories['raw_features'],
                    'analyze_ID': self.analyze_uuid
                })

                control_bar = robjects.ListVector({
                    'enable_auto_path_set': True,
                    'enable_Proofread': False,
                    'enable_cat_info': True
                })

                # 設置R變數
                robjects.r.assign("MotorOptions", motor_options)
                robjects.r.assign("AnalyzOptions", analyze_options)
                robjects.r.assign("control_bar", control_bar)
        except Exception as e:
                raise Exception(f"Error setup R environment: {str(e)}")


    def execute_r_analysis(self):
        """執行R分析腳本"""
        with localconverter(default_converter):
            try:
                robjects.r.source("util_Analyze.R")
                robjects.r.source("util.R")
                robjects.r.source("3.3EF_lite.R")
            except Exception as e:
                raise Exception(f"Error executing R scripts: {str(e)}")

    def read_json_results(self, directories):
        """讀取分析結果"(by json)"""
        results_path = os.path.join(directories['raw_features'], f"{self.analyze_uuid}.json")
        if not os.path.exists(results_path):
            raise FileNotFoundError("Analysis results not found")

        with open(results_path, 'r') as f:
            return json.load(f)

    # def upload_csv_transform(self, directories):
    #     """上傳轉換後的音頻檔案到 GridFS"""
    #     try:
    #         # 取得轉換後的檔案路徑
    #         transformed_dir = directories['csv_transform']
    #         files = os.listdir(transformed_dir)
    #
    #         if not files:
    #             raise ValueError("No transformed files found in directory")
    #
    #         # 通常應該只有一個檔案
    #         transformed_file = files[0]
    #         file_path = os.path.join(transformed_dir, transformed_file)
    #
    #         # 準備檔案資訊
    #         fs = GridFS(db)
    #
    #         # 讀取並上傳檔案到 GridFS
    #         with open(file_path, 'rb') as f:
    #             file_id = fs.put(
    #                 f.read(),
    #                 filename=transformed_file,
    #                 metadata={
    #                     "AnalyzeUUID": self.analyze_uuid,
    #                     "created_at": datetime.datetime.utcnow()
    #                 }
    #             )
    #
    #         # 更新 MongoDB 中的文件資訊
    #         file_info = {
    #             "fileId": file_id,
    #             "filename": transformed_file,
    #             "type": transformed_file.split('.')[-1].lower()
    #         }
    #
    #         db.analyses.update_one(
    #             {"AnalyzeUUID": self.analyze_uuid},
    #             {
    #                 "$set": {
    #                     "files.csv_transform": file_info
    #                 }
    #             }
    #         )
    #
    #         return file_info
    #
    #     except Exception as e:
    #         raise Exception(f"Error uploading transformed file: {str(e)}")

    def extract_r_list_results(self,R_objects):
        """從 R 環境中提取分析結果，逐行處理表格數據"""
        try:
            with localconverter(default_converter):
                r_data = robjects.r[R_objects]

                if r_data is None:
                    raise ValueError(f"No data found in {R_objects}")

                # 獲取col
                colnames = list(r_data.names)

                # 將R數據框轉換為列表格式，每個元素是一行數據的字典
                result_list = []
                nrows = len(r_data[0])  # 獲取行數

                for row in range(nrows):
                    row_dict = {}
                    for col in colnames:
                        value = r_data.rx2(col)[row]

                        # 根據數據類型進行轉換
                        if isinstance(value, (float, numpy.float64)):
                            row_dict[col] = float(value)
                        elif isinstance(value, (int, numpy.integer)):
                            row_dict[col] = int(value)
                        elif isinstance(value, str):
                            row_dict[col] = str(value)
                        else:
                            row_dict[col] = str(value)

                    result_list.append(row_dict)

                return result_list

        except Exception as e:
            raise Exception(f"Error extracting R results: {str(e)}")

    def process(self):
        """執行完整的處理流程"""
        try:
            directories = self.setup_directories()
            self.download_files(directories,download_file_type='csv_transform')
            self.setup_r_environment(directories)
            self.execute_r_analysis()
            results = self.extract_r_list_results(R_objects='flt_feature1')

            return results

        except Exception as e:
            raise Exception(f"Processing error: {str(e)}")

        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)


def initialize_r_environment():
    """
    初始化 R 環境並安裝必要的套件
    這個函數會在程式啟動時執行，確保所有需要的 R 套件都已正確安裝
    """
    try:
        # 獲取 install_r_packages.R 的完整路徑
        current_dir = os.path.dirname(os.path.abspath(__file__))
        install_script_path = os.path.join(current_dir, 'install_r_packages.R')

        # 確認檔案存在
        if not os.path.exists(install_script_path):
            raise FileNotFoundError(f"找不到套件安裝腳本：{install_script_path}")

        logger.info("開始執行 R 套件安裝程序...")

        # 執行 R 腳本
        r_base.source(install_script_path)

        logger.info("R 套件安裝完成")
        return True

    except Exception as e:
        logger.error(f"R 環境初始化失敗：{str(e)}")
        raise


def process_audio(analyze_uuid):
    """處理音頻分析的主要函數"""
    try:
        # 更新任務狀態為處理中
        db.analyses.update_one(
            {"AnalyzeUUID": analyze_uuid},
            {
                "$set": {
                    "analyze_features.$[elem].features_state": "processing",
                    "analyze_features.$[elem].started_at": datetime.datetime.utcnow()
                }
            },
            array_filters=[{"elem.features_step": config.THE_STEP}]
        )

        logger.info(f"Starting processing for {analyze_uuid}")

        # 執行處理
        processor = AudioProcessor(analyze_uuid)
        results = processor.process()

        logger.info(f"Processing completed for {analyze_uuid}")

        # 更新處理結果
        db.analyses.update_one(
            {"AnalyzeUUID": analyze_uuid},
            {
                "$set": {
                    "analyze_features.$[elem].features_state": "completed",
                    "analyze_features.$[elem].features_data": results,
                    "analyze_features.$[elem].completed_at": datetime.datetime.utcnow()
                }
            },
            array_filters=[{"elem.features_step": config.THE_STEP}]
        )

        # 發送處理完成通知
        send_completion_notification(analyze_uuid)

    except Exception as e:
        error_message = str(e)
        logger.error(f"Error in process_audio: {error_message}")
        db.analyses.update_one(
            {"AnalyzeUUID": analyze_uuid},
            {
                "$set": {
                    "analyze_features.$[elem].features_state": "error",
                    "analyze_features.$[elem].error_message": error_message
                }
            },
            array_filters=[{"elem.features_step": config.THE_STEP}]
        )


def send_completion_notification(analyze_uuid):
    """發送完成通知到RabbitMQ"""
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=config.RABBITMQ_HOST,
                port=config.RABBITMQ_PORT,
                virtual_host=config.RABBITMQ_VHOST,
                credentials=pika.PlainCredentials(
                    config.RABBITMQ_USER,
                    config.RABBITMQ_PASS
                )
            )
        )
        channel = connection.channel()

        message = {
            "AnalyzeUUID": analyze_uuid,
            "step": config.THE_STEP,
            "status": "completed",
            "timestamp": datetime.datetime.utcnow().isoformat()
        }

        channel.basic_publish(
            exchange=config.EXCHANGE_NAME,
            routing_key='analyze.state.check',
            body=json.dumps(message)
        )

        connection.close()
    except Exception as e:
        logger.info(f"Error sending notification: {str(e)}")


def callback(ch, method, properties, body):
    """處理接收到的消息"""
    try:
        logger.info(f"Received message: {body}")
        message = json.loads(body)
        analyze_uuid = message.get('AnalyzeUUID')

        if analyze_uuid:
            logger.info(f"Processing analyze_uuid: {analyze_uuid}")
            analysis = db.analyses.find_one({"AnalyzeUUID": analyze_uuid})
            if analysis and analysis.get('AnalyzeState') == 'registered':
                # 直接在當前線程執行，避免多線程問題
                process_audio(analyze_uuid)
            else:
                logger.warning(f"Analysis not found or not in registered state: {analyze_uuid}")

        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        ch.basic_nack(delivery_tag=method.delivery_tag)


def start_consuming():
    """開始監聽消息隊列"""
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=config.RABBITMQ_HOST,
                    port=config.RABBITMQ_PORT,
                    virtual_host=config.RABBITMQ_VHOST,
                    credentials=pika.PlainCredentials(
                        config.RABBITMQ_USER,
                        config.RABBITMQ_PASS
                    )
                )
            )
            channel = connection.channel()

            channel.exchange_declare(
                exchange=config.EXCHANGE_NAME,
                exchange_type='direct',
                durable=True
            )

            channel.queue_declare(queue=config.QUEUE_NAME, durable=True)
            channel.queue_bind(
                exchange=config.EXCHANGE_NAME,
                queue=config.QUEUE_NAME,
                routing_key=config.ROUTING_KEY
            )

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=config.QUEUE_NAME,
                on_message_callback=callback
            )

            logger.info(f" [*] Waiting for messages in {config.QUEUE_NAME}")
            channel.start_consuming()
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            time.sleep(1)  # 等待5秒後重試


@app.route('/health', methods=['GET'])
def health_check():
    """健康檢查端點"""

    return jsonify({
        "status": "healthy",
        "version": config.SERVER_VISION,
        "server_name": config.SERVER_NAME,
        "instance_id": config.INSTANCE_ID,
        "queues": config.QUEUE_NAME
    })


if __name__ == '__main__':
    # 設定基本的日誌配置
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format=config.LOG_FORMAT
    )
    logger = logging.getLogger(__name__)

    try:
        # 初始化 R 環境
        initialize_r_environment()

        # 在背景線程中啟動消息監聽
        consumer_thread = threading.Thread(target=start_consuming)
        consumer_thread.daemon = True
        consumer_thread.start()

        # 啟動 Flask 應用
        app.run(
            host=config.FLASK_HOST,
            port=config.FLASK_PORT,
            debug=config.DEBUG,
            use_reloader=False
        )
    except Exception as e:
        logger.error(f"程式啟動失敗：{str(e)}")
        sys.exit(1)