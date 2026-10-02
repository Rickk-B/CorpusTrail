"""Loopback-only, dependency-free broad-corpus review interface."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
from urllib.parse import parse_qs, urlsplit

from corpustrail._internal.values import ContractError


HTML = r'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>CorpusTrail human corpus review</title>
<style>body{font:16px system-ui;max-width:1000px;margin:2em auto;padding:0 1em}button,input,select,textarea{font:inherit;margin:.3em}textarea{width:95%;height:6em}fieldset{margin:1em 0}#abstract{white-space:pre-wrap}#overview button{font-size:12px}#message{color:#963}small{display:block}details{margin:1em 0}</style>
<h1>Human broad-corpus review</h1><p id="question"></p><p id="recording_notice"></p><p id="counts"></p><p id="priority"></p><p id="message" role="status"></p>
<div id="nav"><button data-nav="first">First</button><button data-nav="previous">Previous</button><button data-nav="next">Next</button><button data-nav="last">Last</button>
Go to: <input id="jump" type="number" min="1" style="width:5em"><button id="go">Go</button><span id="position"></span>
<button data-nav="next_partial">Next partial</button><button data-nav="next_incomplete">Next incomplete</button><button data-nav="previous_incomplete">Previous incomplete</button></div>
<label>Order <select id="ordering"><option value="original">Original population order</option><option value="paper_id">Canonical ID order</option><option id="assigned" value="assigned">Assigned review order</option></select></label>
<h2 id="title"></h2><p id="bib"></p><p id="identifiers"></p><div id="abstract"></div>
<p id="evidence"></p><button id="document">Open verified structured document</button>
<form id="form"><fieldset><legend>Enough evidence to judge broad-corpus membership?</legend>
<label><input type="radio" name="sufficiency" value="sufficient">Yes</label><label><input type="radio" name="sufficiency" value="insufficient">No / need more evidence</label></fieldset>
<fieldset id="decision"><legend>Decision</legend><label><input type="radio" name="decision" value="included">Include in broad corpus</label><label><input type="radio" name="decision" value="excluded">Exclude from broad corpus</label></fieldset>
<fieldset><legend>What did you review?</legend><select id="extent"><option value="">Choose evidence reviewed</option><option value="metadata">Title / metadata only</option><option value="abstract">Abstract only</option><option value="sections">Checked sections of the paper</option><option value="full_document">Read full paper</option></select>
<small>Opening a document does not mean it was read. Sections/full paper are your explicit attestation of the actual review extent.</small></fieldset>
<label id="rationale_label" for="rationale">Short rationale</label><textarea id="rationale" maxlength="20000"></textarea>
<details><summary>Evidence details / advanced</summary><label>Pages, sections or evidence notes <input id="location"></label></details>
<p>Drafts autosave. A draft never changes corpus membership. Use the explicit button below to record a human decision.</p>
<button type="button" id="record">Record human decision</button><small id="recorded"></small></form>
<details><summary>Progress overview</summary><div id="overview"></div></details>
<p>No automatic stopping or exclusion is performed. Every candidate remains accessible; completion is a human decision.</p>
<script nonce="TOKEN">
const token='TOKEN';let state,queue=Promise.resolve(),timer,dirty=false,pending=0;
const el=id=>document.getElementById(id);
function selected(name){return document.querySelector('input[name="'+name+'"]:checked')?.value||null;}
function draft(){return {sufficiency:selected('sufficiency'),decision:selected('sufficiency')==='sufficient'?selected('decision'):null,review_extent:el('extent').value||null,rationale:el('rationale').value,location:el('location').value.trim()||null};}
async function request(action,value){const r=await fetch('/api/update',{method:'POST',headers:{'Content-Type':'application/json','X-CorpusTrail-CSRF':token},body:JSON.stringify({expected_revision:state.revision,action,value})});const body=await r.json();if(!r.ok)throw Error(body.error);return body;}
function enabled(){const sufficient=selected('sufficiency')==='sufficient';document.querySelectorAll('input[name="decision"]').forEach(x=>{x.disabled=!sufficient;if(!sufficient)x.checked=false;});el('rationale_label').textContent=sufficient?'Short rationale (required)':'Short note: what more evidence is needed?';}
function progress(s){el('recording_notice').textContent=s.recording_notice||'';el('counts').textContent=Object.entries(s.counts).map(([k,v])=>k+': '+v).join(' / ')+' — '+s.remaining_count+' not yet explicitly recorded in this session';el('overview').replaceChildren();s.overview.forEach((status,i)=>{const b=document.createElement('button');b.textContent=(i+1)+': '+status;b.onclick=()=>perform('navigate',i+1);el('overview').append(b);});el('priority').textContent=s.priority?'Priority rank '+s.priority+' — '+s.priority_notice:'';}
function render(s){state=s;dirty=false;el('message').textContent='Saved';el('question').textContent=s.question;el('title').textContent=s.title||'(Title unavailable)';el('bib').textContent=[(s.authors||[]).join('; '),s.year,s.source].filter(Boolean).join(' · ');el('identifiers').textContent=s.identifiers.map(x=>x.scheme+': '+x.value).join(' · ');el('abstract').textContent=s.abstract?'Abstract\n'+s.abstract:'No abstract available. A human metadata-only decision is allowed.';
el('position').textContent=s.number+' / '+s.total;el('jump').value=s.number;el('jump').max=s.total;el('counts').textContent=Object.entries(s.counts).map(([k,v])=>k+': '+v).join(' / ')+' — '+s.remaining_count+' not yet explicitly recorded in this session';
el('evidence').textContent=(s.document_available?'Verified structured document available. ':'Metadata/abstract evidence only. ')+(s.pending_documents?s.pending_documents+' pending-identity document(s) unavailable as trusted evidence.':'');el('document').disabled=!s.document_available;
for(const name of ['sufficiency','decision'])document.querySelectorAll('input[name="'+name+'"]').forEach(x=>x.checked=x.value===s.review[name]);
for(const option of el('extent').options){option.disabled=option.value&&!s.review_options.includes(option.value);if(['sections','full_document'].includes(option.value))option.disabled=option.disabled||!s.document_opened;}
el('extent').value=s.review.review_extent||'';el('rationale').value=s.review.rationale;el('location').value=s.review.location||'';el('recorded').textContent=s.recorded?'A human decision has been recorded. A later explicit commit preserves this event as history.':'No decision recorded from this session yet.';
el('assigned').disabled=!s.assigned_order_available;el('assigned').textContent=s.mode==='method-blind'?'Assigned review order':'Priority order (ordering aid only)';el('ordering').value=s.ordering==='priority'?'assigned':s.ordering;
progress(s);enabled();}
function fail(e){el('message').textContent='Not saved: '+e.message+' — keep this page open. Reload only after resolving the conflict.';}
function flush(){clearTimeout(timer);if(!dirty)return queue;const value=draft();dirty=false;pending++;queue=queue.then(async()=>{const s=await request('draft',value);state=s;progress(s);el('message').textContent='Draft saved';}).catch(e=>{dirty=true;fail(e);throw e;}).finally(()=>pending--);return queue;}
function perform(action,value){flush();pending++;queue=queue.then(async()=>{render(await request(action,value));}).catch(e=>{fail(e);}).finally(()=>pending--);return queue;}
el('form').addEventListener('input',()=>{enabled();dirty=true;el('message').textContent='Unsaved draft';clearTimeout(timer);timer=setTimeout(()=>flush().catch(()=>{}),450);});
document.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>perform('navigate',b.dataset.nav));el('go').onclick=()=>perform('navigate',Number(el('jump').value));el('ordering').onchange=()=>perform('ordering',el('ordering').value);el('record').onclick=()=>perform('commit');
el('document').onclick=()=>{const popup=window.open('about:blank','_blank');perform('open').then(()=>{if(popup&&state.document_opened)popup.location='/document?paper_id='+encodeURIComponent(state.paper_id);else if(popup)popup.close();});};
window.addEventListener('beforeunload',e=>{if(dirty||pending){e.preventDefault();e.returnValue='Unsaved draft';}});fetch('/api/state').then(r=>r.json()).then(render).catch(fail);
</script></html>'''


def make_server(project, session_id, *, port=8765):
    """Start/resume an existing session; never prepare packets or train implicitly."""
    project.review_sessions.view(session_id)
    csrf = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        timeout = 30  # Bound idle header/body reads; still a single-user local UI.

        def log_message(self, *_):
            pass  # No bibliographic data or reviewer input in runtime logs.

        def allowed(self):
            host = '127.0.0.1:'+str(self.server.server_port)
            origin = self.headers.get('Origin')
            return self.headers.get('Host')==host and (origin is None or origin=='http://'+host)

        def respond(self, status, body, content_type='application/json; charset=utf-8'):
            data = body if isinstance(body,bytes) else body.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'nonce-"+csrf+"'; style-src 'unsafe-inline'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self.allowed():
                return self.respond(403,'{"error":"loopback origin required"}')
            try:
                path=urlsplit(self.path)
                if path.path=='/':
                    return self.respond(200,HTML.replace('TOKEN',csrf),'text/html; charset=utf-8')
                if path.path=='/api/state':
                    return self.respond(200,json.dumps(project.review_sessions.view(session_id),ensure_ascii=False))
                if path.path=='/document':
                    query=parse_qs(path.query)
                    if set(query)!={'paper_id'} or len(query['paper_id'])!=1:
                        raise ContractError('invalid document request')
                    document=project.review_sessions.document(session_id,query['paper_id'][0])
                    return self.respond(200,document.read_bytes(),'text/plain; charset=utf-8')
                return self.respond(404,'{"error":"not found"}')
            except (ContractError,KeyError,ValueError,OSError) as exc:
                self.respond(400,json.dumps({'error':str(exc)}))

        def do_POST(self):
            if not self.allowed() or self.headers.get('X-CorpusTrail-CSRF')!=csrf:
                return self.respond(403,'{"error":"valid loopback session token required"}')
            try:
                if self.path!='/api/update' or self.headers.get('Content-Type')!='application/json':
                    raise ContractError('invalid endpoint/content type')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=65536:
                    raise ContractError('request size out of bounds')
                value=json.loads(self.rfile.read(length))
                if not isinstance(value,dict) or set(value)-{'expected_revision','action','value'}:
                    raise ContractError('invalid request fields')
                result=project.review_sessions.update(session_id,**value)
                self.respond(200,json.dumps(result,ensure_ascii=False))
            except (ContractError,KeyError,ValueError,TypeError,OSError) as exc:
                self.respond(400,json.dumps({'error':str(exc)}))

    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def serve(project,session_id,*,port=8765):
    server=make_server(project,session_id,port=port)
    print('Review session: http://127.0.0.1:'+str(server.server_port),flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
