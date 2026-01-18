"""
Tests for Analysis Pipeline

Tests cover:
- 4-step pipeline flow
- Configuration application
- Error handling
- Result generation
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestPipelineExecution:
    """Test pipeline execution flow"""

    @pytest.mark.unit
    def test_pipeline_process_success(self, mock_analysis_pipeline, sample_recording_for_analysis, sample_analysis_config):
        """Test successful pipeline processing"""
        result = mock_analysis_pipeline.process(
            sample_recording_for_analysis,
            sample_analysis_config
        )

        assert result['status'] == 'success'
        assert 'results' in result

    @pytest.mark.unit
    def test_pipeline_has_all_steps(self, mock_analysis_pipeline):
        """Test pipeline contains all required steps"""
        expected_steps = ['step0_converter', 'step1_slicer', 'step2_leaf', 'step3_classifier']

        assert mock_analysis_pipeline.steps == expected_steps

    @pytest.mark.unit
    def test_pipeline_result_format(self, mock_analysis_pipeline, sample_recording_for_analysis, sample_analysis_config):
        """Test pipeline result format"""
        result = mock_analysis_pipeline.process(
            sample_recording_for_analysis,
            sample_analysis_config
        )

        assert 'status' in result
        assert 'results' in result
        assert 'processed_at' in result


class TestConfigurationApplication:
    """Test configuration application in pipeline"""

    @pytest.mark.unit
    def test_apply_classification_config(self, sample_analysis_config):
        """Test applying classification configuration"""
        params = sample_analysis_config['parameters']

        assert 'slice_duration' in params
        assert 'sample_rate' in params

    @pytest.mark.unit
    def test_config_model_files(self, sample_analysis_config):
        """Test accessing model files from config"""
        model_files = sample_analysis_config['model_files']

        assert 'classification_method' in model_files
        assert model_files['classification_method'] == 'onnx'

    @pytest.mark.unit
    def test_load_config_from_db(self, analysis_configs_in_db, sample_analysis_config):
        """Test loading configuration from database"""
        configs_collection = analysis_configs_in_db['analysis_configs']

        config = configs_collection.find_one({
            'config_id': sample_analysis_config['config_id']
        })

        assert config is not None
        assert config['enabled'] is True


class TestStepExecution:
    """Test individual step execution"""

    @pytest.mark.unit
    def test_step0_converter_input(self, sample_recording_for_analysis):
        """Test Step 0 converter input requirements"""
        required_fields = ['file_id', 'sample_rate', 'channels']

        for field in required_fields:
            assert field in sample_recording_for_analysis

    @pytest.mark.unit
    def test_step1_slicer_params(self, sample_analysis_config):
        """Test Step 1 slicer parameters"""
        params = sample_analysis_config['parameters']

        # Slicer needs duration and overlap
        assert 'slice_duration' in params

    @pytest.mark.unit
    def test_step2_leaf_feature_extraction(self):
        """Test Step 2 LEAF feature extraction mock"""
        # Mock LEAF processor output
        mock_features = {
            'feature_shape': (100, 64),  # time_steps x n_mels
            'sample_rate': 16000,
        }

        assert mock_features['feature_shape'][1] == 64

    @pytest.mark.unit
    def test_step3_classifier_prediction(self, sample_analysis_result):
        """Test Step 3 classifier prediction format"""
        predictions = sample_analysis_result['results']['predictions']

        assert len(predictions) > 0
        assert 'label' in predictions[0]
        assert 'score' in predictions[0]


class TestErrorHandling:
    """Test pipeline error handling"""

    @pytest.mark.unit
    def test_handle_missing_recording(self, mock_get_db):
        """Test handling missing recording"""
        recordings_collection = mock_get_db['recordings']

        recording = recordings_collection.find_one({'_id': 'nonexistent'})
        assert recording is None

    @pytest.mark.unit
    def test_handle_missing_config(self, mock_get_db):
        """Test handling missing configuration"""
        configs_collection = mock_get_db['analysis_configs']

        config = configs_collection.find_one({'config_id': 'nonexistent'})
        assert config is None

    @pytest.mark.unit
    def test_task_failure_logging(self, task_logs_collection):
        """Test logging task failure"""
        task_logs_collection.insert_one({
            'task_id': 'failed-task',
            'status': 'processing',
        })

        task_logs_collection.update_one(
            {'task_id': 'failed-task'},
            {
                '$set': {
                    'status': 'failed',
                    'error_message': 'Model file not found',
                    'failed_at': datetime.now(timezone.utc),
                }
            }
        )

        log = task_logs_collection.find_one({'task_id': 'failed-task'})
        assert log['status'] == 'failed'
        assert 'error_message' in log


class TestResultGeneration:
    """Test analysis result generation"""

    @pytest.mark.unit
    def test_result_structure(self, sample_analysis_result):
        """Test analysis result structure"""
        required_fields = ['recording_id', 'task_id', 'analysis_method', 'results']

        for field in required_fields:
            assert field in sample_analysis_result

    @pytest.mark.unit
    def test_classification_result(self, sample_analysis_result):
        """Test classification result format"""
        results = sample_analysis_result['results']

        assert 'classification' in results
        assert 'confidence' in results
        assert results['confidence'] >= 0 and results['confidence'] <= 1

    @pytest.mark.unit
    def test_store_result_in_db(self, mock_get_db, sample_analysis_result):
        """Test storing analysis result in database"""
        results_collection = mock_get_db['analysis_results']

        results_collection.insert_one(sample_analysis_result)

        stored = results_collection.find_one({
            'recording_id': sample_analysis_result['recording_id']
        })

        assert stored is not None
        assert stored['results']['classification'] == 'normal'

    @pytest.mark.unit
    def test_update_recording_status(self, mock_get_db, sample_recording_for_analysis):
        """Test updating recording analysis status"""
        recordings_collection = mock_get_db['recordings']
        recordings_collection.insert_one(sample_recording_for_analysis)

        recordings_collection.update_one(
            {'_id': sample_recording_for_analysis['_id']},
            {'$set': {'analysis_status': 'completed'}}
        )

        recording = recordings_collection.find_one({
            '_id': sample_recording_for_analysis['_id']
        })
        assert recording['analysis_status'] == 'completed'
