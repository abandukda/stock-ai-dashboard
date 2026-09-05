from services.data_mode_policy import AtlasDataMode, atlas_data_mode, display_scope, internal_trial_mode


def test_development_default_is_internal_trial():
    assert atlas_data_mode(environ={}, secrets={}) is AtlasDataMode.INTERNAL_TRIAL
    assert internal_trial_mode(environ={}, secrets={}) is True
    assert display_scope(environ={}, secrets={}) == "INTERNAL_TRIAL"


def test_commercial_mode_is_explicit_and_invalid_values_fail_closed():
    assert atlas_data_mode(environ={"ATLAS_DATA_MODE": "COMMERCIAL_CUSTOMER"}) is AtlasDataMode.COMMERCIAL_CUSTOMER
    assert atlas_data_mode(environ={"ATLAS_DATA_MODE": "unexpected"}) is AtlasDataMode.COMMERCIAL_CUSTOMER

