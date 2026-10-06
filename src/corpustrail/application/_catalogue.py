"""Internal read repository. No initialization, DDL, writes or network execution.

Bulk SQL bounds Python/HTTP memory; scientific selectors remain shared with their
services. This is a live operational catalogue, not a frozen candidate population.
"""

from corpustrail.discovery.service import _catalogue_field_sql
from corpustrail.curation.service import _catalogue_membership_sql


def catalogue_sql():
    return """WITH heads AS (""" + _catalogue_membership_sql() + """),
    reviews AS (
      SELECT paper_id,SUM(producer_type='human') AS human_count,
             SUM(producer_type!='human') AS other_count
      FROM ct_review_events GROUP BY paper_id
    ),
    draft_papers AS (
      SELECT DISTINCT e.session_id,j.key AS paper_id
      FROM ct_review_session_events e,json_each(COALESCE(
        json_extract(e.payload_json,'$.delta.drafts'),
        json_extract(e.payload_json,'$.state.drafts'),'{}')) j
    ),
    drafts AS (SELECT paper_id,COUNT(*) AS draft_sessions FROM draft_papers GROUP BY paper_id),
    representations AS (
      SELECT paper_id,
        MAX(json_extract(payload_json,'$.payload.representation')='abstract'
          AND json_extract(payload_json,'$.payload.trusted')=1) AS recovered_abstract,
        MAX(json_extract(payload_json,'$.payload.representation')='structured_text'
          AND json_extract(payload_json,'$.payload.trusted')=1
          AND json_extract(payload_json,'$.payload.evidence_depth')='document_body') AS structured,
        SUM(json_extract(payload_json,'$.payload.artifact_validity')='pending_identity') AS pending,
        SUM(json_extract(payload_json,'$.payload.artifact_validity') IN ('mismatch','invalid')) AS invalid
      FROM ct_pipeline_events WHERE kind='representation' GROUP BY paper_id
    ),
    paper_abstracts AS (
      SELECT paper_id,MAX(COALESCE(json_extract(payload_json,'$.record.abstract'),'')!='') AS available
      FROM ct_paper_observations GROUP BY paper_id
    ),
    catalogue AS (
      SELECT p.paper_id,p.identity_state,
        """ + _catalogue_field_sql('title') + """ AS title,
        """ + _catalogue_field_sql('authors') + """ AS authors,
        """ + _catalogue_field_sql('year') + """ AS year,
        """ + _catalogue_field_sql('source') + """ AS source,
        COALESCE(m.membership_state,'not_reviewed') AS membership,
        COALESCE(r.human_count,0) AS human_count,COALESCE(r.other_count,0) AS other_count,
        COALESCE(d.draft_sessions,0) AS draft_sessions,
        CASE WHEN x.structured=1 THEN 'structured_text'
          WHEN a.available=1 OR x.recovered_abstract=1 THEN 'abstract' ELSE 'metadata' END AS evidence,
        CASE WHEN a.available=1 OR x.recovered_abstract=1 THEN 1 ELSE 0 END AS abstract_available,
        COALESCE(x.pending,0) AS pending,COALESCE(x.invalid,0) AS invalid
      FROM paper_entities p LEFT JOIN heads h ON h.paper_id=p.paper_id
      LEFT JOIN ct_review_events m ON m.sequence=h.sequence
      LEFT JOIN reviews r ON r.paper_id=p.paper_id
      LEFT JOIN drafts d ON d.paper_id=p.paper_id
      LEFT JOIN representations x ON x.paper_id=p.paper_id
      LEFT JOIN paper_abstracts a ON a.paper_id=p.paper_id
    ) """


SORTS = {
    'title': "CASE WHEN title IS NULL THEN 1 ELSE 0 END,ct_fold(COALESCE(title,'')),paper_id",
    'year_newest': "CASE WHEN year IS NULL THEN 1 ELSE 0 END,year DESC,ct_fold(COALESCE(title,'')),paper_id",
    'year_oldest': "CASE WHEN year IS NULL THEN 1 ELSE 0 END,year,ct_fold(COALESCE(title,'')),paper_id",
}


def filter_sql(filters):
    clauses, values = [], []
    if filters['q']:
        clauses.append("(instr(ct_fold(COALESCE(title,'')),?)>0 OR "
                       "instr(ct_fold(COALESCE(authors,'')),?)>0 OR "
                       "instr(ct_fold(COALESCE(source,'')),?)>0)")
        values += [filters['q'].casefold()] * 3
    if filters['membership']:
        clauses.append('membership=?'); values.append(filters['membership'])
    if filters['evidence'] in {'metadata', 'abstract', 'structured_text'}:
        clauses.append('evidence=?'); values.append(filters['evidence'])
    elif filters['evidence'] == 'pending':
        clauses.append('pending>0')
    elif filters['evidence'] == 'mismatch_or_invalid':
        clauses.append('invalid>0')
    if filters['review'] == 'human_reviewed':
        clauses.append('human_count>0')
    elif filters['review'] == 'not_human_reviewed':
        clauses.append('human_count=0')
    elif filters['review'] == 'draft_history':
        clauses.append('draft_sessions>0')
    return (' WHERE ' + ' AND '.join(clauses) if clauses else ''), values
