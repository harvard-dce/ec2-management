# -*- coding: utf-8 -*-

import json
import logging
import socket
from urllib2 import URLError, HTTPError

import utils
from exceptions import MatterhornCommunicationException


class MatterhornController():

    def __init__(self, loggingPrefix, dry_run=False):
        self.logger = logging.getLogger(loggingPrefix + ".MatterhornController")
        self.dry_run = dry_run

    def __generate_matterhorn_node_names__(self, awsInstance):
        listOfNames = []
        listOfNames.append(self.get_matterhorn_internal_name(awsInstance))
        listOfNames.append(self.get_matterhorn_external_name(awsInstance))
        listOfNames.append(self.get_matterhorn_external_dns_name(awsInstance))
        listOfNames.append(self.get_matterhorn_external_https_dns_name(awsInstance))
        listOfNames.append(self.get_matterhorn_internal_https_name(awsInstance))
        listOfNames.append(self.get_matterhorn_external_https_name(awsInstance))
        return listOfNames

    def is_matterhorn_alive(self, adminAwsInstance, awsInstance):
        result = None
        for node in self.__generate_matterhorn_node_names__(awsInstance):
            endpoint = "/services/services.json?host=" + node
            self.logger.debug("Asking {0} @ {1} if {2} is alive".format(adminAwsInstance.id, node, node))
            result = self.get_json_from_endpoint(adminAwsInstance, endpoint)
            if 'services' not in result or 'service' not in result['services']:
                self.logger.debug("{0} has never heard of {1}".format(adminAwsInstance.id, node))
                continue
            else:
                break

        if 'service' not in result['services']:
            return False
        services = utils.ensureList(result['services']['service'])
        online = True
        for service in services:
            if service['online'] != True:
                online = False
        if online:
          self.logger.debug("{0} says {1} is alive".format(adminAwsInstance.id, node))
          return True
        else:
          self.logger.debug("{0} says {1} is down, or is not up by that name".format(adminAwsInstance.id, node))
          return False

    def place_matterhorn_in_maintenance(self, admin_aws_instance, aws_instance, maintenance_mode):
        endpoint = "/services/maintenance"
        #Iterate over the non-admin node's possible names.  The admin node itself gets iterated over by get_from_endpoint
        for host in self.__generate_matterhorn_node_names__(aws_instance):
            pData = {"host": str(host), "maintenance": str(maintenance_mode)}
            if self.dry_run:
                self.logger.info(
                    "Dry run prevented telling {0} to set {1} to maintenance state {2}".format(admin_aws_instance.id, host, maintenance_mode))
            else:
                self.logger.debug(
                    "Telling {0} to set the maintenance value for {1} to {2}".format(admin_aws_instance.id, host, maintenance_mode))
                try:
                  self.get_from_endpoint(admin_aws_instance, endpoint, pData)
                  return
                except MatterhornCommunicationException as e:
                    self.logger.info("{0} does not know about {1}, or {2} is down".format(admin_aws_instance.id, host, host))

    def get_matterhorn_external_dns_name(self, awsInstance):
        return "http://" + awsInstance.public_dns_name

    def get_matterhorn_external_https_dns_name(self, awsInstance):
        return "https://" + awsInstance.public_dns_name

    def get_matterhorn_internal_name(self, awsInstance):
        return "http://" + awsInstance.private_ip_address

    def get_matterhorn_internal_https_name(self, awsInstance):
        return "https://" + awsInstance.private_ip_address

    def get_matterhorn_external_name(self, awsInstance):
        return "http://" + awsInstance.ip_address

    def get_matterhorn_external_https_name(self, awsInstance):
        return "https://" + awsInstance.ip_address

    def get_from_endpoint(self, awsInstance, endpoint, data=None):
        for host in self.__generate_matterhorn_node_names__(awsInstance):
            self.logger.debug("Attempting communication with {0} at {1}".format(awsInstance.id, host))
            try:
                return self.__get_from_endpoint__(host, endpoint, data)
            except HTTPError as e:
              if hasattr(e, 'reason'):
                error = MatterhornCommunicationException(e.code, e.reason)
              else:
                error = MatterhornCommunicationException(e.code, "None specified")
              raise error
            except URLError as e:
              if type(e.reason) != socket.timeout:
                error = MatterhornCommunicationException('-2', e.reason)
                raise error
        error = MatterhornCommunicationException('-1', "timed out")
        raise error

    def __get_from_endpoint__(self, host, endpoint, data=None):
        if data != None:
          return utils.http_request(host, endpoint, data, special_request="MATTERHORN")
        else:
          return utils.http_request(host, endpoint, special_request="MATTERHORN")

    def get_json_from_endpoint(self, awsInstance, endpoint, data=None):
        return json.loads(self.get_from_endpoint(awsInstance, endpoint, data))

    def is_node_in_maintenance(self, adminInstance, awsInstance):
        nodeLoads = self.get_all_node_loads(adminInstance)
        for node in self.__generate_matterhorn_node_names__(awsInstance):
            if node not in nodeLoads:
              continue
            nodeLoad = nodeLoads[node]
            for service in nodeLoad['services']:
                if nodeLoad['services'][service]['maintenance'] == False:
                    self.logger.debug("{0} @ {1} is not in maintenance".format(awsInstance.id, node))
                    return False
            self.logger.debug("{0} @ {1} is in maintenance".format(awsInstance.id, node))
            return True
        self.logger.debug("{0} is not listed in the service registry".format(awsInstance.id))
        error = MatterhornCommunicationException('-3', "Node is not present")
        raise error

    def get_related_hosts(self, awsInstance):
        if not self.is_matterhorn_alive(awsInstance):
            return {}
        endpoint = "/services/hosts.json"
        results = self.get_json_from_endpoint(awsInstance, endpoint)
        hosts = {}

        results['hosts']['host'] = utils.ensureList(results['hosts']['host'])

        for host in results['hosts']['host']:
            hosts[host["base_url"]] = host
        return hosts

    def is_node_idle(self, adminInstance, awsInstance):
        loadData = self.get_all_node_loads(adminInstance)
        return self.__is_node_idle__(awsInstance, loadData)

    def __is_node_idle__(self, awsInstance, loadData):
        self.logger.debug("Searching load data for {0} for the node load".format(awsInstance.id))
        for internalName in self.__generate_matterhorn_node_names__(awsInstance):
            if internalName not in loadData:
                continue
            if int(loadData[internalName]['running']) > 0:
                #Ignore workflow jobs, these get stuck too often
                WORKFLOW_KEY = 'org.opencastproject.workflow'
                #If there are workflow jobs running, and they are *not* equal to the total number of jobs running on this node, then the node is not idle.
                if WORKFLOW_KEY in loadData[internalName]['services'] and int(loadData[internalName]['services'][WORKFLOW_KEY]['running']) != int(loadData[internalName]['running']):
                    self.logger.debug("{0} @ {1} is NOT idle".format(awsInstance.id, internalName))
                    return False
            self.logger.debug("{0} @ {1} is idle".format(awsInstance.id, internalName))
            return True
        self.logger.debug("{0} is not present in the load data".format(awsInstance.id))
        error = MatterhornCommunicationException('-3', "Node is not present")
        raise error

    def are_nodes_idle(self, awsInstance):
        loadData = self.get_all_node_loads(awsInstance)
        for host in self.get_related_hosts(awsInstance):
            if not self.__is_node_idle__(host, loadData):
                return False
        return True

    def get_all_node_loads(self, awsInstance):
        self.logger.debug("Asking {0} for the node loads".format(awsInstance.id))
        endpoint = "/services/statistics.json"
        results = self.get_json_from_endpoint(awsInstance, endpoint)
        loadsByHost = {}
        for service in utils.ensureList(results['statistics']['service']):
            registration = service["serviceRegistration"]
            hostDict = {}
            if registration["host"] in loadsByHost:
                hostDict = loadsByHost[registration["host"]]
            else:
                hostDict = {
                    'running': 0, 'host': registration["host"], 'services': {}}
            hostDict['running'] += int(service["running"])
            hostDict['services'][registration["type"]] = {'maintenance': registration[
                "maintenance"], 'online': registration["online"], 'running': service["running"]}
            loadsByHost[registration["host"]] = hostDict
        return loadsByHost

