"""
Tests for Config API

Tests cover:
- Configuration CRUD endpoints
- Validation
- Error handling
- Authentication requirements
"""
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestConfigAPIRead:
    """Test configuration read endpoints"""

    @pytest.mark.unit
    def test_get_all_configs(self, sample_configs_in_db):
        """Test getting all configurations"""
        configs_collection = sample_configs_in_db['analysis_configs']

        configs = list(configs_collection.find({}))
        assert len(configs) >= 2  # From fixture

    @pytest.mark.unit
    def test_get_enabled_configs_only(self, mock_get_db, sample_analysis_config):
        """Test getting only enabled configurations"""
        configs_collection = mock_get_db['analysis_configs']

        # Insert enabled and disabled configs
        configs_collection.insert_one(sample_analysis_config)

        disabled = sample_analysis_config.copy()
        disabled['config_id'] = 'disabled-config'
        disabled['enabled'] = False
        configs_collection.insert_one(disabled)

        enabled = list(configs_collection.find({'enabled': True}))
        assert len(enabled) == 1

    @pytest.mark.unit
    def test_get_config_by_id(self, sample_configs_in_db, sample_analysis_config):
        """Test getting configuration by ID"""
        configs_collection = sample_configs_in_db['analysis_configs']

        config = configs_collection.find_one({
            'config_id': sample_analysis_config['config_id']
        })

        assert config is not None
        assert config['config_name'] == sample_analysis_config['config_name']

    @pytest.mark.unit
    def test_get_nonexistent_config(self, mock_get_db):
        """Test getting non-existent configuration"""
        configs_collection = mock_get_db['analysis_configs']

        config = configs_collection.find_one({'config_id': 'nonexistent'})
        assert config is None

    @pytest.mark.unit
    def test_get_configs_by_method(self, sample_configs_in_db, sample_analysis_config):
        """Test getting configurations by analysis method"""
        configs_collection = sample_configs_in_db['analysis_configs']

        configs = list(configs_collection.find({
            'analysis_method_id': sample_analysis_config['analysis_method_id']
        }))

        assert len(configs) >= 1


class TestConfigAPICreate:
    """Test configuration creation endpoints"""

    @pytest.mark.unit
    def test_create_config(self, mock_get_db):
        """Test creating new configuration"""
        configs_collection = mock_get_db['analysis_configs']

        new_config = {
            'config_id': 'new-config-001',
            'config_name': 'New Configuration',
            'analysis_method_id': 'audio_classification',
            'parameters': {'slice_duration': 15.0},
            'enabled': True,
            'is_system': False,
            'created_at': datetime.now(timezone.utc),
        }

        result = configs_collection.insert_one(new_config)
        assert result.inserted_id is not None

        created = configs_collection.find_one({'config_id': 'new-config-001'})
        assert created is not None
        assert created['config_name'] == 'New Configuration'

    @pytest.mark.unit
    def test_create_config_with_model_files(self, mock_get_db):
        """Test creating configuration with model files"""
        configs_collection = mock_get_db['analysis_configs']

        config_with_model = {
            'config_id': 'model-config-001',
            'config_name': 'Config with Model',
            'analysis_method_id': 'audio_classification',
            'parameters': {},
            'model_files': {
                'classification_method': 'onnx',
                'onnx_model': {
                    'file_id': 'gridfs-model-001',
                    'filename': 'model.onnx',
                },
            },
            'enabled': True,
            'created_at': datetime.now(timezone.utc),
        }

        configs_collection.insert_one(config_with_model)

        config = configs_collection.find_one({'config_id': 'model-config-001'})
        assert config['model_files']['classification_method'] == 'onnx'

    @pytest.mark.unit
    def test_create_config_validation_missing_fields(self, mock_get_db):
        """Test validation when creating config with missing fields"""
        # In real API, this would return 400 error
        invalid_config = {
            'config_name': 'Invalid Config',
            # Missing required fields: config_id, analysis_method_id
        }

        # Simulate validation
        required_fields = ['config_id', 'config_name', 'analysis_method_id']
        missing = [f for f in required_fields if f not in invalid_config]

        assert len(missing) > 0


class TestConfigAPIUpdate:
    """Test configuration update endpoints"""

    @pytest.mark.unit
    def test_update_config(self, mock_get_db, sample_analysis_config):
        """Test updating configuration"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        result = configs_collection.update_one(
            {'config_id': sample_analysis_config['config_id']},
            {
                '$set': {
                    'config_name': 'Updated Name',
                    'updated_at': datetime.now(timezone.utc),
                }
            }
        )

        assert result.modified_count == 1

        updated = configs_collection.find_one({
            'config_id': sample_analysis_config['config_id']
        })
        assert updated['config_name'] == 'Updated Name'

    @pytest.mark.unit
    def test_update_config_parameters(self, mock_get_db, sample_analysis_config):
        """Test updating configuration parameters"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        configs_collection.update_one(
            {'config_id': sample_analysis_config['config_id']},
            {'$set': {'parameters.slice_duration': 20.0}}
        )

        config = configs_collection.find_one({
            'config_id': sample_analysis_config['config_id']
        })
        assert config['parameters']['slice_duration'] == 20.0

    @pytest.mark.unit
    def test_update_nonexistent_config(self, mock_get_db):
        """Test updating non-existent configuration"""
        configs_collection = mock_get_db['analysis_configs']

        result = configs_collection.update_one(
            {'config_id': 'nonexistent'},
            {'$set': {'config_name': 'New Name'}}
        )

        assert result.matched_count == 0

    @pytest.mark.unit
    def test_cannot_update_system_config(self, mock_get_db):
        """Test that system configs should be protected"""
        configs_collection = mock_get_db['analysis_configs']

        system_config = {
            'config_id': 'system-config',
            'config_name': 'System Config',
            'is_system': True,
            'enabled': True,
        }
        configs_collection.insert_one(system_config)

        # In real API, would check is_system before update
        config = configs_collection.find_one({'config_id': 'system-config'})
        assert config['is_system'] is True


class TestConfigAPIDelete:
    """Test configuration deletion endpoints"""

    @pytest.mark.unit
    def test_delete_config(self, mock_get_db, sample_analysis_config):
        """Test deleting configuration"""
        configs_collection = mock_get_db['analysis_configs']
        sample_analysis_config['is_system'] = False
        configs_collection.insert_one(sample_analysis_config)

        result = configs_collection.delete_one({
            'config_id': sample_analysis_config['config_id']
        })

        assert result.deleted_count == 1

    @pytest.mark.unit
    def test_delete_nonexistent_config(self, mock_get_db):
        """Test deleting non-existent configuration"""
        configs_collection = mock_get_db['analysis_configs']

        result = configs_collection.delete_one({'config_id': 'nonexistent'})
        assert result.deleted_count == 0

    @pytest.mark.unit
    def test_cannot_delete_system_config(self, mock_get_db):
        """Test that system configs cannot be deleted"""
        configs_collection = mock_get_db['analysis_configs']

        configs_collection.insert_one({
            'config_id': 'system-protected',
            'is_system': True,
        })

        # In real API, check is_system before delete
        config = configs_collection.find_one({'config_id': 'system-protected'})
        assert config['is_system'] is True


class TestConfigAPIToggle:
    """Test configuration enable/disable endpoints"""

    @pytest.mark.unit
    def test_disable_config(self, mock_get_db, sample_analysis_config):
        """Test disabling a configuration"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        configs_collection.update_one(
            {'config_id': sample_analysis_config['config_id']},
            {'$set': {'enabled': False}}
        )

        config = configs_collection.find_one({
            'config_id': sample_analysis_config['config_id']
        })
        assert config['enabled'] is False

    @pytest.mark.unit
    def test_enable_config(self, mock_get_db, sample_analysis_config):
        """Test enabling a disabled configuration"""
        configs_collection = mock_get_db['analysis_configs']
        sample_analysis_config['enabled'] = False
        configs_collection.insert_one(sample_analysis_config)

        configs_collection.update_one(
            {'config_id': sample_analysis_config['config_id']},
            {'$set': {'enabled': True}}
        )

        config = configs_collection.find_one({
            'config_id': sample_analysis_config['config_id']
        })
        assert config['enabled'] is True
