#!/usr/bin/env python3
"""Run on the authoritative source host only. Verify bytes; never copy or write."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat


def identity(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('REGULAR_FILE_REQUIRED')
        h = hashlib.sha256()
        while True:
            block = os.read(descriptor, 1024*1024)
            if not block:
                break
            h.update(block)
        after = os.fstat(descriptor)
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns) != (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
            raise ValueError('SOURCE_CHANGED_DURING_READ')
        return after, h.hexdigest()
    finally:
        os.close(descriptor)


def verify(source, backup, expected):
    a, ah = identity(source); b, bh = identity(backup)
    if (a.st_dev,a.st_ino) == (b.st_dev,b.st_ino):
        raise ValueError('BACKUP_IS_SAME_FILE')
    if ah != expected or bh != expected:
        raise ValueError('EXPECTED_SOURCE_OR_BACKUP_DIGEST_MISMATCH')
    if a.st_dev == b.st_dev:
        raise ValueError('BACKUP_MUST_USE_INDEPENDENT_STORAGE')
    return dict(status='BYTE_IDENTITIES_VERIFIED', sha256=expected, bytes=a.st_size,
                independent_device=True, physical_failure_domain_verified=False,
                ledger_chain_certified=False, source_modified=False, transfer=False)


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--backup',required=True,type=Path)
    p.add_argument('--expected-sha256',required=True)
    args=p.parse_args()
    if len(args.expected_sha256)!=64 or any(c not in '0123456789abcdef' for c in args.expected_sha256):
        raise SystemExit('EXACT_EXPECTED_SHA256_REQUIRED')
    print(json.dumps(verify(args.source,args.backup,args.expected_sha256),sort_keys=True))
