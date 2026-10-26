"""Controlled provider transport, real OAuth/Responses parser and CP8 services.

No scientific API responses are mocked. No account or real eligibility is used.
"""
import io
import json
import time

from corpustrail._internal.values import content_hash
from corpustrail.chatgpt.connection import ChatGPTConnection, DIRECT
from corpustrail.chatgpt.credentials import CredentialStore
from corpustrail.chatgpt.transport import API, AUTH, DISCOVERY, Transport


class Wire(io.BytesIO):
    status = 200


class ProviderFixture:
    def __init__(self): self.sent=[]; self.limit=False
    def open(self, request, **kwargs):
        if request.full_url == API+'/models':
            return Wire(json.dumps({'models':[{'slug':'synthetic-model','display_name':'Synthetic offline model','visibility':'list'}]}).encode())
        if request.full_url == DISCOVERY: return Wire(json.dumps({'revocation_endpoint':AUTH+'/oauth/revoke'}).encode())
        if request.full_url == AUTH+'/oauth/revoke': return Wire()
        if request.full_url != API+'/responses': raise AssertionError('Unexpected synthetic ChatGPT endpoint')
        value=json.loads(request.data); self.sent.append(value)
        if self.limit:
            return Wire(b'data: {"type":"response.failed","response":{"error":{"code":"subscription_sharing_usage_limit_exceeded"}}}\n\n')
        target=json.loads(value['input'][0]['content'])['target']
        answer={'paper_id':target['paper_id'],'outcome':'uncertain','evidence_sufficiency':'unknown',
            'rationale':'Synthetic protocol example; no real model or scientific performance claim.',
            'uncertainty':'Not scientifically validated.','limitations':['Offline simulated output only.'],
            'evidence_hashes':target['source_hashes']}
        response={'status':'completed','id':'synthetic-response','model':'synthetic-reported-model',
            'output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':json.dumps(answer)}]}],
            'usage':{'input_tokens':10,'output_tokens':10}}
        return Wire(('data: '+json.dumps({'type':'response.completed','response':response})+'\n\n').encode())


class ConnectionFixture(ChatGPTConnection):
    def status(self):
        result=super().status();result['installed']=True  # Simulates the approved optional extra, not live identity.
        return result


def client(fixture):
    if not hasattr(fixture,'chatgpt_wire'):fixture.chatgpt_wire=ProviderFixture()
    return ConnectionFixture(store=CredentialStore(fixture.base/'private-chatgpt'),
        transport=Transport(open_request=fixture.chatgpt_wire.open))


def connect(fixture, *, permitted=True, notice=True):
    with fixture.chatgpt.connection.store.transaction() as state:
        state['host_id']='urn:uuid:00000000-0000-4000-8000-000000000001';state['active']='synthetic-chatgpt-profile'
        state['profiles'][state['active']]={'client_id':'oaiapp_synthetic','subject':'synthetic-subject',
            'label':'Synthetic offline registration','access_token':'synthetic-access','refresh_token':'synthetic-refresh',
            'scope':DIRECT,'expires_at':time.time()+3600,'plan_notice_acknowledged':notice,
            'plan_only_permit':{'client_id':'oaiapp_synthetic','subject':'synthetic-subject','credits_disabled_verified':permitted,
                'owner_evidence_sha256':'0'*64,'expires_at':time.time()+3600}}
    fixture.chatgpt.connection._models={'synthetic-chatgpt-profile':[{'slug':'synthetic-model','display_name':'Synthetic offline model'}]}
