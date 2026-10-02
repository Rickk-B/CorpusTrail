"""Small scoped vocabulary, not an approved ontology or implicit field crosswalk."""
from copy import deepcopy
from dataclasses import asdict, dataclass
import json
import re

from corpustrail._internal.database import connection, latest_config
from corpustrail._internal.values import canonical, content_hash, identifier, text, timestamp, ContractError

VERSION = 'corpustrail-generic/v0a'
DEFINITIONS = {
    'ct.report_role': 'Report/study role; not review eligibility.',
    'ct.organism_population': 'Organism/population explicitly stated in source context.',
    'ct.human_participation': 'Actual human participants; not topic scope or human-derived material.',
    'ct.experimental_context': 'Explicit in vivo, ex vivo, in vitro or computational setting.',
    'ct.anatomical_system': 'Tissue or anatomical system in source context.',
    'ct.measurement_modality': 'Measurement technique; mention and use remain distinct.',
    'ct.intervention_exposure': 'Condition/exposure; not question-specific outcome extraction.',
    'ct.biological_process': 'Biological/mechanistic process; mention does not establish causation.',
    'ct.instrumentation_role': 'Development, calibration, application or discussion of a method.',
    'ct.evidence_availability': 'Representation availability; not sufficiency, relevance or authority.',
    'ct.publication_type': 'Publication format/type; separate from study role.',
    'ct.broad_corpus_membership': 'Explicit broad-topic review; not question-specific eligibility.',
    'bibliography.record': 'Source-bound bibliographic metadata; no scientific characterization inferred.',
}
CHARACTERIZATION = frozenset(DEFINITIONS) - {
    'ct.evidence_availability', 'ct.broad_corpus_membership', 'bibliography.record'}


@dataclass(frozen=True)
class Concept:
    concept_id: str
    version: str
    label: str
    description: str
    value_types: tuple[str, ...] = ()
    deprecated: bool = False
    superseded_by: str | None = None

    @property
    def namespace(self):
        return self.concept_id.split('.')[0]

    def to_dict(self):
        for key in ('concept_id', 'version', 'label', 'description'):
            text(getattr(self, key), key)
        if not re.fullmatch(r'[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*', self.concept_id):
            raise ContractError('concept requires an explicit namespace')
        if type(self.deprecated) is not bool or not isinstance(self.value_types, tuple):
            raise ContractError('invalid concept definition')
        if any(t not in ('unknown','string','boolean','integer','number','object','array') for t in self.value_types):
            raise ContractError('unknown value datatype expectation')
        if self.superseded_by is not None:
            text(self.superseded_by, 'replacement concept')
            if not self.deprecated or self.superseded_by == self.concept_id:
                raise ContractError('replacement needs explicit deprecation and a distinct concept')
        return json.loads(canonical({**asdict(self),'namespace':self.namespace}))

    @classmethod
    def from_dict(cls, value):
        raw = dict(value)
        namespace = raw.pop('namespace',None)
        result = cls(**{**raw, 'value_types': tuple(value.get('value_types', ()))})
        if namespace not in (None,result.namespace):
            raise ContractError('concept namespace mismatch')
        result.to_dict()
        return result


class Registry:
    def __init__(self, *, extensions=()):
        self._concepts = {key: Concept(key, VERSION, key.split('.')[1].replace('_',' '), description)
                          for key, description in DEFINITIONS.items()}
        for concept in extensions:
            concept.to_dict()
            if concept.concept_id.split('.')[0] in ('ct', 'bibliography', 'unmapped_field'):
                raise ContractError('extensions cannot redefine a reserved namespace')
            self._concepts[concept.concept_id] = concept

    @classmethod
    def for_project(cls, project):
        with connection(project.database_path) as db:
            return cls.from_connection(db)

    @classmethod
    def from_connection(cls, db):
        concepts = {}
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ct_knowledge_registry_records'").fetchone():
            # Read-only pre-035 adapter comparison: absence is not a migration.
            return cls()
        for row in db.execute('SELECT * FROM ct_knowledge_registry_records ORDER BY sequence'):
            p = json.loads(row['payload_json'])
            if (identifier('knowledge-vocabulary', p) != row['record_id'] or content_hash(p) != row['content_sha256']
                    or canonical(p) != row['payload_json'] or p['config_event_id'] != row['config_event_id']):
                raise ContractError('vocabulary provenance corrupt')
            for value in p['concepts']:
                concept = Concept.from_dict(value)
                concepts[concept.concept_id] = concept
        return cls(extensions=tuple(concepts.values()))

    def describe(self):
        return {'registry_version': 'corpustrail-knowledge-registry/v0a',
                'concepts': {k: canonical(v.to_dict()) for k,v in sorted(self._concepts.items())},
                'versions': {k:v.version for k,v in sorted(self._concepts.items())},
                'legacy_field_mappings': {},
                'status': 'organizational_definitions_not_approved_ontology'}

    def definitions(self):
        return [v.to_dict() for _,v in sorted(self._concepts.items())]

    def field(self, name):
        text(name, 'source field')
        return 'unmapped_field.' + name

    @staticmethod
    def plan_extension(project, concepts, *, producer_id, created_at, source, taxonomy=None):
        """Explicit opt-in project vocabulary snapshot; no mappings/observations created."""
        text(producer_id, 'vocabulary producer'); timestamp(created_at)
        if not isinstance(source, dict):
            raise ContractError('vocabulary provenance required')
        values = [c.to_dict() for c in concepts]
        if not values or len({v['concept_id'] for v in values}) != len(values):
            raise ContractError('unique nonempty concepts required')
        values.sort(key=lambda v:v['concept_id'])
        configured = {c.namespace:c for c in project.config.concept_extensions}
        for value in values:
            namespace = value['concept_id'].split('.')[0]
            extension = configured.get(namespace)
            if namespace in ('ct','bibliography','unmapped_field') or extension is None or (
                    value['concept_id'] not in extension.predicates or value['version'] != extension.version):
                raise ContractError('extension must match an explicitly configured project namespace/version/predicate')
        payload = {'concepts':values, 'producer_id':producer_id, 'created_at':created_at,
                   'source':deepcopy(source), 'taxonomy':deepcopy(taxonomy), 'taxonomy_status':'project_supplied_not_promoted',
                   'config_event_id':project.configuration_history()[-1]['event_id']}
        return {'record_id':identifier('knowledge-vocabulary',payload),
                'content_sha256':content_hash(payload), 'payload':payload}

    @staticmethod
    def apply_extension(project, plan):
        p = deepcopy(plan['payload'])
        recreated = Registry.plan_extension(project, [Concept.from_dict(v) for v in p['concepts']],
            producer_id=p['producer_id'], created_at=p['created_at'], source=p['source'], taxonomy=p['taxonomy'])
        if recreated != plan:
            raise ContractError('vocabulary plan/configuration mismatch')
        with connection(project.database_path, write=True) as db:
            if latest_config(db)[0] != p['config_event_id']:
                raise ContractError('stale vocabulary configuration')
            for row in db.execute('SELECT payload_json FROM ct_knowledge_registry_records'):
                old = json.loads(row[0])
                for a in old['concepts']:
                    for b in p['concepts']:
                        if (a['concept_id'],a['version']) == (b['concept_id'],b['version']) and a != b:
                            raise ContractError('concept version cannot be redefined; register a new version')
            old = db.execute('SELECT payload_json FROM ct_knowledge_registry_records WHERE record_id=?', (plan['record_id'],)).fetchone()
            if old:
                if old[0] != canonical(p):
                    raise ContractError('vocabulary identity collision')
                return plan['record_id']
            db.execute('INSERT INTO ct_knowledge_registry_records(record_id,content_sha256,payload_json,config_event_id) VALUES(?,?,?,?)',
                       (plan['record_id'],plan['content_sha256'],canonical(p),p['config_event_id']))
        return plan['record_id']
