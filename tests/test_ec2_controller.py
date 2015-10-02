
import logging
import unittest
import boto.ec2
from boto.exception import EC2ResponseError
from moto import mock_ec2
from mock import Mock, patch, PropertyMock
from controllers.exceptions import ClusterException, ScalingException

from controllers import EC2Controller

class EC2ControllerTests(unittest.TestCase):

    def setUp(self):

        log = logging.getLogger()
        if not log.handlers:
            log.addHandler(logging.NullHandler())

        self.ec2_mock = mock_ec2()
        self.ec2_mock.start()

    def tearDown(self):
        self.ec2_mock.stop()

    def test_init(self):

        ec2 = EC2Controller('dev99')
        self.assertEqual(ec2.prefix, 'dev99')

    @patch.object(boto.ec2.EC2Connection, 'describe_account_attributes')
    @patch('controllers.ec2.settings', autospec=True)
    def test_connection_init(self, mock_settings, mock_daa):

        mock_settings.AWS_ACCESS_KEY_ID = 'bar'
        mock_settings.AWS_SECRET_ACCESS_KEY = 'baz'
        mock_settings.AWS_REGION = 'us-west-1'

        ec2 = EC2Controller('dev99')
        self.assertIsInstance(ec2.connection, boto.ec2.EC2Connection)

        self.assertEqual(ec2.connection.aws_access_key_id, 'bar')
        self.assertEqual(ec2.connection.aws_secret_access_key,'baz')
        self.assertEqual(ec2.connection.region.name, 'us-west-1')

    @patch.object(boto.ec2.EC2Connection, 'describe_account_attributes')
    def test_connection_401(self, mock_daa):

        mock_daa.side_effect = EC2ResponseError('401', 'No ec2 for you!')
        ec2 = EC2Controller('dev99')
        self.assertRaises(SystemExit, ec2.create_connection)

    def test_instance_tag(self):

        ec2 = EC2Controller('dev99')
        ec2._admin = Mock(tags={
            'foo': 'bar',
        })
        self.assertEqual(ec2.instance_tag('foo'), 'bar')
        self.assertEqual(ec2.instance_tag('foo', 'baz'), 'bar')
        self.assertIsNone(ec2.instance_tag('baz'))
        self.assertEqual(ec2.instance_tag('baz', 2), 2)

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
        ec2._admin = Mock(tags={'Name': 'dev99-admin'})
        self.assertFalse(ec2.autoscale_off)
        ec2._admin = Mock(tags={'Name': 'dev99-admin', 'ec2m:autoscale_off': 1})
        self.assertTrue(ec2.autoscale_off)
        self.assertRaises(ScalingException, ec2.autoscale)

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

    def test_billing_minutes(self):

        from utils import billed_minutes
        from freezegun import freeze_time

        with freeze_time('2015-08-25T20:00:00.000Z'):
            self.assertEqual(billed_minutes(Mock(launch_time='2015-08-25T19:41:56.000Z')), 18)
            self.assertEqual(billed_minutes(Mock(launch_time='2015-08-24T19:21:56.000Z')), 38)
            self.assertEqual(billed_minutes(Mock(launch_time='2015-08-24T09:21:56.000Z')), 38)

        with freeze_time('2015-08-25T00:01:00.000Z'):
            self.assertEqual(billed_minutes(Mock(launch_time='2015-08-25T00:00:00.000Z')), 1)
            self.assertEqual(billed_minutes(Mock(launch_time='2015-08-25T00:01:00.000Z')), 0)
            self.assertRaises(RuntimeError, billed_minutes, Mock(launch_time='2015-08-25T00:04:00.000Z'))

    def test_scale_down_no_running_workers(self):

        ec2 = EC2Controller('dev99')
        ec2._instances = [
            Mock(tags={'Name': 'dev99-worker'})
        ]
        self.assertRaisesRegexp(ScalingException, "1 running workers", ec2.scale_down, 1)

    @patch('controllers.ec2.settings', autospec=True)
    def test_scale_down_min_workers(self, mock_settings):

        ec2 = EC2Controller('dev99')
        ec2._instances = [
            Mock(tags={'Name': 'dev99-worker'}, state="running"),
            Mock(tags={'Name': 'dev99-worker'}, state="running"),
            Mock(tags={'Name': 'dev99-worker'}, state="running")
        ]
        mock_settings.EC2M_MIN_WORKERS = 3
        self.assertRaisesRegexp(ScalingException, 'violates min workers', ec2.scale_down, 1)

    @patch.object(EC2Controller, 'idle_workers', new_callable=PropertyMock)
    @patch('controllers.ec2.settings', autospec=True)
    def test_scale_down_no_idle_workers(self, mock_settings, mock_idle):
        ec2 = EC2Controller('dev99')
        ec2._instances = [
            Mock(tags={'Name': 'dev99-worker'}, state="running"),
            Mock(tags={'Name': 'dev99-worker'}, state="running")
        ]
        mock_idle.return_value = []
        mock_settings.EC2M_MIN_WORKERS = 0
        self.assertRaisesRegexp(ScalingException, "1 idle workers to stop", ec2.scale_down, 1)

    @patch.object(EC2Controller, 'idle_workers', new_callable=PropertyMock)
    @patch.object(EC2Controller, 'stop_instances')
    @patch('controllers.ec2.utils.billed_minutes')
    @patch('controllers.ec2.utils.total_uptime')
    @patch('controllers.ec2.settings', autospec=True)
    def test_scale_down_billing_check(self, mock_settings, mock_uptime, mock_minutes, mock_stop, mock_idle):
        ec2 = EC2Controller('dev99')
        workers = [
            Mock(id=1, tags={'Name': 'dev99-worker'},
                 state="running"),
            Mock(id=2, tags={'Name': 'dev99-worker'},
                 state="running"),
            Mock(id=3, tags={'Name': 'dev99-worker'},
                 state="running"),
        ]
        ec2._instances = workers
        mock_settings.EC2M_MIN_WORKERS = 0
        mock_settings.EC2M_IDLE_UPTIME_THRESHOLD = 50
        mock_idle.return_value = workers
        mock_minutes.side_effect = [10, 20, 30]
        self.assertRaisesRegexp(ScalingException, "No workers available", ec2.scale_down, 1, check_uptime=True)

        mock_minutes.reset_mock()
        mock_minutes.side_effect = [10, 52, 25]
        ec2.scale_down(1, check_uptime=True)
        args, kwargs = mock_stop.call_args
        # stop_instances should have been called with the 2nd mock instance
        self.assertEqual(len(args[0]), 1)
        self.assertEqual(args[0][0].id, 2)

        mock_minutes.reset_mock()
        mock_minutes.side_effect = [10, 52, 25]
        # should still scale down 1
        ec2.scale_down(2, check_uptime=True)
        args, kwargs = mock_stop.call_args
        self.assertEqual(len(args[0]), 1)
        self.assertEqual(args[0][0].id, 2)

        mock_uptime.reset_mock()
        mock_uptime.side_effect = [100, 300, 200]
        mock_minutes.reset_mock()
        # note: these values get used in the order of instances sorted by uptime
        mock_minutes.side_effect = [52, 18, 55]
        # should get the one with the most uptime
        ec2.scale_down(1, check_uptime=True)
        args, kwargs = mock_stop.call_args
        # stop_instances should have been called with the 3rd mock instance
        self.assertEqual(len(args[0]), 1)
        self.assertEqual(args[0][0].id, 2)

        mock_uptime.reset_mock()
        mock_uptime.side_effect = [100, 200, 300]
        mock_minutes.reset_mock()
        mock_minutes.side_effect = [52, 55, 18]
        # should get the one with the most billed minutes
        ec2.scale_down(2, check_uptime=True)
        args, kwargs = mock_stop.call_args
        # stop_instances should have been called with the 3rd & 2nd mock instance
        self.assertEqual(len(args[0]), 2)
        self.assertEqual(args[0][0].id, 3)
        self.assertEqual(args[0][1].id, 2)

    @patch.object(EC2Controller, 'maintenance_on')
    @patch.object(EC2Controller, 'maintenance_off')
    def test_in_maintenance(self, mock_maint_off, mock_maint_on):

        ec2 = EC2Controller('dev99')
        ec2._mh = Mock()
        ec2._mh.is_in_maintenance.return_value = False

        instances = [
            Mock(id='a', tags={'Name': 'a'}, state="running"),
            Mock(id='b', tags={'Name': 'b'}, state="running"),
            Mock(id='c', tags={'Name': 'c'}, state="running"),
        ]

        with ec2.in_maintenance(instances):
            args, kwargs = mock_maint_on.call_args
            self.assertEqual(args[0], instances)
            ec2.instance_actions = [
                {'instance': instances[0], 'action': 'stopped'}
            ]

            # mark one of the instances as "stopped" to verify it doesn't have
            # it's maintenance state restored in the finally block of the
            # context manager

        args, kwargs = mock_maint_off.call_args
        self.assertEqual(args[0], instances[1:])

    def test_instance_actions(self):

        ec2 = EC2Controller('dev99')
        inst = Mock()
        ec2._stop_instance(inst)
        self.assertEqual(ec2.instance_actions[0], {'instance': inst, 'action': 'stopped'})
        ec2._start_instance(inst)
        self.assertEqual(ec2.instance_actions[1], {'instance': inst, 'action': 'started'})
