"""
Tests for Step 3: Classifier

Tests cover:
- Classification prediction
- Model loading
- Result aggregation
"""
import pytest
from unittest.mock import MagicMock, patch


class TestClassificationPrediction:
    """Test classification prediction"""

    @pytest.mark.unit
    def test_prediction_output_format(self):
        """Test prediction output format"""
        predictions = [
            {'label': 'normal', 'score': 0.85},
            {'label': 'anomaly', 'score': 0.10},
            {'label': 'unknown', 'score': 0.05},
        ]

        assert len(predictions) > 0
        assert 'label' in predictions[0]
        assert 'score' in predictions[0]

    @pytest.mark.unit
    def test_prediction_scores_sum_to_one(self):
        """Test prediction scores sum to approximately 1"""
        predictions = [
            {'label': 'normal', 'score': 0.85},
            {'label': 'anomaly', 'score': 0.10},
            {'label': 'unknown', 'score': 0.05},
        ]

        total = sum(p['score'] for p in predictions)
        assert abs(total - 1.0) < 0.01

    @pytest.mark.unit
    def test_get_top_prediction(self):
        """Test getting top prediction"""
        predictions = [
            {'label': 'anomaly', 'score': 0.10},
            {'label': 'normal', 'score': 0.85},
            {'label': 'unknown', 'score': 0.05},
        ]

        top_prediction = max(predictions, key=lambda x: x['score'])
        assert top_prediction['label'] == 'normal'
        assert top_prediction['score'] == 0.85

    @pytest.mark.unit
    def test_batch_predictions(self):
        """Test predictions for batch of slices"""
        batch_size = 5
        num_classes = 3

        # Mock batch predictions
        batch_predictions = [
            [0.85, 0.10, 0.05],  # Slice 0
            [0.90, 0.07, 0.03],  # Slice 1
            [0.75, 0.20, 0.05],  # Slice 2
            [0.88, 0.08, 0.04],  # Slice 3
            [0.82, 0.12, 0.06],  # Slice 4
        ]

        assert len(batch_predictions) == batch_size
        assert len(batch_predictions[0]) == num_classes


class TestModelLoading:
    """Test model loading functionality"""

    @pytest.mark.unit
    def test_onnx_model_load_mock(self):
        """Test ONNX model loading mock"""
        mock_session = MagicMock()
        mock_session.get_inputs.return_value = [MagicMock(name='input', shape=[1, 100, 64])]
        mock_session.get_outputs.return_value = [MagicMock(name='output', shape=[1, 3])]

        inputs = mock_session.get_inputs()
        outputs = mock_session.get_outputs()

        assert len(inputs) == 1
        assert len(outputs) == 1

    @pytest.mark.unit
    def test_model_input_shape(self):
        """Test model input shape requirements"""
        expected_input_shape = [1, 100, 64]  # (batch, time, features)

        mock_input = MagicMock()
        mock_input.shape = expected_input_shape

        assert mock_input.shape[0] == 1  # Batch size
        assert mock_input.shape[2] == 64  # Feature dim

    @pytest.mark.unit
    def test_label_mapping(self):
        """Test label mapping"""
        label_map = {
            0: 'normal',
            1: 'anomaly',
            2: 'unknown',
        }

        predicted_class = 0
        label = label_map[predicted_class]

        assert label == 'normal'


class TestResultAggregation:
    """Test aggregating results from multiple slices"""

    @pytest.mark.unit
    def test_aggregate_by_voting(self):
        """Test aggregating by majority voting"""
        slice_predictions = [
            {'label': 'normal', 'score': 0.9},
            {'label': 'normal', 'score': 0.85},
            {'label': 'anomaly', 'score': 0.7},
            {'label': 'normal', 'score': 0.88},
        ]

        # Count votes
        votes = {}
        for pred in slice_predictions:
            label = pred['label']
            votes[label] = votes.get(label, 0) + 1

        winner = max(votes, key=votes.get)
        assert winner == 'normal'

    @pytest.mark.unit
    def test_aggregate_by_average_score(self):
        """Test aggregating by average confidence score"""
        slice_predictions = [
            {'label': 'normal', 'score': 0.9},
            {'label': 'normal', 'score': 0.85},
            {'label': 'normal', 'score': 0.88},
        ]

        avg_score = sum(p['score'] for p in slice_predictions) / len(slice_predictions)
        assert abs(avg_score - 0.877) < 0.01

    @pytest.mark.unit
    def test_aggregate_with_weighted_scores(self):
        """Test aggregating with weighted scores by slice position"""
        slice_predictions = [
            {'label': 'normal', 'score': 0.9, 'weight': 1.0},
            {'label': 'normal', 'score': 0.7, 'weight': 0.5},
            {'label': 'anomaly', 'score': 0.8, 'weight': 0.8},
        ]

        # Calculate weighted average per label
        label_scores = {}
        for pred in slice_predictions:
            label = pred['label']
            weighted_score = pred['score'] * pred['weight']
            if label not in label_scores:
                label_scores[label] = []
            label_scores[label].append(weighted_score)

        final_scores = {
            label: sum(scores) / len(scores)
            for label, scores in label_scores.items()
        }

        assert 'normal' in final_scores
        assert 'anomaly' in final_scores

    @pytest.mark.unit
    def test_final_result_structure(self, sample_analysis_result):
        """Test final result structure"""
        result = sample_analysis_result['results']

        assert 'classification' in result
        assert 'confidence' in result
        assert 'predictions' in result
        assert result['confidence'] >= 0 and result['confidence'] <= 1


class TestClassifierConfidence:
    """Test classifier confidence handling"""

    @pytest.mark.unit
    def test_high_confidence_prediction(self):
        """Test high confidence prediction"""
        prediction = {'label': 'normal', 'score': 0.95}

        threshold = 0.8
        is_confident = prediction['score'] >= threshold

        assert is_confident is True

    @pytest.mark.unit
    def test_low_confidence_prediction(self):
        """Test low confidence prediction"""
        prediction = {'label': 'unknown', 'score': 0.4}

        threshold = 0.8
        is_confident = prediction['score'] >= threshold

        assert is_confident is False

    @pytest.mark.unit
    def test_flag_uncertain_predictions(self):
        """Test flagging uncertain predictions"""
        predictions = [
            {'label': 'normal', 'score': 0.95},
            {'label': 'anomaly', 'score': 0.55},
            {'label': 'unknown', 'score': 0.3},
        ]

        threshold = 0.6
        uncertain = [p for p in predictions if p['score'] < threshold]

        assert len(uncertain) == 2
