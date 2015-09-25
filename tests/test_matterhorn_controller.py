
import requests
import unittest
from mock import Mock, patch

import pyhorn
from pyhorn.endpoints import ServiceStatistics, ServiceHost

from controllers import MatterhornController, MatterhornCommunicationException

class MatterhornControllerTests(unittest.TestCase):

    def setUp(self):

        # prevent controller's client connection check from failing
        self.client_me_mock = patch.object(pyhorn.MHClient, 'me')
        self.client_me_mock.start()

        # fail all requests!
        self.fail_requests = patch.object(
            requests.Session, 'send',
            return_value="", side_effect=RuntimeError("Uh-oh! Something made an actual request!")
        )
        self.fail_requests.start()

    def tearDown(self):
        self.client_me_mock.stop()
        self.fail_requests.stop()

    def test_init(self):
        mh = MatterhornController('http://example.edu')
        self.assertEqual(mh.client.base_url, 'http://example.edu')

    def test_init_client_fail(self):
        self.client_me_mock.stop()
        self.assertRaises(MatterhornCommunicationException, MatterhornController, 'http://example.edu')
        self.client_me_mock.start()

    def test_create_instance_host_map(self):
        mh = MatterhornController('http://example.edu')
        fake_hosts = [
            { "base_url": "http://1.1.1.1" },
            { "base_url": "http://2.2.2.2" },
            { "base_url": "https://baz" },
            { "base_url": "https://fizzbuzz" },
            { "base_url": "http://blergh-private"}
        ]
        mh.client.hosts = Mock(return_value=[ServiceHost(x, mh.client) for x in fake_hosts])
        fake_instances = [
            Mock(id=1,
                 private_ip_address='1.1.1.1',
                 public_dns_name="foo",
                 private_dns_name="foo-private"
                 ),
            Mock(id=2,
                 private_ip_address='2.2.2.2',
                 public_dns_name="bar",
                 private_dns_name="bar-private"
                 ),
            Mock(id=3,
                 private_ip_address='3.3.3.3',
                 public_dns_name="baz",
                 private_dns_name="baz-private"
                 ),
            # this one won't explicitly match a host entry so the mapping
            # will be (hackishly) assumed
            Mock(id=4,
                 private_ip_address='4.4.4.4',
                 public_dns_name="frobozz",
                 private_dns_name="frobozz-private"
                 ),
            Mock(id=5,
                 private_ip_address='5.5.5.5',
                 public_dns_name="blergh",
                 private_dns_name="blergh-private"
                 ),
        ]
        mh.create_instance_host_map(fake_instances)
        expected = {
            1: "http://1.1.1.1",
            2: "http://2.2.2.2",
            3: "https://baz",
            4: "https://fizzbuzz",
            5: "http://blergh-private"
        }
        self.assertEqual(mh.instance_host_map, expected)

    def test_service_stats(self):
        mh = MatterhornController('http://example.edu')
        mh.client.statistics = Mock(return_value={'foo': 1})
        stats = mh.service_stats()
        self.assertEqual(stats['foo'], 1)

    def test_queued_job_count(self):
        """
        mockapalooza!
        """
        mh = MatterhornController('http://example.edu')
        mh.client = Mock()
        mh.client.workflows.return_value = [
            Mock(operations=[
                Mock(id="foo",
                     state="RUNNING",
                     job=Mock(children=[
                         Mock(status="RUNNING"),
                         Mock(status="QUEUED"),
                     ])),
                Mock(id="foo",
                     state="RUNNING",
                     job=Mock(children=[
                         Mock(status="RUNNING"),
                         Mock(status="QUEUED")
                     ])),
            ]),
            Mock(operations=[
                Mock(id="foo",
                     state="RUNNING",
                     job=Mock(children=[
                         Mock(status="QUEUED"),
                         Mock(status="QUEUED")
                     ])),
                Mock(id="bar",
                     state="RUNNING",
                     job=Mock(children=[
                         Mock(status="QUEUED"),
                         Mock(status="QUEUED")
                     ])),
                Mock(id="foo",
                     state="INSTANTIATED")
            ]),
            Mock(operations=[
                Mock(id="foo",
                     state="INSTANTIATED"),
                Mock(id="foo",
                     state="RUNNING",
                     job=Mock(children=[
                         Mock(status="RUNNING"),
                         Mock(status="RUNNING")
                     ])),
                Mock(id="bar",
                     state="WAITING",
                     job=Mock(children=[
                         Mock(status="QUEUED"),
                         Mock(status="QUEUED")
                     ])),
                Mock(id="baz",
                     state="RUNNING",
                     job=Mock(children=[
                         Mock(status="RUNNING"),
                         Mock(status="QUEUED")
                     ]))
            ])
        ]
        self.assertEqual(mh.queued_job_count(), 9)
        self.assertEqual(mh.queued_job_count(operation_types=["foo"]), 4)
        self.assertEqual(mh.queued_job_count(operation_types=["bar"]), 4)
        self.assertEqual(mh.queued_job_count(operation_types=["foo","bar"]), 8)
        self.assertEqual(mh.queued_job_count(operation_types=["foo","bar","baz"]), 9)

    def test_is_idle(self):

        mh = MatterhornController('http://example.edu')
        mh.instance_host_map = {
            1: "http://foo",
            2: "http://bar"
        }
        fake_stats = {
            'statistics': {
                'service': [
                    {
                        'running': "1",
                        'serviceRegistration': { 'host': 'http://foo' }
                    },
                    {
                        'running': "0",
                        'serviceRegistration': { 'host': 'http://foo' }
                    },
                    {
                        'running': "0",
                        'serviceRegistration': { 'host': 'http://bar' }
                    },
                    {
                        'running': "0",
                        'serviceRegistration': { 'host': 'http://bar' }
                    },
                    {
                        'running': "1",
                        'serviceRegistration': { 'host': 'http://foo' }
                    }
                ]
            }
        }
        mh.client.statistics = Mock(return_value=ServiceStatistics(fake_stats, mh.client))
        self.assertFalse(mh.is_idle(Mock(id=1)))
        self.assertTrue(mh.is_idle(Mock(id=2)))

    def test_is_in_maintenance(self):
        mh = MatterhornController('http://example.edu')
        mh.instance_host_map = {
            1: "http://foo",
            2: "http://bar"
        }
        fake_hosts = [
            {
                "base_url": "http://foo",
                "maintenance": True
            },
            {
                "base_url": "http://bar",
                "maintenance": False
            }
        ]
        mh.client.hosts = Mock(return_value=[ServiceHost(x, mh.client) for x in fake_hosts])
        self.assertTrue(mh.is_in_maintenance(Mock(id=1)))
        self.assertFalse(mh.is_in_maintenance(Mock(id=2)))
