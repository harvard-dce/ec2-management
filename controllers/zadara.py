# -*- coding: utf-8 -*-

import json
import logging

import utils

CHANGE_STATES = ['hibernate_offlining', 'hibernating', 'launching', 'booting']

log = logging.getLogger()

class ZadaraController():

    def __init__(self, logPrefix, security_token=None, dry_run=False):
        self.security_token = security_token
        self.dry_run = dry_run

    def __zadara_request__(self, endpoint, isPost=False):
        if isPost:
            #Don't return anything, because this just hangs if you do...
            utils.http_request("https://manage.zadarastorage.com", endpoint, special_request="ZADARA_POST", content_type="application/json")
        else:
            return json.loads(
                utils.http_request("https://manage.zadarastorage.com", endpoint, content_type="application/json"))

    def get_vpsas(self):
        log.debug("Getting VPSAs for {0}".format(self.security_token))
        return self.__zadara_request__("/api/vpsas.json?token={0}".format(self.security_token))

    def get_vpsa_state(self, vpsa_id):
        log.debug("Getting state for VPSA {0}".format(vpsa_id))
        return self.__zadara_request__("/api/vpsas/{0}.json?token={1}".format(vpsa_id, self.security_token))['vpsa']['status']

    def is_vpsa_stable_state(self, vpsa_id):
        if self.get_vpsa_state(vpsa_id) in CHANGE_STATES:
            return False
        return True

    def is_vpsa_up(self, vpsa_id):
        if 'created' in self.get_vpsa_state(vpsa_id):
            return True
        else:
            return False

    def is_vpsa_down(self, vpsa_id):
        if 'hibernated' in self.get_vpsa_state(vpsa_id):
            return True
        else:
            return False

    def hibernate(self, vpsa_id):
        log.debug("Hibernating VPSA {0}".format(vpsa_id))
        if not self.dry_run:
            self.__zadara_request__("/api/vpsas/{0}/hibernate.json?token={1}".format(str(vpsa_id), self.security_token), isPost=True)
            log.info("Hibernate command for VPSA with ID {0} sent".format(vpsa_id))
        else:
            log.info(
                "Dry run prevented hibernation of VPSA {0}".format(vpsa_id))
            return "dry_run"

    def resume(self, vpsa_id):
        log.debug("Resuming VPSA {0}".format(vpsa_id))
        if not self.dry_run:
            self.__zadara_request__("/api/vpsas/{0}/restore.json?token={1}".format(str(vpsa_id), self.security_token), isPost=True)
            log.info("Resume command for VPSA with ID {0} sent".format(vpsa_id))
        else:
            log.info(
                "Dry run prevented resume of VPSA {0}".format(vpsa_id))
            return "dry_run"
