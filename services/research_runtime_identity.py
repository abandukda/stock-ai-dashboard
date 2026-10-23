"""Read-only function-body comparison; not data or complete runtime attestation.

Compile fixed code files without executing them. Inspect the actual by-value
function bindings held by the renderer; never import/reload a financial module,
invoke a financial function, inspect configuration or access retained data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import CodeType, FunctionType

_ROOT = Path(__file__).resolve().parents[1]
_TARGETS = (
    ('view', 'services/customer_research_view.py', 'build_customer_research_view'),
    ('projection', 'services/customer_research_v2.py', 'build_customer_research_v2'),
    ('reader', 'services/research_market_read_model.py', 'load_research_market_context'),
)
_MAX_SOURCE_BYTES = 1024 * 1024


def _constant(value):
    if isinstance(value, CodeType):
        return ['code', _body(value)]
    if value is None or value is Ellipsis:
        return ['none' if value is None else 'ellipsis']
    if type(value) in (bool, int, str):
        return [type(value).__name__, value]
    if type(value) is bytes:
        return ['bytes', value.hex()]
    if type(value) is float:
        return ['float', value.hex()]
    if type(value) is complex:
        return ['complex', value.real.hex(), value.imag.hex()]
    if type(value) is tuple:
        return ['tuple', [_constant(item) for item in value]]
    if type(value) is frozenset:
        return ['frozenset', sorted((_constant(item) for item in value), key=_encoded)]
    raise TypeError('UNSUPPORTED_CODE_CONSTANT')


def _body(code):
    # Ignore filenames/line tables: identical bodies can move in a source file.
    # Include nested bodies, free variables and exception handling bytecode.
    return {
        'name': code.co_name, 'code': code.co_code.hex(),
        'args': [code.co_argcount, code.co_posonlyargcount, code.co_kwonlyargcount],
        'flags': code.co_flags, 'locals': code.co_nlocals, 'stack': code.co_stacksize,
        'names': code.co_names, 'vars': code.co_varnames,
        'free': code.co_freevars, 'cells': code.co_cellvars,
        'exceptions': getattr(code, 'co_exceptiontable', b'').hex(),
        'constants': [_constant(value) for value in code.co_consts],
    }


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _fingerprint(code):
    return hashlib.sha256(_encoded(_body(code)).encode()).hexdigest()


def _read_source(path):
    with path.open('rb') as source:
        value = source.read(_MAX_SOURCE_BYTES + 1)
    if len(value) > _MAX_SOURCE_BYTES:
        raise ValueError('SOURCE_BOUND')
    return value


def _binding(function, name):
    # Do not invoke custom mapping methods from an unexpected callable graph.
    if type(function) is not FunctionType or type(function.__globals__) is not dict:
        return None
    return function.__globals__.get(name)


def research_function_body_identity(view_builder):
    """Return sanitized observations of three bound functions, with no reload.

    BODY_MATCH only compares executable bodies under this interpreter. It does
    not attest globals/constants, defaults, decorators, helpers, configuration,
    source-data identity, financial authority, or chart admission.
    """
    projection = _binding(view_builder, 'build_customer_research_v2')
    reader = _binding(projection, 'load_research_market_context')
    result = {'scope': 'FUNCTION_BODIES_ONLY', 'data_admission': 'NOT_ATTESTED',
              'globals_defaults_helpers': 'NOT_ATTESTED'}
    for (label, relative, name), bound in zip(_TARGETS, (view_builder, projection, reader)):
        item = {'status': 'UNAVAILABLE', 'loaded_sha256': '', 'disk_sha256': ''}
        if type(bound) is FunctionType:
            try:
                path = _ROOT / relative
                if path.stat().st_size > _MAX_SOURCE_BYTES:
                    raise ValueError('SOURCE_BOUND')
                source = _read_source(path)
                module = compile(source, relative, 'exec', dont_inherit=True, optimize=sys.flags.optimize)
                expected = [c for c in module.co_consts if isinstance(c, CodeType) and c.co_name == name]
                if len(expected) != 1 or _read_source(path) != source:
                    raise ValueError('SOURCE_UNSTABLE_OR_AMBIGUOUS')
                item['loaded_sha256'] = _fingerprint(bound.__code__)
                item['disk_sha256'] = _fingerprint(expected[0])
                item['status'] = ('BODY_MATCH' if item['loaded_sha256'] == item['disk_sha256']
                                  else 'BODY_MISMATCH')
            except Exception:
                # Diagnostics must not crash Research or leak a source/path.
                item = {'status': 'UNAVAILABLE', 'loaded_sha256': '', 'disk_sha256': ''}
        result[label] = item
    return result
