"""Pinned, test-only workaround for WebKit's inert screenshot style injection.

Playwright 1.63 injects `body {}` even when its screenshot has no animation to
sync. Strict CSP correctly blocks that inline stylesheet. Disable ONLY that
inert synchronization step in the driver process, in memory. Never bypass CSP,
alter application responses, filter console errors or modify installed files.
"""
from contextlib import contextmanager
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path

BUNDLE_SHA256='549070af3acabb3efcc4f55bfe6210f9f7c2fcf633cf7eaa59bfe60719969171'


@contextmanager
def driver_environment(engine):
    if engine!='webkit':
        yield
        return
    import playwright
    bundle=Path(playwright.__file__).parent/'driver/package/lib/coreBundle.js'
    if version('playwright')!='1.63.0' or hashlib.sha256(bundle.read_bytes()).hexdigest()!=BUNDLE_SHA256:
        raise ValueError('WebKit screenshot adapter requires its reviewed Playwright 1.63 driver hash')
    if os.environ.get('NODE_OPTIONS'):
        raise ValueError('Use an isolated test process without NODE_OPTIONS for the pinned WebKit adapter')
    changes={'NODE_OPTIONS':'--require '+json.dumps(str(Path(__file__).with_suffix('.cjs'))),
             'CORPUSTRAIL_PLAYWRIGHT_BUNDLE':str(bundle.resolve())}
    previous={k:os.environ.get(k) for k in changes}
    try:
        os.environ.update(changes)
        yield
    finally:
        for k,v in previous.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
