"""Bounded RIS exchange profile v1. Raw bytes and unsupported tags stay preserved.

Identifiers are assertions explicitly approved at import, not verified documents.
CorpusTrail origin tokens are opaque source-record keys, never invented DOIs.
"""
from dataclasses import asdict
import hashlib
import re

from corpustrail._internal.values import ContractError, canonical
from corpustrail.identity import BibliographicRecord, Identifier

PROFILE = 'corpustrail-ris/v1'
MEDIA = 'application/x-research-info-systems'
MAX_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 2000
MAX_FIELD = 200000
TAG = re.compile(r'^([A-Z0-9]{2})[ \t]{1,2}- ?(.*)$')
KNOWN = {'TY','ER','TI','T1','CT','AB','N2','AU','A1','PY','Y1','DA','JF','JO','T2','JA',
         'DO','UR','AN','PM','C2','C1','ID','VL','IS','SP','EP','SN','LA','KW','N1','L1','L2'}


def record(fields, origin):
    warnings = []
    if not fields.get('TY') or not fields['TY'][0].strip():raise ContractError('A nonempty TY publication type is required.')
    def choose(tags):
        values = [(tag, value.strip()) for tag in tags for value in fields.get(tag, []) if value.strip()]
        if len({v for _, v in values}) > 1:
            warnings.append('Alternative '+('/'.join(tags))+' values retained in source; first preferred value selected.')
        return values[0][1] if values else None
    title = choose(('TI','T1','CT'))
    abstract = choose(('AB','N2'))
    journal = choose(('JF','JO','T2','JA'))
    date = choose(('PY','Y1','DA')); year = None
    if date:
        matched = re.fullmatch(r'([0-9]{4})(?:[ /-].*)?', date)
        if matched and 1 <= int(matched[1]) <= 9999: year = int(matched[1])
        else: warnings.append('Unrecognized publication date retained in source; year is missing.')
    ids = []
    def add(scheme, value):
        item = Identifier(scheme, value); normalized = item.normalized()
        if normalized not in {i.normalized() for i in ids}: ids.append(item)
    for value in fields.get('DO', []):
        if value.strip(): add('doi', value.strip())
    for value in fields.get('UR', []):
        if value.casefold().startswith(('https://doi.org/', 'http://doi.org/')): add('doi', value.strip())
    for value in fields.get('PM', []):
        if value.strip(): add('pmid', value.strip())
    for value in fields.get('AN', []):
        if value.strip().upper().startswith('PMID:'): add('pmid', value.strip()[5:].strip())
    for value in fields.get('C2', []):
        if value.strip().upper().startswith('PMC'): add('pmcid', value.strip())
    for value in fields.get('C1', []):
        if value.startswith('CorpusTrail-Origin: '):
            key = value.removeprefix('CorpusTrail-Origin: ').strip()
            if not re.fullmatch('[0-9a-f]{64}', key): raise ContractError('Malformed CorpusTrail origin token.')
            add('corpustrail.ris', key)
        elif value.startswith('OpenAlex: '): add('openalex', value.removeprefix('OpenAlex: ').strip())
        elif value.startswith('SemanticScholar: '): add('semantic_scholar', value.removeprefix('SemanticScholar: ').strip())
    for scheme in ('doi','pmid','pmcid','openalex','semantic_scholar'):
        if len({i.normalized()[1] for i in ids if i.scheme==scheme}) > 1:
            raise ContractError('Conflicting '+scheme+' assertions in one source record; manual identity review required.')
    add('corpustrail.ris', origin)
    authors = tuple(dict.fromkeys(v.strip() for tag in ('AU','A1') for v in fields.get(tag,[]) if v.strip()))
    if not title and not abstract and not any(i.scheme!='corpustrail.ris' for i in ids):
        raise ContractError('No title, abstract or supported bibliographic identifier; raw record retained.')
    value = BibliographicRecord(title, abstract, authors, year, journal, tuple(ids));value.validate()
    unknown = sorted(set(fields)-KNOWN)
    if unknown: warnings.append('Unsupported tags retained without interpretation: '+', '.join(unknown))
    if fields.get('L1') or fields.get('L2'):warnings.append('Attachment locations retained only; never opened or retrieved.')
    if not abstract:warnings.append('Abstract missing; no exclusion inferred.')
    if not any(i.scheme!='corpustrail.ris' for i in ids):warnings.append('No global identifier; identity is confined to the exact source origin token, not title similarity.')
    return value, warnings


def parse(body):
    if not isinstance(body, bytes) or not 1 <= len(body) <= MAX_BYTES:
        raise ContractError('Choose a nonempty RIS file up to 4 MiB.')
    digest = hashlib.sha256(body).hexdigest()
    try: text = body.decode('utf-8-sig')
    except UnicodeDecodeError:
        return [{'index':1,'line_start':1,'line_end':None,'fields':{},'record':None,
                 'warnings':[],'file_error':True,'error':'Invalid UTF-8. Original bytes retained; source record count unknown.'}]
    text=text.replace('\r\n','\n').replace('\r','\n')
    if '\x00' in text:return [{'index':1,'line_start':1,'line_end':None,'fields':{},'record':None,'warnings':[],'file_error':True,'error':'NUL bytes in source. Original bytes retained; source record count unknown.'}]
    rows=[];current=None;last=None;errors=[];start=1
    def finish(end, incomplete=False):
        nonlocal current,last,errors,start
        if current is None:return
        index=len(rows)+1
        error=' '.join(errors+(['Missing ER record terminator.'] if incomplete else []))
        value=None;warnings=[]
        if not error:
            try:value,warnings=record(current,hashlib.sha256((digest+':'+str(index)).encode()).hexdigest())
            except ContractError as exc:error=str(exc)
        snapshot={'record':asdict(value) if value else None,'fields':{k:v for k,v in current.items() if k in {'TY','ID','VL','IS','SP','EP','SN','LA','KW','N1','UR'}}}
        if len(canonical(snapshot).encode('utf-8'))>1_000_000:
            value=None;current={};error='Normalized record exceeds the explicit 1 MiB budget; original source retained.'
        rows.append({'index':index,'line_start':start,'line_end':end,'fields':current,
                     'record':asdict(value) if value else None,'warnings':warnings,'error':error or None})
        if len(rows)>MAX_RECORDS:raise ContractError('RIS operation exceeds the documented 2,000-record budget; split the source explicitly.')
        current=None;last=None;errors=[]
    for number,line in enumerate(text.split('\n'),1):
        match=TAG.fullmatch(line)
        if match and match[1]=='TY':
            finish(number-1,True);current={'TY':[match[2]]};start=number;last='TY';continue
        if current is None:
            if not line.strip():continue
            current={};start=number;errors=['Content outside a TY/ER record.'];last=None
        if match:
            tag,value=match.groups()
            if tag=='ER':finish(number);continue
            current.setdefault(tag,[]).append(value);last=tag
        elif line.strip():
            if last is None:errors.append('Unattached continuation line.')
            else:current[last][-1]+='\n'+(line[6:] if line.startswith('      ') else line)
        elif last in {'AB','N2'}:current[last][-1]+='\n'
        if last and current and len(current[last][-1])>MAX_FIELD:
            raise ContractError('RIS field exceeds the documented 200,000-character budget.')
    finish(len(text.split('\n')),True)
    if not rows:raise ContractError('No TY/ER bibliographic records found.')
    return rows


def bibliography(raw):
    return BibliographicRecord(**{**raw,'authors':tuple(raw['authors']),
                                 'identifiers':tuple(Identifier(**v) for v in raw['identifiers'])})


def serialize(records):
    """Only supported bibliographic fields; never encode judgments or trust."""
    lines=[]
    def emit(tag,value):
        if value is None or value=='':return
        for index,line in enumerate(str(value).split('\n')):
            # Indentation prevents metadata from manufacturing a new RIS tag.
            lines.append(tag+'  - '+line if index==0 else '      '+line)
    for row in records:
        emit('TY',row.get('publication_type','GEN'));emit('TI',row.get('title'));emit('AB',row.get('abstract'))
        for author in row.get('authors',[]):emit('AU',author)
        emit('PY',row.get('year'));emit('JF',row.get('source'))
        for item in row.get('identifiers',[]):
            scheme,value=item['scheme'],item['value']
            tag={'doi':'DO','pmid':'PM','pmcid':'C2'}.get(scheme)
            if tag:emit(tag,value)
            elif scheme in {'corpustrail.ris','openalex','semantic_scholar'}:
                emit('C1',{'corpustrail.ris':'CorpusTrail-Origin: ','openalex':'OpenAlex: ','semantic_scholar':'SemanticScholar: '}[scheme]+value)
        for tag in sorted(row.get('supplemental',{})):
            for value in row['supplemental'][tag]:emit(tag,value)
        lines.append('ER  - ');lines.append('')
    body=('\n'.join(lines)+'\n').encode('utf-8')
    if len(body)>MAX_BYTES:raise ContractError('RIS export exceeds 4 MiB; select a smaller explicit population.')
    return body


def implementation_hash():
    from pathlib import Path
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
