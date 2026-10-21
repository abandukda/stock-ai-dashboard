"""Pure credential-role matching. Never infer privilege from credential cleanup."""
from __future__ import annotations
import hmac
from typing import Mapping


class CredentialRoleCollision(ValueError):
    pass


def qa_password(value: str | None) -> str:
    """Match app whitespace policy while preserving literal quote characters."""
    return str(value or '').strip()


def credential_configuration(admin: str, viewers: Mapping[str, str]) -> dict:
    admin = qa_password(admin)
    configured = {name: qa_password(value) for name, value in viewers.items() if qa_password(value)}
    collisions = sorted(name for name, value in configured.items()
                        if admin and hmac.compare_digest(admin.encode(), value.encode()))
    return {'admin_configured': bool(admin), 'viewer_aliases': sorted(configured),
            'ambiguous_aliases': collisions, 'role_configuration_valid': not collisions}


def resolve_credential_role(password: str, *, admin: str, viewers: Mapping[str, str]) -> str | None:
    configuration = credential_configuration(admin, viewers)
    if not configuration['role_configuration_valid']:
        raise CredentialRoleCollision('AUTH_ROLE_CONFIGURATION_AMBIGUOUS')
    supplied = qa_password(password)
    if not supplied:
        return None
    if admin and hmac.compare_digest(supplied.encode(), qa_password(admin).encode()):
        return 'admin'
    if any(qa_password(value) and hmac.compare_digest(supplied.encode(), qa_password(value).encode())
           for value in viewers.values()):
        return 'viewer'
    return None


def select_qa_credential(override: str | None, environment: Mapping[str, str]) -> tuple[str, str]:
    """An explicit empty override must fail authentication, never switch identity."""
    if override is not None:
        return qa_password(override), 'EXPLICIT_OVERRIDE'
    for name in ('ATLAS_AUDIT_PASSWORD', 'GUEST_PASSWORD', 'VIEWER_PASSWORD', 'VIEW_PASSWORD'):
        if environment.get(name):
            return qa_password(environment[name]), name
    return '', 'UNCONFIGURED'
