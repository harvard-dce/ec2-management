
import logging
import unittest
import boto.ec2
from boto.exception import EC2ResponseError
from moto import mock_ec2
from mock import Mock, patch
from wrapt import ObjectProxy
from controllers.exceptions import ClusterException

import settings
from controllers import EC2Controller

class EC2ControllerTests(unittest.TestCase):

    def setUp(self):

        log = logging.getLogger()
        if not log.handlers:
            log.addHandler(logging.NullHandler())

        self.ec2_mock = mock_ec2()
        self.ec2_mock.start()
        #
        # # add some instances
        # conn = boto.ec2.connect_to_region('us-east-1')
        # conn.run_instances('ami-6e9ecc06').instances[0].add_tag('Name', 'dev99-admin')
        # conn.run_instances('ami-6e9ecc06').instances[0].add_tag('Name', 'dev99-engage')
        # conn.run_instances('ami-6e9ecc06').instances[0].add_tag('Name', 'dev99-worker')
        # conn.run_instances('ami-6e9ecc06').instances[0].add_tag('Name', 'dev99-worker')

    def tearDown(self):
        self.ec2_mock.stop()

    def test_init(self):

        ec2 = EC2Controller('dev99')
        self.assertEqual(ec2.prefix, 'dev99')

    @patch.object(boto.ec2.EC2Connection, 'describe_account_attributes')
    def test_connection_init(self, mock_daa):

        ec2 = EC2Controller('dev99')
        self.assertIsInstance(ec2.connection, boto.ec2.EC2Connection)

        ec2 = EC2Controller('dev99', region='us-west-1',
                            aws_access_key_id='bar',
                            aws_secret_access_key='baz')
        self.assertEqual(ec2.connection.aws_access_key_id, 'bar')
        self.assertEqual(ec2.connection.aws_secret_access_key,'baz')
        self.assertEqual(ec2.connection.region.name, 'us-west-1')

    @patch.object(boto.ec2.EC2Connection, 'describe_account_attributes')
    def test_connection_401(self, mock_daa):

        mock_daa.side_effect = EC2ResponseError('401', 'No ec2 for you!')
        ec2 = EC2Controller('dev99')
        self.assertRaises(SystemExit, ec2.create_connection)

    # have to use direct patch here as moto_ec2 doesn't support matching
    # tags using wildcards
    @patch.object(boto.ec2.EC2Connection, 'describe_account_attributes')
    @patch.object(boto.ec2.EC2Connection, 'get_only_instances')
    def test_instances(self, mock_goi, mock_daa):
        mock_goi.return_value = [
            Mock(tags={'Name': 'dev99-admin'}),
            Mock(tags={'Name': 'dev99-worker'})
        ]
        ec2 = EC2Controller('dev99')
        self.assertIsInstance(ec2.instances, list)
        self.assertEqual(len(ec2.instances), 2)
        mock_goi.assert_called_with(filters={'tag:Name': 'dev99-*'})

    def test_get_admin_node(self):
        ec2 = EC2Controller('dev99')
        ec2._instances = [
            Mock(id=1, tags={'Name': 'dev99-foo'}),
            Mock(id=2, tags={'Name': 'dev99-admin'}),
            Mock(id=3, tags={'Name': 'dev99-bar'})
        ]
        self.assertEqual(ec2.admin_instance.id, 2)

    def test_filtered_instances(self):
        ec2 = EC2Controller('dev99')
        ec2._instances = [
            Mock(id=1, tags={'Name': 'dev99-nfs'}),
            Mock(id=2, tags={'Name': 'dev99-admin'}),
            Mock(id=3, tags={'Name': 'dev99-db'}),
            Mock(id=4, tags={'Name': 'dev99-foo'}),
            Mock(id=5, tags={'Name': 'dev99-mysql'}),
            Mock(id=6, tags={'Name': 'dev99-engage'}),
            Mock(id=7, tags={'Name': 'dev99-worker'}),
            Mock(id=8, tags={'Name': 'dev99-baz'}),
            Mock(id=9, tags={'Name': 'dev99-worker'})
        ]
        support_ids = [x.id for x in ec2.support_instances]
        self.assertEqual(support_ids, [1, 3, 5])
        mh_ids = [x.id for x in ec2.mh_instances]
        self.assertEqual(mh_ids, [2, 6, 7, 9])

    @patch.object(EC2Controller, 'start_instances')
    def test_start_mh_instances(self, mock_method):
        ec2 = EC2Controller('dev99')
        ec2._instances = [
            Mock(id=1, tags={'Name': 'dev99-nfs'}),
            Mock(id=2, tags={'Name': 'dev99-admin'}),
            Mock(id=3, tags={'Name': 'dev99-db'}),
            Mock(id=4, tags={'Name': 'dev99-engage'}),
            Mock(id=5, tags={'Name': 'dev99-worker'}),
            Mock(id=6, tags={'Name': 'dev99-worker'}),
            Mock(id=7, tags={'Name': 'dev99-worker'}, state="running"),
            Mock(id=8, tags={'Name': 'dev99-worker'}, state="running")
        ]
        ec2.start_mh_instances()
        self.assertTrue(mock_method.called)
        started_instances = mock_method.call_args[0][0]
        started_ids = [x.id for x in started_instances]
        self.assertEqual(started_ids, [2, 4, 5, 6, 7, 8])

        ec2.start_mh_instances(num_workers=2)
        started_instances = mock_method.call_args[0][0]
        started_ids = [x.id for x in started_instances]
        self.assertEqual(started_ids, [2, 4])

        ec2.start_mh_instances(num_workers=3)
        started_instances = mock_method.call_args[0][0]
        started_ids = [x.id for x in started_instances]
        # this gets #6 rather than #5 because workers get
        # pop()ed off the non-running list
        self.assertEqual(started_ids, [2, 4, 6])

        ec2.start_mh_instances(num_workers=5)
        started_instances = mock_method.call_args[0][0]
        started_ids = [x.id for x in started_instances]
        self.assertEqual(started_ids, [2, 4, 6, 5])

    @patch.object(EC2Controller, 'start_zadara')
    @patch.object(EC2Controller, 'maintenance_off')
    @patch.object(EC2Controller, 'start_support_instances')
    @patch.object(EC2Controller, 'wait_for_state')
    @patch.object(EC2Controller, 'start_mh_instances')
    def test_start_cluster(self, mock_mh_inst, mock_wait, mock_supp_inst, mock_maint, mock_zadara):
        ec2 = EC2Controller('dev99')
        ec2._instances = [
            Mock(tags={'Name': 'dev99-worker'}),
            Mock(tags={'Name': 'dev99-worker'})
        ]
        ec2.start_cluster()
        mock_mh_inst.assert_called_once()
        mock_wait.assert_called_once()
        mock_supp_inst.assert_called_once()
        mock_maint.assert_called_once()
        mock_zadara.assert_called_once()

    @patch.object(EC2Controller, 'maintenance_off')
    @patch.object(EC2Controller, 'start_zadara')
    @patch.object(EC2Controller, 'start_support_instances')
    @patch.object(EC2Controller, 'wait_for_state')
    @patch.object(EC2Controller, 'start_mh_instances')
    def test_start_cluster_with_workers(self, mock_mh_inst, mock_wait, mock_supp_inst, mock_zadara, mock_maint):
        ec2 = EC2Controller('dev99')
        ec2._instances = [
            Mock(tags={'Name': 'dev99-worker'}),
            Mock(tags={'Name': 'dev99-worker'})
        ]
        ec2.start_cluster(num_workers=2)
        mock_mh_inst.assert_called_once_with(num_workers=2)
        mock_wait.assert_called_once()
        mock_supp_inst.assert_called_once()
        mock_maint.assert_called_once()
        mock_zadara.assert_called_once()

    @patch.object(EC2Controller, 'get_instances')
    def test_refresh_instances(self, mock_method):
        orig_mocks = [
            Mock(id=1, tags={'Name': 'dev99-nfs'}),
            Mock(id=2, tags={'Name': 'dev99-admin'}),
            Mock(id=3, tags={'Name': 'dev99-db'}),
            Mock(id=4, tags={'Name': 'dev99-engage'}),
            Mock(id=5, tags={'Name': 'dev99-worker'}),
            Mock(id=6, state="stopped", tags={'Name': 'dev99-worker'})
            ]
        mock_method.return_value = orig_mocks
        ec2 = EC2Controller('dev99')
        self.assertIsInstance(ec2.instances[0], ObjectProxy)

        # get a subset of the instances
        mh_instances = ec2.mh_instances
        workers = filter(ec2.is_worker, mh_instances)
        self.assertEqual(workers[1].state, "stopped")

        # supply a new set of "instances"
        new_mocks = [
            Mock(id=1, tags={'Name': 'dev99-nfs'}),
            Mock(id=2, tags={'Name': 'dev99-admin'}),
            Mock(id=3, tags={'Name': 'dev99-db'}),
            Mock(id=4, tags={'Name': 'dev99-engage'}),
            Mock(id=5, tags={'Name': 'dev99-worker'}),
            Mock(id=6, state="running", tags={'Name': 'dev99-worker'})
        ]
        mock_method.return_value = new_mocks
        ec2.refresh_instances()

        # check that we're dealing with new proxied objects
        self.assertNotEqual(
            mh_instances[0].__hash__(),
            orig_mocks[1].__hash__()
        )
        # check that our subsets contain the refreshed proxies
        self.assertEqual(
            mh_instances[0].__hash__(),
            new_mocks[1].__hash__()
        )
        self.assertEqual(
            workers[0].__hash__(),
            new_mocks[4].__hash__()
        )
        # see, we didn't touch the workers list but it's instances
        # reflect the new state
        self.assertEqual(workers[1].state, "running")


    def test_stop_held_cluster(self):
        ec2 = EC2Controller('dev99')
        for tag in ['hold', 'HOLD', 'Hold']:
            ec2._instances = [ Mock(tags={tag: 1, 'Name': 'foo'}) ]
            self.assertRaises(ClusterException, ec2.stop_cluster)

    @patch.object(EC2Controller, 'maintenance_on')
    @patch.object(EC2Controller, 'stop_zadara')
    @patch.object(EC2Controller, 'stop_support_instances')
    @patch.object(EC2Controller, 'stop_mh_instances')
    def test_stop_cluster(self, mock_mh, mock_support, mock_zadara, mock_maint):
        ec2 = EC2Controller('dev99')

        ec2._instances = []
        # should complain that there's no running admin instance
        self.assertRaises(ClusterException, ec2.stop_cluster)

        ec2._instances = [Mock(state="running", tags={'Name': 'dev99-admin'})]
        ec2.stop_cluster()
        mock_maint.assert_called_once()
        mock_mh.assert_called_once()
        mock_support.assert_called_once()
        mock_zadara.assert_called_once()

    def test_autoscale_disabled(self):
        ec2 = EC2Controller('dev99')
        ec2._instances = [Mock(state="running", tags={'Name': 'dev99-admin'})]
        self.assertFalse(ec2.autoscale_disabled())
        ec2._instances = [Mock(state="running", tags={'Name': 'dev99-admin', 'autoscale': 'on'})]
        self.assertFalse(ec2.autoscale_disabled())
        ec2._instances = [Mock(state="running", tags={'Name': 'dev99-admin', 'autoscale': 'Off'})]
        self.assertTrue(ec2.autoscale_disabled())

    def test_scale_to(self):
        ec2 = EC2Controller('dev99')
        ec2._instances = [
            Mock(state="running", tags={'Name': 'dev99-worker'}),
            Mock(state="running", tags={'Name': 'dev99-worker'}),
            Mock(state="running", tags={'Name': 'dev99-worker'})
        ]
        self.assertRaises(ClusterException, ec2.scale_to, 3)

        with patch.object(EC2Controller, 'scale_down') as scale_down:
            ec2.scale_to(1)
            scale_down.assert_called_with(2)

        with patch.object(EC2Controller, 'scale_up') as scale_up:
            ec2.scale_to(10)
            scale_up.assert_called_with(7)
