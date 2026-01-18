"""
State Management Test Configuration

Fixtures specific to state_management module testing
"""
import os
import sys
import pytest
from typing import Generator, Dict, Any
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# Add project paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE_MGMT_PATH = os.path.join(PROJECT_ROOT, 'core', 'state_management')
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, STATE_MGMT_PATH)

# Create mock modules to avoid import errors
_mock_mongodb_handler = MagicMock()
_mock_rabbitmq_handler = MagicMock()
_mock_utils = MagicMock()
_mock_utils.mongodb_handler = _mock_mongodb_handler
_mock_utils.rabbitmq_handler = _mock_rabbitmq_handler

# Pre-register mock modules
sys.modules['core.state_management.utils'] = _mock_utils
sys.modules['core.state_management.utils.mongodb_handler'] = _mock_mongodb_handler
sys.modules['core.state_management.utils.rabbitmq_handler'] = _mock_rabbitmq_handler


@pytest.fixture
def mock_get_db(mock_database):
    """
    Mock the get_db() function used by models

    Usage:
        def test_model_crud(mock_get_db):
            from models.user import User
            user = User.create(...)
    """
    # Update the mock to return our mock_database
    _mock_mongodb_handler.get_db = MagicMock(return_value=mock_database)

    yield mock_database


@pytest.fixture
def mock_flask_app(mock_env_vars, patched_mongodb):
    """
    Create a Flask test application for state management

    Includes all necessary mocks for MongoDB and configuration
    """
    # Create minimal Flask app for testing
    from flask import Flask

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SECRET_KEY'] = 'test-secret-key'

    return app


@pytest.fixture
def flask_test_client(mock_flask_app):
    """
    Create a Flask test client

    Usage:
        def test_api_endpoint(flask_test_client):
            response = flask_test_client.get('/api/configs')
    """
    return mock_flask_app.test_client()


@pytest.fixture
def authenticated_client(flask_test_client, sample_user_data):
    """
    Create an authenticated Flask test client

    Simulates a logged-in user session
    """
    with flask_test_client.session_transaction() as session:
        session['user_id'] = 'user-001'
        session['username'] = sample_user_data['username']
        session['role'] = sample_user_data['role']
        session['_fresh'] = True

    return flask_test_client


@pytest.fixture
def admin_client(flask_test_client, sample_admin_user_data):
    """
    Create an admin authenticated Flask test client

    Simulates a logged-in admin user session
    """
    with flask_test_client.session_transaction() as session:
        session['user_id'] = 'admin-001'
        session['username'] = sample_admin_user_data['username']
        session['role'] = 'admin'
        session['_fresh'] = True

    return flask_test_client


@pytest.fixture
def sample_users_in_db(mock_get_db, sample_user_data, sample_admin_user_data):
    """
    Pre-populate database with sample users

    Returns the database with users inserted
    """
    users_collection = mock_get_db['users']
    users_collection.insert_one({**sample_user_data, '_id': 'user-001'})
    users_collection.insert_one({**sample_admin_user_data, '_id': 'admin-001'})
    return mock_get_db


@pytest.fixture
def sample_configs_in_db(mock_get_db, sample_analysis_config):
    """
    Pre-populate database with sample analysis configs

    Returns the database with configs inserted
    """
    configs_collection = mock_get_db['analysis_configs']
    configs_collection.insert_one({
        **sample_analysis_config,
        '_id': sample_analysis_config['config_id']
    })

    # Add a system config
    system_config = sample_analysis_config.copy()
    system_config.update({
        '_id': 'system-config-001',
        'config_id': 'system-config-001',
        'config_name': 'System Default Config',
        'is_system': True,
    })
    configs_collection.insert_one(system_config)

    return mock_get_db


@pytest.fixture
def sample_routing_rules_in_db(mock_get_db, sample_routing_rule):
    """
    Pre-populate database with sample routing rules

    Returns the database with rules inserted
    """
    rules_collection = mock_get_db['routing_rules']
    rules_collection.insert_one({
        **sample_routing_rule,
        '_id': sample_routing_rule['rule_id']
    })

    # Add additional rules for testing priority
    high_priority_rule = sample_routing_rule.copy()
    high_priority_rule.update({
        '_id': 'high-priority-rule',
        'rule_id': 'high-priority-rule',
        'rule_name': 'High Priority Rule',
        'priority': 1000,
        'conditions': {'device_id': {'$regex': 'priority-.*'}},
    })
    rules_collection.insert_one(high_priority_rule)

    return mock_get_db


@pytest.fixture
def sample_mongodb_instances_in_db(mock_get_db, sample_mongodb_instance):
    """
    Pre-populate database with sample MongoDB instances

    Returns the database with instances inserted
    """
    instances_collection = mock_get_db['mongodb_instances']

    # Default instance (system)
    default_instance = {
        '_id': 'default',
        'instance_id': 'default',
        'instance_name': 'Default Instance',
        'host': 'localhost',
        'port': 27017,
        'database': 'sound_analysis',
        'collection': 'recordings',
        'enabled': True,
        'is_system': True,
        'created_at': datetime.now(timezone.utc),
    }
    instances_collection.insert_one(default_instance)

    # Custom instance
    instances_collection.insert_one({
        **sample_mongodb_instance,
        '_id': sample_mongodb_instance['instance_id']
    })

    return mock_get_db


@pytest.fixture
def sample_edge_devices_in_db(mock_get_db, sample_edge_device):
    """
    Pre-populate database with sample edge devices

    Returns the database with devices inserted
    """
    devices_collection = mock_get_db['edge_devices']
    devices_collection.insert_one({
        **sample_edge_device,
        '_id': sample_edge_device['device_id']
    })

    # Add an offline device
    offline_device = sample_edge_device.copy()
    offline_device.update({
        '_id': 'offline-device-001',
        'device_id': 'offline-device-001',
        'device_name': 'Offline Device',
        'status': 'offline',
        'last_heartbeat': datetime(2026, 1, 1, tzinfo=timezone.utc),
    })
    devices_collection.insert_one(offline_device)

    return mock_get_db


@pytest.fixture
def full_populated_db(
    sample_users_in_db,
    sample_configs_in_db,
    sample_routing_rules_in_db,
    sample_mongodb_instances_in_db,
    sample_edge_devices_in_db
):
    """
    Database populated with all sample data

    Combines all sample data fixtures into one database
    """
    # All fixtures use the same mock_get_db, so just return it
    return sample_users_in_db


# WebSocket fixtures for state management
@pytest.fixture
def mock_socketio():
    """
    Mock Flask-SocketIO for WebSocket testing
    """
    socketio = MagicMock()
    socketio.emit = MagicMock()
    socketio.on = MagicMock()
    socketio.run = MagicMock()

    return socketio


@pytest.fixture
def mock_websocket_manager_service(mock_socketio):
    """
    Mock WebSocketManager service

    Usage:
        def test_push_update(mock_websocket_manager_service):
            mock_websocket_manager_service.push_device_status(...)
    """
    manager = MagicMock()
    manager.socketio = mock_socketio
    manager.push_device_status = MagicMock()
    manager.push_analysis_update = MagicMock()
    manager.push_recording_update = MagicMock()
    manager.broadcast = MagicMock()

    return manager
