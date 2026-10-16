"""Offline real urllib/application/scientific pipeline; never contact a provider."""
from contextlib import contextmanager
import io
import json
import socket
import ssl
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from corpustrail.application.discovery import _SafeTransport, request_failure, transport_failure_type, offline_environment_report
from corpustrail._internal.pipeline import events
from corpustrail.project import Project, ProjectConfig, ProviderConfig
from corpustrail.providers import metadata_provider
from corpustrail.providers.network import UrlLibTransport, ProviderTransportError

AT='2026-01-01T00:00:00+00:00'
PRIVATE='private-proxy-password-and-local-path'


class TransportDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='ct-transport-synthetic-');self.addCleanup(temp.cleanup)
        self.project=Project.create(Path(temp.name)/'project',ProjectConfig('transport-fixture','Synthetic transport','Fixture',
            providers=(ProviderConfig('europepmc','europepmc'),)),created_by='fixture',created_at=AT)

    def execute(self,responses,**bounds):
        provider=metadata_provider('europepmc')
        plan=self.project.discovery.plan(provider,run_id='transport-fixture',query='synthetic',created_at=AT,**bounds)
        transport=UrlLibTransport()
        @contextmanager
        def response(status,headers):
            yield type('Response',(),{'status':status,'headers':headers,'read':lambda _,n:b'{}',
                'geturl':lambda _:'https://www.ebi.ac.uk/europepmc/webservices/rest/search'})()
        outcomes=[]
        for item in responses:
            if isinstance(item,BaseException):outcomes.append(item)
            else:outcomes.append(response(*item))
        with patch.object(transport._opener,'open',side_effect=outcomes) as opened,patch('socket.create_connection',side_effect=AssertionError('No network permitted')):
            result=self.project.discovery.execute(plan,provider,transport=_SafeTransport(transport,[]),
                confirm_external=True,clock=lambda:AT,sleeper=lambda _:None)
        return result,opened,events(self.project,scope_id=plan.run_id,kind='request_result'),request_failure(self.project,plan.run_id)

    def test_typed_failures_are_sanitized_and_keep_no_response_retry_contract(self):
        cases=((ssl.SSLCertVerificationError(1,PRIVATE),'ProviderCertificateError'),
            (ssl.SSLError(1,PRIVATE),'ProviderTlsError'),(socket.gaierror(-2,PRIVATE),'ProviderDnsError'),
            (TimeoutError(PRIVATE),'ProviderTimeoutError'),(ConnectionRefusedError(PRIVATE),'ProviderConnectionRefusedError'),
            (OSError(PRIVATE),'ProviderTransportError'),(urllib.error.URLError('Tunnel connection failed: '+PRIVATE),'ProviderTransportError'))
        for primitive,name in cases:
            with self.subTest(category=name),tempfile.TemporaryDirectory() as temp:
                self.project=Project.create(Path(temp)/'project',ProjectConfig('transport-fixture','Synthetic','Fixture',providers=(ProviderConfig('europepmc','europepmc'),)),created_by='fixture',created_at=AT)
                result,opened,records,diagnostic=self.execute([urllib.error.URLError(primitive)])
                self.assertEqual(opened.call_count,1);self.assertEqual(result['outcome'],'retryable_error')
                self.assertEqual(records[0]['payload']['error'],name)
                self.assertIsNone(records[0]['payload']['http_status']);self.assertFalse(records[0]['payload']['will_retry'])
                serialized=json.dumps(records)+json.dumps(diagnostic)
                self.assertNotIn(PRIVATE,serialized);self.assertNotIn('HTTP 429',diagnostic['message'])
                self.assertEqual(self.project.identities.papers(),[])

    def test_retry_exhaustion_retains_every_attempt_without_policy_change(self):
        result,opened,records,diagnostic=self.execute([TimeoutError(PRIVATE)]*3,max_attempts=3,retry_delay_seconds=0)
        self.assertEqual(opened.call_count,3);self.assertEqual(result['physical_attempts'],3)
        self.assertEqual([e['payload']['will_retry'] for e in records],[True,True,False])
        self.assertIn('No further automatic attempt',diagnostic['message'])

    def test_real_http_errors_remain_distinct_from_no_response(self):
        for status in (429,500,503):
            with self.subTest(status=status),tempfile.TemporaryDirectory() as temp:
                self.project=Project.create(Path(temp)/'project',ProjectConfig('transport-fixture','Synthetic','Fixture',providers=(ProviderConfig('europepmc','europepmc'),)),created_by='fixture',created_at=AT)
                error=urllib.error.HTTPError('https://www.ebi.ac.uk/europepmc/webservices/rest/search',status,PRIVATE,{'Retry-After':'3600'},io.BytesIO(b'controlled response'))
                result,opened,records,diagnostic=self.execute([error],max_attempts=3)
                self.assertEqual(opened.call_count,1);self.assertTrue(records[0]['payload']['retry_blocked'])
                self.assertEqual(diagnostic['http_status'],status);self.assertIn('HTTP '+str(status),diagnostic['message'])
                self.assertIn('Retry blocked',diagnostic['message']);self.assertNotIn(PRIVATE,json.dumps(records))

    def test_default_ssl_and_proxy_handlers_and_no_redirect_remain_in_effect(self):
        transport=UrlLibTransport()
        names={type(h).__name__ for h in transport._opener.handlers}
        self.assertIn('HTTPSHandler',names);self.assertIn('_NoRedirect',names)
        from corpustrail.providers.network import _NoRedirect
        self.assertIsNone(_NoRedirect().redirect_request(None,None,302,'',{},'https://example.invalid'))
        # Classification must not execute or interpolate hostile exception text.
        error=ProviderTransportError(PRIVATE);error.__cause__=error
        self.assertIs(transport_failure_type(error),ProviderTransportError)

    def test_offline_environment_diagnostic_never_connects_or_prints_paths_secrets(self):
        with patch('socket.create_connection',side_effect=AssertionError('No network')),patch('urllib.request.urlopen',side_effect=AssertionError('No requests')),patch('urllib.request.getproxies',return_value={'https':'https://user:'+PRIVATE+'@proxy.invalid'}):
            value=offline_environment_report()
        self.assertTrue(value['offline']);self.assertFalse(value['project_access'])
        self.assertEqual(value['proxy_configuration_present'],{'https':True})
        self.assertNotIn(PRIVATE,json.dumps(value));self.assertNotIn(str(Path.home()),json.dumps(value))


if __name__=='__main__':unittest.main()
