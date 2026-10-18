"""Offline synthetic layout experiment; no research project or model access."""
import argparse
import hashlib
import json
import platform
import sqlite3
import tempfile
import time
from pathlib import Path


def measure(count, versions, mode):
    with tempfile.TemporaryDirectory(prefix='ct-reference-layout-') as temporary:
        path=Path(temporary)/'synthetic.sqlite3'
        db=sqlite3.connect(path)
        db.executescript('CREATE TABLE chunks(id TEXT PRIMARY KEY); CREATE TABLE items(chunk TEXT,position INTEGER,paper TEXT,assignment TEXT,PRIMARY KEY(chunk,position)); CREATE TABLE links(version INTEGER,bucket INTEGER,chunk TEXT,PRIMARY KEY(version,bucket)); CREATE TABLE full(version INTEGER,paper TEXT,assignment TEXT,PRIMARY KEY(version,paper));')
        papers=[hashlib.sha256(('invented-paper-'+str(i)).encode()).hexdigest() for i in range(count)]
        assignments={p:hashlib.sha256((p+'-0').encode()).hexdigest() for p in papers}
        started=time.perf_counter();digests=[]
        for version in range(versions):
            if version:
                for p in papers[version*7:version*7+7]:assignments[p]=hashlib.sha256((p+'-'+str(version)).encode()).hexdigest()
            ordered=sorted(assignments.items());digests.append(hashlib.sha256(json.dumps(ordered).encode()).hexdigest())
            if mode=='full-rows':
                db.executemany('INSERT INTO full VALUES (?,?,?)',((version,p,a) for p,a in ordered))
            else:
                buckets={}
                for p,a in ordered:buckets.setdefault(int(p[:2],16),[]).append((p,a))
                for bucket,items in sorted(buckets.items()):
                    # This experiment measures <=10k entries; production further
                    # divides each bucket into bounded chunks, not a collection cap.
                    key=hashlib.sha256(json.dumps(items).encode()).hexdigest()
                    fresh=db.execute('INSERT OR IGNORE INTO chunks VALUES (?)',(key,)).rowcount
                    if fresh:db.executemany('INSERT INTO items VALUES (?,?,?,?)',((key,i,p,a) for i,(p,a) in enumerate(items)))
                    db.execute('INSERT INTO links VALUES (?,?,?)',(version,bucket,key))
            db.commit()
        write_seconds=time.perf_counter()-started
        query=('SELECT paper,assignment FROM full WHERE version=? ORDER BY paper LIMIT 100 OFFSET ?' if mode=='full-rows' else
            'SELECT i.paper,i.assignment FROM links v JOIN items i ON i.chunk=v.chunk WHERE v.version=? ORDER BY v.bucket,i.position LIMIT 100 OFFSET ?')
        started=time.perf_counter();page=db.execute(query,(versions-1,max(0,count-100))).fetchall();page_seconds=time.perf_counter()-started
        restored=(db.execute('SELECT paper,assignment FROM full WHERE version=0 ORDER BY paper').fetchall() if mode=='full-rows' else
            sorted(db.execute('SELECT i.paper,i.assignment FROM links v JOIN items i ON i.chunk=v.chunk WHERE v.version=0').fetchall()))
        assert hashlib.sha256(json.dumps(restored).encode()).hexdigest()==digests[0]
        assert len(page)==min(count,100)
        rows=db.execute('SELECT COUNT(*) FROM '+('full' if mode=='full-rows' else 'items')).fetchone()[0]
        plan=[r[3] for r in db.execute('EXPLAIN QUERY PLAN '+query,(versions-1,max(0,count-100)))]
        db.close()
        return {'papers':count,'versions':versions,'corrections_per_successor':7,'mode':mode,
            'membership_rows':rows,'database_bytes':path.stat().st_size,'write_seconds':round(write_seconds,4),
            'last_page_seconds':round(page_seconds,6),'historical_reconstruction_verified':True,'query_plan':plan}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--counts',nargs='+',type=int,default=[1000,5000,10000])
    parser.add_argument('--versions',type=int,default=12)
    args=parser.parse_args()
    if not 1<=args.versions<=100 or any(not 1<=n<=100000 for n in args.counts):parser.error('Choose bounded synthetic benchmark workloads')
    print(json.dumps({'schema':'corpustrail-reference-layout-experiment/v1','python':platform.python_version(),
        'platform':platform.system(),'sqlite':sqlite3.sqlite_version,'synthetic_only':True,
        'results':[measure(n,args.versions,m) for n in args.counts for m in ('full-rows','shared-buckets')]},indent=2))


if __name__=='__main__':main()
