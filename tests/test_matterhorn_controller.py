
from mock import patch
import unittest
from controllers import MatterhornController

class MatterhornControllerTests(unittest.TestCase):

    def test_init(self):
        mh = MatterhornController('foo')
        self.assertEqual(mh.cluster_prefix, 'foo')
