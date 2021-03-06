
import re
import sys
import time
import stopit
import logging
from wrapt import ObjectProxy
from operator import itemgetter
from contextlib import contextmanager
from functools import wraps
from requests.exceptions import Timeout as RequestsTimeout

import boto.ec2.networkinterface
from boto.exception import EC2ResponseError

import utils
import settings
from exceptions import *
from zadara import ZadaraController
from matterhorn import MatterhornController

log = logging.getLogger('ec2-manager')

def admin_is_up(cmd):
    """
    confirm that the Matterhorn admin instance is running
    """
    @wraps(cmd)
    def wrapped(ec2, *args, **kwargs):
        if not ec2.admin_is_up():
            raise ClusterException(
                "This command requires the Matterhorn admin instance to be running"
            )
        return cmd(ec2, *args, **kwargs)
    return wrapped

def log_before_after_stats(cmd):
    @wraps(cmd)
    def wrapped(ec2, *args, **kwargs):
        utils.log_status_summary(ec2.status_summary())
        result = cmd(ec2, *args, **kwargs)
        utils.log_action_summary(ec2.action_summary())
        return result
    return wrapped

class EC2Instance(ObjectProxy):
    pass


class EC2Controller(object):

    def __init__(self, cluster_prefix, dry_run=False, force=False):

        self.prefix = cluster_prefix
        self.dry_run = dry_run
        self.force = force
        self.region = settings.AWS_REGION

        self.aws_access_key_id = settings.AWS_ACCESS_KEY_ID
        self.aws_secret_access_key = settings.AWS_SECRET_ACCESS_KEY
        self.aws_profile = settings.AWS_PROFILE

        self.instance_actions = []

    @property
    def connection(self):
        if not hasattr(self, '_connection'):
            self._connection = self.create_connection()
        return self._connection

    @property
    def aws_connect_params(self):

        if self.aws_access_key_id is not None:
            return {
                'aws_access_key_id': self.aws_access_key_id,
                'aws_secret_access_key': self.aws_secret_access_key
            }
        elif self.aws_profile is not None:
            return {'profile_name': self.aws_profile}
        else:
            return {}

    def create_connection(self):

        conn = boto.ec2.connect_to_region(self.region, **self.aws_connect_params)

        try:
            conn.describe_account_attributes()
            log.debug("boto.ec2 connection to region %s established", self.region)
            return conn
        except EC2ResponseError, e:
            if e.status == '401':
                log.error(e.message)
                log.error("Unable to establish boto.ec2 connection. Check your aws credentials.")
                sys.exit(1)
            else:
                raise

    @property
    def instances(self):
        if not hasattr(self, '_instances'):
            self._instances = map(EC2Instance, self.get_instances())
        return self._instances

    @property
    def instance_filter(self):
        return { 'tag:Name': self.prefix + '-*' }

    def get_instances(self):
        log.debug("Fetching instances using filter: %s", str(self.instance_filter))
        instances = self.connection.get_only_instances(filters=self.instance_filter)

        for inst in instances:
            log.debug("Found: %s, %s, %s, %s, %s, monitor %s",
                inst.tags['Name'],
                inst.id,
                inst.state,
                inst.ip_address,
                inst.private_ip_address,
                inst.monitoring_state
            )
        return instances

    def refresh_instances(self):
        log.debug("Refreshing instances list")
        for inst in self._instances:
            inst.update()

    def instance_tag(self, tag, default=None):
        if tag in self.admin_instance.tags:
            log.debug(
                "Found instance tag %s, value: %s", tag, self.admin_instance.tags[tag]
            )
            return self.admin_instance.tags[tag]
        return default

    @property
    def autoscale_off(self):
        return self.instance_tag('ec2m:autoscale_off', False)

    def is_admin(self, instance):
        return instance.tags['Name'].endswith('admin')

    def is_worker(self, instance):
        return instance.tags['Name'].endswith('worker')

    _support_pattern = re.compile('(' + '|'.join(settings.NON_MH_SUFFIXES) + ')$')
    def is_support(self, instance):
        return re.search(self._support_pattern, instance.tags['Name'])

    _mh_pattern = re.compile('(' + '|'.join(settings.MH_SUFFIXES) + ')$')
    def is_mh(self, instance):
        return re.search(self._mh_pattern, instance.tags['Name'])

    def is_stopped(self, instance):
        return instance.state == "stopped"

    def is_running(self, instance):
        return instance.state == "running"

    def on_hold(self, instance):
        return "hold" in [x.lower() for x in instance.tags.keys()]

    @property
    def admin_instance(self):
        if not hasattr(self, '_admin'):
            try:
                self._admin = next(x for x in self.instances if self.is_admin(x))
            except StopIteration:
                raise ClusterException("Can't find an admin node for your cluster!")
        return self._admin

    def admin_is_up(self):
        return self.is_running(self.admin_instance)

    @property
    def support_instances(self):
        return filter(self.is_support, self.instances)

    @property
    def mh_instances(self):
        return filter(self.is_mh, self.instances)

    @property
    def workers(self):
        return filter(self.is_worker, self.mh_instances)

    def get_idle_workers(self):
        return filter(
            lambda inst: self.is_running(inst) and self.mh.is_idle(inst),
            self.workers
        )

    def instance(self, id):
        try:
            return next(x for x in self.instances if x.id == id)
        except StopIteration:
            raise ClusterException("Can't find an instance with id %s", id)

    @property
    def zadara(self):
        if not hasattr(self, '_zadara'):
            # disable zadara control for now
            self._zadara = None

        return self._zadara

    @property
    def mh(self):
        if not hasattr(self, '_mh'):
            mh_api_url = 'http://' + self.admin_instance.ip_address
            self._mh = MatterhornController(mh_api_url, dry_run=self.dry_run)
            self._mh.create_instance_host_map(self.mh_instances)
        return self._mh

    def status_summary(self):

        summary = {
            'cluster': self.prefix,
            'instances_online': len(filter(self.is_running, self.instances)),
            'workers': len(self.workers),
            'workers_online': len(filter(self.is_running, self.workers)),
            'instances': []
        }

        try:
            log.debug("Trying to fetch stats from Matterhorn")
            with stopit.SignalTimeout(5, swallow_exc=False):
                stats = self.mh.service_stats()
                mh_is_up = True
        except (RequestsTimeout,
                stopit.TimeoutException,
                MatterhornCommunicationException), e:
            log.debug("Unable to communicate with Matterhorn: %s", str(e))
            mh_is_up = False

        if mh_is_up:
            summary.update({
                'queued_jobs': self.mh.queued_job_count(),
                'queued_high_load_jobs': self.mh.queued_job_count(
                    operation_types=settings.MAJOR_LOAD_OPERATION_TYPES
                ),
                'running_jobs': stats.running_jobs(),
            })

        for inst in self.instances:
            inst_summary = {
                'id': inst.id,
                'name': inst.tags['Name'],
                'state': inst.state,
            }
            if mh_is_up and self.is_mh(inst):
                try:
                    mh_host = self.mh.get_host_for_instance(inst)
                    inst_summary['maintenance'] = mh_host.maintenance
                    inst_summary['mh_host'] = mh_host.base_url
                except MatterhornControllerException:
                    inst_summary['mh_host'] = 'unknown'
            summary['instances'].append(inst_summary)

        return summary

    def action_summary(self):
        stopped = [x['instance'] for x in self.instance_actions if x['action'] == 'stopped']
        started = [x['instance'] for x in self.instance_actions if x['action'] == 'started']
        summary = {
            'stopped': len(stopped),
            'stopped_ids': ', '.join(x.id for x in stopped),
            'started': len(started),
            'started_ids': ', '.join(x.id for x in started)
        }
        return summary

    def add_instance_action(self, instance, action):
        self.instance_actions.append({
            'instance': instance,
            'action': action
        })

    def start_instance(self, instance):
        try:
            log.debug("Starting: {0}, {1}, {2}, {3}, {4}".format(
                instance.tags['Name'], instance.id,  instance.state,
                instance.ip_address, instance.private_ip_address))
            self._start_instance(instance)
            self.add_instance_action(instance, 'started')
        except EC2ResponseError, e:
            log.error("Error starting instance: %s", e.errors)

    def _start_instance(self, instance):
        instance.start(dry_run=self.dry_run)

    def stop_instance(self, instance):
        try:
            log.debug("Stopping: {0}, {1}, {2}, {3}, {4}".format(
                instance.tags['Name'], instance.id,  instance.state,
                instance.ip_address, instance.private_ip_address))
            self._stop_instance(instance)
            self.add_instance_action(instance, 'stopped')
        except EC2ResponseError, e:
            log.error("Error stopping instance: %s", e.errors)

    def _stop_instance(self, instance):
        instance.stop(dry_run=self.dry_run)

    def start_support_instances(self, wait=True):
        self.start_instances(self.support_instances, wait)

    def start_mh_instances(self, wait=True, num_workers=None):

        # NOTE: this method does not check/enforce that the number of
        # eventual running workers == num_workers, only that at least
        # num_workers are running/started
        instances = self.mh_instances

        if num_workers:
            # we know we want to start the non-workers
            instances = filter(lambda inst: not self.is_worker(inst), self.mh_instances)

            # but maybe not all of these
            workers_to_start = self.workers
            running = filter(self.is_running, self.workers)
            workers_needed = num_workers

            for inst in running:
                workers_to_start.remove(inst)
                workers_needed -= 1

            while workers_needed > 0:
                try:
                    instances.append(workers_to_start.pop())
                    workers_needed -= 1
                except IndexError:
                    log.error("No more non-running instances to start!")
                    break

        self.start_instances(instances, wait)

    def start_instances(self, instances, wait=True):
        for inst in instances:
            self.start_instance(inst)

        if wait:
            def running_callback(cb_instances):
                self.refresh_instances()
                running = filter(self.is_running, cb_instances)
                return len(running) == len(cb_instances)
            log.debug("Waiting for %d instances to start...", len(instances))
            self.wait_for_state(running_callback, instances)
        else:
            self.refresh_instances()

    def wait_for_state(self, state_cb, instances, success_msg=None):

        if self.dry_run:
            log.info("Dry-run enabled. Not waiting.")
            return

        if success_msg is None:
            success_msg = "Instances now in desired state"

        retries = settings.EC2M_WAIT_RETRIES
        while retries > 0:
            if state_cb(instances):
                log.debug(success_msg)
                return
            retries -= 1
            log.debug("Waiting for desired state... (retries remaining: %d)", retries)
            time.sleep(settings.EC2M_WAIT_TIME)

        if self.force:
            log.warning("Retries exceeded but 'force' enabled. Proceeding anyway.")
        else:
            raise GiveUpWaitingException("Retries exceeded. Giving up.")

    def start_cluster(self, num_workers=None):
        log.info("Bringing up cluster")

        if num_workers is None:
            num_workers = settings.EC2M_MIN_WORKERS

        # check that we have enough workers available
        log.debug("Workers requested: %d; available: %d", num_workers, len(self.workers))
        if len(self.workers) < num_workers:
            raise ClusterException(
                "Cluster only has {} workers but was asked to start with {}!".format(
                    len(self.workers), num_workers)
            )

        # but not too many running already
        running = filter(self.is_running, self.workers)
        log.debug("Workers already running: %d", len(running))
        if len(running) > num_workers:
            raise ClusterException(
                "Cluster already has {} running workers but was asked to start with {}!".format(
                    len(running), num_workers
                )
            )

        # not less than EC2M_MIN_WORKERS setting
        if num_workers < settings.EC2M_MIN_WORKERS:
            log.warning("Workers requested %d is less than min workers %d",
                        num_workers, settings.EC2M_MIN_WORKERS)
            if not self.force:
                raise ClusterException("Aborting. Cluster must be started with "
                                       "at least {} workers".format(settings.EC2M_MIN_WORKERS))

        # and not more than our EC2M_MAX_WORKERS setting
        if num_workers > settings.EC2M_MAX_WORKERS:
            log.warning("%d workers exceeds max workers setting of %d",
                        num_workers, settings.EC2M_MAX_WORKERS)
            if not self.force:
                raise ClusterException("Aborting. Not allowed to start that many workers.")

        log.info("Starting zadara...")
        self.start_zadara()

        log.info("Starting support nodes...")
        self.start_support_instances()

        log.info("Starting MH nodes...")
        self.start_mh_instances(num_workers=num_workers)

        def api_callback(cb_instances):
            api_url = 'http://' + self.admin_instance.ip_address
            try:
                # set a short timeout as we're polling for the api to be up
                with stopit.SignalTimeout(5, swallow_exc=False):
                    client = MatterhornController.client_factory(api_url)
                return True
            except Exception:
                pass

        log.info("Waiting for Matterhorn API to be online...")
        self.wait_for_state(api_callback, [], success_msg="Matterhorn API is up")

        log.info("Taking cluster out of maintenance...")
        self.maintenance_off()

        log.info("Cluster is now online")

    def stop_mh_instances(self, wait=True):

        def idle_callback(cb_instances):
            idle = filter(self.mh.is_idle, cb_instances)
            return len(idle) == len(cb_instances)

        log.debug("Waiting for workers to be idle...")
        self.wait_for_state(idle_callback, self.workers)

        self.stop_instances(self.mh_instances, wait)

    def stop_support_instances(self, wait=True):
        self.stop_instances(self.support_instances, wait)

    def stop_instances(self, instances, wait=True):

        for inst in instances:
            self.stop_instance(inst)

        if wait:
            def stopped_callback(cb_instances):
                self.refresh_instances()
                stopped = filter(self.is_stopped, cb_instances)
                return len(stopped) == len(cb_instances)
            log.debug("Waiting for %d instances to stop...", len(instances))
            self.wait_for_state(stopped_callback, instances)
        else:
            self.refresh_instances()

    def stop_cluster(self):

        log.info("Bringing down cluster")

        held_instances = filter(self.on_hold, self.instances)
        if len(held_instances):
            log.warning("Instances {} are tagged \"hold\".".format(
                ",".join(x.tags['Name'] for x in held_instances)
            ))
            if not self.force:
                raise ClusterException("Aborting due to held instances")

        if not self.is_running(self.admin_instance):
            raise ClusterException("Admin instance is not running.")

        log.info("Putting nodes in maintenance...")
        self.maintenance_on()

        log.info("Stopping Matterhorn nodes...")
        self.stop_mh_instances()

        log.info("Stopping support nodes...")
        self.stop_support_instances()

        log.info("Stopping zadara...")
        self.stop_zadara()

        log.info("Cluster is now stopped")

    def start_zadara(self):

        if self.zadara is None:
            log.info("No Zadara VPSA for this cluster")
            return
        elif self.dry_run:
            log.info("Dry-run enabled. Not starting zadara.")
            return

        self.zadara.start()

    def stop_zadara(self):

        if self.zadara is None:
            log.info("No Zadara VPSA for this cluster")
            return
        elif self.dry_run:
            log.info("Dry-run enabled. Not stopping zadara.")
            return

        self.zadara.stop()

    def autoscale(self):

        if self.autoscale_off:
            raise ScalingException("Autoscaling disabled for this cluster")

        with self.in_maintenance(self.workers):

            queued_jobs = self.mh.queued_job_count(
                operation_types=settings.MAJOR_LOAD_OPERATION_TYPES
            )
            log.debug("%d queued jobs of operation type(s) %s.",
                      queued_jobs,
                      settings.MAJOR_LOAD_OPERATION_TYPES
                      )
            if queued_jobs > settings.EC2M_MAX_QUEUED_JOBS:
                log.info("Attempting to scale up.")
                self.scale_up(num_workers=1)
                return

            idle = self.get_idle_workers()
            log.debug("%d idle workers", len(idle))
            if len(idle) > settings.EC2M_MIN_IDLE_WORKERS:
                log.info("Attempting to scale down.")
                self.scale_down(num_workers=1, check_uptime=True,
                                stop_candidates=idle)
                return

    def scale_to(self, num_workers):

        running_workers = filter(self.is_running, self.workers)
        if len(running_workers) == num_workers:
            raise ClusterException("Cluster already at {} running workers".format(num_workers))
        elif len(running_workers) > num_workers:
            self.scale_down(len(running_workers) - num_workers)
        else:
            self.scale_up(num_workers - len(running_workers))

    def scale(self, direction, num_workers):

        if num_workers is None:
            num_workers = 1

        if direction == "up":
            self.scale_up(num_workers)
        elif direction == "down":
            with self.in_maintenance(self.workers):
                self.scale_down(num_workers)

    def scale_up(self, num_workers):

        running = filter(self.is_running, self.workers)
        stopped = filter(self.is_stopped, self.workers)

        # do we have enough non-running workers?
        if len(stopped) < num_workers:
            raise ScalingException(
                "Cluster does not have {} to start!".format(num_workers))

        # are we allowed to scale up by num_workers?
        if len(running) + num_workers > settings.EC2M_MAX_WORKERS:
            error_msg = "Starting {} workers violates max workers setting of {}".format(
                num_workers, settings.EC2M_MAX_WORKERS
            )
            if self.force:
                log.warning(error_msg)
            else:
                raise ScalingException(error_msg)

        instances_to_start = stopped[:num_workers]
        log.info("Starting %d worker(s)", len(instances_to_start))
        self.start_instances(instances_to_start, wait=False)

    def scale_down(self, num_workers, check_uptime=False, stop_candidates=None):

        running = filter(self.is_running, self.workers)

        # do we have that many running workers?
        if len(running) - num_workers < 0:
            raise ScalingException(
                "Cluster does not have {} running workers to stop".format(
                    num_workers
                ))

        if len(running) - num_workers < settings.EC2M_MIN_WORKERS:
            error_msg = "Stopping {} workers violates min workers setting of {}".format(
                num_workers, settings.EC2M_MIN_WORKERS
            )
            if self.force:
                log.warning(error_msg)
            else:
                raise ScalingException(error_msg)

        if stop_candidates is None:
            stop_candidates = self.get_idle_workers()

        if len(stop_candidates) < num_workers:
            error_msg = "Cluster does not have {} idle workers to stop".format(
                num_workers
            )
            if self.force:
                log.warning(error_msg)
                # just pick from running workers
                stop_candidates = filter(self.is_running, self.workers)
            else:
                raise ScalingException(error_msg)

        # helps ensure we're stopping the longest-running, and also that we'll
        # stop the same instance again if (for some reason) an earlier stop
        # action got wedged
        stop_candidates = sorted(stop_candidates, key=utils.total_uptime, reverse=True)

        if not check_uptime:
            instances_to_stop = stop_candidates[:num_workers]
        else:
            # only stop idle workers if they're approaching an uptime near to being
            # divisible by 60m since we're paying for the full hour anyway
            instances_to_stop = []
            for inst in stop_candidates:
                minutes = utils.billed_minutes(inst)
                log.debug("Instance %s has used %d minutes of it's billing hour",
                          inst.id, minutes)
                if minutes < settings.EC2M_IDLE_UPTIME_THRESHOLD:
                    if self.force:
                        log.warning("Stopping %s anyway because --force", inst.id)
                    else:
                        log.debug("Not stopping %s", inst.id)
                        continue
                instances_to_stop.append(inst)
                if len(instances_to_stop) == num_workers:
                    break

            if not len(instances_to_stop):
                raise ScalingException("No workers available to stop")

        log.info("Shutting down %d worker(s)", len(instances_to_stop))
        self.stop_instances(instances_to_stop, wait=False)

    @contextmanager
    def in_maintenance(self, instances=None, restore_state=True):
        """Context manager for ensuring matterhorn nodes are in maintenance
        state while performing operations"""

        if instances is None:
            instances = self.mh_instances

        log.debug("Ensuring instances %s in maintenance",
                  ','.join(x.tags['Name'] for x in instances))

        # make sure we're only dealing with nodes that are running
        # and not already in maintenance
        for_maintenance = filter(
            lambda inst: self.is_running(inst) and not self.mh.is_in_maintenance(inst),
            instances
        )

        if not len(for_maintenance):
            # don't do anything
            yield
        else:
            try:
                self.maintenance_on(for_maintenance)
                log.debug("Instances %s put in maintenance",
                          ','.join(x.tags['Name'] for x in for_maintenance))
                yield # let calling code do it's thing
            except Exception, e:
                log.debug("Exception caught during 'in_maintenance' context: %s, %s", type(e), str(e))
                raise
            finally:
                if restore_state:
                    stopped = [x['instance'] for x in self.instance_actions if x['action'] == 'stopped']
                    for inst in stopped:
                        if inst in for_maintenance:
                            log.debug("not toggling maintenance for %s as it was stopped", inst.id)
                            for_maintenance.remove(inst)
                    log.debug("restoring maintenance state for: %s",
                              ','.join([x.id for x in for_maintenance]))
                    self.maintenance_off(for_maintenance)

    def maintenance_on(self, instances=None, wait=True):
        self.set_maintenance(instances, True, wait)

    def maintenance_off(self, instances=None, wait=True):
        self.set_maintenance(instances, False, wait)

    def set_maintenance(self, instances=None, state=True, wait=True):

        if self.dry_run:
            log.info("Dry-run enabled. Not changing maintenance states.")
            return

        if instances is None:
            instances = filter(self.is_running, self.mh_instances)

        state_str = state and "on" or "off"

        log.debug("Setting maintenance state for instances %s to %s",
                 ','.join(x.tags['Name'] for x in instances), state_str)

        for inst in instances:
            if state:
                self.mh.maintenance_on(inst)
            else:
                self.mh.maintenance_off(inst)

        if wait:
            def maint_callback(cb_instances):
                in_state = filter(
                    lambda inst: self.mh.is_in_maintenance(inst) == state,
                    cb_instances
                )
                return len(in_state) == len(cb_instances)
            self.wait_for_state(maint_callback, instances)


