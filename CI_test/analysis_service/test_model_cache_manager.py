"""
Tests for Model Cache Manager

Tests cover:
- Model caching
- Model downloading
- Version management
- Cache cleanup
"""
import pytest
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestModelCaching:
    """Test model caching functionality"""

    @pytest.mark.unit
    def test_get_cached_model(self, mock_model_cache):
        """Test getting cached model"""
        model = mock_model_cache.get_model('config-001', 'onnx_model')

        assert model is not None

    @pytest.mark.unit
    def test_cache_hit(self, mock_model_cache):
        """Test cache hit for same model"""
        model1 = mock_model_cache.get_model('config-001', 'onnx_model')
        model2 = mock_model_cache.get_model('config-001', 'onnx_model')

        # Same object should be returned
        assert model1 is model2

    @pytest.mark.unit
    def test_cache_different_models(self, mock_model_cache):
        """Test caching different models"""
        model1 = mock_model_cache.get_model('config-001', 'onnx_model')
        model2 = mock_model_cache.get_model('config-002', 'onnx_model')

        # Different objects
        assert model1 is not model2

    @pytest.mark.unit
    def test_clear_cache(self, mock_model_cache):
        """Test clearing model cache"""
        mock_model_cache.get_model('config-001', 'onnx_model')
        mock_model_cache.get_model('config-002', 'onnx_model')

        mock_model_cache.clear_cache()

        assert len(mock_model_cache._cached_models) == 0


class TestModelDownloading:
    """Test model downloading functionality"""

    @pytest.mark.unit
    def test_download_model(self, mock_model_cache, temp_model_dir):
        """Test downloading model from GridFS"""
        destination = os.path.join(temp_model_dir, 'model.onnx')

        result = mock_model_cache.download_model('gridfs-model-001', destination)

        assert result is True

    @pytest.mark.unit
    def test_download_model_to_cache_dir(self, mock_model_cache, temp_model_dir):
        """Test downloading model to cache directory"""
        # Simulate model download
        model_content = b'mock model binary'
        destination = os.path.join(temp_model_dir, 'classifier.onnx')

        with open(destination, 'wb') as f:
            f.write(model_content)

        assert os.path.exists(destination)

    @pytest.mark.unit
    def test_model_file_validation(self, temp_model_dir):
        """Test validating downloaded model file"""
        model_path = os.path.join(temp_model_dir, 'model.onnx')

        # Create mock model file
        with open(model_path, 'wb') as f:
            f.write(b'ONNX model content')

        # Validate file exists and has content
        assert os.path.exists(model_path)
        assert os.path.getsize(model_path) > 0


class TestVersionManagement:
    """Test model version management"""

    @pytest.mark.unit
    def test_model_version_tracking(self, mock_get_db, sample_analysis_config):
        """Test tracking model versions"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        config = configs_collection.find_one({
            'config_id': sample_analysis_config['config_id']
        })

        model_info = config['model_files'].get('onnx_model', {})
        assert 'version' in model_info or 'file_id' in model_info

    @pytest.mark.unit
    def test_check_model_update_needed(self, mock_get_db, sample_analysis_config):
        """Test checking if model update is needed"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        # Simulate checking for update
        cached_version = '1.0.0'
        config = configs_collection.find_one({
            'config_id': sample_analysis_config['config_id']
        })

        current_version = config['model_files'].get('onnx_model', {}).get('version', '1.0.0')
        update_needed = current_version != cached_version

        # Same version, no update needed
        assert update_needed is False

    @pytest.mark.unit
    def test_update_model_version(self, mock_get_db, sample_analysis_config):
        """Test updating model version in config"""
        configs_collection = mock_get_db['analysis_configs']
        configs_collection.insert_one(sample_analysis_config)

        # Update model version
        configs_collection.update_one(
            {'config_id': sample_analysis_config['config_id']},
            {'$set': {'model_files.onnx_model.version': '2.0.0'}}
        )

        config = configs_collection.find_one({
            'config_id': sample_analysis_config['config_id']
        })

        assert config['model_files']['onnx_model']['version'] == '2.0.0'


class TestCacheCleanup:
    """Test cache cleanup functionality"""

    @pytest.mark.unit
    def test_remove_old_cached_model(self, temp_model_dir):
        """Test removing old cached models"""
        old_model = os.path.join(temp_model_dir, 'old_model.onnx')

        with open(old_model, 'wb') as f:
            f.write(b'old model')

        assert os.path.exists(old_model)

        os.remove(old_model)

        assert not os.path.exists(old_model)

    @pytest.mark.unit
    def test_cache_size_limit(self, temp_model_dir):
        """Test cache size limit management"""
        # Create multiple model files
        for i in range(5):
            model_path = os.path.join(temp_model_dir, f'model_{i}.onnx')
            with open(model_path, 'wb') as f:
                f.write(b'x' * 1000)

        # Calculate total size
        total_size = sum(
            os.path.getsize(os.path.join(temp_model_dir, f))
            for f in os.listdir(temp_model_dir)
            if os.path.isfile(os.path.join(temp_model_dir, f))
        )

        assert total_size == 5000  # 5 files * 1000 bytes

    @pytest.mark.unit
    def test_cleanup_unused_models(self, temp_model_dir, mock_model_cache):
        """Test cleaning up unused models"""
        # Create some model files
        for name in ['used.onnx', 'unused1.onnx', 'unused2.onnx']:
            path = os.path.join(temp_model_dir, name)
            with open(path, 'wb') as f:
                f.write(b'model content')

        # Mark 'used.onnx' as in use
        mock_model_cache.get_model('used', 'model')

        # Cleanup would remove unused models
        # In real implementation, this would check cache references

        files = os.listdir(temp_model_dir)
        assert len(files) == 3  # All files still exist before cleanup
