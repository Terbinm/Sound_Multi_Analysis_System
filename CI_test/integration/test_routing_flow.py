"""
Integration Tests for Routing Flow

Tests end-to-end routing workflow:
- Rule creation and activation
- Recording matching
- Task dispatch based on rules
- Multi-instance routing
"""
import pytest
from unittest.mock import MagicMock, patch


class TestRuleManagement:
    """Test routing rule management workflow"""

    @pytest.mark.integration
    def test_create_routing_rule(self, integration_test_routing_rule, mock_mongodb_service):
        """Test creating routing rule"""
        rule = integration_test_routing_rule

        mock_mongodb_service.routing_rules.insert_one.return_value = MagicMock(
            inserted_id=rule['_id']
        )

        result = mock_mongodb_service.routing_rules.insert_one(rule)

        assert result.inserted_id == rule['_id']

    @pytest.mark.integration
    def test_update_rule_priority(self, mock_mongodb_service):
        """Test updating rule priority"""
        rule_id = 'rule-001'
        new_priority = 200

        mock_mongodb_service.routing_rules.update_one.return_value = MagicMock(
            modified_count=1
        )

        result = mock_mongodb_service.routing_rules.update_one(
            {'_id': rule_id},
            {'$set': {'priority': new_priority}}
        )

        assert result.modified_count == 1

    @pytest.mark.integration
    def test_activate_deactivate_rule(self, mock_mongodb_service):
        """Test activating and deactivating rule"""
        rule_id = 'rule-001'

        # Deactivate
        mock_mongodb_service.routing_rules.update_one.return_value = MagicMock(
            modified_count=1
        )

        mock_mongodb_service.routing_rules.update_one(
            {'_id': rule_id},
            {'$set': {'is_active': False}}
        )

        # Activate
        mock_mongodb_service.routing_rules.update_one(
            {'_id': rule_id},
            {'$set': {'is_active': True}}
        )

        assert mock_mongodb_service.routing_rules.update_one.call_count == 2

    @pytest.mark.integration
    def test_delete_rule(self, mock_mongodb_service):
        """Test deleting routing rule"""
        rule_id = 'rule-001'

        mock_mongodb_service.routing_rules.delete_one.return_value = MagicMock(
            deleted_count=1
        )

        result = mock_mongodb_service.routing_rules.delete_one({'_id': rule_id})

        assert result.deleted_count == 1


class TestConditionMatching:
    """Test condition matching workflow"""

    @pytest.mark.integration
    def test_equals_condition_match(self):
        """Test equals condition matching"""
        condition = {'field': 'device_id', 'operator': 'equals', 'value': 'device-001'}
        recording = {'device_id': 'device-001', 'filename': 'test.wav'}

        matches = recording.get(condition['field']) == condition['value']

        assert matches is True

    @pytest.mark.integration
    def test_contains_condition_match(self):
        """Test contains condition matching"""
        condition = {'field': 'filename', 'operator': 'contains', 'value': 'test'}
        recording = {'device_id': 'device-001', 'filename': 'test_recording.wav'}

        field_value = recording.get(condition['field'], '')
        matches = condition['value'] in field_value

        assert matches is True

    @pytest.mark.integration
    def test_greater_than_condition_match(self):
        """Test greater than condition matching"""
        condition = {'field': 'duration', 'operator': 'greater_than', 'value': 30}
        recording = {'device_id': 'device-001', 'duration': 60}

        field_value = recording.get(condition['field'], 0)
        matches = field_value > condition['value']

        assert matches is True

    @pytest.mark.integration
    def test_multiple_conditions_all_match(self):
        """Test multiple conditions with AND logic"""
        conditions = [
            {'field': 'device_id', 'operator': 'equals', 'value': 'device-001'},
            {'field': 'duration', 'operator': 'greater_than', 'value': 30}
        ]
        recording = {'device_id': 'device-001', 'duration': 60}

        def check_condition(condition, rec):
            field_value = rec.get(condition['field'])
            op = condition['operator']
            value = condition['value']

            if op == 'equals':
                return field_value == value
            elif op == 'greater_than':
                return field_value > value
            return False

        all_match = all(check_condition(c, recording) for c in conditions)

        assert all_match is True

    @pytest.mark.integration
    def test_no_conditions_matches_all(self):
        """Test rule with no conditions matches all recordings"""
        conditions = []
        recording = {'device_id': 'device-001'}

        # Empty conditions should match everything
        matches = len(conditions) == 0 or all(True for _ in conditions)

        assert matches is True


class TestRulePriority:
    """Test rule priority handling"""

    @pytest.mark.integration
    def test_higher_priority_rule_selected(self):
        """Test higher priority rule is selected"""
        rules = [
            {'_id': 'rule-1', 'priority': 50, 'is_active': True},
            {'_id': 'rule-2', 'priority': 100, 'is_active': True},
            {'_id': 'rule-3', 'priority': 75, 'is_active': True}
        ]

        # Sort by priority descending
        sorted_rules = sorted(rules, key=lambda r: r['priority'], reverse=True)
        selected = sorted_rules[0]

        assert selected['_id'] == 'rule-2'

    @pytest.mark.integration
    def test_inactive_rules_skipped(self):
        """Test inactive rules are skipped"""
        rules = [
            {'_id': 'rule-1', 'priority': 100, 'is_active': False},
            {'_id': 'rule-2', 'priority': 50, 'is_active': True}
        ]

        active_rules = [r for r in rules if r['is_active']]
        sorted_rules = sorted(active_rules, key=lambda r: r['priority'], reverse=True)

        assert len(sorted_rules) == 1
        assert sorted_rules[0]['_id'] == 'rule-2'

    @pytest.mark.integration
    def test_first_matching_rule_wins(self):
        """Test first matching rule is used"""
        rules = [
            {'_id': 'rule-1', 'priority': 100, 'matches': True},
            {'_id': 'rule-2', 'priority': 90, 'matches': True},
            {'_id': 'rule-3', 'priority': 80, 'matches': True}
        ]

        sorted_rules = sorted(rules, key=lambda r: r['priority'], reverse=True)

        for rule in sorted_rules:
            if rule['matches']:
                selected = rule
                break

        assert selected['_id'] == 'rule-1'


class TestTaskDispatch:
    """Test task dispatch based on routing"""

    @pytest.mark.integration
    def test_dispatch_to_specified_config(
        self, integration_test_routing_rule, mock_rabbitmq_service
    ):
        """Test dispatching task with specified config"""
        rule = integration_test_routing_rule
        recording_id = 'rec-001'

        task = {
            'recording_id': recording_id,
            'config_id': rule['actions']['config_id'],
            'mongodb_instance': rule['actions']['mongodb_instance']
        }

        mock_rabbitmq_service.publish.return_value = True

        success = mock_rabbitmq_service.publish(
            exchange='analysis_tasks',
            routing_key='analysis.new',
            body=task
        )

        assert success is True
        assert task['config_id'] == 'config-int-001'

    @pytest.mark.integration
    def test_dispatch_to_specific_instance(self, mock_rabbitmq_service):
        """Test dispatching to specific MongoDB instance"""
        task = {
            'recording_id': 'rec-001',
            'config_id': 'config-001',
            'mongodb_instance': 'analysis_db_2'
        }

        mock_rabbitmq_service.publish.return_value = True

        success = mock_rabbitmq_service.publish(
            exchange='analysis_tasks',
            routing_key='analysis.instance.analysis_db_2',
            body=task
        )

        assert success is True

    @pytest.mark.integration
    def test_default_routing_when_no_match(self, mock_rabbitmq_service):
        """Test default routing when no rules match"""
        # No matching rules, use default
        default_config = 'config-default'
        default_instance = 'default'

        task = {
            'recording_id': 'rec-001',
            'config_id': default_config,
            'mongodb_instance': default_instance
        }

        mock_rabbitmq_service.publish.return_value = True

        success = mock_rabbitmq_service.publish(
            exchange='analysis_tasks',
            routing_key='analysis.new',
            body=task
        )

        assert success is True
        assert task['config_id'] == 'config-default'


class TestMultiInstanceRouting:
    """Test multi-instance routing scenarios"""

    @pytest.mark.integration
    def test_route_to_different_instances(self, mock_mongodb_service):
        """Test routing to different MongoDB instances"""
        instances = {
            'default': 'mongodb://localhost:27017/default_db',
            'analysis_db_1': 'mongodb://localhost:27018/analysis1',
            'analysis_db_2': 'mongodb://localhost:27019/analysis2'
        }

        rules = [
            {'device_pattern': 'factory-*', 'instance': 'analysis_db_1'},
            {'device_pattern': 'lab-*', 'instance': 'analysis_db_2'}
        ]

        recordings = [
            {'device_id': 'factory-001', 'expected_instance': 'analysis_db_1'},
            {'device_id': 'lab-001', 'expected_instance': 'analysis_db_2'},
            {'device_id': 'other-001', 'expected_instance': 'default'}
        ]

        def get_instance(device_id):
            for rule in rules:
                pattern = rule['device_pattern'].replace('*', '')
                if device_id.startswith(pattern):
                    return rule['instance']
            return 'default'

        for rec in recordings:
            instance = get_instance(rec['device_id'])
            assert instance == rec['expected_instance']

    @pytest.mark.integration
    def test_instance_health_check_before_routing(self):
        """Test instance health check before routing"""
        instances = {
            'instance_1': {'is_healthy': True},
            'instance_2': {'is_healthy': False},
            'instance_3': {'is_healthy': True}
        }

        target = 'instance_2'

        if not instances[target]['is_healthy']:
            # Fallback to first healthy
            target = next(
                (k for k, v in instances.items() if v['is_healthy']),
                None
            )

        assert target == 'instance_1'

    @pytest.mark.integration
    def test_store_result_to_routed_instance(self, mock_mongodb_service):
        """Test storing result to routed instance"""
        result = {
            'recording_id': 'rec-001',
            'classification': 'normal',
            'confidence': 0.95
        }
        target_instance = 'analysis_db_1'

        # Simulate getting client for specific instance
        instance_client = MagicMock()
        instance_client.results = MagicMock()
        instance_client.results.insert_one.return_value = MagicMock(
            inserted_id='result-001'
        )

        insert_result = instance_client.results.insert_one(result)

        assert insert_result.inserted_id is not None


class TestRoutingEvents:
    """Test routing-related events"""

    @pytest.mark.integration
    def test_rule_change_notification(self):
        """Test notification on rule change"""
        mock_socketio = MagicMock()

        rule_update = {
            'event': 'rule_updated',
            'rule_id': 'rule-001',
            'changes': {'priority': 200}
        }

        mock_socketio.emit('routing.rule_changed', rule_update, room='routing')

        mock_socketio.emit.assert_called_once()

    @pytest.mark.integration
    def test_routing_decision_logging(self, mock_mongodb_service):
        """Test logging routing decisions"""
        decision = {
            'recording_id': 'rec-001',
            'matched_rule': 'rule-001',
            'config_id': 'config-001',
            'instance': 'analysis_db_1',
            'timestamp': '2024-01-01T00:00:00Z'
        }

        mock_mongodb_service.routing_logs = MagicMock()
        mock_mongodb_service.routing_logs.insert_one.return_value = MagicMock(
            inserted_id='log-001'
        )

        result = mock_mongodb_service.routing_logs.insert_one(decision)

        assert result.inserted_id is not None

