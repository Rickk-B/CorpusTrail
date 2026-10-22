"""Injected offline examples only; never registered by the production launcher."""
from dataclasses import replace
from corpustrail._internal.values import content_hash
from corpustrail.classification import Assessment, AssessmentPlan, EngineDescription, ClassificationService, Budgets
from .fixtures import AT


class CurationExample:
    def __init__(self,identity,*,alternate=False):self.identity=identity;self.alternate=alternate

    def describe(self):
        return EngineDescription(self.identity,'fixture/v1',content_hash({'synthetic':self.identity,'alternate':self.alternate}),
            'invented-offline','curation-fixture','v1','no-model')

    def prepare(self,request):
        return AssessmentPlan(request.request_sha256,request.engine_sha256,content_hash(__import__('json').loads(request.settings_json)),{'synthetic_only':True})

    def assess(self,plan,chunk):
        values=[]
        for unit in chunk:
            target=unit.input()['target']
            # Identity-ordered stable synthetic labels, not title-based science.
            code=int(content_hash(target['paper_id']).split(':')[1][:8],16)%3
            if self.alternate:code=(code+1)%3
            values.append(Assessment(target['paper_id'],('include','exclude','uncertain')[code],
                'insufficient' if code==2 else 'sufficient','Invented offline architecture example; no scientific inference.',
                (target['representation']['sha256'],),'Synthetic uncertainty, not calibrated probability.',('No real-model validation.',)))
        return tuple(values)


def seed(fixture):
    project=fixture.project
    if 'fixture_reviewer' not in project.config.review.authorized_reviewers:
        project.configure(replace(project.config,config_version=project.config.config_version+1,
            review=replace(project.config.review,authorized_reviewers=('fixture_reviewer',))),
            expected_event_id=project.configuration_history()[-1]['event_id'],created_by='fixture',created_at=AT)
    revision=project.configuration_history()[-1]['event_id']
    fields=dict(request_id='a'*32,name='Synthetic curation population',actor='fixture_reviewer',sources=[{'kind':'all'}],parent=None)
    preview=project.populations.preview(**fields)
    population=project.populations.create(**fields,expected_preview_sha256=preview['preview_sha256'],created_at=AT)['version_id']
    changes=[{'action':'assign','paper_id':pid,'label':'in_scope' if i==0 else 'out_of_scope',
        'producer':{'type':'human','id':'fixture_reviewer','version':'manual/v1'},'human_attested':True,
        'rationale':'Invented boundary example.','evidence_used':['metadata'],'supersedes':[],'source_assignment_ids':[],
        'source_event_id':None,'source_artifact_sha256':None,'source_record':'synthetic-curation:'+str(i)} for i,pid in enumerate(fixture.papers[:2])]
    fields=dict(request_id='b'*32,name='Synthetic scope examples',actor='fixture_reviewer',parent=None,changes=changes,created_at=AT,config_event_id=revision)
    preview=project.references.preview(**fields);reference=project.references.commit(**fields,expected_preview_sha256=preview['preview_sha256'])['version_id']
    engines=[CurationExample('synthetic.curation-a'),CurationExample('synthetic.curation-b',alternate=True)]
    for engine in engines:fixture.curation_registry.register(engine)
    service=ClassificationService(project,registry=fixture.curation_registry);runs=[]
    for index,engine in enumerate(engines):
        fields=dict(request_id=str(index+1)*32,name='Synthetic curation '+str(index+1),actor='fixture_reviewer',created_at=AT,
            config_event_id=revision,population_version_id=population,reference_version_id=reference,engine_id=engine.identity,
            engine_version='fixture/v1',budgets=Budgets(max_items_per_execution=100))
        preview=service.prepare(**fields);plan=service.commit_plan(**fields,expected_preview_sha256=preview['preview_sha256'])
        run=service.start_run(plan['plan_id'],request_id=str(index+3)*32,actor='fixture_reviewer',created_at=AT)['run_id']
        service.execute(run,expected_revision=service.inspect_run(run)['revision'],clock=lambda:AT);runs.append(run)
    return {'population':population,'reference':reference,'runs':runs,'service':service}
