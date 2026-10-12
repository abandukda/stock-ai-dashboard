# R1 exact-SHA deployment and rollback

## Reproducible runtime

- Python is pinned to 3.11 by `runtime.txt`.
- Direct Python dependencies are pinned in `requirements.txt` to the versions
  used by the reviewed local environment; CI must create a clean environment
  and install that file before certification.
- Secrets are referenced by name only and must be validated for presence through
  the deployment platform. Values must never appear in logs or artifacts.

## Deployment identity gate

Before promotion, record the current main SHA and Streamlit deployed SHA. After
an explicitly authorized fast-forward, require the application source marker,
customer navigation marker, repository, branch and entrypoint to match the new
exact main SHA. GitHub main alone is not deployment proof.

## Rollback

If startup, identity, authentication, authority parity, mobile CRC, or B1-B18
fails, redeploy the recorded pre-promotion main SHA using the supported
Streamlit deployment control. Do not rewrite certified data, reset the Report
Card ledger, force-push, or substitute a different runtime artifact. Verify the
rolled-back application source marker and repeat a bounded authentication/home
smoke check.

