import ast
from pathlib import Path
import pytest
from services.authentication_roles import (
    CredentialRoleCollision, credential_configuration, qa_password, resolve_credential_role,
)


def test_literal_quoted_viewer_never_becomes_admin():
    viewers = {'GUEST_PASSWORD': '"operator"'}
    assert qa_password(' "operator" ') == '"operator"'
    assert resolve_credential_role(qa_password('"operator"'), admin='operator', viewers=viewers) == 'viewer'
    assert resolve_credential_role('operator', admin='operator', viewers=viewers) == 'admin'


@pytest.mark.parametrize('alias', ['VIEWER_PASSWORD', 'GUEST_PASSWORD', 'VIEW_PASSWORD'])
def test_alias_collision_fails_closed_without_secret_disclosure(alias):
    secret = 'never-print-credential'
    info = credential_configuration(secret, {alias: secret})
    assert info['ambiguous_aliases'] == [alias]
    assert secret not in str(info)
    with pytest.raises(CredentialRoleCollision) as exc:
        resolve_credential_role(secret, admin=secret, viewers={alias:secret})
    assert secret not in str(exc.value)


def test_distinct_aliases_and_unmatched_or_missing_credentials():
    viewers = {'GUEST_PASSWORD':'guest-one','VIEW_PASSWORD':'guest-two','VIEWER_PASSWORD':''}
    assert resolve_credential_role('guest-one',admin='admin',viewers=viewers) == 'viewer'
    assert resolve_credential_role('guest-two',admin='admin',viewers=viewers) == 'viewer'
    assert resolve_credential_role('admin',admin='admin',viewers=viewers) == 'admin'
    assert resolve_credential_role('',admin='admin',viewers=viewers) is None
    assert resolve_credential_role('unknown',admin='admin',viewers=viewers) is None


def test_app_checks_collision_before_session_restoration_and_keeps_one_login_path():
    tree=ast.parse(Path('app.py').read_text())
    gate=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='dashboard_login_gate')
    code=ast.unparse(gate)
    assert code.index('role_configuration_valid') < code.index("get('authenticated')")
    assert 'resolve_credential_role' in code
    assert 'password == ADMIN_PASSWORD' not in code


def test_explicit_empty_override_never_falls_back_to_another_identity():
    from services.authentication_roles import select_qa_credential
    environment = {'ATLAS_AUDIT_PASSWORD':'admin', 'GUEST_PASSWORD':'viewer'}
    assert select_qa_credential('', environment) == ('', 'EXPLICIT_OVERRIDE')
    assert select_qa_credential(' "viewer" ', environment) == ('"viewer"', 'EXPLICIT_OVERRIDE')
    assert select_qa_credential(None, environment) == ('admin', 'ATLAS_AUDIT_PASSWORD')
    assert select_qa_credential(None, {}) == ('', 'UNCONFIGURED')
