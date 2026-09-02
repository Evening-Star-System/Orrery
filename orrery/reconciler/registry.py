"""Maps a check id to its implementation.

Profiles name checks by id, so the registry is the one place that knows the concrete
classes. Register a new check here and it becomes available to every profile.
"""

from __future__ import annotations

from .checks.base import Check
from .checks.behavior_lock import BehaviorLockCheck
from .checks.declared_presence import DeclaredPresenceCheck
from .checks.fleet_reach import FleetReachCheck
from .checks.floors import FloorsCheck
from .checks.managed_settings import ManagedSettingsCheck
from .checks.memory_headroom import MemoryHeadroomCheck
from .checks.org_map import OrgMapCheck
from .checks.secret_edges import SecretEdgesCheck
from .checks.session_ownership import SessionOwnershipCheck
from .checks.vault_capability import VaultCapabilityCheck

_REGISTRY: dict[str, Check] = {
    OrgMapCheck.id: OrgMapCheck(),
    DeclaredPresenceCheck.id: DeclaredPresenceCheck(),
    FleetReachCheck.id: FleetReachCheck(),
    SecretEdgesCheck.id: SecretEdgesCheck(),
    FloorsCheck.id: FloorsCheck(),
    ManagedSettingsCheck.id: ManagedSettingsCheck(),
    SessionOwnershipCheck.id: SessionOwnershipCheck(),
    MemoryHeadroomCheck.id: MemoryHeadroomCheck(),
    VaultCapabilityCheck.id: VaultCapabilityCheck(),
    BehaviorLockCheck.id: BehaviorLockCheck(),
}


def get_check(check_id: str) -> Check | None:
    return _REGISTRY.get(check_id)


def known_ids() -> list[str]:
    return sorted(_REGISTRY)


def option_schemas() -> dict[str, tuple[frozenset[str], frozenset[str]]]:
    """For each check that declares one, its (recognized_keys, required_keys). A check
    that declares neither is omitted, so it is validated by id only."""
    out: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
    for cid, check in _REGISTRY.items():
        keys = getattr(check, "option_keys", None)
        if keys is not None:
            out[cid] = (frozenset(keys), frozenset(getattr(check, "required_keys", frozenset())))
    return out
