"""
MongoDB Fixtures for Testing

Provides fixtures for:
- MongoDBHandler mocking
- MultiMongoDBHandler mocking
- Sample data collections
- GridFS fixtures
"""
import pytest
from typing import Dict, Any, List, Generator
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone

from CI_test.mocks.mock_mongodb import (
    MockMongoClient,
    MockDatabase,
    MockCollection,
    MockGridFS,
    MockGridFSBucket,
)


@pytest.fixture
def mock_mongodb_handler(mock_mongo_client: MockMongoClient) -> Generator[MagicMock, None, None]:
    """
    Mock MongoDBHandler singleton

    Usage:
        def test_something(mock_mongodb_handler):
            # mock_mongodb_handler is ready to use
            collection = mock_mongodb_handler.get_collection('test')
    """
    handler = MagicMock()
    handler._client = mock_mongo_client
    handler._db = mock_mongo_client['test_database']

    def get_collection(name: str):
        return handler._db[name]

    def get_database():
        return handler._db

    handler.get_collection = get_collection
    handler.get_database = get_database
    handler.close = MagicMock()

    # Patch the singleton
    with patch('core.state_management.utils.mongodb_handler.MongoDBHandler._instance', handler):
        with patch('core.state_management.utils.mongodb_handler.MongoDBHandler.get_instance', return_value=handler):
            yield handler


@pytest.fixture
def mock_multi_mongodb_handler(mock_mongo_client: MockMongoClient) -> Generator[MagicMock, None, None]:
    """
    Mock MultiMongoDBHandler for multiple instance connections

    Usage:
        def test_multi_instance(mock_multi_mongodb_handler):
            db = mock_multi_mongodb_handler.connect('instance_id', config)
    """
    handler = MagicMock()
    handler._connections = {}

    def connect(instance_id: str, instance_config: Dict[str, Any]):
        client = MockMongoClient(
            host=instance_config.get('host', 'localhost'),
            port=instance_config.get('port', 27017)
        )
        handler._connections[instance_id] = client
        db_name = instance_config.get('database', 'test_db')
        return client[db_name]

    def get_connection(instance_id: str):
        return handler._connections.get(instance_id)

    def disconnect(instance_id: str):
        if instance_id in handler._connections:
            handler._connections[instance_id].close()
            del handler._connections[instance_id]

    def disconnect_all():
        for client in handler._connections.values():
            client.close()
        handler._connections.clear()

    handler.connect = connect
    handler.get_connection = get_connection
    handler.disconnect = disconnect
    handler.disconnect_all = disconnect_all

    yield handler

    # Cleanup
    handler.disconnect_all()


@pytest.fixture
def sample_collection_data() -> Dict[str, List[Dict[str, Any]]]:
    """
    Sample data for various collections

    Returns a dictionary with collection names as keys and lists of documents as values
    """
    now = datetime.now(timezone.utc)

    return {
        'users': [
            {
                '_id': 'user-001',
                'username': 'admin',
                'email': 'admin@example.com',
                'password_hash': 'hashed_admin_password',
                'role': 'admin',
                'is_active': True,
                'created_at': now,
            },
            {
                '_id': 'user-002',
                'username': 'test_user',
                'email': 'test@example.com',
                'password_hash': 'hashed_user_password',
                'role': 'user',
                'is_active': True,
                'created_at': now,
            },
        ],
        'analysis_configs': [
            {
                '_id': 'config-001',
                'config_id': 'config-001',
                'config_name': 'Audio Classification',
                'analysis_method_id': 'audio_classification',
                'parameters': {
                    'slice_duration': 10.0,
                    'overlap': 0.5,
                },
                'model_files': {
                    'classification_method': 'onnx',
                    'onnx_model': {
                        'file_id': 'model-001',
                        'filename': 'classifier.onnx',
                    },
                },
                'enabled': True,
                'is_system': False,
                'created_at': now,
            },
        ],
        'routing_rules': [
            {
                '_id': 'rule-001',
                'rule_id': 'rule-001',
                'rule_name': 'Default Rule',
                'conditions': {'device_id': {'$regex': '.*'}},
                'target_config_id': 'config-001',
                'priority': 100,
                'enabled': True,
                'created_at': now,
            },
        ],
        'mongodb_instances': [
            {
                '_id': 'default',
                'instance_id': 'default',
                'instance_name': 'Default Instance',
                'host': 'localhost',
                'port': 27017,
                'database': 'sound_analysis',
                'collection': 'recordings',
                'enabled': True,
                'is_system': True,
                'created_at': now,
            },
        ],
        'edge_devices': [
            {
                '_id': 'device-001',
                'device_id': 'device-001',
                'device_name': 'Test Device',
                'platform': 'win32',
                'status': 'online',
                'last_heartbeat': now,
                'registered_at': now,
            },
        ],
        'recordings': [
            {
                '_id': 'rec-001',
                'recording_uuid': 'uuid-001',
                'device_id': 'device-001',
                'filename': 'recording_001.wav',
                'file_size': 320000,
                'duration': 10.0,
                'upload_status': 'completed',
                'analysis_status': 'pending',
                'created_at': now,
            },
        ],
        'node_status': [
            {
                '_id': 'node-001',
                'node_id': 'node-001',
                'capabilities': ['audio_classification'],
                'status': 'active',
                'current_tasks': 0,
                'max_tasks': 4,
                'last_heartbeat': now,
            },
        ],
    }


@pytest.fixture
def populated_mock_database(
    mock_mongo_client: MockMongoClient,
    sample_collection_data: Dict[str, List[Dict[str, Any]]]
) -> MockDatabase:
    """
    Create a mock database populated with sample data

    Usage:
        def test_with_data(populated_mock_database):
            users = populated_mock_database['users']
            user = users.find_one({'username': 'admin'})
    """
    db = mock_mongo_client['test_database']

    for collection_name, documents in sample_collection_data.items():
        collection = db[collection_name]
        for doc in documents:
            collection.insert_one(doc)

    return db


@pytest.fixture
def mock_gridfs_handler(mock_database: MockDatabase) -> MockGridFS:
    """
    Mock GridFS handler

    Usage:
        def test_file_upload(mock_gridfs_handler):
            file_id = mock_gridfs_handler.put(b'content', filename='test.wav')
    """
    return MockGridFS(mock_database)


@pytest.fixture
def mock_gridfs_bucket(mock_database: MockDatabase) -> MockGridFSBucket:
    """
    Mock GridFS Bucket (newer API)

    Usage:
        def test_file_upload_bucket(mock_gridfs_bucket):
            file_id = mock_gridfs_bucket.upload_from_stream('test.wav', b'content')
    """
    return MockGridFSBucket(mock_database)


@pytest.fixture
def sample_wav_content() -> bytes:
    """
    Generate sample WAV file content

    Returns minimal valid WAV file bytes
    """
    import struct

    sample_rate = 16000
    duration = 1.0
    num_samples = int(sample_rate * duration)

    # WAV header
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + num_samples * 2,
        b'WAVE',
        b'fmt ',
        16,  # Subchunk1 size
        1,   # PCM
        1,   # Mono
        sample_rate,
        sample_rate * 2,
        2,   # Block align
        16,  # Bits per sample
        b'data',
        num_samples * 2,
    )

    # Silent audio
    audio_data = bytes(num_samples * 2)

    return header + audio_data


@pytest.fixture
def gridfs_with_sample_files(
    mock_gridfs_handler: MockGridFS,
    sample_wav_content: bytes
) -> MockGridFS:
    """
    GridFS populated with sample files

    Usage:
        def test_file_download(gridfs_with_sample_files):
            gfs_file = gridfs_with_sample_files.get_last_version('sample.wav')
    """
    # Add sample files
    mock_gridfs_handler.put(sample_wav_content, filename='sample.wav', metadata={'type': 'audio'})
    mock_gridfs_handler.put(b'{"test": "config"}', filename='config.json', metadata={'type': 'config'})
    mock_gridfs_handler.put(b'model binary content', filename='model.onnx', metadata={'type': 'model'})

    return mock_gridfs_handler
