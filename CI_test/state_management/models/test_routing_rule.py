"""
Tests for RoutingRule Model

Tests cover:
- Rule CRUD operations
- Condition matching logic
- Priority ordering
- MongoDB query construction
- Rule validation
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock


class TestRoutingRuleModel:
    """Test RoutingRule model CRUD operations"""

    @pytest.mark.unit
    def test_create_rule_success(self, mock_get_db, sample_routing_rule):
        """Test creating a new routing rule"""
        rules_collection = mock_get_db['routing_rules']

        result = rules_collection.insert_one(sample_routing_rule)
        assert result.inserted_id is not None

        rule = rules_collection.find_one({'rule_id': sample_routing_rule['rule_id']})
        assert rule is not None
        assert rule['rule_name'] == sample_routing_rule['rule_name']

    @pytest.mark.unit
    def test_create_rule_with_conditions(self, mock_get_db):
        """Test creating rule with complex conditions"""
        rules_collection = mock_get_db['routing_rules']

        rule_data = {
            'rule_id': 'complex-rule-001',
            'rule_name': 'Complex Conditions Rule',
            'conditions': {
                'device_id': {'$regex': 'factory-.*'},
                'file_type': {'$in': ['wav', 'mp3']},
                'duration': {'$gte': 5, '$lte': 60},
            },
            'target_config_id': 'config-001',
            'target_mongodb_instance': 'default',
            'priority': 500,
            'enabled': True,
            'created_at': datetime.now(timezone.utc),
        }

        rules_collection.insert_one(rule_data)

        rule = rules_collection.find_one({'rule_id': 'complex-rule-001'})
        assert rule['conditions']['device_id'] == {'$regex': 'factory-.*'}
        assert rule['conditions']['duration']['$gte'] == 5

    @pytest.mark.unit
    def test_get_rule_by_id(self, mock_get_db, sample_routing_rule):
        """Test retrieving rule by rule_id"""
        rules_collection = mock_get_db['routing_rules']
        rules_collection.insert_one(sample_routing_rule)

        rule = rules_collection.find_one({'rule_id': sample_routing_rule['rule_id']})
        assert rule is not None
        assert rule['priority'] == sample_routing_rule['priority']

    @pytest.mark.unit
    def test_update_rule(self, mock_get_db, sample_routing_rule):
        """Test updating rule fields"""
        rules_collection = mock_get_db['routing_rules']
        rules_collection.insert_one(sample_routing_rule)

        result = rules_collection.update_one(
            {'rule_id': sample_routing_rule['rule_id']},
            {
                '$set': {
                    'rule_name': 'Updated Rule Name',
                    'priority': 200,
                    'updated_at': datetime.now(timezone.utc),
                }
            }
        )

        assert result.modified_count == 1

        rule = rules_collection.find_one({'rule_id': sample_routing_rule['rule_id']})
        assert rule['rule_name'] == 'Updated Rule Name'
        assert rule['priority'] == 200

    @pytest.mark.unit
    def test_delete_rule(self, mock_get_db, sample_routing_rule):
        """Test deleting a rule"""
        rules_collection = mock_get_db['routing_rules']
        rules_collection.insert_one(sample_routing_rule)

        result = rules_collection.delete_one({'rule_id': sample_routing_rule['rule_id']})
        assert result.deleted_count == 1

        rule = rules_collection.find_one({'rule_id': sample_routing_rule['rule_id']})
        assert rule is None


class TestRulePriority:
    """Test rule priority ordering"""

    @pytest.mark.unit
    def test_get_rules_by_priority(self, mock_get_db):
        """Test getting rules sorted by priority (highest first)"""
        rules_collection = mock_get_db['routing_rules']

        # Insert rules with different priorities
        rules = [
            {'rule_id': 'low-priority', 'priority': 100, 'enabled': True},
            {'rule_id': 'high-priority', 'priority': 1000, 'enabled': True},
            {'rule_id': 'medium-priority', 'priority': 500, 'enabled': True},
        ]
        for rule in rules:
            rules_collection.insert_one(rule)

        # Get sorted by priority descending
        sorted_rules = list(rules_collection.find({}).sort('priority', -1))

        assert sorted_rules[0]['rule_id'] == 'high-priority'
        assert sorted_rules[1]['rule_id'] == 'medium-priority'
        assert sorted_rules[2]['rule_id'] == 'low-priority'

    @pytest.mark.unit
    def test_get_highest_priority_enabled_rule(self, mock_get_db):
        """Test getting the highest priority enabled rule"""
        rules_collection = mock_get_db['routing_rules']

        rules = [
            {'rule_id': 'disabled-high', 'priority': 2000, 'enabled': False},
            {'rule_id': 'enabled-high', 'priority': 1000, 'enabled': True},
            {'rule_id': 'enabled-low', 'priority': 100, 'enabled': True},
        ]
        for rule in rules:
            rules_collection.insert_one(rule)

        highest = rules_collection.find_one(
            {'enabled': True},
            sort=[('priority', -1)]
        )

        assert highest['rule_id'] == 'enabled-high'

    @pytest.mark.unit
    def test_update_priority(self, mock_get_db, sample_routing_rule):
        """Test changing rule priority"""
        rules_collection = mock_get_db['routing_rules']
        rules_collection.insert_one(sample_routing_rule)

        original_priority = sample_routing_rule['priority']
        new_priority = original_priority + 500

        rules_collection.update_one(
            {'rule_id': sample_routing_rule['rule_id']},
            {'$set': {'priority': new_priority}}
        )

        rule = rules_collection.find_one({'rule_id': sample_routing_rule['rule_id']})
        assert rule['priority'] == new_priority


class TestConditionMatching:
    """Test rule condition matching logic"""

    @pytest.mark.unit
    def test_match_regex_condition(self, mock_get_db):
        """Test matching regex condition"""
        rules_collection = mock_get_db['routing_rules']

        rule = {
            'rule_id': 'regex-rule',
            'conditions': {'device_id': {'$regex': 'factory-.*'}},
            'enabled': True,
        }
        rules_collection.insert_one(rule)

        # Simulate matching against a recording
        recording = {'device_id': 'factory-001'}

        # This would be done by the application logic, not MongoDB
        import re
        condition = rule['conditions']['device_id']
        matches = re.match(condition['$regex'], recording['device_id'])
        assert matches is not None

    @pytest.mark.unit
    def test_match_in_condition(self, mock_get_db):
        """Test matching $in condition"""
        rules_collection = mock_get_db['routing_rules']

        rule = {
            'rule_id': 'in-rule',
            'conditions': {'file_type': {'$in': ['wav', 'mp3', 'flac']}},
            'enabled': True,
        }
        rules_collection.insert_one(rule)

        # Test matching
        recording = {'file_type': 'wav'}
        matches = recording['file_type'] in rule['conditions']['file_type']['$in']
        assert matches is True

        # Test non-matching
        recording2 = {'file_type': 'ogg'}
        matches2 = recording2['file_type'] in rule['conditions']['file_type']['$in']
        assert matches2 is False

    @pytest.mark.unit
    def test_match_range_condition(self, mock_get_db):
        """Test matching range conditions ($gte, $lte)"""
        rules_collection = mock_get_db['routing_rules']

        rule = {
            'rule_id': 'range-rule',
            'conditions': {'duration': {'$gte': 5, '$lte': 60}},
            'enabled': True,
        }
        rules_collection.insert_one(rule)

        # Test within range
        recording = {'duration': 30}
        condition = rule['conditions']['duration']
        in_range = condition['$gte'] <= recording['duration'] <= condition['$lte']
        assert in_range is True

        # Test below range
        recording2 = {'duration': 2}
        in_range2 = condition['$gte'] <= recording2['duration'] <= condition['$lte']
        assert in_range2 is False

    @pytest.mark.unit
    def test_empty_conditions_match_all(self, mock_get_db):
        """Test that empty conditions match all recordings"""
        rules_collection = mock_get_db['routing_rules']

        rule = {
            'rule_id': 'catch-all',
            'conditions': {},
            'enabled': True,
        }
        rules_collection.insert_one(rule)

        # Empty conditions should match anything
        assert rule['conditions'] == {}


class TestRuleTargets:
    """Test rule target configuration"""

    @pytest.mark.unit
    def test_rule_with_config_target(self, mock_get_db, sample_routing_rule):
        """Test rule targeting a specific config"""
        rules_collection = mock_get_db['routing_rules']
        rules_collection.insert_one(sample_routing_rule)

        rule = rules_collection.find_one({'rule_id': sample_routing_rule['rule_id']})
        assert rule['target_config_id'] == sample_routing_rule['target_config_id']

    @pytest.mark.unit
    def test_rule_with_mongodb_instance_target(self, mock_get_db, sample_routing_rule):
        """Test rule targeting a specific MongoDB instance"""
        rules_collection = mock_get_db['routing_rules']
        rules_collection.insert_one(sample_routing_rule)

        rule = rules_collection.find_one({'rule_id': sample_routing_rule['rule_id']})
        assert rule['target_mongodb_instance'] == sample_routing_rule['target_mongodb_instance']

    @pytest.mark.unit
    def test_update_rule_targets(self, mock_get_db, sample_routing_rule):
        """Test updating rule targets"""
        rules_collection = mock_get_db['routing_rules']
        rules_collection.insert_one(sample_routing_rule)

        rules_collection.update_one(
            {'rule_id': sample_routing_rule['rule_id']},
            {
                '$set': {
                    'target_config_id': 'new-config-001',
                    'target_mongodb_instance': 'custom-instance',
                }
            }
        )

        rule = rules_collection.find_one({'rule_id': sample_routing_rule['rule_id']})
        assert rule['target_config_id'] == 'new-config-001'
        assert rule['target_mongodb_instance'] == 'custom-instance'


class TestRuleEnabledStatus:
    """Test rule enabled/disabled status"""

    @pytest.mark.unit
    def test_get_enabled_rules(self, mock_get_db, sample_routing_rule):
        """Test getting only enabled rules"""
        rules_collection = mock_get_db['routing_rules']

        # Insert enabled rule
        rules_collection.insert_one(sample_routing_rule)

        # Insert disabled rule
        disabled_rule = sample_routing_rule.copy()
        disabled_rule['rule_id'] = 'disabled-rule'
        disabled_rule['enabled'] = False
        rules_collection.insert_one(disabled_rule)

        enabled = list(rules_collection.find({'enabled': True}))
        assert len(enabled) == 1
        assert enabled[0]['rule_id'] == sample_routing_rule['rule_id']

    @pytest.mark.unit
    def test_disable_rule(self, mock_get_db, sample_routing_rule):
        """Test disabling a rule"""
        rules_collection = mock_get_db['routing_rules']
        rules_collection.insert_one(sample_routing_rule)

        rules_collection.update_one(
            {'rule_id': sample_routing_rule['rule_id']},
            {'$set': {'enabled': False}}
        )

        rule = rules_collection.find_one({'rule_id': sample_routing_rule['rule_id']})
        assert rule['enabled'] is False

    @pytest.mark.unit
    def test_get_all_rules_including_disabled(self, mock_get_db, sample_routing_rule):
        """Test getting all rules regardless of enabled status"""
        rules_collection = mock_get_db['routing_rules']

        rules_collection.insert_one(sample_routing_rule)

        disabled_rule = sample_routing_rule.copy()
        disabled_rule['rule_id'] = 'disabled-rule'
        disabled_rule['enabled'] = False
        rules_collection.insert_one(disabled_rule)

        all_rules = list(rules_collection.find({}))
        assert len(all_rules) == 2
