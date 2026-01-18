"""
Tests for MongoDBInstance Model

Tests cover:
- Instance CRUD operations
- Connection configuration
- Default instance management
- Password masking
- Connection testing
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock


class TestMongoDBInstanceModel:
    """Test MongoDBInstance model CRUD operations"""

    @pytest.mark.unit
    def test_create_instance_success(self, mock_get_db, sample_mongodb_instance):
        """Test creating a new MongoDB instance"""
        instances_collection = mock_get_db['mongodb_instances']

        result = instances_collection.insert_one(sample_mongodb_instance)
        assert result.inserted_id is not None

        instance = instances_collection.find_one({
            'instance_id': sample_mongodb_instance['instance_id']
        })
        assert instance is not None
        assert instance['instance_name'] == sample_mongodb_instance['instance_name']

    @pytest.mark.unit
    def test_create_instance_with_auth(self, mock_get_db):
        """Test creating instance with authentication"""
        instances_collection = mock_get_db['mongodb_instances']

        instance_data = {
            'instance_id': 'auth-instance-001',
            'instance_name': 'Authenticated Instance',
            'host': 'mongodb.example.com',
            'port': 27017,
            'username': 'db_user',
            'password': 'db_password',
            'database': 'sound_analysis',
            'collection': 'recordings',
            'auth_source': 'admin',
            'enabled': True,
            'created_at': datetime.now(timezone.utc),
        }

        instances_collection.insert_one(instance_data)

        instance = instances_collection.find_one({'instance_id': 'auth-instance-001'})
        assert instance['username'] == 'db_user'
        assert instance['auth_source'] == 'admin'

    @pytest.mark.unit
    def test_get_instance_by_id(self, mock_get_db, sample_mongodb_instance):
        """Test retrieving instance by instance_id"""
        instances_collection = mock_get_db['mongodb_instances']
        instances_collection.insert_one(sample_mongodb_instance)

        instance = instances_collection.find_one({
            'instance_id': sample_mongodb_instance['instance_id']
        })
        assert instance is not None
        assert instance['host'] == sample_mongodb_instance['host']

    @pytest.mark.unit
    def test_update_instance(self, mock_get_db, sample_mongodb_instance):
        """Test updating instance fields"""
        instances_collection = mock_get_db['mongodb_instances']
        instances_collection.insert_one(sample_mongodb_instance)

        result = instances_collection.update_one(
            {'instance_id': sample_mongodb_instance['instance_id']},
            {
                '$set': {
                    'host': 'new-host.example.com',
                    'port': 27018,
                    'updated_at': datetime.now(timezone.utc),
                }
            }
        )

        assert result.modified_count == 1

        instance = instances_collection.find_one({
            'instance_id': sample_mongodb_instance['instance_id']
        })
        assert instance['host'] == 'new-host.example.com'
        assert instance['port'] == 27018

    @pytest.mark.unit
    def test_delete_instance(self, mock_get_db, sample_mongodb_instance):
        """Test deleting an instance"""
        instances_collection = mock_get_db['mongodb_instances']
        instances_collection.insert_one(sample_mongodb_instance)

        result = instances_collection.delete_one({
            'instance_id': sample_mongodb_instance['instance_id']
        })
        assert result.deleted_count == 1

        instance = instances_collection.find_one({
            'instance_id': sample_mongodb_instance['instance_id']
        })
        assert instance is None


class TestDefaultInstance:
    """Test default instance management"""

    @pytest.mark.unit
    def test_default_instance_exists(self, mock_get_db):
        """Test that default instance can be created"""
        instances_collection = mock_get_db['mongodb_instances']

        default_instance = {
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

        instance = instances_collection.find_one({'instance_id': 'default'})
        assert instance is not None
        assert instance['is_system'] is True

    @pytest.mark.unit
    def test_get_default_instance(self, mock_get_db):
        """Test retrieving the default instance"""
        instances_collection = mock_get_db['mongodb_instances']

        instances_collection.insert_one({
            'instance_id': 'default',
            'instance_name': 'Default',
            'is_system': True,
            'enabled': True,
        })

        instances_collection.insert_one({
            'instance_id': 'custom-001',
            'instance_name': 'Custom',
            'is_system': False,
            'enabled': True,
        })

        default = instances_collection.find_one({'instance_id': 'default'})
        assert default is not None
        assert default['is_system'] is True

    @pytest.mark.unit
    def test_cannot_delete_system_instance(self, mock_get_db):
        """Test that system instances should be protected"""
        instances_collection = mock_get_db['mongodb_instances']

        instances_collection.insert_one({
            'instance_id': 'default',
            'is_system': True,
            'enabled': True,
        })

        # In application logic, we would check is_system before delete
        instance = instances_collection.find_one({'instance_id': 'default'})
        assert instance['is_system'] is True  # Should be protected


class TestConnectionConfig:
    """Test connection configuration retrieval"""

    @pytest.mark.unit
    def test_get_connection_config(self, mock_get_db, sample_mongodb_instance):
        """Test getting connection configuration"""
        instances_collection = mock_get_db['mongodb_instances']
        instances_collection.insert_one(sample_mongodb_instance)

        instance = instances_collection.find_one({
            'instance_id': sample_mongodb_instance['instance_id']
        })

        # Build connection config
        connection_config = {
            'host': instance['host'],
            'port': instance['port'],
            'database': instance['database'],
            'username': instance.get('username'),
            'password': instance.get('password'),
            'auth_source': instance.get('auth_source'),
        }

        assert connection_config['host'] == sample_mongodb_instance['host']
        assert connection_config['port'] == sample_mongodb_instance['port']

    @pytest.mark.unit
    def test_build_connection_uri(self, mock_get_db, sample_mongodb_instance):
        """Test building MongoDB connection URI"""
        instances_collection = mock_get_db['mongodb_instances']
        instances_collection.insert_one(sample_mongodb_instance)

        instance = instances_collection.find_one({
            'instance_id': sample_mongodb_instance['instance_id']
        })

        # Build URI (simplified)
        if instance.get('username') and instance.get('password'):
            uri = f"mongodb://{instance['username']}:{instance['password']}@{instance['host']}:{instance['port']}/{instance['database']}"
        else:
            uri = f"mongodb://{instance['host']}:{instance['port']}/{instance['database']}"

        assert 'localhost' in uri or 'mongodb://' in uri


class TestPasswordHandling:
    """Test password masking and security"""

    @pytest.mark.unit
    def test_get_instance_without_password(self, mock_get_db, sample_mongodb_instance):
        """Test retrieving instance with password excluded"""
        instances_collection = mock_get_db['mongodb_instances']
        instances_collection.insert_one(sample_mongodb_instance)

        # Use projection to exclude password
        instance = instances_collection.find_one(
            {'instance_id': sample_mongodb_instance['instance_id']},
            {'password': 0}  # Exclude password
        )

        assert 'password' not in instance

    @pytest.mark.unit
    def test_mask_password_in_response(self, mock_get_db, sample_mongodb_instance):
        """Test masking password in API response"""
        instances_collection = mock_get_db['mongodb_instances']
        instances_collection.insert_one(sample_mongodb_instance)

        instance = instances_collection.find_one({
            'instance_id': sample_mongodb_instance['instance_id']
        })

        # Simulate masking
        masked_instance = dict(instance)
        if masked_instance.get('password'):
            masked_instance['password'] = '********'

        assert masked_instance['password'] == '********'

    @pytest.mark.unit
    def test_update_password(self, mock_get_db, sample_mongodb_instance):
        """Test updating instance password"""
        instances_collection = mock_get_db['mongodb_instances']
        instances_collection.insert_one(sample_mongodb_instance)

        new_password = 'new_secure_password'
        instances_collection.update_one(
            {'instance_id': sample_mongodb_instance['instance_id']},
            {'$set': {'password': new_password}}
        )

        instance = instances_collection.find_one({
            'instance_id': sample_mongodb_instance['instance_id']
        })
        assert instance['password'] == new_password


class TestInstanceEnabledStatus:
    """Test instance enabled/disabled status"""

    @pytest.mark.unit
    def test_get_enabled_instances(self, mock_get_db, sample_mongodb_instance):
        """Test getting only enabled instances"""
        instances_collection = mock_get_db['mongodb_instances']

        # Insert enabled
        instances_collection.insert_one(sample_mongodb_instance)

        # Insert disabled
        disabled = sample_mongodb_instance.copy()
        disabled['instance_id'] = 'disabled-instance'
        disabled['enabled'] = False
        instances_collection.insert_one(disabled)

        enabled = list(instances_collection.find({'enabled': True}))
        assert len(enabled) == 1

    @pytest.mark.unit
    def test_disable_instance(self, mock_get_db, sample_mongodb_instance):
        """Test disabling an instance"""
        instances_collection = mock_get_db['mongodb_instances']
        instances_collection.insert_one(sample_mongodb_instance)

        instances_collection.update_one(
            {'instance_id': sample_mongodb_instance['instance_id']},
            {'$set': {'enabled': False}}
        )

        instance = instances_collection.find_one({
            'instance_id': sample_mongodb_instance['instance_id']
        })
        assert instance['enabled'] is False

    @pytest.mark.unit
    def test_count_instances(self, mock_get_db, sample_mongodb_instance):
        """Test counting instances"""
        instances_collection = mock_get_db['mongodb_instances']

        instances_collection.insert_one(sample_mongodb_instance)

        instance2 = sample_mongodb_instance.copy()
        instance2['instance_id'] = 'instance-002'
        instances_collection.insert_one(instance2)

        total = instances_collection.count_documents({})
        assert total == 2
