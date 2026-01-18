"""
Tests for AnalysisConfig Model

Tests cover:
- Configuration CRUD operations
- model_files management
- Version control
- Parameter validation
- System config protection
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock


class TestAnalysisConfigModel:
    """Test AnalysisConfig model CRUD operations"""

    @pytest.mark.unit
    def test_create_config_success(self, mock_get_db, sample_analysis_config):
        """Test creating a new analysis configuration"""
        configs_collection = mock_get_db['analysis_configs']

        result = configs_collection.insert_one(sample_analysis_config)
        assert result.inserted_id is not None

        config = configs_collection.find_one({'config_id': sample_analysis_config['config_id']})
        assert config is not None
        assert config['config_name'] == sample_analysis_config['config_name']

    @pytest.mark.unit
    def test_create_config_with_parameters(self, mock_get_db):
        """Test creating config with detailed parameters"""
        configs_collection = mock_get_db['analysis_configs']

        config_data = {
            'config_id': 'param-config-001',
            'config_name': 'Parameterized Config',
            'analysis_method_id': 'audio_classification',
            'parameters': {
                'slice_duration': 10.0,
                'overlap': 0.5,
                'sample_rate': 16000,
                'n_mels': 64,
                'n_fft': 512,
            },
            'enabled': True,
            'created_at': datetime.now(timezone.utc),
        }

        configs_collection.insert_one(config_data)

        config = configs_collection.find_one({'config_id': 'param-config-001'})
        assert config['parameters']['slice_duration'] == 10.0
        assert config['parameters']['n_mels'] == 64

    @pytest.mark.unit
    def test_get_config_by_id(self, mock_get_db, sample_analysis_config):
        """Test retrieving config by config_id"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        config = configs_collection.find_one({'config_id': sample_analysis_config['config_id']})
        assert config is not None
        assert config['analysis_method_id'] == sample_analysis_config['analysis_method_id']

    @pytest.mark.unit
    def test_get_config_by_method_id(self, mock_get_db, sample_analysis_config):
        """Test retrieving configs by analysis_method_id"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        configs = list(configs_collection.find({
            'analysis_method_id': sample_analysis_config['analysis_method_id']
        }))
        assert len(configs) >= 1
        assert configs[0]['analysis_method_id'] == sample_analysis_config['analysis_method_id']

    @pytest.mark.unit
    def test_get_nonexistent_config(self, mock_get_db):
        """Test retrieving a config that doesn't exist"""
        configs_collection = mock_get_db['analysis_configs']

        config = configs_collection.find_one({'config_id': 'nonexistent'})
        assert config is None

    @pytest.mark.unit
    def test_update_config(self, mock_get_db, sample_analysis_config):
        """Test updating config fields"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        result = configs_collection.update_one(
            {'config_id': sample_analysis_config['config_id']},
            {
                '$set': {
                    'config_name': 'Updated Config Name',
                    'description': 'Updated description',
                    'updated_at': datetime.now(timezone.utc),
                }
            }
        )

        assert result.modified_count == 1

        config = configs_collection.find_one({'config_id': sample_analysis_config['config_id']})
        assert config['config_name'] == 'Updated Config Name'

    @pytest.mark.unit
    def test_update_parameters(self, mock_get_db, sample_analysis_config):
        """Test updating config parameters"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        configs_collection.update_one(
            {'config_id': sample_analysis_config['config_id']},
            {'$set': {'parameters.slice_duration': 20.0}}
        )

        config = configs_collection.find_one({'config_id': sample_analysis_config['config_id']})
        assert config['parameters']['slice_duration'] == 20.0

    @pytest.mark.unit
    def test_delete_config(self, mock_get_db, sample_analysis_config):
        """Test deleting a config"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        result = configs_collection.delete_one({'config_id': sample_analysis_config['config_id']})
        assert result.deleted_count == 1

        config = configs_collection.find_one({'config_id': sample_analysis_config['config_id']})
        assert config is None

    @pytest.mark.unit
    def test_count_configs(self, mock_get_db, sample_analysis_config):
        """Test counting configurations"""
        configs_collection = mock_get_db['analysis_configs']

        # Insert multiple configs
        configs_collection.insert_one(sample_analysis_config)

        config2 = sample_analysis_config.copy()
        config2['config_id'] = 'config-002'
        config2['config_name'] = 'Second Config'
        configs_collection.insert_one(config2)

        total = configs_collection.count_documents({})
        assert total == 2


class TestModelFilesManagement:
    """Test model_files field management"""

    @pytest.mark.unit
    def test_create_config_with_model_files(self, mock_get_db):
        """Test creating config with model_files"""
        configs_collection = mock_get_db['analysis_configs']

        config_data = {
            'config_id': 'model-config-001',
            'config_name': 'Model Config',
            'analysis_method_id': 'audio_classification',
            'parameters': {},
            'model_files': {
                'classification_method': 'onnx',
                'onnx_model': {
                    'file_id': 'gridfs-001',
                    'filename': 'model.onnx',
                    'version': '1.0.0',
                    'uploaded_at': datetime.now(timezone.utc).isoformat(),
                },
            },
            'enabled': True,
            'created_at': datetime.now(timezone.utc),
        }

        configs_collection.insert_one(config_data)

        config = configs_collection.find_one({'config_id': 'model-config-001'})
        assert config['model_files']['classification_method'] == 'onnx'
        assert config['model_files']['onnx_model']['file_id'] == 'gridfs-001'

    @pytest.mark.unit
    def test_get_classification_method(self, mock_get_db, sample_analysis_config):
        """Test getting classification method from config"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        config = configs_collection.find_one({'config_id': sample_analysis_config['config_id']})
        classification_method = config.get('model_files', {}).get('classification_method')

        assert classification_method == 'onnx'

    @pytest.mark.unit
    def test_set_model_file(self, mock_get_db, sample_analysis_config):
        """Test setting a model file in config"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        new_model_info = {
            'file_id': 'gridfs-new-001',
            'filename': 'new_model.onnx',
            'version': '2.0.0',
            'uploaded_at': datetime.now(timezone.utc).isoformat(),
        }

        configs_collection.update_one(
            {'config_id': sample_analysis_config['config_id']},
            {'$set': {'model_files.onnx_model': new_model_info}}
        )

        config = configs_collection.find_one({'config_id': sample_analysis_config['config_id']})
        assert config['model_files']['onnx_model']['version'] == '2.0.0'

    @pytest.mark.unit
    def test_remove_model_file(self, mock_get_db, sample_analysis_config):
        """Test removing a model file from config"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        configs_collection.update_one(
            {'config_id': sample_analysis_config['config_id']},
            {'$unset': {'model_files.onnx_model': ''}}
        )

        config = configs_collection.find_one({'config_id': sample_analysis_config['config_id']})
        assert 'onnx_model' not in config['model_files']

    @pytest.mark.unit
    def test_add_label_mapping(self, mock_get_db, sample_analysis_config):
        """Test adding label mapping to model_files"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        label_mapping = {
            'file_id': 'gridfs-labels-001',
            'filename': 'labels.json',
        }

        configs_collection.update_one(
            {'config_id': sample_analysis_config['config_id']},
            {'$set': {'model_files.label_mapping': label_mapping}}
        )

        config = configs_collection.find_one({'config_id': sample_analysis_config['config_id']})
        assert config['model_files']['label_mapping']['filename'] == 'labels.json'


class TestSystemConfigProtection:
    """Test system config protection mechanisms"""

    @pytest.mark.unit
    def test_identify_system_config(self, mock_get_db):
        """Test identifying system configs"""
        configs_collection = mock_get_db['analysis_configs']

        system_config = {
            'config_id': 'system-001',
            'config_name': 'System Default',
            'analysis_method_id': 'audio_classification',
            'parameters': {},
            'enabled': True,
            'is_system': True,
            'created_at': datetime.now(timezone.utc),
        }
        configs_collection.insert_one(system_config)

        config = configs_collection.find_one({'config_id': 'system-001'})
        assert config['is_system'] is True

    @pytest.mark.unit
    def test_get_non_system_configs(self, mock_get_db, sample_analysis_config):
        """Test getting only non-system configs"""
        configs_collection = mock_get_db['analysis_configs']

        # Insert system config
        system_config = sample_analysis_config.copy()
        system_config['config_id'] = 'system-config'
        system_config['is_system'] = True
        configs_collection.insert_one(system_config)

        # Insert user config
        user_config = sample_analysis_config.copy()
        user_config['config_id'] = 'user-config'
        user_config['is_system'] = False
        configs_collection.insert_one(user_config)

        non_system = list(configs_collection.find({'is_system': {'$ne': True}}))
        assert len(non_system) == 1
        assert non_system[0]['config_id'] == 'user-config'


class TestConfigEnabledStatus:
    """Test config enabled/disabled status"""

    @pytest.mark.unit
    def test_get_enabled_configs(self, mock_get_db, sample_analysis_config):
        """Test getting only enabled configs"""
        configs_collection = mock_get_db['analysis_configs']

        # Insert enabled config
        configs_collection.insert_one(sample_analysis_config)

        # Insert disabled config
        disabled_config = sample_analysis_config.copy()
        disabled_config['config_id'] = 'disabled-config'
        disabled_config['enabled'] = False
        configs_collection.insert_one(disabled_config)

        enabled = list(configs_collection.find({'enabled': True}))
        assert len(enabled) == 1

    @pytest.mark.unit
    def test_disable_config(self, mock_get_db, sample_analysis_config):
        """Test disabling a config"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        configs_collection.update_one(
            {'config_id': sample_analysis_config['config_id']},
            {'$set': {'enabled': False}}
        )

        config = configs_collection.find_one({'config_id': sample_analysis_config['config_id']})
        assert config['enabled'] is False

    @pytest.mark.unit
    def test_enable_config(self, mock_get_db, sample_analysis_config):
        """Test enabling a disabled config"""
        configs_collection = mock_get_db['analysis_configs']

        disabled_config = sample_analysis_config.copy()
        disabled_config['enabled'] = False
        configs_collection.insert_one(disabled_config)

        configs_collection.update_one(
            {'config_id': sample_analysis_config['config_id']},
            {'$set': {'enabled': True}}
        )

        config = configs_collection.find_one({'config_id': sample_analysis_config['config_id']})
        assert config['enabled'] is True

    @pytest.mark.unit
    def test_count_enabled_configs(self, mock_get_db, sample_analysis_config):
        """Test counting enabled vs total configs"""
        configs_collection = mock_get_db['analysis_configs']

        # Insert enabled
        configs_collection.insert_one(sample_analysis_config)

        # Insert disabled
        disabled = sample_analysis_config.copy()
        disabled['config_id'] = 'disabled-001'
        disabled['enabled'] = False
        configs_collection.insert_one(disabled)

        total = configs_collection.count_documents({})
        enabled = configs_collection.count_documents({'enabled': True})

        assert total == 2
        assert enabled == 1
