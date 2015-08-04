
import unittest
import boto.opsworks
import boto.ec2
from moto import mock_ec2
from mock import patch

from controllers import OpsworksController

class OpsworksControllerTests(unittest.TestCase):

    @mock_ec2
    @patch.object(boto.ec2.EC2Connection, 'describe_account_attributes')
    def test_connection_init(self, mock_daa):

        ops = OpsworksController('foo')
        self.assertIsInstance(ops.connection, boto.ec2.EC2Connection)
        self.assertIsInstance(ops.opsworks, boto.opsworks.layer1.OpsWorksConnection)
