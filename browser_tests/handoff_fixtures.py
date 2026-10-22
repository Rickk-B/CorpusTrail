"""Deterministic offline wire/ranking adapters below real application services."""
from corpustrail.models import AdapterInfo,ModelResponse,AdapterRegistry,ModelService
from corpustrail.prioritization import _algorithm


class OrderingFixture:
    method='synthetic_ordering_fixture'
    version='v1'
    def fit(self,snapshot,*,purpose,parent_model_id=None):
        return _algorithm.seal('model',{'method':self.method,'method_version':self.version,
            'training_snapshot_id':snapshot['artifact_id'],'training_snapshot':snapshot,'purpose':purpose,
            'parent_model_id':parent_model_id,'non_authoritative':True,'fixture_only':True})
    def scores(self,model,rows):
        _algorithm.check(model,'model');return [float(i)/max(1,len(rows)) for i,_ in enumerate(rows)]


class WireFixture:
    info=AdapterInfo('synthetic-wire','synthetic-offline','v1',True,('structured_assertions/v1','connection_test/v1'))
    def __init__(self):self.calls=[]
    def connection_request(self):return {'message':'Synthetic connection fixture only; no evidence.'}
    def test_connection(self,request,*,credential=None):
        self.calls.append(('connection',request));return ModelResponse({},'synthetic-model',('synthetic-model',),False)
    def invoke(self,request,*,credential=None):
        self.calls.append(('task',request));source=request['evidence'][0]
        return ModelResponse({'claims':[{'predicate':'ct.organism_population','raw_value':source['text'],
            'value_datatype':'string','evidence_id':source['evidence_id'],'quote':source['text']}]},
            'synthetic-model',('synthetic-model',),False)


def service(fixture,project):
    registry=AdapterRegistry([fixture.model_wire])
    from corpustrail.models.integrations import register_reference_adapters
    register_reference_adapters(registry)
    return ModelService(project,registry=registry)
