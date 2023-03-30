"""Collections of juju helper functions."""
import asyncio
from typing import List, Set

from juju.controller import Controller
from juju.model import Model


class ModelNotFoundError(Exception):
    """Juju model not found exception."""


class AppNotFoundError(Exception):
    """Juju application not found exception."""


class UnitNotFoundError(Exception):
    """Juju unit not found exception."""


class MachineNotFoundError(Exception):
    """Juju machine not found exception."""


def parse_comma_separated_string(strings: str) -> List[str]:
    """Parse commad separated string."""
    return [string.strip() for string in strings.split(",")]


def _get_ip_by_apps(model: Model, apps: List[str]) -> List[str]:
    model_apps = model.applications.keys()
    if not set(apps).issubset(model_apps):
        raise AppNotFoundError(
            f"{set(apps).difference(model_apps)} does not exists. "
            f"Available applications are {model_apps}"
        )
    return [unit.public_address for app in apps for unit in model.applications[app].units]


def _get_ip_by_units(model: Model, units: List[str]) -> List[str]:
    model_units = model.units.keys()
    if not set(units).issubset(model_units):
        raise UnitNotFoundError(
            f"{set(units).difference(model_units)} does not exists. "
            f"Available units are {model_units}"
        )
    return [model.units[unit].public_address for unit in units]


def _get_ip_by_machines(model: Model, machines: List[str]) -> List[str]:
    model_machines = model.machines.keys()
    if not set(machines).issubset(model_machines):
        raise MachineNotFoundError(
            f"{set(machines).difference(model_machines)} does not exists. "
            f"Available machines are {model_machines}"
        )
    # need to find the public_address from unit object.
    machines_set = set(machines)
    return [
        unit.public_address
        for unit in model.units.values()
        if unit.safe_data["machine-id"] in machines_set
    ]


async def _get_nodes(  # pylint: disable=too-many-arguments
    endpoint: str,
    username: str,
    password: str,
    cacert: str,
    model_name: str,
    apps_string: str = "",
    units_string: str = "",
    machines_string: str = "",
) -> Set[str]:
    """Get the public ip address of the nodes in juju 'cluster'."""
    controller = Controller()
    await controller.connect(
        endpoint=endpoint, username=username, password=password, cacert=cacert
    )

    all_models = set(await controller.list_models())
    if model_name not in all_models:
        raise ModelNotFoundError(
            f"{model_name} does not exists. Avaliable models are {all_models}."
        )

    model = await controller.get_model(model_name)

    nodes = set()

    if apps_string != "":
        apps = parse_comma_separated_string(apps_string)
        nodes.update(_get_ip_by_apps(model, apps))

    if units_string != "":
        units = parse_comma_separated_string(units_string)
        nodes.update(_get_ip_by_units(model, units))

    if machines_string != "":
        machines = parse_comma_separated_string(machines_string)
        nodes.update(_get_ip_by_machines(model, machines))

    return nodes or {unit.public_address for unit in model.units.values()}


def get_nodes(  # pylint: disable=too-many-arguments
    endpoint: str,
    username: str,
    password: str,
    cacert: str,
    model_name: str,
    apps_string: str = "",
    units_string: str = "",
    machines_string: str = "",
) -> Set[str]:
    """Get the public ip address of the nodes in juju 'cluster'."""
    return asyncio.run(
        _get_nodes(
            endpoint,
            username,
            password,
            cacert,
            model_name,
            apps_string,
            units_string,
            machines_string,
        )
    )
