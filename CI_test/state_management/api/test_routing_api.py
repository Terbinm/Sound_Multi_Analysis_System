"""
Tests for Routing API

Tests cover:
- Routing rule CRUD endpoints
- Rule matching
- Priority management
"""
import pytest
import re
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


class TestRoutingAPIRead:
    """Test routing rule read endpoints"""

    @pytest.mark.unit
    def test_get_all_rules(self, sample_routing_rules_in_db):
        """Test getting all routing rules"""
        rules_collection = sample_routing_rules_in_db['routing_rules']

        rules = list(rules_collection.find({}))
        assert len(rules) >= 2

    @pytest.mark.unit
    def test_get_enabled_rules_only(self, mock_get_db, sample_routing_rule):
        """Test getting only enabled rules"""
        rules_collection = mock_get_db['routing_rules']

        rules_collection.insert_one(sample_routing_rule)

        disabled = sample_routing_rule.copy()
        disabled['rule_id'] = 'disabled-rule'
        disabled['enabled'] = False
        rules_collection.insert_one(disabled)

        enabled = list(rules_collection.find({'enabled': True}))
        assert len(enabled) == 1

    @pytest.mark.unit
    def test_get_rules_sorted_by_priority(self, mock_get_db):
        """Test getting rules sorted by priority"""
        rules_collection = mock_get_db['routing_rules']

        rules_collection.insert_one({'rule_id': 'low', 'priority': 100, 'enabled': True})
        rules_collection.insert_one({'rule_id': 'high', 'priority': 1000, 'enabled': True})
        rules_collection.insert_one({'rule_id': 'med', 'priority': 500, 'enabled': True})

        sorted_rules = list(rules_collection.find({}).sort('priority', -1))

        assert sorted_rules[0]['rule_id'] == 'high'
        assert sorted_rules[1]['rule_id'] == 'med'
        assert sorted_rules[2]['rule_id'] == 'low'

    @pytest.mark.unit
    def test_get_rule_by_id(self, sample_routing_rules_in_db, sample_routing_rule):
        """Test getting rule by ID"""
        rules_collection = sample_routing_rules_in_db['routing_rules']

        rule = rules_collection.find_one({'rule_id': sample_routing_rule['rule_id']})
        assert rule is not None


class TestRoutingAPICreate:
    """Test routing rule creation endpoints"""

    @pytest.mark.unit
    def test_create_rule(self, mock_get_db):
        """Test creating new routing rule"""
        rules_collection = mock_get_db['routing_rules']

        new_rule = {
            'rule_id': 'new-rule-001',
            'rule_name': 'New Rule',
            'conditions': {'device_id': {'$regex': 'new-.*'}},
            'target_config_id': 'config-001',
            'target_mongodb_instance': 'default',
            'priority': 500,
            'enabled': True,
            'created_at': datetime.now(timezone.utc),
        }

        result = rules_collection.insert_one(new_rule)
        assert result.inserted_id is not None

    @pytest.mark.unit
    def test_create_rule_with_complex_conditions(self, mock_get_db):
        """Test creating rule with complex conditions"""
        rules_collection = mock_get_db['routing_rules']

        rule = {
            'rule_id': 'complex-rule',
            'conditions': {
                'device_id': {'$regex': 'factory-.*'},
                'file_type': {'$in': ['wav', 'mp3']},
                'duration': {'$gte': 5, '$lte': 60},
            },
            'target_config_id': 'config-001',
            'priority': 800,
            'enabled': True,
        }

        rules_collection.insert_one(rule)

        created = rules_collection.find_one({'rule_id': 'complex-rule'})
        assert 'device_id' in created['conditions']
        assert 'file_type' in created['conditions']


class TestRoutingAPIUpdate:
    """Test routing rule update endpoints"""

    @pytest.mark.unit
    def test_update_rule(self, mock_get_db, sample_routing_rule):
        """Test updating routing rule"""
        rules_collection = mock_get_db['routing_rules']
        rules_collection.insert_one(sample_routing_rule)

        rules_collection.update_one(
            {'rule_id': sample_routing_rule['rule_id']},
            {'$set': {'rule_name': 'Updated Rule', 'priority': 999}}
        )

        updated = rules_collection.find_one({'rule_id': sample_routing_rule['rule_id']})
        assert updated['rule_name'] == 'Updated Rule'
        assert updated['priority'] == 999

    @pytest.mark.unit
    def test_update_rule_conditions(self, mock_get_db, sample_routing_rule):
        """Test updating rule conditions"""
        rules_collection = mock_get_db['routing_rules']
        rules_collection.insert_one(sample_routing_rule)

        new_conditions = {
            'device_id': {'$regex': 'updated-.*'},
            'file_type': 'wav',
        }

        rules_collection.update_one(
            {'rule_id': sample_routing_rule['rule_id']},
            {'$set': {'conditions': new_conditions}}
        )

        updated = rules_collection.find_one({'rule_id': sample_routing_rule['rule_id']})
        assert updated['conditions']['device_id']['$regex'] == 'updated-.*'


class TestRoutingAPIDelete:
    """Test routing rule deletion endpoints"""

    @pytest.mark.unit
    def test_delete_rule(self, mock_get_db, sample_routing_rule):
        """Test deleting routing rule"""
        rules_collection = mock_get_db['routing_rules']
        rules_collection.insert_one(sample_routing_rule)

        result = rules_collection.delete_one({'rule_id': sample_routing_rule['rule_id']})
        assert result.deleted_count == 1

    @pytest.mark.unit
    def test_delete_nonexistent_rule(self, mock_get_db):
        """Test deleting non-existent rule"""
        rules_collection = mock_get_db['routing_rules']

        result = rules_collection.delete_one({'rule_id': 'nonexistent'})
        assert result.deleted_count == 0


class TestRuleMatching:
    """Test rule matching functionality"""

    @pytest.mark.unit
    def test_match_regex_condition(self):
        """Test matching regex condition"""
        rule_condition = {'device_id': {'$regex': 'factory-.*'}}
        recording = {'device_id': 'factory-001'}

        pattern = rule_condition['device_id']['$regex']
        matches = re.match(pattern, recording['device_id'])

        assert matches is not None

    @pytest.mark.unit
    def test_match_in_condition(self):
        """Test matching $in condition"""
        rule_condition = {'file_type': {'$in': ['wav', 'mp3', 'flac']}}
        recording = {'file_type': 'wav'}

        matches = recording['file_type'] in rule_condition['file_type']['$in']
        assert matches is True

    @pytest.mark.unit
    def test_match_range_condition(self):
        """Test matching range condition"""
        rule_condition = {'duration': {'$gte': 5, '$lte': 60}}
        recording = {'duration': 30}

        cond = rule_condition['duration']
        matches = cond['$gte'] <= recording['duration'] <= cond['$lte']
        assert matches is True

    @pytest.mark.unit
    def test_find_matching_rule_highest_priority(self, mock_get_db):
        """Test finding the highest priority matching rule"""
        rules_collection = mock_get_db['routing_rules']

        # Insert rules with different priorities
        rules_collection.insert_one({
            'rule_id': 'low-priority',
            'conditions': {},  # Matches all
            'priority': 100,
            'enabled': True,
        })
        rules_collection.insert_one({
            'rule_id': 'high-priority',
            'conditions': {},  # Matches all
            'priority': 1000,
            'enabled': True,
        })

        # Get highest priority enabled rule
        rule = rules_collection.find_one(
            {'enabled': True},
            sort=[('priority', -1)]
        )

        assert rule['rule_id'] == 'high-priority'

    @pytest.mark.unit
    def test_no_matching_rule(self):
        """Test when no rule matches"""
        rule_condition = {'device_id': {'$regex': 'special-.*'}}
        recording = {'device_id': 'normal-device'}

        pattern = rule_condition['device_id']['$regex']
        matches = re.match(pattern, recording['device_id'])

        assert matches is None


class TestRulePriorityManagement:
    """Test rule priority management"""

    @pytest.mark.unit
    def test_reorder_rules(self, mock_get_db):
        """Test reordering rules by priority"""
        rules_collection = mock_get_db['routing_rules']

        rules_collection.insert_one({'rule_id': 'r1', 'priority': 100})
        rules_collection.insert_one({'rule_id': 'r2', 'priority': 200})

        # Swap priorities
        rules_collection.update_one({'rule_id': 'r1'}, {'$set': {'priority': 200}})
        rules_collection.update_one({'rule_id': 'r2'}, {'$set': {'priority': 100}})

        r1 = rules_collection.find_one({'rule_id': 'r1'})
        r2 = rules_collection.find_one({'rule_id': 'r2'})

        assert r1['priority'] == 200
        assert r2['priority'] == 100

    @pytest.mark.unit
    def test_get_priority_order(self, mock_get_db):
        """Test getting rules in priority order"""
        rules_collection = mock_get_db['routing_rules']

        for i, priority in enumerate([300, 100, 500, 200]):
            rules_collection.insert_one({
                'rule_id': f'rule-{i}',
                'priority': priority,
            })

        rules = list(rules_collection.find({}).sort('priority', -1))
        priorities = [r['priority'] for r in rules]

        assert priorities == sorted(priorities, reverse=True)
