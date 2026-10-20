"""Regression for a new deployed SHA retaining the previous Research renderer."""
from types import SimpleNamespace

from ui import research_runtime as runtime


def test_refreshes_consumers_after_dependencies_once_per_deployed_build(monkeypatch):
    events = []
    first = object()
    full = object()
    modules = {name: SimpleNamespace(name=name) for name in runtime._MODULES}
    modules['ui.customer_research_v2'].render_customer_research_first_screen = 'stale'
    modules['ui.research_vnext'].render_full_research_vnext = 'stale'

    def reload_module(module):
        events.append(module.name)
        if module.name == 'ui.customer_research_v2':
            module.render_customer_research_first_screen = first
        if module.name == 'ui.research_vnext':
            module.render_full_research_vnext = full
        return module

    monkeypatch.setattr(runtime, '_loaded_build', None)
    monkeypatch.setattr(runtime.importlib, 'import_module', modules.__getitem__)
    monkeypatch.setattr(runtime.importlib, 'reload', reload_module)
    assert runtime.research_renderers('a' * 40) == (first, full)
    assert events == list(runtime._MODULES)
    runtime.research_renderers('a' * 40)
    assert len(events) == 3
    runtime.research_renderers('b' * 40)
    assert events == list(runtime._MODULES) * 2


def test_failed_refresh_does_not_certify_the_new_build(monkeypatch):
    monkeypatch.setattr(runtime, '_loaded_build', 'previous')
    monkeypatch.setattr(runtime.importlib, 'import_module', lambda name: SimpleNamespace(name=name))

    def fail(_module):
        raise ImportError('renderer unavailable')

    monkeypatch.setattr(runtime.importlib, 'reload', fail)
    import pytest
    with pytest.raises(ImportError):
        runtime.research_renderers('new')
    assert runtime._loaded_build == 'previous'
