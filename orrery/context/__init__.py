"""Per-cwd context resolution: the right context for the project you are in, and
nothing from the projects you are not. Ends the shared-digest cross-contamination.
"""

from .config import ContextConfig, load_config
from .resolver import ContextBundle, resolve
from .scope import Scope, resolve_scope

__all__ = ["ContextConfig", "load_config", "ContextBundle", "resolve", "Scope", "resolve_scope"]
