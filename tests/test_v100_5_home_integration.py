from pathlib import Path


def test_v100_5_app_integration_contract():
    app_text = Path("app.py").read_text(encoding="utf-8")

    assert "V1005_INSTITUTIONAL_HOME_INTEGRATION_VERIFIED = True" in app_text
    assert 'APP_VERSION = "V100.5 Institutional Home Integration"' in app_text
    assert "v1005_render_command_center" in app_text
    assert "v1005_render_institutional_card" in app_text
    assert "_v1005_prior_dynamic_home" in app_text


def test_v100_5_preserves_legacy_home_fallback():
    app_text = Path("app.py").read_text(encoding="utf-8")

    assert "Legacy Discovery Detail" in app_text
    assert "_v1005_prior_dynamic_home(full_df, top_df, recovery_df)" in app_text


def test_v100_5_uses_read_only_engine_contracts():
    app_text = Path("app.py").read_text(encoding="utf-8")

    required = [
        "v1005_validate_transparency_contract",
        "v1005_validate_ranking_contract",
        "v1005_validate_competition_contract",
        "v1005_validate_command_center_contract",
    ]
    for name in required:
        assert name in app_text
