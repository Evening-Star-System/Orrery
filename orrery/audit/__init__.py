"""Durable plan-audit: an append-only, tamper-evident record of every consequential action, as
proposed, approved, and resulting-diff. This is generic mechanism: it records. Any layer that reads
these records to make a decision is a separate concern and out of scope here."""

from .record import PlanRecord
from .store import AuditStore

__all__ = ["AuditStore", "PlanRecord"]
