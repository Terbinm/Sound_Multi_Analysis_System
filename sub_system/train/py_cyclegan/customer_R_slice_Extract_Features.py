
# customer_R_Extract_Features_app.py
import logging
import os
import json
import shutil
import sys
import threading
import datetime
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy
from flask import Flask, jsonify
import pika
from pymongo import MongoClient
from gridfs import GridFS
from bson import ObjectId
import rpy2.robjects as robjects
from rpy2.robjects.conversion import localconverter
from rpy2.robjects import default_converter, vectors
from rpy2.robjects import r as r_base

from config import (
    MONGODB_CONFIG,
    RABBITMQ_CONFIG,
    WORKER_CONFIG,
    FILE_STORAGE_CONFIG,
    PROCESSING_STEP_CONFIG,
    SERVER_METADATA,
    FLASK_CONFIG,
    SERVICE_LOGGING_CONFIG,
)
from utils.mongo_helpers import (
    build_step_update_path,
    find_step_across_runs,
)

app = Flask(__name__)

mongo_client = MongoClient(MONGODB_CONFIG['uri'])
mongo_db = mongo_client[MONGODB_CONFIG['database']]
recordings_col = mongo_db[MONGODB_CONFIG['collection']]
grid_fs = GridFS(mongo_db)

TARGET_STEP = PROCESSING_STEP_CONFIG['target_step']

logger = logging.getLogger(__name__)


class AudioProcessor:
    def __init__(self, analyze_uuid: str):
        self.analyze_uuid = analyze_uuid
        self.temp_dir: Optional[str] = None
        self.chunk_size = WORKER_CONFIG['chunk_size']
        self.max_retries = WORKER_CONFIG['max_retries']
        self.timeout = WORKER_CONFIG['timeout_seconds']

    def setup_directories(self) -> Dict[str, str]:
        base_dir = Path(FILE_STORAGE_CONFIG['temp_dir']) / self.analyze_uuid
        directories = {
            'raw_wav': base_dir / 'raw_wav',
            'csv_transform': base_dir / 'csv_transform',
            'input_features': base_dir / 'input_features',
            'raw_features': base_dir / 'raw_features',
        }
        for path_obj in directories.values():
            path_obj.mkdir(parents=True, exist_ok=True)
        self.temp_dir = str(base_dir)
        return {key: str(value) for key, value in directories.items()}

    def _normalize_file_id(self, file_id: Any) -> ObjectId:
        if isinstance(file_id, ObjectId):
            return file_id
        if isinstance(file_id, dict) and '$oid' in file_id:
            return ObjectId(file_id['$oid'])
        return ObjectId(file_id)

    def download_files(self, directories: Dict[str, str], download_file_type: str):
        record = recordings_col.find_one({'AnalyzeUUID': self.analyze_uuid})
        files = (record or {}).get('files', {}) or {}
        if download_file_type not in files:
            raise ValueError(f'Missing file type: {download_file_type}')
        file_meta = files[download_file_type]
        file_id = self._normalize_file_id(file_meta['fileId'])
        grid_file = grid_fs.get(file_id)
        if grid_file.length > FILE_STORAGE_CONFIG['upload_limit_bytes']:
            raise ValueError('File too large')
        file_ext = os.path.splitext(file_meta['filename'])[1][1:].lower()
        if file_ext not in FILE_STORAGE_CONFIG['allowed_extensions']:
            raise ValueError('Invalid file type')
        target_path = Path(directories[download_file_type]) / file_meta['filename']
        with open(target_path, 'wb') as handle:
            handle.write(grid_file.read())

    def setup_r_environment(self, directories: Dict[str, str]):
        with localconverter(default_converter):
            record = recordings_col.find_one({'AnalyzeUUID': self.analyze_uuid})
            if not record:
                raise ValueError('Record not found')
            step_doc, _ = find_step_across_runs(record, step_order=1, require_completed=True)
            if not step_doc or not step_doc.get('features_data'):
                raise ValueError('Missing Step 1 data')
            data_vectors = {
                'equID': vectors.FloatVector([row['equID'] for row in step_doc['features_data']]),
                'faultID': vectors.StrVector([row['faultID'] for row in step_doc['features_data']]),
                'faultValue': vectors.FloatVector([row['faultValue'] for row in step_doc['features_data']]),
                'sound.files': vectors.StrVector([row['sound.files'] for row in step_doc['features_data']]),
                'channel': vectors.FloatVector([row['channel'] for row in step_doc['features_data']]),
                'selec': vectors.IntVector([row['selec'] for row in step_doc['features_data']]),
                'start': vectors.FloatVector([row['start'] for row in step_doc['features_data']]),
                'end': vectors.FloatVector([row['end'] for row in step_doc['features_data']]),
                'bottom.freq': vectors.FloatVector([row['bottom.freq'] for row in step_doc['features_data']]),
                'top.freq': vectors.FloatVector([row['top.freq'] for row in step_doc['features_data']]),
            }
            r_df = robjects.DataFrame({
                'equID': data_vectors['equID'],
                'faultID': data_vectors['faultID'],
                'faultValue': data_vectors['faultValue'],
                'sound.files': data_vectors['sound.files'],
                'channel': data_vectors['channel'],
                'selec': data_vectors['selec'],
                'start': data_vectors['start'],
                'end': data_vectors['end'],
                'bottom.freq': data_vectors['bottom.freq'],
                'top.freq': data_vectors['top.freq'],
            })
            robjects.r.assign('flt_table1', r_df)
            for col_name, values in data_vectors.items():
                robjects.r.assign(f'temp_{col_name}', values)
                robjects.r(f'flt_table1${col_name} <- temp_{col_name}')
            motor_options = robjects.ListVector({
                'work.case': 3,
                'max.records': 50,
                'curr.frame.dur': 60,
                'curr.skip.dur': 40,
                'curr.frame.start': 1,
            })
            analyze_options = robjects.ListVector({
                'analyze.data.root': self.temp_dir,
                'raw.wav.dir': directories['raw_wav'],
                'transformed.wav.dir': directories['csv_transform'],
                'raw.features.dir': directories['raw_features'],
                'analyze_ID': self.analyze_uuid,
            })
            control_bar = robjects.ListVector({
                'enable_auto_path_set': True,
                'enable_Proofread': False,
                'enable_cat_info': True,
            })
            robjects.r.assign('MotorOptions', motor_options)
            robjects.r.assign('AnalyzOptions', analyze_options)
            robjects.r.assign('control_bar', control_bar)

    def execute_r_analysis(self):
        with localconverter(default_converter):
            robjects.r.source('util_Analyze.R')
            robjects.r.source('util.R')
            robjects.r.source('3.3EF_lite.R')

    def extract_r_list_results(self, r_object: str) -> List[Dict[str, Any]]:
        with localconverter(default_converter):
            r_data = robjects.globalenv.get(r_object)
            colnames = list(r_data.names)
            result_list: List[Dict[str, Any]] = []
            nrows = len(r_data[0])
            for row in range(nrows):
                row_dict: Dict[str, Any] = {}
                for col in colnames:
                    value = r_data.rx2(col)[row]
                    if isinstance(value, (float, numpy.floating)):
                        row_dict[col] = float(value)
                    elif isinstance(value, (int, numpy.integer)):
                        row_dict[col] = int(value)
                    else:
                        row_dict[col] = str(value)
                result_list.append(row_dict)
            return result_list

    def process(self) -> List[Dict[str, Any]]:
        directories = self.setup_directories()
        try:
            self.download_files(directories, download_file_type='csv_transform')
            self.setup_r_environment(directories)
            self.execute_r_analysis()
            return self.extract_r_list_results('flt_feature1')
        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)


def initialize_r_environment():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    install_script_path = os.path.join(current_dir, 'install_r_packages.R')
    if not os.path.exists(install_script_path):
        raise FileNotFoundError('install_r_packages.R not found')
    r_base.source(install_script_path)


def select_run_id(record: Dict[str, Any]) -> Optional[str]:
    analyze_features = record.get('analyze_features', {}) or {}
    if isinstance(analyze_features, dict):
        for key in ('active_analysis_id', 'latest_analysis_id'):
            run_id = analyze_features.get(key)
            if run_id:
                return str(run_id)
        runs = analyze_features.get('runs')
        if isinstance(runs, dict) and runs:
            return str(next(iter(runs.keys())))
        if isinstance(runs, list) and runs:
            run_id = runs[0].get('analysis_id')
            if run_id:
                return str(run_id)
    return None


def resolve_step_context(analyze_uuid: str) -> Tuple[Dict[str, Any], str, str]:
    record = recordings_col.find_one({'AnalyzeUUID': analyze_uuid})
    if not record:
        raise ValueError('record not found')
    step_doc, run_id = find_step_across_runs(record, step_order=TARGET_STEP, require_completed=False)
    if not run_id:
        run_id = select_run_id(record)
    if not run_id:
        raise ValueError('unable to resolve run id')
    step_label = None
    if step_doc:
        step_label = step_doc.get('step_name') or step_doc.get('features_name')
    if not step_label:
        step_label = f'Step {TARGET_STEP}'
    update_path = build_step_update_path(run_id, step_label)
    if not step_doc:
        base_doc = {
            'display_order': TARGET_STEP,
            'step_name': step_label,
            'features_state': 'pending',
            'features_data': [],
            'processor_metadata': {},
            'error_message': None,
            'started_at': None,
            'completed_at': None,
        }
        recordings_col.update_one({'AnalyzeUUID': analyze_uuid}, {'$set': {update_path: base_doc}})
    return record, run_id, update_path


def process_audio(analyze_uuid: str):
    update_path: Optional[str] = None
    run_id: Optional[str] = None
    try:
        _, run_id, update_path = resolve_step_context(analyze_uuid)
        now = datetime.datetime.utcnow()
        recordings_col.update_one(
            {'AnalyzeUUID': analyze_uuid},
            {'$set': {
                f'{update_path}.features_state': 'processing',
                f'{update_path}.started_at': now,
                f'{update_path}.error_message': None,
                'analysis_status': 'processing',
            }}
        )
        processor = AudioProcessor(analyze_uuid)
        results = processor.process()
        recordings_col.update_one(
            {'AnalyzeUUID': analyze_uuid},
            {'$set': {
                f'{update_path}.features_state': 'completed',
                f'{update_path}.features_data': results,
                f'{update_path}.completed_at': datetime.datetime.utcnow(),
                f'{update_path}.error_message': None,
                'analysis_status': 'completed',
            }}
        )
        send_completion_notification(analyze_uuid, run_id)
    except Exception as exc:
        logger.exception('process_audio error: %s', exc)
        if update_path:
            recordings_col.update_one(
                {'AnalyzeUUID': analyze_uuid},
                {'$set': {
                    f'{update_path}.features_state': 'error',
                    f'{update_path}.error_message': str(exc),
                    'analysis_status': 'error',
                }}
            )


def send_completion_notification(analyze_uuid: str, run_id: Optional[str]):
    try:
        credentials = pika.PlainCredentials(
            RABBITMQ_CONFIG['username'],
            RABBITMQ_CONFIG['password'],
        )
        parameters = pika.ConnectionParameters(
            host=RABBITMQ_CONFIG['host'],
            port=RABBITMQ_CONFIG['port'],
            virtual_host=RABBITMQ_CONFIG['virtual_host'],
            credentials=credentials,
            heartbeat=RABBITMQ_CONFIG.get('heartbeat'),
            blocked_connection_timeout=RABBITMQ_CONFIG.get('blocked_connection_timeout'),
        )
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        message = {
            'AnalyzeUUID': analyze_uuid,
            'run_id': run_id,
            'step': TARGET_STEP,
            'status': 'completed',
            'timestamp': datetime.datetime.utcnow().isoformat(),
        }
        channel.basic_publish(
            exchange=RABBITMQ_CONFIG['exchange'],
            routing_key=RABBITMQ_CONFIG['routing_key'],
            body=json.dumps(message),
        )
        connection.close()
    except Exception as exc:
        logger.warning('send_completion_notification error: %s', exc)


def callback(ch, method, properties, body):
    try:
        message = json.loads(body)
        analyze_uuid = message.get('AnalyzeUUID')
        if not analyze_uuid:
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
        record = recordings_col.find_one({'AnalyzeUUID': analyze_uuid})
        if record and record.get('analysis_status', 'registered') == 'registered':
            logger.info('processing %s', analyze_uuid)
            process_audio(analyze_uuid)
        else:
            logger.warning('record %s not found or not registered', analyze_uuid)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        logger.exception('callback error: %s', exc)
        ch.basic_nack(delivery_tag=method.delivery_tag)


def start_consuming():
    while True:
        try:
            credentials = pika.PlainCredentials(
                RABBITMQ_CONFIG['username'],
                RABBITMQ_CONFIG['password'],
            )
            parameters = pika.ConnectionParameters(
                host=RABBITMQ_CONFIG['host'],
                port=RABBITMQ_CONFIG['port'],
                virtual_host=RABBITMQ_CONFIG['virtual_host'],
                credentials=credentials,
                heartbeat=RABBITMQ_CONFIG.get('heartbeat'),
                blocked_connection_timeout=RABBITMQ_CONFIG.get('blocked_connection_timeout'),
            )
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.exchange_declare(
                exchange=RABBITMQ_CONFIG['exchange'],
                exchange_type='direct',
                durable=True,
            )
            channel.queue_declare(queue=RABBITMQ_CONFIG['queue'], durable=True)
            channel.queue_bind(
                exchange=RABBITMQ_CONFIG['exchange'],
                queue=RABBITMQ_CONFIG['queue'],
                routing_key=RABBITMQ_CONFIG['routing_key'],
            )
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=RABBITMQ_CONFIG['queue'],
                on_message_callback=callback,
            )
            logger.info('[*] waiting for messages in %s', RABBITMQ_CONFIG['queue'])
            channel.start_consuming()
        except Exception as exc:
            logger.error('connection error: %s', exc)
            time.sleep(1)


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'version': SERVER_METADATA['server_version'],
        'server_name': SERVER_METADATA['server_name'],
        'instance_id': SERVER_METADATA['instance_id'],
        'queue': RABBITMQ_CONFIG['queue'],
    })


if __name__ == '__main__':
    logging.basicConfig(
        level=getattr(logging, SERVICE_LOGGING_CONFIG['level'], logging.INFO),
        format=SERVICE_LOGGING_CONFIG['format'],
    )
    logger = logging.getLogger(__name__)
    try:
        initialize_r_environment()
        consumer_thread = threading.Thread(target=start_consuming, daemon=True)
        consumer_thread.start()
        app.run(
            host=FLASK_CONFIG['host'],
            port=FLASK_CONFIG['port'],
            debug=FLASK_CONFIG['debug'],
            use_reloader=False,
        )
    except Exception as exc:
        logger.error('application error: %s', exc)
        sys.exit(1)
