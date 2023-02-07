#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Sosreport Charm.

"""

import logging
import os
import glob
import socket
import paramiko
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus
from subprocess import check_call, CalledProcessError, check_output


logger = logging.getLogger(__name__)

class SosreportCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.collect_and_upload_action, self._on_collect_and_upload)

    def _on_install(self, _):
        self.model.unit.status = ActiveStatus("Unit is ready.")

    def _on_collect_and_upload(self, event):
        ret, msg = self._collect_sos(event)
        if not ret:
            event.fail(msg)
            return
        
        case_id = event.params["case"]
        files = glob.glob(f"/tmp/sos-collector-{case_id}*")
        logger.info(files)
        ret, msg = self._upload_sos(files)
        if not ret:
            event.fail(msg)
            return
        event.set
        event.set_results({"sosreports": files})


    def _collect_sos(self, event):
        # TOFIX
        ips = "10.211.227.47"
        ssh_user = self.model.config["ssh-user"]
        collect_cmd = f"sudo -u {ssh_user} sos collect --no-local --nopasswd-sudo --batch --nodes {ips}"
        collect_cmd = f"{collect_cmd} --ssh-user {ssh_user}"

        try:
            case_id = event.params["case"]
        except KeyError:
            msg = "Please specify a case number identifier"
            return False, msg

        collect_cmd = f"{collect_cmd} --case-id {case_id}"

        extra_args = event.params.get("extra-args")
        if extra_args:
            collect_cmd = f"{collect_cmd} {extra_args}"

        logger.info(collect_cmd)

        try:
            check_call(collect_cmd, shell=True)
        except CalledProcessError as e:
            msg = f"sos collection failed: {e.output}"
            logger.error(msg)
            return False, msg

        return True, None


    def _upload_sos(self, files):
        file_server = self.model.config["server"]
        username = self.model.config["server-username"]
        password = self.model.config["server-password"]
        access, error = self._check_sftp_access(file_server, username, password)
        if not access:
            msg = f"SFTP access to {file_server} is blocked: {error}"
            logger.error(msg)
            return False, msg
        
        for file in files:
            self._scp_transfer(file,file_server, "", username, password)
            # upload_cmd = f"curl --retry 10 -T {file} {file_server} -u ubuntu:ubuntu | tee"
            # logger.info(upload_cmd)
            # try:
            #     check_call(upload_cmd, shell=True)
            # except CalledProcessError as e:
            #     msg = f"{file} upload failed."
            #     return False, msg

        return True, None

    
    def _clear_local_sos(self,files):
        for file in files:
            os. remove(file)

    def _check_sftp_access(self,server, username, password):
        try:
            client = paramiko.Transport((server, 22))
            client.connect(username=username, password=password)
        except (socket.error, paramiko.ssh_exception.AuthenticationException) as e:
            return False, str(e)
        else:
            return True, None

    def _scp_transfer(self, src_files, dst_server, dst_path, username, password):
        client = paramiko.Transport((dst_server, 22))
        client.connect(username=username, password=password)

        sftp = client.open_sftp()

        for src_file in src_files:
            dst_file = dst_path + "/" + src_file.split("/")[-1]
            sftp.put(src_file, dst_file)

        sftp.close()
        client.close()

if __name__ == "__main__":
    main(SosreportCharm, use_juju_for_storage=True)
