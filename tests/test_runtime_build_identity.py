from services.runtime_build_identity import HOME_RENDERER_VERSION, runtime_build_identity


def test_runtime_identity_uses_explicit_deployment_metadata():
    identity = runtime_build_identity({
        "ATLAS_BUILD_SHA": "08ffe8822fa8010985838e719ffc592a0cac86e3",
        "ATLAS_DEPLOY_BRANCH": "codex/discovery-engine-v2",
    })
    assert identity == {
        "build_sha": "08ffe8822fa8010985838e719ffc592a0cac86e3",
        "short_sha": "08ffe882",
        "branch": "codex/discovery-engine-v2",
        "home_renderer_version": HOME_RENDERER_VERSION,
        "source": "DEPLOYMENT_ENVIRONMENT",
    }


def test_runtime_identity_never_infers_sha_from_local_git():
    identity = runtime_build_identity({})
    assert identity["build_sha"] == "UNAVAILABLE"
    assert identity["branch"] == "UNAVAILABLE"
    assert identity["source"] == "NOT_EXPOSED_BY_DEPLOYMENT"


def test_invalid_deployment_sha_fails_closed():
    identity = runtime_build_identity({"ATLAS_BUILD_SHA": "main-latest"})
    assert identity["build_sha"] == "UNAVAILABLE"
