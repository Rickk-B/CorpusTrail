"""Read-only redacted heuristics over every reachable Git blob and commit.

Run from this repository. No Git config, environment values or matched content
is printed. No network, checkout changes, credential rotation or history edits.
This is evidence for human review, not a guarantee that opaque secrets are absent.
"""
import collections
import json
from pathlib import Path
import subprocess
from audit_release import inspect_text


def audit(root):
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args])
    objects=git('rev-list','--objects','--all').decode('utf-8').splitlines()
    findings=[];counts=collections.Counter();binary=[]
    child=subprocess.Popen(['git','-C',str(root),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    try:
        for line in objects:
            oid,_,path=line.partition(' ')
            child.stdin.write((oid+'\n').encode());child.stdin.flush()
            header=child.stdout.readline().decode('ascii').split();size=int(header[-1])
            # Resource bound applies to scans too; large objects stay visible.
            if size>25_000_000:
                remaining=size
                while remaining:
                    part=child.stdout.read(min(remaining,65536));remaining-=len(part)
                raw=None
            else:raw=child.stdout.read(size)
            child.stdout.read(1)
            if header[1]!='blob':
                if raw is not None:
                    found,_=inspect_text(raw.decode('utf-8',errors='replace'),'<'+header[1]+'>')
                    findings.extend({**f,'oid':oid} for f in found)
                continue
            counts['unique_blobs']+=1
            if raw is None:
                findings.append({'path':path,'oid':oid,'category':'oversized_blob_not_scanned','bytes':size});continue
            signatures=((b'%PDF','pdf'),(b'SQLite format 3','database'),(b'PK\x03\x04','zip'),(b'\x1f\x8b','gzip'))
            kind=next((name for magic,name in signatures if raw.startswith(magic)),None)
            if kind:findings.append({'path':path,'oid':oid,'category':kind,'bytes':size})
            try:text=raw.decode('utf-8')
            except UnicodeDecodeError:
                counts['binary_blobs']+=1
                if not (path.startswith('browser_tests/baselines/') and raw.startswith(b'\x89PNG\r\n\x1a\n')):
                    binary.append({'path':path,'oid':oid,'bytes':size})
                continue
            found,_=inspect_text(text,path)
            findings.extend({**f,'oid':oid} for f in found)
        identities=git('log','--all','--format=%ae%n%ce').decode('utf-8').splitlines()
        neutral=all(x=='noreply@corpustrail.invalid' for x in identities)
    finally:
        child.stdin.close();child.wait();child.stdout.close()
    return {'schema':'corpustrail-redacted-history-audit/v1',
        'commit_count':int(git('rev-list','--all','--count')),'counts':dict(counts),
        'neutral_commit_emails_only':neutral,'findings_requiring_review':findings,
        'unclassified_binary_blobs':binary,
        'limitations':'Reachable local refs only; pattern heuristics cannot certify no secrets. Test literals require review. GitHub logs/artifacts, dependency advisories and rights require separate checks.'}


if __name__=='__main__':print(json.dumps(audit(Path(__file__).resolve().parents[1]),indent=2))
