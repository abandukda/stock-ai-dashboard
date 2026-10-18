# ATLAS Contabo migration readiness

This runbook prepares a safe migration from the authoritative DigitalOcean
runner to the owner-provisioned Contabo VPS. It does not authorize access,
licensed-evidence transfer, secret transfer, runner cutover, or shutdown.

## Current boundary

- Owner-supplied terminal evidence verifies the Contabo Cloud VPS 12 hardware
  profile, Ubuntu 24.04, and successful root SSH access. This is evidence of
  initial host reachability only; Codex has not independently verified the SSH
  host identity or inspected the machine.
- Non-root key-only administration, independent SSH host-key verification,
  baseline hardening, protected-data migration, runner registration, and a
  provider-free certification on this host are still **PENDING**.
- The DigitalOcean runner and its protected mounts remain authoritative.
- licensed evidence transfer is not authorized until target security, licensing,
  exact scope, and explicit owner approval are all established.

The owner should use the provider console to record the server's SSH host-key
fingerprint before the next administrative session.
Passwords, recovery codes, and private keys must never be pasted into GitHub,
Codex, commands captured in logs, or this repository.

## First authorized login

Before accepting the SSH connection, compare the presented host-key fingerprint
with the trusted console value. After login, record only sanitized output from:

```bash
cat /etc/os-release
lscpu
free -h
df -hT
ip -brief address
sshd -T | grep -E '^(passwordauthentication|permitrootlogin|pubkeyauthentication)'
systemctl --no-pager --failed
apt list --upgradable
ufw status verbose
```

Create a dedicated administrative user, add the owner's public SSH key, and
prove a second login before changing root/password authentication. Preserve
Contabo recovery-console access. Apply security updates and firewall rules only
after access recovery is proven.

## Source inventory and manifest

Inventory without modifying these DigitalOcean sources:

- `/mnt/atlas_incremental_raw`
- `/mnt/atlas_incremental_checkpoints`
- the 41 retained-history shards and their registered aggregate identity
- original/recovery acquisition envelopes and certification artifacts
- Report Card primary and independently stored backup identities
- position-shadow storage and runner service metadata

Generate a restart-safe file list and SHA-256 manifest on the source filesystem:

```bash
find /mnt/atlas_incremental_raw /mnt/atlas_incremental_checkpoints -xdev -type f -print0 \
  | sort -z | xargs -0 sha256sum > atlas-source.sha256
```

Record mount identity, capacity, ownership, modes, file count, byte count, and
manifest digest. Never delete or alter the DigitalOcean source.

## Authorized transfer design

After security, licensing, capacity, and explicit owner approval:

1. Create separate protected raw/checkpoint destinations owned by the dedicated
   runner account with mode `0700`.
2. Transfer over authenticated SSH with restart-safe `rsync --partial` while
   preserving modes and times. Do not copy provider secrets or runner tokens.
3. Verify every destination file with the source `sha256sum` manifest.
4. Perform read-only provider-free replay and checkpoint-resume validation.
5. Keep an independent recovery copy on storage outside the Contabo system.
6. Register the replacement runner with a fresh GitHub runner registration token
   and noncompeting labels. Do not clone runner credentials.
7. Keep the DigitalOcean runner operational until a separately approved cutover.

One physical Contabo disk cannot serve as both primary and independent backup.

## Exact approvals still required

1. Owner confirms the trusted SSH host key and proves non-root key-only login.
2. Owner authorizes baseline hardening after that key-based login is proven.
3. Owner confirms Finnhub retention/hosting terms permit the named evidence
   classes on Contabo.
4. Owner approves an exact path/file-count/byte-count migration manifest.
5. Owner separately approves GitHub runner registration and controlled cutover.
