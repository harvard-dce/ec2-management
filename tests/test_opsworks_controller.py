
import unittest
import boto.opsworks.layer1
import boto.ec2
from moto import mock_ec2
from mock import Mock, patch

from controllers import EC2Controller, OpsworksController
from controllers.exceptions import ClusterException

@patch.object(boto.ec2.EC2Connection, 'describe_account_attributes')
class OpsworksControllerTests(unittest.TestCase):

    @mock_ec2
    def test_connection_init(self, mock_daa):

        ops = OpsworksController('foo')
        self.assertIsInstance(ops.connection, boto.ec2.EC2Connection)

    @patch.object(boto.ec2.EC2Connection, 'get_only_instances')
    @patch.object(boto.opsworks.layer1.OpsWorksConnection, 'describe_instances')
    def test_instances(self, mock_di, mock_goi, mock_daa):
        mock_di.return_value = {
            'Instances': [
                {'InstanceId': 'asdf', 'Ec2InstanceId': 1},
                {'InstanceId': 'fdsa', 'Ec2InstanceId': 2},
                # this one should be ignored
                {'InstanceId': 'zxcv', 'Ec2InstanceId': 3, 'AutoScalingType': 'timer'},
            ]
        }
        mock_goi.return_value = [
            Mock(id=1, tags={
                'opsworks:stack': 'foobar',
                'Name': 'abc',
                'opsworks:layer:admin': 1
            }),
            Mock(id=2, tags={
                'opsworks:stack': 'foobar',
                'Name': 'def',
                'opsworks:layer:workers': 1
            }),
            Mock(id=3, tags={
                'opsworks:stack': 'foobar',
                'Name': 'ghi',
                'opsworks:layer:workers': 1
            }),
        ]
        ops = OpsworksController('foobar')
        ops._stack = {'StackId': 123}
        self.assertIsInstance(ops.instances, list)
        self.assertEqual(len(ops.instances), 2)
        mock_goi.assert_called_with(filters={'tag:opsworks:stack': 'foobar'})

    def test_is_admin(self, mock_daa):

        ops = OpsworksController('foobar')
        self.assertTrue(ops.is_admin(Mock(tags={
            'opsworks:layer:admin': 'Foo'
        })))
        self.assertFalse(ops.is_admin(Mock(tags={
            'opsworks:layer:foo': 'Bar'
        })))

    def test_is_worker(self, mock_daa):

        ops = OpsworksController('foobar')
        self.assertTrue(ops.is_worker(Mock(tags={
            'opsworks:layer:workers': 'Foo'
        })))
        self.assertFalse(ops.is_worker(Mock(tags={
            'opsworks:layer:werkerz': 'Bar'
        })))

    def test_is_mh(self, mock_daa):

        ops = OpsworksController('foobar')
        self.assertTrue(ops.is_mh(Mock(tags={
            'opsworks:layer:workers': 'Worker'
        })))
        self.assertTrue(ops.is_mh(Mock(tags={
            'opsworks:layer:admin': 'Admin'
        })))
        self.assertTrue(ops.is_mh(Mock(tags={
            'opsworks:layer:engage': 'Engage'
        })))
        self.assertFalse(ops.is_mh(Mock(tags={
            'opsworks:layer:storage': 'Storage'
        })))

    def test_stack(self, mock_daa):
        ops = OpsworksController('foobar')
        ops._opsworks = Mock(describe_stacks = Mock(
            return_value={
                'Stacks': [
                    { 'Name': 'foobar', 'StackId': 1},
                    { 'Name': 'froboz', 'StackId': 2}
                ]
            }
        ))
        self.assertEqual(ops.stack['StackId'], 1)

        ops = OpsworksController('fizzbuzz')
        self.assertRaises(ClusterException, getattr, ops, 'stack')


