
import boto.opsworks
import logging

from ec2 import EC2Controller
import settings

log = logging.getLogger()

class OpsworksController(EC2Controller):

    def __init__(self, *args, **kwargs):
        self._opsworks = None
        super(OpsworksController, self).__init__(*args, **kwargs)

    @property
    def opsworks(self):
        if self._opsworks is None:
            self._opsworks = self.create_opsworks_connection()
        return self._opsworks

    def create_opsworks_connection(self):
        conn = boto.opsworks.connect_to_region(self.region,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )
        return conn
