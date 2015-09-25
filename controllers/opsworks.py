import sys

import boto.opsworks
from boto.exception import JSONResponseError

from ec2 import EC2Controller, EC2Instance
from exceptions import *

import logging
log = logging.getLogger()

class OpsworksEC2Instance(EC2Instance):

    opsworks_instance = None

    def __init__(self, wrapped, opsworks_instance):
        super(OpsworksEC2Instance, self).__init__(wrapped)
        self.opsworks_instance = opsworks_instance


class OpsworksController(EC2Controller):

    @property
    def opsworks(self):
        if not hasattr(self, '_opsworks'):
            self._opsworks = self.create_opsworks_conn()
        return self._opsworks

    def create_opsworks_conn(self):
        conn = boto.opsworks.connect_to_region(self.region,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
            )
        try:
            conn.describe_my_user_profile()
            log.debug("boto.opsworks connection to region %s established", self.region)
            return conn
        except JSONResponseError, e:
            if e.status == '400':
                log.error(e.message)
                log.error("Unable to establish boto.opsworks connection. Check your aws credentials.")
                sys.exit(1)
            else:
                raise

    @property
    def stack(self):
        if not hasattr(self, '_stack'):
            stacks = self.opsworks.describe_stacks()
            try:
                self._stack = next(x for x in stacks['Stacks'] if x['Name'] == self.prefix)
            except StopIteration:
               raise ClusterException(
                   "Can't find a stack named {}".format(self.prefix)
               )
        return self._stack

    @property
    def instances(self):
        if not hasattr(self, '_instances'):

            # we only want to deal with mh nodes
            ec2_instances = filter( self.is_mh,
                super(OpsworksController, self).get_instances()
            )

            opsworks_instances = self.opsworks.describe_instances(self.stack['StackId'])['Instances']
            self._instances = []

            for ec2_inst in ec2_instances:
                try:
                    ops_inst = next(x for x in opsworks_instances if x['Ec2InstanceId'] == ec2_inst.id)
                except StopIteration:
                    raise ClusterException(
                        "Cannot find matching opsworks instance for {}".format(ec2_inst.id)
                    )
                else:
                    log.debug("Found matching opsworks instance %s", ops_inst['InstanceId'])

                    # ignore non "24/7" opsworks instances (i.e. timer/load autoscale intances)
                    if 'AutoScalingType' in ops_inst:
                        log.debug("ignoring opsworks autoscale instance %s", ops_inst['InstanceId'])
                        continue

                    self._instances.append(OpsworksEC2Instance(ec2_inst, ops_inst))

        return self._instances

    @property
    def instance_filter(self):
        return {
            'tag:opsworks:stack': self.prefix
        }

    def is_admin(self, instance):
        return 'opsworks:layer:admin' in instance.tags

    def is_worker(self, instance):
        return 'opsworks:layer:workers' in instance.tags

    def is_mh(self, instance):
        for layer in ['admin','engage','workers']:
            if 'opsworks:layer:' + layer in instance.tags:
                return True
        return False

    def _start_instance(self, instance):
        opsworks_id = instance.opsworks_instance['InstanceId']
        if self.dry_run:
            log.info("If this wasn't a dry run, would be starting %s, %s", opsworks_id, instance.id)
        self.opsworks.start_instance(opsworks_id)

    def _stop_instance(self, instance):
        opsworks_id = instance.opsworks_instance['InstanceId']
        if self.dry_run:
            log.info("If this wasn't a dry run, would be stopping %s, %s", opsworks_id, instance.id)
        self.opsworks.stop_instance(opsworks_id)

    def _not_implemented(self, *args, **kwargs):
        raise NotImplementedError(
            "This operation is not implemented for opsworks clusters"
        )

    # ec2-manager is not intended to perform these types of operations for
    # opsworks clusters
    start_cluster = _not_implemented
    stop_cluster = _not_implemented
    start_zadara = _not_implemented
    stop_zadara = _not_implemented

    is_support = _not_implemented
