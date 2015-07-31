

import time
import logging
import traceback
import boto.ec2.networkinterface
from boto.exception import EC2ResponseError

import settings
from exceptions import MatterhornCommunicationException

"""
class Instance(boto.ec2.ec2object.TaggedEC2Object)
 |  Represents an instance.
 |  
 |  :ivar id: The unique ID of the Instance.
 |  :ivar groups: A list of Group objects representing the security
 |                groups associated with the instance.
 |  :ivar public_dns_name: The public dns name of the instance.
 |  :ivar private_dns_name: The private dns name of the instance.
 |  :ivar state: The string representation of the instance''s current state.
 |  :ivar state_code: An integer representation of the instance''s
 |      current state.
 |  :ivar previous_state: The string representation of the instance''s
 |      previous state.
 |  :ivar previous_state_code: An integer representation of the
 |      instance''s current state.
 |  :ivar key_name: The name of the SSH key associated with the instance.
 |  :ivar instance_type: The type of instance (e.g. m1.small).
 |  :ivar launch_time: The time the instance was launched.
 |  :ivar image_id: The ID of the AMI used to launch this instance.
 |  :ivar placement: The availability zone in which the instance is running.
 |  :ivar placement_group: The name of the placement group the instance
 |      is in (for cluster compute instances).
 |  :ivar placement_tenancy: The tenancy of the instance, if the instance
 |      is running within a VPC.  An instance with a tenancy of dedicated
 |      runs on a single-tenant hardware.
 |  :ivar kernel: The kernel associated with the instance.
 |  :ivar ramdisk: The ramdisk associated with the instance.
 |  :ivar architecture: The architecture of the image (i386|x86_64).
 |  :ivar hypervisor: The hypervisor used.
 |  :ivar virtualization_type: The type of virtualization used.
 |  :ivar product_codes: A list of product codes associated with this instance.
 |  :ivar ami_launch_index: This instances position within it''s launch group.
 |  :ivar monitored: A boolean indicating whether monitoring is enabled or not.
 |  :ivar monitoring_state: A string value that contains the actual value
 |      of the monitoring element returned by EC2.
 |  :ivar spot_instance_request_id: The ID of the spot instance request
 |      if this is a spot instance.
 |  :ivar subnet_id: The VPC Subnet ID, if running in VPC.
 |  :ivar vpc_id: The VPC ID, if running in VPC.
 |  :ivar private_ip_address: The private IP address of the instance.
 |  :ivar ip_address: The public IP address of the instance.
 |  :ivar platform: Platform of the instance (e.g. Windows)
 |  :ivar root_device_name: The name of the root device.
 |  :ivar root_device_type: The root device type (ebs|instance-store).
 |  :ivar block_device_mapping: The Block Device Mapping for the instance.
 |  :ivar state_reason: The reason for the most recent state transition.
 |  :ivar groups: List of security Groups associated with the instance.
 |  :ivar interfaces: List of Elastic Network Interfaces associated with
 |      this instance.
 |  :ivar ebs_optimized: Whether instance is using optimized EBS volumes
 |      or not.
 |  :ivar instance_profile: A Python dict containing the instance
 |      profile id and arn associated with this instance.
 |  
 |  Method resolution order:
 |      Instance
 |      boto.ec2.ec2object.TaggedEC2Object
 |      boto.ec2.ec2object.EC2Object
 |      __builtin__.object
 |  
"""


class AWSController():

    def __init__(self, logPrefix, region='us-east-1', test=False, force=False, aws_access_key_id=None, aws_secret_access_key=None, matterhorn_controller=None, zadara_controller=None, retries=6):
        self.conn = boto.ec2.connect_to_region(
            region, aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)
        self.matterhorn = matterhorn_controller
        self.zadara = zadara_controller
        self.dry_run = test
        self.forced = force
        self.retries = retries
        self.logger = logging.getLogger(logPrefix + ".AWSController")

    # tag = "stgAWS-" or "devAWS-* or "devAWS-worker"
    # see
    # http://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html
    def get_tagged_instances(self,  tag=None, ids=None, state=None):
        if not ids and not tag:
            raise "Need to pass instance ids as a list or a tag name"
        instances = []
        filters = {}

        # Set up the state filters, if any
        if state:
            self.logger.debug("State set to " + str(state))
            filters = {"instance-state-name": state}

        # Set up the tag filters, if any
        if tag:
            self.logger.debug("Tag set to " + str(tag))
            filters["tag:Name"] = tag

        # Set up the id filters, if any
        if ids:
            for id in ids:
                self.logger.debug("Searching for ID {0}".format(id))
                filters["instance-id"] = id
                instances += self.conn.get_only_instances(filters=filters)
        else:
            # Get the instances
            instances = self.conn.get_only_instances(filters=filters)

        if len(instances) < 1:
            self.logger.debug("No matching instances found")
        for i in instances:
            self.logger.debug("Found: {0}, {1}, {2}, {3}, {4}, monitor {5}".format(i.tags[
                         'Name'], i.id,  i.state, i.ip_address, i.private_ip_address, i.monitoring_state))
        return self.createInstanceListDict(instances)

    # start stopped instances
    # instances = a dict of instance objects
    def start_instances(self, instances):
        for instance in instances.values():
            self.start_instance(instance)

    # instances = a dict of instance objects
    def stop_instances(self, instances):
        for instance in instances.values():
            self.stop_instance(instance)

    def isMatterhornNode(self, instance):
        # All suffixes, except the support suffixes
        for suffix in settings.AWS_MH_SUFFIXES:
            if suffix in instance.tags['Name']:
                return True
        return False

    def isMatterhornAdminNode(self, instance):
        if settings.AWS_MH_SUFFIXES[0] in instance.tags['Name']:
            return True
        return False

    def isPublicAwsInstance(self, instance):
        for suffix in settings.AWS_PUBLIC_SUFFIXES:
            if suffix in instance.tags['Name']:
                return True
        return False

    def getListOfMatterhornAdminNodes(self, instanceDict):
        adminNodes = []
        for instance in instanceDict.values():
            if self.isMatterhornAdminNode(instance):
                adminNodes.append(instance)
        if len(adminNodes) < 1:
            self.logger.error("Unable to determine admin node for cluster")
            raise Exception("Unable to determine admin node for cluster")
        return adminNodes

    def isMatterhornAlive(self, adminNode, instance):
        if self.isPublicAwsInstance(instance):
            return self.matterhorn.is_matterhorn_alive(instance, instance)
        else:
            return self.matterhorn.is_matterhorn_alive(adminNode, instance)

    def awsInstanceInList(self, instance, instanceList):
        for listInstance in instanceList:
            if instance.id == listInstance.id:
                return True
        return False

    def createInstanceListDict(self, instanceList):
        instanceDict = {}
        for instance in instanceList:
            instanceDict[instance.id] = instance
        return instanceDict

    def place_cluster_in_maintenance(self, prefix, targetMaintenanceState):
        instances = self.get_tagged_instances(tag=prefix + "*")
        mhInstances = {}
        adminInstances = []

        # Sort the instances
        for instance in instances.values():
            if self.isMatterhornNode(instance):
                self.logger.debug("Instance {0} with name {1} detected as a Matterhorn instance".format(
                    instance.id, instance.tags['Name']))
                mhInstances[instance.id] = instance
        # Get the admin instances
        adminInstances = self.getListOfMatterhornAdminNodes(instances)
        # Put things in maintenance
        self.place_in_maintenance(
            adminInstances[0], mhInstances, targetMaintenanceState)

    def place_in_maintenance(self, adminInstance, instances, targetMaintenanceState):
        matterhornNodes = []
        for i in instances.values():
            if self.isMatterhornNode(i):
                if i.state != "running":
                    self.logger.info("Skipping setting maintenance to {0} for node {1}, internally {2}, because the node is not running".format(
                        targetMaintenanceState, i.tags['Name'], i.private_ip_address))
                    continue
                matterhornNodes.append(i)

        attempts = {}
        done = 0
        while done != len(matterhornNodes):
            #Note: we're using done as an index into the list
            i = matterhornNodes[done]
            self.logger.info("Setting maintenance to {0} for node {1}, internally {2}".format(
                targetMaintenanceState, i.tags['Name'], i.private_ip_address))
            # Ugh, this is ugly but functional.  Basically, the public node is an all-in-one but still shows up as having an admin instance since it matches the prefix
            # This just looks for the public suffix (which, currently, is
            # an all-in-one box by definition) and forces the 'admin' node
            # for that instance to be itself
            all_in_one = False
            for suffix in settings.AWS_PUBLIC_SUFFIXES:
                if suffix in i.tags['Name']:
                    all_in_one = True
                    break
            try:
                if all_in_one:
                    self.matterhorn.place_matterhorn_in_maintenance(
                        i, i, targetMaintenanceState)
                else:
                    self.matterhorn.place_matterhorn_in_maintenance(
                        adminInstance, i, targetMaintenanceState)
                done = done + 1
            except MatterhornCommunicationException as e:
                self.logger.warning("Unable to communicate with Matterhorn, error code is {0}".format(e.code))
                if i.id not in attempts:
                    attempts[i.id] = 1
                else:
                    attempts[i.id] = attempts[i.id] + 1

                if attempts[i.id] >= self.retries:
                    if settings.AWS_PROD_PREFIX in adminInstance.tags['Name'] and not self.forced:
                        self.logger.error("This is a prod worker, so we are being very paranoid here")
                        self.logger.error("Raising the same exception to break things, rather than allowing things to continue")
                        raise e
                    elif settings.AWS_PROD_PREFIX in adminInstance.tags['Name'] and self.forced:
                        self.logger.warning("This is a prod worker, so normally we would be very paranoid here")
                        self.logger.warning("The --force flag has been activated however, so we are continuing")
                        done = done + 1
                    else:
                        self.logger.warn("Ignoring the issue since this is not a prod node")
                        done = done + 1
                else:
                    self.logger.info("Retrying maintenance call to {0}".format(i.private_ip_address))

    def sort_node_loads(self, prefix, adminNode, runningNodes, neededNodes):
        maintenancedNodes = {}
        nodesByMatterhornName = {}
        # Get the mapping of internal Matterhorn name -> AWS instance
        for node in runningNodes.values():
            nodesByMatterhornName[
                self.matterhorn.get_matterhorn_internal_name(node)] = node
        try:
            # Get the current loads and sort them based on the number of things
            # running
            currentLoads = [x for x in self.matterhorn.get_all_node_loads(
                adminNode).values() if x['host'] in nodesByMatterhornName]
            currentLoads.sort(key=lambda node: node['running'])
        except MatterhornCommunicationException as e:
            self.logger.warning("Unable to communicate with Matterhorn, error code is {0}".format(e.code))
            raise e

        # Go through the sorted list of loads and shut down the least busy
        # nodes
        for i in range(0, neededNodes):
            internalNodeName = currentLoads[i]['host']
            instance = nodesByMatterhornName[internalNodeName]
            self.logger.debug("Sorted instance {0} into maintenance for cluster {1}".format(
                instance.id, prefix))
            maintenancedNodes[instance.id] = instance

        return maintenancedNodes

    # TODO: reference - doesn't work yet
    def create_instance(self, tags):
        interface = boto.ec2.networkinterface.NetworkInterfaceSpecification(subnet_id='subnet-c4e5b1a5',    # us-east-1a
                                                                            # ec2_instance
                                                                            groups=[
                                                                                'sg-a52ef3c1'],
                                                                            # 'sg-df869aba'],
                                                                            associate_public_ip_address=True)
        interfaces = boto.ec2.networkinterface.NetworkInterfaceCollection(
            interface)

        # Doesn't work for micro - hvm
        reservation = self.conn.run_instances(image_id='ami-b66ed3de',    # amazon default
                                              instance_type='t1.micro',
                                              # the following two arguments are provided in the network_interface
                                              # instead at the global level !!
                                              network_interfaces=interfaces,

                                              #security_group_ids= ['sg--a52ef3c1'],
                                              #subnet_id= 'subnet-c4e5b1a5',
                                              # associate_public_ip_address=True,

                                              key_name='PhoebeWowzaKeyPair')

        instance = reservation.instances[0]
        instance.update()
        while instance.state == "pending":
            print instance, instance.state
            time.sleep(5)
        instance.update()
        for (k, v) in tags.items():
            instance.add_tag(k, v)

    def tag_instances(self, instances, tags):
        for instance in instances.values():
            newTags = dict(tags.items() + instance.tags.items())
            instance.add_tags(newTags)

    def start_instance(self, instance):
        try:
            self.logger.debug("Starting: {0}, {1}, {2}, {3}, {4}".format(
                instance.tags['Name'], instance.id,  instance.state, instance.ip_address, instance.private_ip_address))
            instance.start(dry_run=self.dry_run)
        except EC2ResponseError as e:
            self.logger.error("Error starting instance: {}".format(
                traceback.format_exc().splitlines()[-1]))

    def stop_instance(self, instance):
        try:
            self.logger.debug("Stopping: {0}, {1}, {2}, {3}, {4}".format(
                instance.tags['Name'], instance.id,  instance.state, instance.ip_address, instance.private_ip_address))
            instance.stop(dry_run=self.dry_run)
        except EC2ResponseError as e:
            self.logger.error("Error stopping instance: {}".format(
                traceback.format_exc().splitlines()[-1]))

    def ensureClusterHasWorkers(self, prefix, numberOfWorkers):
        adminNodes = self.get_tagged_instances(
            tag=prefix + settings.AWS_MH_SUFFIXES[0], state="running")
        if len(adminNodes) < 1:
            self.logger.error(
                "Unable to find running admins for cluster {0}, is the cluster online?".format(prefix))
            return
        runningWorkers = self.get_tagged_instances(
            tag=prefix + settings.AWS_MH_SUFFIXES[1], state="running")
        stoppedWorkers = self.get_tagged_instances(
            tag=prefix + settings.AWS_MH_SUFFIXES[1], state="stopped")

        #Build a list of workers who are turned on, but in maintenance
        alreadyInMaintenance = {}
        for worker in runningWorkers.values():
            if self.matterhorn.is_node_in_maintenance(adminNodes.values()[0], worker):
              alreadyInMaintenance[worker.id] = worker

        if len(runningWorkers) + len(stoppedWorkers) < 1:
            self.logger.error(
                "Unable to find workers for cluster {0}".format(prefix))
        elif len(runningWorkers) == numberOfWorkers:
            self.logger.info(
                "Cluster {0} already has {1} workers running".format(prefix, numberOfWorkers))
        else:
            # Determine the number of workers affected (this could be
            # negative!)
            neededWorkers = len(runningWorkers) - numberOfWorkers
            self.logger.info("We currently have {0} workers running with {1} in maintenance, we want {2} running".format(len(runningWorkers), len(alreadyInMaintenance), numberOfWorkers))
            # If we need more workers
            if neededWorkers < 0:
                neededWorkers = abs(neededWorkers)
                self.logger.info(
                    "We need {0} more workers, starting them up".format(neededWorkers))
                if neededWorkers > len(stoppedWorkers):
                    self.logger.warning(
                        "Desired number of workers exceeds the total number of workers in the cluster.  Starting all workers!")
                    # TODO: Spin up new workers!
                neededWorkers = min(neededWorkers, len(stoppedWorkers))
                startedInstances = {}
                for i in range(0, neededWorkers):
                    startedInstance = stoppedWorkers.values()[i]
                    self.logger.info(
                        "Starting instance {0} for cluster {1}".format(startedInstance.id, prefix))
                    startedInstances[startedInstance.id] = startedInstance
                self.start_instances(startedInstances)
                #Add the maintenanced workers to the list of newly started instances
                startedInstances.update(alreadyInMaintenance)
                self.takeClusterOutOfMaintenance(
                    adminNodes.values()[0], startedInstances)
            # If we need fewer workers
            else:
                self.logger.info(
                    "We need {0} fewer workers, shutting some down".format(neededWorkers))

                # Figure out which workers to put into maintenance
                workersToPutInMaintenance = max(0, neededWorkers - len(alreadyInMaintenance))

                #Build a filtered list of workers who are running but *not* in maintenance
                filteredWorkers = {}
                for worker in runningWorkers.values():
                    if worker.id not in alreadyInMaintenance:
                        filteredWorkers[worker.id] = worker

                maintenancedWorkers = self.sort_node_loads(
                    prefix, adminNodes.values()[0], filteredWorkers, workersToPutInMaintenance)
                #Add the list of workers which are already in maintenance to the list of maintenanced workers
                maintenancedWorkers.update(alreadyInMaintenance)
                # Put everything in maintenance
                self.place_in_maintenance(
                    adminNodes.values()[0], maintenancedWorkers, True)
                for instance in maintenancedWorkers.values():
                    isIdle = False
                    try:
                        isIdle = self.matterhorn.is_node_idle(adminNodes.values()[0], instance)
                    except MatterhornCommunicationException as e:
                        self.logger.warning("Unable to communicate with admin node for cluster {0}, error code is {1}".format(prefix, e.code))
                        if e.code == -1:
                            if settings.AWS_PROD_PREFIX in prefix and not self.forced:
                                self.logger.error("This is operating on prod, so we are being very paranoid")
                                self.logger.error("Raising the same exception to break things, rather than attempting to recover")
                                raise e
                            elif settings.AWS_PROD_PREFIX in prefix and self.forced:
                                self.logger.warning("This is operating on prod, so normally we would be being very paranoid")
                                self.logger.warning("The --force flag has been activated however, so we are continuing")
                                isIdle = True
                            else:
                                self.logger.warning("Since this is a dev system, we are going to assume that it is either broken or somehow offline")
                                isIdle = True
                    if isIdle:
                        self.logger.info("Node {0} is in maintenance".format(instance.id))
                        # Shut the node(s) down
                        self.stop_instance(instance)
                    else:
                        self.logger.warn("Node {0} is either offline, or not yet in maintenance".format(instance.id))

    def startupAwsInstancesBySuffixList(self, awsInstances, suffixList, nodeLimits={}):
        changedInstances = {}
        activeNodeTypes = {}
        candidateNodes = {}
        # Iterate through the list of suffixes
        for suffix in suffixList:
            # Ensure the lists are present in the dictionaries
            if suffix not in candidateNodes:
                candidateNodes[suffix] = []
            if suffix not in activeNodeTypes:
                activeNodeTypes[suffix] = []

            # Iterate through the list of instances
            for awsInstance in awsInstances.values():
                # If the instance is named correctly and stopped
                if awsInstance.state == "stopped" and suffix in awsInstance.tags["Name"]:
                    candidateNodes[suffix].append(awsInstance)
                # If the instance is named correctly and running, add it to the
                # list of currently active nodes
                elif awsInstance.state == "running" and suffix in awsInstance.tags["Name"]:
                    activeNodeTypes[suffix].append(awsInstance)

        # Iterate through the candidates and start the appropriate ones
        for suffix in suffixList:
            for candidate in candidateNodes[suffix]:
                # If we are at or above the limit for this suffix
                if suffix in activeNodeTypes and suffix in nodeLimits and len(activeNodeTypes[suffix]) >= nodeLimits[suffix]:
                    self.logger.debug("Skipping candidate node {0} at ip {1}, internally {2}, because we are already at or above the limit of {3} for {4} nodes".format(
                        candidate.tags['Name'], candidate.ip_address, candidate.private_ip_address, nodeLimits[suffix], suffix))
                    continue

                # Keep track of the total nodes that have been marked as active
                activeNodeTypes[suffix].append(candidate)

                # Start the candidate
                self.logger.info("Starting node {0} at ip {1}, internally {2}".format(
                    candidate.tags['Name'], candidate.ip_address, candidate.private_ip_address))
                changedInstances[candidate.id] = candidate
        self.start_instances(changedInstances)
        return changedInstances

    def startupAwsInstancesBySuffixListAndWait(self, prefix, awsInstances, suffixList, nodeLimits={}):
        # How many nodes are already running?
        running = [x for x in awsInstances.values() if x.state == "running"]
        # Start the instances, and get a list of what changed
        changedInstances = self.startupAwsInstancesBySuffixList(
            awsInstances, suffixList, nodeLimits)

        changes = len(changedInstances)
        done = 0
        while changes != done:
                # Prevent waiting when there are no changes
            if changes > 0:
                time.sleep(30)
            # Poll the current state
            started = [x for x in self.get_tagged_instances(
                tag=prefix + "*", state="running").values() if not self.awsInstanceInList(x, running)]
            done = 0
            # For each changed instance, if the state is running, add one to
            # the done counter
            for instance in started:
                if instance.id in changedInstances:
                    done = done + 1
            # Note: changes and done both get len(running) added to them.
            # This is so that when you're starting N Matterhorn nodes with M support nodes already running you see N+M/N+M at
            # the end, rather than N/N, otherwise it looks weird.  Functionally, you can remove the addition clause without
            # hurting anything, as long as you remove *both*
            self.logger.info(
                "{0} / {1} instances started...".format(done + len(running), changes + len(running)))
        return changedInstances

    def takeClusterOutOfMaintenance(self, adminNode, changedInstances):
        # Wait until MH is all the way up
        done = 0
        # Take the nodes out of maintenance
        attempts  = {}
        while done != len(changedInstances):
            self.logger.info("Waiting for Matterhorn to be alive...")
            #time.sleep(10)
            done = 0
            for instance in changedInstances.values():
                if instance.id not in attempts:
                    attempts[instance.id] = 0

                if instance.private_ip_address == None:
                    instance.update()
                try:
                    if not self.isMatterhornNode(instance):
                        # So if someone passes in a dict with the NFS and/or DB
                        # nodes things don't break
                        done = done + 1
                    elif self.isMatterhornAlive(adminNode, instance):
                        self.logger.debug("Node {0} with ip {1} is alive".format(
                            instance.id, instance.private_ip_address))
                        done = done + 1
                    else:
                        self.logger.debug("Node {0} with ip {1} is not alive yet".format(
                            instance.id, instance.private_ip_address))
                except MatterhornCommunicationException as e:
                    self.logger.warning("Unable to communicate with Matterhorn, error code is {0}".format(e.code))
                    if instance.id in attempts:
                        if attempts[instance.id] > self.retries:
                            instance.update()
                            if instance.state not in ["pending", "running"]:
                              self.logger.info("Resending start for instance {0}".format(instance.id))
                              self.start_instance(instance)
                              attempts[instance.id] = 0
                            elif instance.state == "running":
                              self.logger.warning("AWS instance {0} appears to be running, but is not responding to attempts to take it out of maintenance".format(instance.id))
                              self.logger.warning("We are ignoring this, and assuming that it will be handled manually")
                              done = done + 1
                        else:
                            attempts[instance.id] = attempts[instance.id] + 1
                    else:
                        attempts[instance.id] = 1

        for instance in changedInstances.values():
            instance.update()
        self.place_in_maintenance(adminNode, changedInstances, False)

    def bringUpZadara(self, prefix):
        vpsaId = None
        if settings.AWS_PROD_PREFIX in prefix:
            vpsaId = settings.ZADARA_VPSA_PROD_ID
            self.logger.debug("{0} matches Zadara vpsa ID of {1}".format(prefix, vpsaId))
        elif settings.AWS_STG_PREFIX in prefix:
            vpsaId = settings.ZADARA_VPSA_STG_ID
            self.logger.debug("{0} matches Zadara vpsa ID of {1}".format(prefix, vpsaId))
        elif settings.AWS_DEV_PREFIX in prefix:
            vpsaId = settings.ZADARA_VPSA_DEV_ID
            self.logger.debug("{0} matches Zadara vpsa ID of {1}".format(prefix, vpsaId))

        if vpsaId != None:
            while not self.zadara.is_vpsa_stable_state(vpsaId):
                self.logger.info(
                    "Waiting for VPSA {0} to be in a stable state".format(vpsaId))
                time.sleep(30)
            if self.zadara.is_vpsa_up(vpsaId):
                self.logger.info(
                    "VPSA with ID {0} is already up".format(str(vpsaId)))
            else:
                self.logger.info(
                    "Prefix is {0}, starting Zadara array {1}".format(prefix, str(vpsaId)))
                self.zadara.resume(vpsaId)
                while not self.zadara.is_vpsa_up(vpsaId):
                    self.logger.info("Waiting for VPSA {0} to be up".format(vpsaId))
                    time.sleep(30)

    def bringupCluster(self, prefix, numWorkers=None):
        self.logger.info("Bringing up cluster %s " % prefix)

        self.bringUpZadara(prefix)

        # Find the support instance(s)
        instances = self.get_tagged_instances(tag=prefix + "*")

        # Define the node limits TODO: expose more of this?
        nodeLimits = {}
        if numWorkers != None:
            nodeLimits = {settings.AWS_MH_SUFFIXES[1]: numWorkers}

        # Start the support instances
        self.startupAwsInstancesBySuffixListAndWait(
            prefix, instances, settings.AWS_NON_MH_SUFFIXES)
        # Refresh the instances
        instances = self.get_tagged_instances(tag=prefix + "*")
        # Start the Matterhorn nodes
        changedInstances = self.startupAwsInstancesBySuffixListAndWait(
            prefix, instances, settings.AWS_MH_SUFFIXES, nodeLimits)

        # Refresh the instances
        instances = self.get_tagged_instances(
            tag=prefix + "*", state="running")
        adminNodes = self.getListOfMatterhornAdminNodes(instances)

        # Bring Matterhorn out of maintenance
        self.takeClusterOutOfMaintenance(adminNodes[0], instances)

        self.logger.info("Cluster %s online" % prefix)

    def shutdownAwsInstancesBySuffixList(self, awsInstances, suffixList):
        changedInstances = {}
        # Iterate through the list of suffixes *backwards*
        for i in xrange(len(suffixList) - 1, -1, -1):
            suffix = suffixList[i]
            for awsInstance in awsInstances.values():
                # If the instance is named correctly and running, stop it and
                # add it to the changed list
                if awsInstance.state == "running" and suffix in awsInstance.tags["Name"]:
                    self.logger.info("Stopping node {0} at ip {1}, internally {2}".format(
                        awsInstance.tags['Name'], awsInstance.ip_address, awsInstance.private_ip_address))
                    changedInstances[awsInstance.id] = awsInstance
        self.stop_instances(changedInstances)
        return changedInstances

    def shutdownAwsInstancesBySuffixListAndWait(self, prefix, awsInstances, suffixList):
        # How many nodes are already stopped?
        alreadyStopped = [
            x for x in awsInstances.values() if x.state == "stopped"]
        # Start the instances, and get a list of what changed
        changedInstances = self.shutdownAwsInstancesBySuffixList(
            awsInstances, suffixList)

        changes = len(changedInstances)
        done = 0
        while changes != done:
                # Prevent waiting when there are no changes
            if changes > 0:
                time.sleep(30)
            # Poll the current state
            stopped = [x for x in self.get_tagged_instances(
                tag=prefix + "*", state="stopped").values() if not self.awsInstanceInList(x, alreadyStopped)]
            done = 0
            # For each changed instance, if the state is stopped, add one to
            # the done counter
            for instance in stopped:
                if instance.id in changedInstances:
                    done = done + 1
            # Note: changes and done both get len(alreadyStopped) added to them.
            # This is so that when you're stopping N support nodes with M Mastterhorn nodes already running you see N+M/N+M at
            # the end, rather than N/N, otherwise it looks weird.  Functionally, you can remove the addition clause without
            # hurting anything, as long as you remove *both*
            self.logger.info("{0} / {1} instances stopped...".format(done +
                                                                len(alreadyStopped), changes + len(alreadyStopped)))
        return changedInstances

    def putClusterInMaintenance(self, adminNode, changedInstances):
        self.place_in_maintenance(adminNode, changedInstances, True)
        attempts = {}
        #Good grief, I'm sorry about this routine but I don't see a cleaner way to do it right now
        done = 0
        # Wait until they are all in maintenance
        while done != len(changedInstances):
            self.logger.debug("Waiting for Matterhorn to be in maintenance...")
            if len(changedInstances) > 0:
                time.sleep(10)
            done = 0
            for instance in changedInstances.values():
                if instance.id not in attempts:
                    attempts[instance.id] = 0

                #Figure out the real admin node (public nodes are their own admin)
                actualAdminNode = adminNode
                if self.isPublicAwsInstance(instance):
                  actualAdminNode = instance

                try:
                    if self.isMatterhornNode(instance) and instance.state == "running" and self.isMatterhornAlive(actualAdminNode, instance):
                        if self.matterhorn.is_node_in_maintenance(actualAdminNode, instance) and self.matterhorn.is_node_idle(actualAdminNode, instance):
                            self.logger.debug("Node {0} with ip {1} is alive, in maintenance, and idle".format(
                                instance.id, instance.private_ip_address))
                            done = done + 1
                        else:
                            self.logger.debug("Node {0} with ip {1} is alive and still active".format(
                                instance.id, instance.private_ip_address))
                            if instance.id in attempts:
                                if attempts[instance.id] > self.retries:
                                    if settings.AWS_PROD_PREFIX in actualAdminNode.tags['Name']:
                                      self.logger.info("We are bored of waiting for {0} to be done".format(instance.id))
                                      self.logger.info("But since this is prod we're being extra paranoid, so we're just going to keep waiting")
                                    else:
                                      self.logger.warning("We are bored of waiting for {0} to be done".format(instance.id))
                                      self.logger.warning("Since this is a dev or stage instance, we're going to assume it's safe to just shut it down")
                                      done = done + 1
                                else:
                                    attempts[instance.id] = attempts[instance.id] + 1
                            else:
                                attempts[instance.id] = 1
                    else:
                        self.logger.debug("Node {0} with ip {1} is already down or not responding".format(
                            instance.id, instance.private_ip_address))
                        # This is right because we're assuming that some of these
                        # nodes are *not* matterhorn nodes and thus do not go into
                        # maintenance!
                        done = done + 1
                except MatterhornCommunicationException as e:
                    self.logger.warning("Unable to communicate with Matterhorn, error code is {0}".format(e.code))
                    if attempts[instance.id] > self.retries:
                        if settings.AWS_PROD_PREFIX in adminNode.tags['Name'] and not self.forced:
                          self.logger.error("Unable to put node {0} into maintenance, unable to communicate with {1}".format(instance.id, self.matterhorn.get_matterhorn_internal_name(adminNode)))
                          self.logger.error("Since this is prod we're being extra paranoid, so this kills the maintenance attempt")
                          self.logger.error("Raising the same error to break things rather than attempt to continue")
                          raise e
                        elif settings.AWS_PROD_PREFIX in adminNode.tags['Name'] and self.forced:
                          self.logger.warning("Unable to put node {0} into maintenance, unable to communicate with {1}".format(instance.id, self.matterhorn.get_matterhorn_internal_name(adminNode)))
                          self.logger.warning("Since this is prod we would normally be extra paranoid and kill the maintenance attempt")
                          self.logger.warning("The --force flag has been activated however, so we are continuing")
                          done = done + 1
                        else:
                          self.logger.warning("Unable to put node {0} into maintenance, unable to communicate with {1}".format(instance.id, self.matterhorn.get_matterhorn_internal_name(adminNode)))
                          self.logger.warning("Since this is a dev or stage instance, we're going to assume it's safe to ignore this")
                          done = done + 1
                    else:
                        attempts[instance.id] = attempts[instance.id] + 1

    def bringDownZadara(self, prefix):
        vpsaId = None
        if settings.AWS_PROD_PREFIX in prefix:
            vpsaId = settings.ZADARA_VPSA_PROD_ID
            self.logger.debug("{0} matches Zadara vpsa ID of {1}".format(prefix, vpsaId))
        elif settings.AWS_STG_PREFIX in prefix:
            vpsaId = settings.ZADARA_VPSA_STG_ID
            self.logger.debug("{0} matches Zadara vpsa ID of {1}".format(prefix, vpsaId))
        elif settings.AWS_DEV_PREFIX in prefix:
            vpsaId = settings.ZADARA_VPSA_DEV_ID
            self.logger.debug("{0} matches Zadara vpsa ID of {1}".format(prefix, vpsaId))

        if vpsaId != None:
            while not self.zadara.is_vpsa_stable_state(vpsaId):
                self.logger.info(
                    "Waiting for VPSA {0} to be in a stable state".format(vpsaId))
                time.sleep(30)
            if self.zadara.is_vpsa_down(vpsaId):
                self.logger.info(
                    "VPSA with ID {0} is already down".format(str(vpsaId)))
            else:
                self.logger.info(
                    "Prefix is {0}, stopping Zadara array {1}".format(prefix, str(vpsaId)))
                self.zadara.hibernate(vpsaId)
                while not self.zadara.is_vpsa_down(vpsaId):
                    self.logger.info(
                        "Waiting for VPSA {0} to be down".format(vpsaId))
                    time.sleep(30)

    def bringdownCluster(self, prefix):
        self.logger.info("Bringing down cluster %s " % prefix)
        # Get the list of AWS instances
        awsInstances = self.get_tagged_instances(tag=prefix + "*")
        for instance in awsInstances.values():
            for tag in instance.tags.keys():
                if "hold" == str(tag).lower():
                    self.logger.info(
                        "Instance {0} has hold tag applied, please remove it and try again.".format(instance.id))
                    return
        adminNodes = self.getListOfMatterhornAdminNodes(awsInstances)
        self.putClusterInMaintenance(adminNodes[0], awsInstances)

        self.logger.info("Matterhorn nodes are now idle")

        # Shut down then engage (and pub), then workers, then admin, then
        # mysql, then NFS (if applicable), then shut down the backing
        # filesystem
        self.logger.info("Stopping Matterhorn nodes")
        self.shutdownAwsInstancesBySuffixListAndWait(
            prefix, awsInstances, settings.AWS_MH_SUFFIXES)

        # Refresh the instances
        awsInstances = self.get_tagged_instances(tag=prefix + "*")

        self.logger.info("Matterhorn nodes shut down, stopping support nodes")
        self.shutdownAwsInstancesBySuffixListAndWait(
            prefix, awsInstances, settings.AWS_NON_MH_SUFFIXES)

        self.bringDownZadara(prefix)

        self.logger.info("Cluster %s down" % prefix)
