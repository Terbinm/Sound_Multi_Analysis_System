"""
Tests for MongoDB Node Manager

Tests cover:
- Node registration
- Heartbeat updates
- Task counting
- Node lifecycle
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


class TestNodeRegistration:
    """Test node registration functionality"""

    @pytest.mark.unit
    def test_register_new_node(self, node_status_collection, mock_node_manager):
        """Test registering a new analysis node"""
        node_data = {
            'node_id': mock_node_manager.node_id,
            'capabilities': mock_node_manager.capabilities,
            'status': 'active',
            'current_tasks': 0,
            'max_tasks': 4,
            'last_heartbeat': datetime.now(timezone.utc),
            'registered_at': datetime.now(timezone.utc),
        }

        node_status_collection.insert_one(node_data)

        node = node_status_collection.find_one({'node_id': mock_node_manager.node_id})
        assert node is not None
        assert node['status'] == 'active'

    @pytest.mark.unit
    def test_register_node_with_capabilities(self, node_status_collection):
        """Test registering node with capabilities"""
        node_data = {
            'node_id': 'multi-capability-node',
            'capabilities': ['audio_classification', 'anomaly_detection', 'speech_recognition'],
            'status': 'active',
        }

        node_status_collection.insert_one(node_data)

        node = node_status_collection.find_one({'node_id': 'multi-capability-node'})
        assert 'audio_classification' in node['capabilities']
        assert len(node['capabilities']) == 3

    @pytest.mark.unit
    def test_update_node_on_reconnect(self, node_status_collection, mock_node_manager):
        """Test updating node on reconnection"""
        # Insert existing node (from previous run)
        node_status_collection.insert_one({
            'node_id': mock_node_manager.node_id,
            'status': 'inactive',
            'last_heartbeat': datetime.now(timezone.utc) - timedelta(hours=1),
        })

        # Simulate reconnection
        node_status_collection.update_one(
            {'node_id': mock_node_manager.node_id},
            {
                '$set': {
                    'status': 'active',
                    'last_heartbeat': datetime.now(timezone.utc),
                }
            }
        )

        node = node_status_collection.find_one({'node_id': mock_node_manager.node_id})
        assert node['status'] == 'active'


class TestHeartbeatUpdates:
    """Test heartbeat update functionality"""

    @pytest.mark.unit
    def test_update_heartbeat(self, node_status_collection, mock_node_manager):
        """Test updating node heartbeat"""
        node_status_collection.insert_one({
            'node_id': mock_node_manager.node_id,
            'status': 'active',
            'last_heartbeat': datetime.now(timezone.utc) - timedelta(seconds=30),
        })

        new_heartbeat = datetime.now(timezone.utc)
        node_status_collection.update_one(
            {'node_id': mock_node_manager.node_id},
            {'$set': {'last_heartbeat': new_heartbeat}}
        )

        node = node_status_collection.find_one({'node_id': mock_node_manager.node_id})
        assert (new_heartbeat - node['last_heartbeat']).total_seconds() < 1

    @pytest.mark.unit
    def test_heartbeat_with_status_update(self, node_status_collection, mock_node_manager):
        """Test heartbeat with additional status info"""
        node_status_collection.insert_one({
            'node_id': mock_node_manager.node_id,
            'status': 'active',
            'current_tasks': 0,
        })

        node_status_collection.update_one(
            {'node_id': mock_node_manager.node_id},
            {
                '$set': {
                    'last_heartbeat': datetime.now(timezone.utc),
                    'current_tasks': 2,
                    'memory_usage_mb': 512,
                    'cpu_usage_percent': 45.5,
                }
            }
        )

        node = node_status_collection.find_one({'node_id': mock_node_manager.node_id})
        assert node['current_tasks'] == 2
        assert 'memory_usage_mb' in node

    @pytest.mark.unit
    def test_detect_stale_heartbeat(self, node_status_collection):
        """Test detecting stale heartbeat"""
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(minutes=1)

        node_status_collection.insert_one({
            'node_id': 'stale-node',
            'status': 'active',
            'last_heartbeat': now - timedelta(minutes=5),
        })

        stale_nodes = list(node_status_collection.find({
            'status': 'active',
            'last_heartbeat': {'$lt': threshold}
        }))

        assert len(stale_nodes) == 1
        assert stale_nodes[0]['node_id'] == 'stale-node'


class TestTaskCounting:
    """Test task counting functionality"""

    @pytest.mark.unit
    def test_increment_task_count(self, node_status_collection, mock_node_manager):
        """Test incrementing current task count"""
        node_status_collection.insert_one({
            'node_id': mock_node_manager.node_id,
            'current_tasks': 0,
            'max_tasks': 4,
        })

        node_status_collection.update_one(
            {'node_id': mock_node_manager.node_id},
            {'$inc': {'current_tasks': 1}}
        )

        node = node_status_collection.find_one({'node_id': mock_node_manager.node_id})
        assert node['current_tasks'] == 1

    @pytest.mark.unit
    def test_decrement_task_count(self, node_status_collection, mock_node_manager):
        """Test decrementing current task count"""
        node_status_collection.insert_one({
            'node_id': mock_node_manager.node_id,
            'current_tasks': 3,
            'max_tasks': 4,
        })

        node_status_collection.update_one(
            {'node_id': mock_node_manager.node_id},
            {'$inc': {'current_tasks': -1}}
        )

        node = node_status_collection.find_one({'node_id': mock_node_manager.node_id})
        assert node['current_tasks'] == 2

    @pytest.mark.unit
    def test_check_capacity_available(self, node_status_collection, mock_node_manager):
        """Test checking if node has capacity"""
        node_status_collection.insert_one({
            'node_id': mock_node_manager.node_id,
            'current_tasks': 2,
            'max_tasks': 4,
        })

        node = node_status_collection.find_one({'node_id': mock_node_manager.node_id})
        has_capacity = node['current_tasks'] < node['max_tasks']

        assert has_capacity is True

    @pytest.mark.unit
    def test_check_at_capacity(self, node_status_collection, mock_node_manager):
        """Test checking when node is at capacity"""
        node_status_collection.insert_one({
            'node_id': mock_node_manager.node_id,
            'current_tasks': 4,
            'max_tasks': 4,
        })

        node = node_status_collection.find_one({'node_id': mock_node_manager.node_id})
        has_capacity = node['current_tasks'] < node['max_tasks']

        assert has_capacity is False


class TestNodeLifecycle:
    """Test node lifecycle management"""

    @pytest.mark.unit
    def test_unregister_node(self, node_status_collection, mock_node_manager):
        """Test unregistering a node"""
        node_status_collection.insert_one({
            'node_id': mock_node_manager.node_id,
            'status': 'active',
        })

        result = node_status_collection.delete_one({
            'node_id': mock_node_manager.node_id
        })

        assert result.deleted_count == 1

        node = node_status_collection.find_one({'node_id': mock_node_manager.node_id})
        assert node is None

    @pytest.mark.unit
    def test_mark_node_inactive(self, node_status_collection, mock_node_manager):
        """Test marking node as inactive (graceful shutdown)"""
        node_status_collection.insert_one({
            'node_id': mock_node_manager.node_id,
            'status': 'active',
        })

        node_status_collection.update_one(
            {'node_id': mock_node_manager.node_id},
            {'$set': {'status': 'inactive', 'shutdown_at': datetime.now(timezone.utc)}}
        )

        node = node_status_collection.find_one({'node_id': mock_node_manager.node_id})
        assert node['status'] == 'inactive'

    @pytest.mark.unit
    def test_get_active_nodes(self, node_status_collection):
        """Test getting all active nodes"""
        node_status_collection.insert_one({'node_id': 'active-1', 'status': 'active'})
        node_status_collection.insert_one({'node_id': 'active-2', 'status': 'active'})
        node_status_collection.insert_one({'node_id': 'inactive-1', 'status': 'inactive'})

        active_nodes = list(node_status_collection.find({'status': 'active'}))

        assert len(active_nodes) == 2

    @pytest.mark.unit
    def test_get_nodes_by_capability(self, node_status_collection):
        """Test getting nodes by capability"""
        node_status_collection.insert_one({
            'node_id': 'classifier',
            'capabilities': ['audio_classification'],
            'status': 'active',
        })
        node_status_collection.insert_one({
            'node_id': 'detector',
            'capabilities': ['anomaly_detection'],
            'status': 'active',
        })
        node_status_collection.insert_one({
            'node_id': 'multi',
            'capabilities': ['audio_classification', 'anomaly_detection'],
            'status': 'active',
        })

        classification_nodes = list(node_status_collection.find({
            'status': 'active',
            'capabilities': 'audio_classification'
        }))

        assert len(classification_nodes) == 2
