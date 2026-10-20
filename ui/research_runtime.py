"""Keep presentation imports coherent when Streamlit retains worker modules."""
from __future__ import annotations

import importlib
import threading


_MODULES = (
    "ui.research_learning",
    "ui.customer_research_v2",
    "ui.research_vnext",
)
_lock = threading.RLock()
_loaded_build = None


def research_renderers(source_sha: str):
    """Refresh presentation dependencies once per worker/build, in import order.

    Re-importing a name alone returns Python's cached module. Reloading the
    learning helper before its consumers prevents a new deployment marker from
    describing old renderer code. No provider, authority or ledger is reloaded.
    """
    global _loaded_build
    with _lock:
        modules = {name: importlib.import_module(name) for name in _MODULES}
        if _loaded_build != source_sha:
            for name in _MODULES:
                modules[name] = importlib.reload(modules[name])
            _loaded_build = source_sha
        return (
            modules["ui.customer_research_v2"].render_customer_research_first_screen,
            modules["ui.research_vnext"].render_full_research_vnext,
        )
