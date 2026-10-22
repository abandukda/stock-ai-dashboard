"""Bounded, provider-free ZIP integrity verification. Never extracts source files."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat
import zipfile

CHUNK=1024*1024
MAX_ENTRIES=1024
MAX_MEMBER=16*1024**3
MAX_EXPANDED=32*1024**3


def _digest(stream):
    digest=hashlib.sha256();size=0
    while True:
        block=stream.read(CHUNK)
        if not block: return digest.hexdigest(),size
        digest.update(block);size+=len(block)


def _safe_members(members):
    if len(members)>MAX_ENTRIES: raise ValueError('ARCHIVE_ENTRY_LIMIT')
    names=set();total=0
    for member in members:
        name=member.filename;p=PurePosixPath(name)
        if (not name or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name
                or any(ord(c)<32 for c in name) or len(name)>1024 or name in names):
            raise ValueError('ARCHIVE_UNSAFE_PATH_OR_DUPLICATE')
        names.add(name)
        if stat.S_ISLNK(member.external_attr>>16): raise ValueError('ARCHIVE_LINK_FORBIDDEN')
        if member.flag_bits&1: raise ValueError('ARCHIVE_ENCRYPTION_FORBIDDEN')
        lower=p.name.lower()
        if (lower.endswith(('.db','.sqlite','.sqlite3','-wal','-shm','-journal'))
                or lower in {'.env','secrets.toml','.runner'} or lower.startswith('.credentials')):
            raise ValueError('ARCHIVE_PROTECTED_MEMBER_FORBIDDEN')
        total+=member.file_size
        if member.file_size>MAX_MEMBER or total>MAX_EXPANDED: raise ValueError('ARCHIVE_EXPANSION_LIMIT')


def verify_archive(path, *, expected_sha256, expected_size=None, required_file_sha256=None):
    if not re.fullmatch('[0-9a-f]{64}',expected_sha256): raise ValueError('ARCHIVE_EXPECTED_HASH_INVALID')
    if Path(path).suffix!='.zip': raise ValueError('ARCHIVE_INPUT_MUST_BE_ZIP')
    # One read-only stable descriptor, no symlink traversal or primary/backup DB access.
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(fd,'rb') as source:
        before=os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode): raise ValueError('ARCHIVE_INPUT_NOT_REGULAR')
        if expected_size is not None and before.st_size!=expected_size: raise ValueError('ARCHIVE_SIZE_MISMATCH')
        digest,size=_digest(source)
        if digest!=expected_sha256: raise ValueError('ARCHIVE_SHA256_MISMATCH')
        source.seek(0);files=[];by_basename={}
        with zipfile.ZipFile(source) as archive:
            members=archive.infolist();_safe_members(members) # validate ALL names before opening ANY member
            for member in members:
                if member.is_dir():continue
                with archive.open(member,'r') as payload: member_sha,read_size=_digest(payload)
                if read_size!=member.file_size:raise ValueError('ARCHIVE_MEMBER_SIZE_MISMATCH')
                files.append({'name':member.filename,'bytes':read_size,'sha256':member_sha})
                basename=PurePosixPath(member.filename).name
                by_basename.setdefault(basename,[]).append(member_sha)
        for name,pin in (required_file_sha256 or {}).items():
            if by_basename.get(name)!=[pin]:raise ValueError('ARCHIVE_REQUIRED_FILE_HASH_MISMATCH')
        after=os.fstat(source.fileno())
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise ValueError('ARCHIVE_CHANGED_DURING_VERIFICATION')
    return {'schema':'ATLAS_AGGREGATE_READONLY_RECEIPT_V1','status':'PASS','archive_sha256':digest,
            'archive_bytes':size,'files':files,'required_file_hashes_verified':bool(required_file_sha256),
            'chunk_bytes':CHUNK,'provider_calls':0,'ledger_access':False,'production_writes':0,
            'financial_certification':False,'current_market_data_certified':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',required=True,type=Path)
    parser.add_argument('--artifact-id',required=True,type=int);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--config',type=Path,default=Path('config/retained_aggregate_verification.json'))
    args=parser.parse_args()
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    output={'status':'FAILED','error':'ARCHIVE_VERIFICATION_FAILED','provider_calls':0,'ledger_access':False,'production_writes':0}
    try:
        config=json.loads(args.config.read_text());item=next(x for x in config['artifacts'] if x['artifact_id']==args.artifact_id)
        output=verify_archive(args.archive,expected_sha256=item['archive_sha256'],expected_size=item['archive_size_bytes'],required_file_sha256=item['required_file_sha256'])
        output.update({'artifact_id':item['artifact_id'],'source_run_id':item['run_id'],'source_sha':item['source_sha']})
        result=0
    except Exception:
        result=1 # no raw exception text, paths or source content in failure reports
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(output,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:output[k] for k in ('status','provider_calls','ledger_access','production_writes')}))
    return result

if __name__=='__main__':raise SystemExit(main())
