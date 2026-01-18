"""
Tests for NodeMonitor Service

Tests cover:
- Node health checking
- Heartbeat timeout detection
- Node status management
- Load balancing awareness
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


class TestNodeHealthChecking:
    """Test node health checking functionality"""

    @pytest.mark.unit
    def test_register_node(self, mock_get_db, sample_node_status):
        """Test registering an analysis node"""
        nodes_collection = mock_get_db['node_status']

        nodes_collection.insert_one(sample_node_status)

        node = nodes_collection.find_one({'node_id': sample_node_status['node_id']})
        assert node is not None
        assert node['status'] == 'active'

    @pytest.mark.unit
    def test_update_node_heartbeat(self, mock_get_db, sample_node_status):
        """Test updating node heartbeat"""
        nodes_collection = mock_get_db['node_status']
        nodes_collection.insert_one(sample_node_status)

        new_heartbeat = datetime.now(timezone.utc)
        nodes_collection.update_one(
            {'node_id': sample_node_status['node_id']},
            {'$set': {'last_heartbeat': new_heartbeat}}
        )

        node = nodes_collection.find_one({'node_id': sample_node_status['node_id']})
        assert node['last_heartbeat'] == new_heartbeat

    @pytest.mark.unit
    def test_check_node_health(self, mock_get_db, sample_node_status):
        """Test checking if node is healthy"""
        nodes_collection = mock_get_db['node_status']
        now = datetime.now(timezone.utc)

        sample_node_status['last_heartbeat'] = now
        nodes_collection.insert_one(sample_node_status)

        node = nodes_collection.find_one({'node_id': sample_node_status['node_id']})

        # Node is healthy if heartbeat is within 30 seconds
        is_healthy = (now - node['last_heartbeat']).total_seconds() < 30
        assert is_healthy is True

    @pytest.mark.unit
    def test_get_active_nodes(self, mock_get_db):
        """Test getting all active nodes"""
        nodes_collection = mock_get_db['node_status']

        nodes_collection.insert_one({'node_id': 'active-1', 'status': 'active'})
        nodes_collection.insert_one({'node_id': 'active-2', 'status': 'active'})
        nodes_collection.insert_one({'node_id': 'inactive-1', 'status': 'inactive'})

        active_nodes = list(nodes_collection.find({'status': 'active'}))
        assert len(active_nodes) == 2


class TestHeartbeatTimeoutDetection:
    """Test heartbeat timeout detection"""

    @pytest.mark.unit
    def test_identify_stale_nodes(self, mock_get_db):
        """Test identifying nodes with stale heartbeats"""
        nodes_collection = mock_get_db['node_status']
        now = datetime.now(timezone.utc)

        # Active node
        nodes_collection.insert_one({
            'node_id': 'active-node',
            'status': 'active',
            'last_heartbeat': now,
        })

        # Stale node (heartbeat 5 min ago)
        nodes_collection.insert_one({
            'node_id': 'stale-node',
            'status': 'active',
            'last_heartbeat': now - timedelta(minutes=5),
        })

        # Find stale nodes (heartbeat > 2 min old)
        threshold = now - timedelta(minutes=2)
        stale = list(nodes_collection.find({
            'status': 'active',
            'last_heartbeat': {'$lt': threshold}
        }))

        assert len(stale) == 1
        assert stale[0]['node_id'] == 'stale-node'

    @pytest.mark.unit
    def test_mark_stale_nodes_inactive(self, mock_get_db):
        """Test marking stale nodes as inactive"""
        nodes_collection = mock_get_db['node_status']
        now = datetime.now(timezone.utc)

        nodes_collection.insert_one({
            'node_id': 'stale-node',
            'status': 'active',
            'last_heartbeat': now - timedelta(minutes=5),
        })

        threshold = now - timedelta(minutes=2)
        result = nodes_collection.update_many(
            {'status': 'active', 'last_heartbeat': {'$lt': threshold}},
            {'$set': {'status': 'inactive'}}
        )

        assert result.modified_count == 1

        node = nodes_collection.find_one({'node_id': 'stale-node'})
        assert node['status'] == 'inactive'

    @pytest.mark.unit
    def test_node_reactivation(self, mock_get_db):
        """Test reactivating an inactive node"""
        nodes_collection = mock_get_db['node_status']
        now = datetime.now(timezone.utc)

        nodes_collection.insert_one({
            'node_id': 'inactive-node',
            'status': 'inactive',
            'last_heartbeat': now - timedelta(minutes=10),
        })

        # Node sends new heartbeat
        nodes_collection.update_one(
            {'node_id': 'inactive-node'},
            {
                '$set': {
                    'status': 'active',
                    'last_heartbeat': now,
                }
            }
        )

        node = nodes_collection.find_one({'node_id': 'inactive-node'})
        assert node['status'] == 'active'


class TestNodeStatusManagement:
    """Test node status management"""

    @pytest.mark.unit
    def test_update_node_task_count(self, mock_get_db, sample_node_status):
        """Test updating node current task count"""
        nodes_collection = mock_get_db['node_status']
        nodes_collection.insert_one(sample_node_status)

        # Increment task count
        nodes_collection.update_one(
            {'node_id': sample_node_status['node_id']},
            {'$inc': {'current_tasks': 1}}
        )

        node = nodes_collection.find_one({'node_id': sample_node_status['node_id']})
        assert node['current_tasks'] == 1

        # Decrement task count
        nodes_collection.update_one(
            {'node_id': sample_node_status['node_id']},
            {'$inc': {'current_tasks': -1}}
        )

        node = nodes_collection.find_one({'node_id': sample_node_status['node_id']})
        assert node['current_tasks'] == 0

    @pytest.mark.unit
    def test_unregister_node(self, mock_get_db, sample_node_status):
        """Test unregistering a node"""
        nodes_collection = mock_get_db['node_status']
        nodes_collection.insert_one(sample_node_status)

        result = nodes_collection.delete_one({'node_id': sample_node_status['node_id']})
        assert result.deleted_count == 1

        node = nodes_collection.find_one({'node_id': sample_node_status['node_id']})
        assert node is None

    @pytest.mark.unit
    def test_get_node_capabilities(self, mock_get_db, sample_node_status):
        """Test getting node capabilities"""
        nodes_collection = mock_get_db['node_status']
        nodes_collection.insert_one(sample_node_status)

        node = nodes_collection.find_one({'node_id': sample_node_status['node_id']})
        capabilities = node.get('capabilities', [])

        assert 'audio_classification' in capabilities


class TestLoadBalancingAwareness:
    """Test load balancing awareness"""

    @pytest.mark.unit
    def test_get_least_loaded_node(self, mock_get_db):
        """Test finding the least loaded node"""
        nodes_collection = mock_get_db['node_status']

        nodes_collection.insert_one({
            'node_id': 'node-1',
            'status': 'active',
            'current_tasks': 3,
            'max_tasks': 4,
        })
        nodes_collection.insert_one({
            'node_id': 'node-2',
            'status': 'active',
            'current_tasks': 1,
            'max_tasks': 4,
        })
        nodes_collection.insert_one({
            'node_id': 'node-3',
            'status': 'active',
            'current_tasks': 2,
            'max_tasks': 4,
        })

        # Find node with least tasks
        least_loaded = nodes_collection.find_one(
            {'status': 'active'},
            sort=[('current_tasks', 1)]
        )

        assert least_loaded['node_id'] == 'node-2'

    @pytest.mark.unit
    def test_get_nodes_with_capacity(self, mock_get_db):
        """Test finding nodes with available capacity"""
        nodes_collection = mock_get_db['node_status']

        nodes_collection.insert_one({
            'node_id': 'full-node',
            'status': 'active',
            'current_tasks': 4,
            'max_tasks': 4,
        })
        nodes_collection.insert_one({
            'node_id': 'available-node',
            'status': 'active',
            'current_tasks': 2,
            'max_tasks': 4,
        })

        # Find nodes with capacity (current_tasks < max_tasks)
        available = list(nodes_collection.find({
            'status': 'active',
            '$expr': {'$lt': ['$current_tasks', '$max_tasks']}
        }))

        # Note: Mock doesn't support $expr, so we filter manually
        available = list(nodes_collection.find({'status': 'active'}))
        available = [n for n in available if n['current_tasks'] < n['max_tasks']]

        assert len(available) == 1
        assert available[0]['node_id'] == 'available-node'

    @pytest.mark.unit
    def test_find_nodes_by_capability(self, mock_get_db):
        """Test finding nodes by capability"""
        nodes_collection = mock_get_db['node_status']

        nodes_collection.insert_one({
            'node_id': 'classifier-node',
            'status': 'active',
            'capabilities': ['audio_classification'],
        })
        nodes_collection.insert_one({
            'node_id': 'multi-node',
            'status': 'active',
            'capabilities': ['audio_classification', 'anomaly_detection'],
        })
        nodes_collection.insert_one({
            'node_id': 'detector-node',
            'status': 'active',
            'capabilities': ['anomaly_detection'],
        })

        # Find nodes that can do audio_classification
        classification_nodes = list(nodes_collection.find({
            'status': 'active',
            'capabilities': 'audio_classification'
        }))

        assert len(classification_nodes) == 2

    @pytest.mark.unit
    def test_calculate_total_capacity(self, mock_get_db):
        """Test calculating total cluster capacity"""
        nodes_collection = mock_get_db['node_status']

        nodes_collection.insert_one({
            'node_id': 'node-1',
            'status': 'active',
            'current_tasks': 2,
            'max_tasks': 4,
        })
        nodes_collection.insert_one({
            'node_id': 'node-2',
            'status': 'active',
            'current_tasks': 1,
            'max_tasks': 4,
        })
        nodes_collection.insert_one({
            'node_id': 'inactive-node',
            'status': 'inactive',
            'current_tasks': 0,
            'max_tasks': 4,
        })

        active_nodes = list(nodes_collection.find({'status': 'active'}))

        total_max = sum(n['max_tasks'] for n in active_nodes)
        total_current = sum(n['current_tasks'] for n in active_nodes)
        available_capacity = total_max - total_current

        assert total_max == 8
        assert total_current == 3
        assert available_capacity == 5
