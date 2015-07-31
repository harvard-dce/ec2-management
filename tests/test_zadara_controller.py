
import unittest
from mock import patch
from controllers import ZadaraController

class ZadaraControllerTests(unittest.TestCase):

    def test_init(self):

        z = ZadaraController('foo', security_token='bar')
        self.assertEqual(z.security_token, 'bar')
