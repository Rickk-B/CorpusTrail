"""Optional installed ASReview 2.2 CSV import smoke; isolated synthetic state only.

Not part of the dependency-free package or test suite. Never accesses the user's
ASReview projects, starts a service, performs active learning, or makes requests.
"""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import runpy
import tempfile


def run():
    import asreview
    from asreview import Project as ASProject
    from asreview.data.tabular import CSVReader, CSVWriter
    from corpustrail.project import Project
    if importlib.metadata.version('asreview')!='2.2':
        raise RuntimeError('this optional smoke is frozen against installed ASReview 2.2')
    candidate=Path(__file__).resolve().parents[1]
    demo=runpy.run_path(str(candidate/'examples/synthetic-asreview/run.py'))
    with tempfile.TemporaryDirectory(prefix='corpustrail-asreview-import-smoke-') as temporary:
        root=Path(temporary); corpus=root/'corpus'
        demo['run'](corpus)
        project=Project.open(corpus)
        before=project.database_path.read_bytes()
        artifact=corpus/'data/asreview/exports/fixture-corpus/dataset.csv'
        records=CSVReader.read_records(artifact,dataset_id='synthetic-import')
        assert len(records)==3 and all(r.included is None for r in records)
        # ASReview's Record drops custom columns. Its original input is preserved.
        ASProject.create(root/'asreview-temporary',project_id='synthetic-question',project_mode='oracle')
        downstream=ASProject(root/'asreview-temporary')
        downstream.add_dataset(artifact,dataset_id='synthetic-import')
        original=downstream.read_input_data()
        assert set(original.corpustrail_paper_id)=={r['corpustrail_paper_id'] for r in project.asreview.inspect('fixture-corpus')['snapshot']['records']}
        assert len(original)==3
        original['asreview_label']=[0,1,-1]
        output=root/'synthetic-downstream-results.csv'
        CSVWriter.write_data(original.iloc[::-1],output)
        mapping=project.asreview.map_results('fixture-corpus',results=output,review_id='installed-smoke',
            question_id='synthetic-question',mapping_id='synthetic-result',asreview_version='2.2',
            created_at='2026-01-01T00:00:00+00:00')
        assert len(mapping['records'])==3 and project.database_path.read_bytes()==before
        package=Path(asreview.__file__).parent
        return {'schema_version':'corpustrail-optional-asreview-smoke/v0','asreview_version':'2.2',
            'network_used':False,'temporary_project_only':True,'imported_records':len(records),
            'all_imported_labels_missing':True,'custom_ids_preserved_in_original_input':True,
            'reordered_exact_round_trip_records':len(mapping['records']), 'corpus_database_unchanged':True,
            'lab_browser_workflow_executed':False,
            'scope':'actual reader/project import/writer; synthetic downstream labels; LAB original-input export source inspected, not end-to-end browser tested',
            'installed_source_hashes':{name:'sha256:'+hashlib.sha256((package/name).read_bytes()).hexdigest()
                for name in ('data/base.py','data/record.py','data/tabular.py','project/api.py','webapp/_api/projects.py')}}


if __name__=='__main__':print(json.dumps(run(),sort_keys=True,indent=2))
