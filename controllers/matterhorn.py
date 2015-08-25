# -*- coding: utf-8 -*-

import pyhorn
# this is a hack until pyhorn can get it's caching controls sorted out
pyhorn.client._session._is_cache_disabled = True

import logging
import settings
from exceptions import *

log = logging.getLogger('ec2-manager')

class MatterhornController():

    @classmethod
    def client_factory(cls, api_url):
        client = pyhorn.MHClient(api_url,
                                 user=settings.MATTERHORN_ADMIN_SERVER_USER,
                                 passwd=settings.MATTERHORN_ADMIN_SERVER_PASS
                                 )
        try:
            log.debug("verifying pyhorn client connection")
            assert client.me() is not None
            return client
        except Exception, e:
            # this could be anything: communication problem, unexpected response, etc
            log.debug("pyhorn client failed to connect")
            raise MatterhornCommunicationException(
                "Error connecting to Matterhorn API at {}: {}".format(
                    api_url, str(e)
                )
            )

    def __init__(self, api_url, dry_run=False):
        self.dry_run = dry_run
        self.instance_host_map = {}
        self.client = MatterhornController.client_factory(api_url)

    def create_instance_host_map(self, instances):
        hosts = dict((x.base_url, x) for x in self.client.hosts())

        def find_host_url(inst):
            candidate_hosts = [
                inst.private_ip_address, # most nodes
                inst.public_dns_name # some public-facing engage nodes
            ]
            host_url = None
            for h in candidate_hosts:
                for scheme in ['http','https']:
                    candidate_url = scheme + '://' + h
                    if candidate_url in hosts:
                        host_url = candidate_url
                        del hosts[host_url]
            # returns the last one found
            # is assumption correct to prefer https?
            return host_url

        for inst in instances:
            url = find_host_url(inst)
            if url is not None:
                log.debug("Mapping %s to Matterhorn host url %s", inst.id, url)
                self.instance_host_map[inst.id] = url
            else:
                log.debug("Failed to find host url for %s", inst.id)

        # check if we missed any hosts (e.g., the engage node usually)
        unmapped = [x for x in instances if x.id not in self.instance_host_map]
        if len(hosts) != len(unmapped) or len(hosts) > 1 or len(unmapped) > 1:
            # big trouble
            raise MatterhornControllerException(
                "Unmappable instances <-> mh hosts!: {}".format(
                    ','.join(x.tags['Name'] for x in unmapped),
                    ','.join(x.base_url for x in hosts)
                )
            )
        elif len(hosts) == len(unmapped) == 1:
            # NOTE: this makes a pretty ugly assumption but there's currently no
            # other alternative for associating the engage instance with it's
            # mh node since the engage node's 'host_url' value doesn't
            # always correspond to an ip/dns name attributes of the aws instance
            log.debug("Assuming host url for %s is %s", unmapped[0].id, hosts.keys()[0])
            self.instance_host_map[unmapped[0].id] = hosts.keys()[0]

    def service_stats(self):
        return self.client.statistics()

    def queued_job_count(self, service_types=None):
        stats = self.client.statistics()
        if service_types is None:
            return stats.queued_jobs()
        else:
            return sum(
                stats.queued_jobs(type=type) for type in service_types
            )

    def is_idle(self, inst):
        stats = self.client.statistics()
        host_url = self.instance_host_map[inst.id]
        log.debug("Checking idleness state of %s, %s", inst.id, host_url)
        running_jobs = stats.running_jobs(host=host_url)
        log.debug("%s has %d running jobs", host_url, running_jobs)
        return running_jobs == 0

    def get_host_for_instance(self, inst):
        hosts = self.client.hosts()
        host_url = self.instance_host_map[inst.id]
        try:
            return next(x for x in hosts if x.base_url == host_url)
        except StopIteration:
            raise MatterhornControllerException(
                "No Matterhorn host found matching {}".format(host_url)
            )

    def is_in_maintenance(self, inst):
        host = self.get_host_for_instance(inst)
        return host.maintenance

    def maintenance_off(self, inst):
        host = self.get_host_for_instance(inst)
        log.debug("Setting maintenance to off for %s, %s", inst.id, host.base_url)
        host.set_maintenance(False)

    def maintenance_on(self, inst):
        host = self.get_host_for_instance(inst)
        log.debug("Setting maintenance to on for %s, %s", inst.id, host.base_url)
        host.set_maintenance(True)

