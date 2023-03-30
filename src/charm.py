#!/usr/bin/env python3

"""Entrypoint of the charm."""
import json
import logging
from typing import Any

from ops.charm import ActionEvent, CharmBase, HookEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus

from cluster import get_nodes
from sos_utils import SoSCollectHelper
from uploader import Uploader

logger = logging.getLogger(__name__)


class SosreportCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args: Any) -> None:
        """Init."""
        super().__init__(*args)

        self.logger = logger

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.collect_action, self._on_collect_action)
        self.framework.observe(self.on.cleanup_action, self._on_cleanup_action)
        self.framework.observe(self.on.upload_action, self._on_upload_action)

        uploader = Uploader(
            self.model.config["upload-method"],
            server=self.model.config["server"],
            username=self.model.config["username"],
            password=self.model.config["password"],
            private_key=self.model.config["private-key"],
        )
        self.sos_collect_helper = SoSCollectHelper(uploader, tmp_dir=self.model.config["tmp-dir"])

    def _on_install(self, _: HookEvent) -> None:
        self.model.unit.status = ActiveStatus("Unit is ready.")

    def _on_collect_action(self, event: ActionEvent) -> None:
        """Run "sos collect" to collect system state information and logs."""
        if not (event.params["model-name"] or self.model.config["model-name"]):
            event.fail(
                "Failed to collect sos reports."
                "'model-name' from either action param of config option is required."
            )
            return

        nodes = get_nodes(
            endpoint=self.model.config["juju-endpoint"],
            username=self.model.config["juju-username"],
            password=self.model.config["juju-password"],
            cacert=self.model.config["juju-cacert"],
            model_name=event.params["model-name"] or self.model.config["model-name"],
            apps=event.params["apps"],
            units=event.params["units"],
            machines=event.params["machines"],
        )

        extra_args = " ".join(
            [
                f"--tmp-dir {self.model.config['tmp-dir']}",
                f"--sos-cmd {self.model.config['sos-cmd']}",
                f"--ssh-user {self.model.config['ssh-user']}",
                f"--case-id {event.params['case-id']}",
                f"{event.params['extra-args']}",
            ]
        )

        success = self.sos_collect_helper.collect(",".join(nodes), extra_args)

        if not success:
            event.fail("Failed to collect sos reports. Check juju debug-log for more details.")
            return

        reports = self.sos_collect_helper.get_reports(event.params["case-id"])
        event.set_results({"sos-reports": json.dumps(reports, indent=4)})

    def _on_upload_action(self, event: ActionEvent) -> None:
        """Upload sos reports to the server using appropriate upload method."""
        reports = self.sos_collect_helper.get_reports(event.params["case-id"])
        success = self.sos_collect_helper.upload_reports(
            reports, cleanup=event.params["cleanup"] is True
        )

        if not success:
            event.fail("Failed to upload sos reports. Check juju debug-log for more details.")
            return

        event.set_results({"success": success})

    def _on_cleanup_action(self, event: ActionEvent) -> None:
        """Remove locally stored sos reports."""
        reports = self.sos_collect_helper.get_reports(event.params["case-id"])
        success = self.sos_collect_helper.cleanup_reports(reports)

        if not success:
            event.fail("Failed to clean up sos reports. Check juju debug-log for more details.")
            return

        event.set_results({"success": success})


if __name__ == "__main__":
    main(SosreportCharm, use_juju_for_storage=True)
