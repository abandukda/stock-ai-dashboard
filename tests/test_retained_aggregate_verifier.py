import hashlib
from pathlib import Path
import stat
import tracemalloc
import zipfile
import pytest
from scripts.verify_retained_aggregate import verify_archive


def archive(tmp_path,entries):
    p=tmp_path/'fixture.zip'
    with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
        for name,value in entries:z.writestr(name,value)
    return p,hashlib.sha256(p.read_bytes()).hexdigest()


def test_required_pin_and_readonly_identity(tmp_path):
    p,digest=archive(tmp_path,[('nested/evidence.json','{}')]);before=p.read_bytes()
    result=verify_archive(p,expected_sha256=digest,expected_size=len(before),required_file_sha256={'evidence.json':hashlib.sha256(b'{}').hexdigest()})
    assert result['status']=='PASS' and result['required_file_hashes_verified']
    assert not result['financial_certification'] and not result['ledger_access']
    assert p.read_bytes()==before and list(tmp_path.iterdir())==[p]


@pytest.mark.parametrize('name',['../bad','/bad','win\\bad','a:bad','ledger.sqlite3','ledger.sqlite3-wal','ledger.sqlite3-journal','.env','nested/secrets.toml'])
def test_protected_members_and_traversal_never_opened(tmp_path,name,monkeypatch):
    p,digest=archive(tmp_path,[(name,'DO_NOT_READ')])
    def forbidden(*a,**k):raise AssertionError('unsafe member was opened')
    monkeypatch.setattr(zipfile.ZipFile,'open',forbidden)
    with pytest.raises(ValueError):verify_archive(p,expected_sha256=digest)


def test_wrong_zip_member_hash_size_and_missing_required_pin_fail(tmp_path):
    p,digest=archive(tmp_path,[('evidence.json','{}')])
    for kwargs in [{'expected_sha256':'0'*64},{'expected_sha256':digest,'expected_size':1},
                   {'expected_sha256':digest,'required_file_sha256':{'missing.json':'0'*64}},
                   {'expected_sha256':digest,'required_file_sha256':{'evidence.json':'0'*64}}]:
        with pytest.raises(ValueError):verify_archive(p,**kwargs)


def test_symlink_rejected_before_opening_payload(tmp_path):
    p=tmp_path/'link.zip';member=zipfile.ZipInfo('link');member.create_system=3;member.external_attr=(stat.S_IFLNK|0o777)<<16
    with zipfile.ZipFile(p,'w') as z:z.writestr(member,'target')
    with pytest.raises(ValueError,match='LINK'):verify_archive(p,expected_sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def test_streamed_96mib_member_keeps_python_allocation_bounded(tmp_path):
    p=tmp_path/'large.zip'
    with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
        with z.open('GENERATED_FIXTURE.bin','w') as out:
            for _ in range(96):out.write(b'F'*1024**2)
    digest=hashlib.sha256(p.read_bytes()).hexdigest();tracemalloc.start()
    try:
        result=verify_archive(p,expected_sha256=digest);_,peak=tracemalloc.get_traced_memory()
    finally:tracemalloc.stop()
    assert result['files'][0]['bytes']==96*1024**2
    assert peak<12*1024**2


def test_dispatch_never_schedules_or_routes_protected_runner_and_uploads_receipts_only():
    import yaml
    root=Path(__file__).resolve().parents[1]
    workflow=yaml.load((root/'.github/workflows/atlas_retained_aggregate_verify.yml').read_text(),Loader=yaml.BaseLoader)
    assert set(workflow['on'])=={'workflow_dispatch'}
    assert workflow['permissions']=={'contents':'read','actions':'read'}
    job=workflow['jobs']['verify']
    assert job['runs-on']=='ubuntu-24.04' and 'environment' not in job
    assert "github.actor == 'abandukda'" in job['if']
    assert 'inputs.approved_source_sha == github.sha' in job['if']
    assert 'AUTHORIZE_RETAINED_ARCHIVE_VERIFY' in job['if']
    assert set(job['strategy']['matrix']['artifact_id'])=={'11318542723','11456584757'}
    upload=job['steps'][-1]
    assert upload['with']['path']=='audit_results/aggregate'
    assert 'retained.zip' not in upload['with']['path']


def test_declared_expansion_bound_rejected_before_member_open(tmp_path,monkeypatch):
    from scripts.verify_retained_aggregate import _safe_members,MAX_MEMBER
    info=zipfile.ZipInfo('large.bin');info.file_size=MAX_MEMBER+1
    with pytest.raises(ValueError,match='EXPANSION'):_safe_members([info])


def test_cli_failure_saves_sanitized_receipt_without_opening_database(tmp_path):
    import json,subprocess,sys
    output=tmp_path/'receipt.json'
    result=subprocess.run([sys.executable,'scripts/verify_retained_aggregate.py',
                           '--archive',str(tmp_path/'PRIVATE_DO_NOT_OPEN.sqlite3'),
                           '--artifact-id','11318542723','--output',str(output)],capture_output=True,text=True)
    assert result.returncode==1
    receipt=json.loads(output.read_text())
    assert receipt['status']=='FAILED' and not receipt['ledger_access']
    assert receipt['error']=='ARCHIVE_INPUT_MUST_BE_ZIP'
    assert 'PRIVATE_DO_NOT_OPEN' not in json.dumps(receipt)+result.stdout+result.stderr


def test_corrupt_member_crc_is_not_accepted_even_with_matching_outer_hash(tmp_path):
    p=tmp_path/'crc.zip'
    with zipfile.ZipFile(p,'w',zipfile.ZIP_STORED) as z:z.writestr('evidence.json','ORIGINAL_CONTENT')
    data=p.read_bytes().replace(b'ORIGINAL_CONTENT',b'CORRUPT__CONTENT');p.write_bytes(data)
    with pytest.raises(zipfile.BadZipFile):
        verify_archive(p,expected_sha256=hashlib.sha256(data).hexdigest())
