
import mock
import unittest
from moto import mock_ec2
from controllers import AWSController

class AWSControllerTests(unittest.TestCase):

    @mock_ec2
    def test_defaults(self):

        aws = AWSController('foo')
        self.assertEqual(aws.retries, 6)
