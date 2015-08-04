# -*- coding: utf-8 -*-

import json
import logging
import time

import utils
import settings

CHANGE_STATES = ['hibernate_offlining', 'hibernating', 'launching', 'booting']

log = logging.getLogger('ec2-manager')

class ZadaraController():

    def __init__(self, vpsa_id, security_token=None, dry_run=False):
        self.vpsa_id = vpsa_id
        self.dry_run = dry_run
        self.security_token = security_token
        if self.security_token is None:
            self.security_token = settings.ZADARA_ACCOUNT_TOKEN

    def __zadara_request__(self, endpoint, isPost=False):
        if isPost:
            #Don't return anything, because this just hangs if you do...
            utils.http_request("https://manage.zadarastorage.com", endpoint, special_request="ZADARA_POST", content_type="application/json")
        else:
            return json.loads(
                utils.http_request("https://manage.zadarastorage.com", endpoint, content_type="application/json"))

    def get_vpsas(self):
        log.debug("Getting VPSAs for token ending in %s", self.security_token[-5:])
        return self.__zadara_request__("/api/vpsas.json?token={0}".format(self.security_token))

    def get_vpsa_state(self):
        log.debug("Getting state for VPSA %s", self.vpsa_id)
        return self.__zadara_request__("/api/vpsas/{0}.json?token={1}".format(self.vpsa_id, self.security_token))['vpsa']['status']

    def is_stable_state(self):
        return self.get_vpsa_state() in CHANGE_STATES

    def is_up(self):
        return 'created' in self.get_vpsa_state()

    def is_down(self):
        return 'hibernated' in self.get_vpsa_state()

    def start(self):

        while not self.in_stable_state():
            log.info("Waiting for VPSA %s to be in a stable state", self.vpsa_id)
            time.sleep(30)
        if self.is_up():
            log.info("VPSA with %s is already up", self.vpsa_id)
        else:
            log.info("Starting Zadara array %s", self.vpsa_id)
            self.resume()
            while not self.is_up():
                log.info("Waiting for VPSA %s to be up", self.vpsa_id)
                time.sleep(30)

    def stop(self):

        while not self.in_stable_state():
            log.info("Waiting for VPSA %s to be in a stable state", self.vpsa_id)
            time.sleep(30)

        if self.is_down():
            log.info("VPSA %s is already down", self.vpsa_id)
        else:
            log.info("Stopping Zadara array %s", self.vpsa_id)
            self.hibernate()
            while not self.is_down():
                log.info("Waiting for VPSA %s to be down", self.vpsa_id)
                time.sleep(30)

    def hibernate(self):

        log.debug("Hibernating VPSA %s", self.vpsa_id)
        if self.dry_run:
            log.info("Dry run prevented hibernation of VPSA %s", self.vpsa_id)
            return

        self.__zadara_request__("/api/vpsas/{0}/hibernate.json?token={1}".format(str(self.vpsa_id), self.security_token), isPost=True)
        log.info("Hibernate command for VPSA with ID {0} sent".format(self.vpsa_id))

    def resume(self):

        log.debug("Resuming VPSA {0}".format(self.vpsa_id))
        if self.dry_run:
            log.info("Dry run prevented resume of VPSA %s", self.vpsa_id)
            return

        self.__zadara_request__("/api/vpsas/{0}/restore.json?token={1}".format(str(self.vpsa_id), self.security_token), isPost=True)
        log.info("Resume command for VPSA with ID {0} sent".format(self.vpsa_id))


