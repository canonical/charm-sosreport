#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

import asyncio
import glob
import logging
import os
import socket
from subprocess import DEVNULL, CalledProcessError, check_call

import paramiko
from juju.controller import Controller
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus

logger = logging.getLogger(__name__)


class SosreportCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        """Init."""
        super().__init__(*args)

        self.controller = Controller(max_frame_size=6**24)
        self.logger = logger

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.collect_and_upload_action, self._on_collect_and_upload
        )

    def _on_install(self, _):
        self.model.unit.status = ActiveStatus("Unit is ready.")

    def _on_collect_and_upload(self, event):
        asyncio.run(self._on_collect_and_upload_async(event))

    async def _on_collect_and_upload_async(self, event):
        """Collect sosreports an upload to remove server."""
        ret, msg = await self._collect_sos(event)
        if not ret:
            event.fail(msg)
            return

        case_id = event.params["case"]
        files = glob.glob(f"/tmp/sos*{case_id}*")
        logger.info(files)
        ret, msg = self._upload_sos(files)
        if not ret:
            event.fail(msg)
            return
        event.set_results({"sosreports": files})

        self._clear_local_sos(files)

    async def _collect_sos(self, event):
        """Collect system state information and logs.

        Arguments:
        event -- an event object that contains information about the collection request.

        Returns:
        tuple -- a tuple of boolean indicating success or failure, and error message
        if failure.
        """
        # TODO: cleanup
        units = event.params["units"]
        model = self.model.config["model"]

        u = []
        a = []
        for t in units.split(","):
            if "/" in t:
                u.append(t)
            else:
                a.append(t)

        ips = await self._get_unit_ips(model, u, a)
        ssh_user = self.model.config["ssh-user"]
        # Build the sos collect command
        collect_cmd = f"sudo -u {ssh_user} sos collect --no-local \
                        --nopasswd-sudo --batch --nodes {ips}"
        collect_cmd = f"{collect_cmd} --ssh-user {ssh_user}"

        try:
            # Get the case id
            case_id = event.params["case"]
        except KeyError:
            msg = "Please specify a case number identifier"
            return False, msg

        collect_cmd = f"{collect_cmd} --case-id {case_id}"
        # Append any extra arguments if available
        extra_args = event.params.get("extra-args")
        if extra_args:
            collect_cmd = f"{collect_cmd} {extra_args}"

        logger.info(collect_cmd)

        try:
            # Execute the sos collection command
            check_call(collect_cmd, stdout=DEVNULL, shell=True)
        except CalledProcessError as e:
            msg = f"sos collection failed: {e.output}"
            logger.error(msg)
            return False, msg

        return True, None

    def _upload_sos(self, files):
        """Upload files to the file server using SCP transfer.

        Arguments:
        files -- list of file names to be uploaded

        Returns:
        tuple -- a tuple of boolean indicating success or failure and msg.
        """
        file_server = self.model.config["server"]
        username = self.model.config["server-username"]
        password = self.model.config["server-password"]
        # Loop through each file to upload
        for file in files:
            self._scp_transfer(file, file_server, ".", username, password)

        return True, None

    def _clear_local_sos(self, files):
        """Remove local sosreport files after upload."""
        for file in files:
            os.remove(file)

    def _scp_transfer(self, src_file, dst_server, dst_path, username, password):
        """Upload sosreport to ftp server."""
        try:
            client = paramiko.Transport((dst_server, 22))
            client.connect(username=username, password=password)
            sftp = client.open_sftp_client()

            dst_file = src_file.split("/")[-1]
            # If the file name begins with 'sosreport-', STS-API will add a
            # comment to SF case.
            # Rename the file from sos-collector* to sosreport*
            dst_file = dst_file.replace("sos-collector", "sosreport", 1)
            dst_file = dst_path + "/" + dst_file
            logger.info(f"target file {dst_file}")
            sftp.put(src_file, dst_file)

            sftp.close()
            client.close()
        except (socket.error, paramiko.ssh_exception.AuthenticationException) as e:
            logger.error(str(e))
            return False, str(e)

    async def _connect_controller(self) -> None:
        if not self.controller.is_connected():
            # TODO: validate config vars
            await self.controller.connect(
                endpoint=self.model.config["juju-endpoint"],
                username=self.model.config["juju-username"],
                password=self.model.config["juju-password"],
                cacert=self.model.config["juju-cacert"],
            )

    async def _get_unit_ips(self, model_name, units, applications):
        unit_ips = []
        await self._connect_controller()
        model = await self.controller.get_model(model_name)
        status = await model.get_status()
        await model.disconnect()

        for application in applications:
            logger.info(
                f"Getting public IPs for application {model_name}/{application}"
            )
            try:
                for unit in status.applications[application].units:
                    unit_ips.append(
                        str(status.applications[application].units[unit].public_address)
                    )
            except Exception as err:  # pylint: disable=W0703
                logger.error(err)

        for unit in units:
            # TOFIX
            logger.info(f"Getting public IP for unit {model_name}/{unit}")
            application = unit.split("/", 1)[0]
            try:
                unit_ips.append(
                    str(status.applications[application].units[unit].public_address)
                )
            except Exception as err:  # pylint: disable=W0703
                logger.error(err)

        return ",".join(unit_ips)


if __name__ == "__main__":
    main(SosreportCharm, use_juju_for_storage=True)
