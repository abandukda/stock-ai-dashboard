"""Refresh only stateless presentation dependencies after a warm Streamlit deploy.

Financial projection, authentication, data/ledger and provider modules are not
admitted. No files are written, caches cleared, services restarted or data read.
"""
from __future__ import annotations
import hashlib
import importlib
from pathlib import Path
from threading import RLock

_ALLOWED = frozenset({'ui.premium_home_styles', 'ui.research_reference_components',
                      'services.research_investment_digest'})
_LOCK = RLock()


def presentation_module(name: str):
    if name not in _ALLOWED:
        raise ValueError('PRESENTATION_MODULE_NOT_ALLOWED')
    with _LOCK:
        module = importlib.import_module(name)
        path = Path(module.__file__)
        if path.suffix != '.py':
            raise RuntimeError('PRESENTATION_PYTHON_SOURCE_REQUIRED')
        source_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if getattr(module, '__atlas_presentation_source_sha256__', None) != source_digest:
            # A new UI function can meet an older imported constant or projection
            # in a long-lived process. Refresh these pure dependencies only.
            importlib.invalidate_caches()
            module = importlib.reload(module)
            if hashlib.sha256(path.read_bytes()).hexdigest() != source_digest:
                raise RuntimeError('PRESENTATION_SOURCE_CHANGED_DURING_LOAD')
            module.__atlas_presentation_source_sha256__ = source_digest
        return module
