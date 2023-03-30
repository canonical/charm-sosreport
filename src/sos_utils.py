"""Collections of sos related utilities."""
import glob
import logging
from pathlib import Path
from subprocess import DEVNULL, CalledProcessError, check_call
from typing import List, Optional, Union

from uploader import Uploader

logger = logging.getLogger(__name__)


class ReportNotFoundError(Exception):
    """Report not found exception."""


class SoSCollectHelper:
    """Helper class for 'sos collect'."""

    sos_collect_cmd_base = "sos collect"
    sos_default_options = "--no-local --nopasswd-sudo --batch"

    def __init__(self, uploader: Uploader, tmp_dir: Union[str, Path] = "/tmp"):
        """Initialize the sos collect helper class."""
        self.tmp_dir = tmp_dir
        self.uploader = uploader
        self.sos_collect_cmd = f"{self.sos_collect_cmd_base} {self.sos_default_options}"

    def collect(self, nodes: str, extra_args: Optional[str] = None) -> bool:
        """Collect the sos report from selected nodes."""
        success, msg = True, "sos collection suceeded."
        command = f"{self.sos_collect_cmd} --nodes {nodes}"
        if extra_args is not None:
            command = f"{command} {extra_args}"

        try:
            logger.info("running command %s", command)
            check_call(command, stdout=DEVNULL, shell=True)
        except CalledProcessError as error:
            logger.error("sos collection failed: %s", str(error))

        logger.info(msg)
        return success

    def get_reports(self, case_id: str) -> List[str]:
        """Get the sos reports filtered by case_id."""
        path = Path(self.tmp_dir, f"sos*{case_id}*")
        return glob.glob(str(path))

    def upload_reports(self, reports: List[str], cleanup: Optional[bool] = False) -> bool:
        """Upload the sos reports to the server using an uploader."""
        logger.info("uploading sos reports.")
        success = self.uploader.upload(reports)

        if success and cleanup:
            logger.info("cleaning up temporary sos reports.")
            self.cleanup_reports(reports)

        return success

    def cleanup_reports(self, reports: List[str]) -> bool:
        """Clean up the local sos reports."""
        success = True
        for report in reports:
            try:
                logger.info("removing report %s.", report)
                Path(report).unlink()
            except PermissionError as error:
                logger.error(str(error))
                success = False
            except FileNotFoundError as error:
                logger.error(str(error))
                success = False

        return success
