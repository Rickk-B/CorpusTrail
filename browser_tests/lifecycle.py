"""Test-only request lifecycle and bounded failure collection (no browser imports)."""
from collections import deque
from contextlib import contextmanager
import signal
import time
from urllib.parse import urlsplit


class RequestLedger:
    """Retain event timing, never headers, bodies, query values or opaque paths."""
    def __init__(self, origin, clock=time.monotonic):
        self.origin = origin
        self.clock = clock
        self.started = clock()
        self.pending = {}
        self.recent = deque(maxlen=30)
        self.sequence = 0
        self.unmatched_completions = 0

    def begin(self, request):
        self.sequence += 1
        parsed = urlsplit(request.url)
        # Only fixed application route vocabulary survives; IDs and unknown
        # components (including filenames) never enter published diagnostics.
        words = {'api','v1','dashboard','projects','papers','review','sessions',
            'command','discovery','history','status','evidence','populations',
            'preview','freeze','union','configuration','settings','assets',
            'app.js','app.css','index.html','plans','jobs','create','open','close'}
        path = '/'.join(part if part in words else '<id>' for part in parsed.path.split('/') if part)
        method = request.method if request.method in {'GET','POST','HEAD','PUT','DELETE','OPTIONS'} else 'OTHER'
        self.pending[request] = {'sequence': self.sequence, 'method': method,
            'route': '/'+path if request.url.startswith(self.origin+'/') else '<external>',
            'query_present': bool(parsed.query), 'started_seconds': round(self.clock()-self.started,3),
            'response_status': None}

    def response(self, response):
        record = self.pending.get(response.request)
        if record is not None:
            record['response_status'] = response.status
            record['response_seconds'] = round(self.clock()-self.started,3)

    def end(self, request, event):
        record = self.pending.pop(request, None)
        if record is None:
            self.unmatched_completions += 1
        else:
            self.recent.append({**record, 'event': event,
                'completed_seconds': round(self.clock()-self.started,3)})

    def snapshot(self):
        elapsed = self.clock()-self.started
        return {'elapsed_seconds': round(elapsed,3), 'pending_count': len(self.pending),
            'pending': [{**v, 'age_seconds': round(elapsed-v['started_seconds'],3)}
                for v in self.pending.values()], 'recent': list(self.recent),
            'unmatched_completions': self.unmatched_completions}


def settle_reads(case):
    """Unchanged ten-second boundary and continuous half-second quiet interval."""
    deadline = time.monotonic()+10
    quiet = None
    while time.monotonic() < deadline:
        case.page.wait_for_timeout(50)  # Pump real Playwright events, not a sleep.
        if case.pending_requests:
            quiet = None
        elif quiet is None:
            quiet = time.monotonic()
        elif time.monotonic()-quiet >= .5:
            return
    case.navigation_timeouts.append(case.request_ledger.snapshot())
    case.fail('Local application requests did not finish within the bounded navigation wait')


def already_failed(case):
    result = case._outcome.result
    return any(test is case for test, _ in result.failures+result.errors)


def finalize_case(case):
    """Do not repeat a failed navigation wait or replace its original exception."""
    primary = already_failed(case)
    wait_error = None
    if not primary:
        try:
            case.settle_reads()
        except Exception as error:
            wait_error = error
    errors = case.diagnostics+case.fixture.errors+case.fixture.transport.errors
    failures = case.runtime.finish_case(case, errors, failed=primary or wait_error is not None)
    if wait_error is not None:
        raise wait_error
    if not primary:
        case.assertEqual(errors+failures, [], 'Browser/backend diagnostics must be clean')


@contextmanager
def diagnostic_deadline(seconds):
    """Bound synchronous cleanup on the existing Linux/macOS browser runners.

    Playwright tracing.stop/close have no public timeout argument. A restored
    main-thread POSIX timer bounds them without cross-thread Playwright access.
    No request is cancelled or suppressed during the scientific test itself.
    """
    if not hasattr(signal, 'setitimer'):
        raise RuntimeError('Diagnostic deadline requires the Linux/macOS browser runner')
    def expired(*_):
        raise TimeoutError('Bounded diagnostic operation timed out')
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    if previous_timer[0]:
        raise RuntimeError('Cannot replace an existing diagnostic timer')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
