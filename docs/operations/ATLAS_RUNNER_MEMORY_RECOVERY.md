# ATLAS protected-runner memory and recovery control

This runbook applies to the existing DigitalOcean host registered as
`atlas-worker-1`. It does not authorize a host reboot, runner replacement,
provider call, or production write.

## Confirmed incident

Protected certification run `38920625431`, job `117059234617`, ended with
exit 137 after the Linux kernel killed `python3` for exhausting the 8 GiB
host. Kernel evidence recorded `anon-rss:7633808kB`. The failure is an OOM,
not a GitHub runner timeout.

## Service recovery audit

Discover the installed unit rather than assuming its generated name:

```sh
systemctl list-units --type=service --all 'actions.runner*'
systemctl status <discovered-unit> --no-pager -l
systemctl show <discovered-unit> -p Restart -p RestartSec -p StartLimitBurst -p StartLimitIntervalUSec
journalctl -u <discovered-unit> --since '2026-10-16 15:30:00 UTC' --no-pager
journalctl -k --since '2026-10-16 15:30:00 UTC' --no-pager
```

The recommended supported override, after the unit name is verified by the
owner/host administrator, is:

```ini
[Service]
Restart=on-failure
RestartSec=15s
StartLimitIntervalSec=300
StartLimitBurst=3
```

Apply with `systemctl edit <discovered-unit>`, then
`systemctl daemon-reload`. Restarting the active service or Droplet remains a
separate privileged action and is not required merely to install the override.
Do not configure an infinite restart loop.

## Capacity and alert evidence

Before a protected replay, retain `free -h`, `df -h`, `df -i`, and
`/proc/meminfo`. The registered certification workflow records GNU time's
maximum RSS and fails unless it proves a peak below 5 GiB. Alerting should fire
when available memory stays below 1 GiB, swap activity grows unexpectedly,
the runner changes to Offline, disk usage exceeds 80%, or the daily workflow
misses its monitored completion window.

The certification checkpoint root is durable and bound to source SHA, plan
digest, receipt-set digest, finalized session, governed membership digest,
batch size, and run identity. Resume may reuse only checkpoints matching that
entire binding. Partial checkpoints never authorize publication.
