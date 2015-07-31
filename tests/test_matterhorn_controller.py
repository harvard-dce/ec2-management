
from mock import patch
import unittest
from controllers import MatterhornController

class MatterhornControllerTests(unittest.TestCase):

    def test_init(self):
        with patch('logging.getLogger') as mock:
            mh = MatterhornController('foo')
            mock.assert_called_with('foo.MatterhornController')
