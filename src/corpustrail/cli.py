"""Standalone operational CLI; external execution always explicitly confirmed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from corpustrail import __version__
from corpustrail._internal.values import ContractError
from corpustrail.project import Project, ProjectConfig


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="corpustrail", description="Broad scientific topic-corpus foundation")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    project = sub.add_parser("project").add_subparsers(dest="operation", required=True)
    init = project.add_parser("init")
    init.add_argument("path", type=Path)
    init.add_argument("--project-id")
    init.add_argument("--name")
    init.add_argument("--description")
    init.add_argument("--config", type=Path)
    init.add_argument("--created-by", required=True)
    configure = project.add_parser('configure', help='Append a revision-guarded configuration event; never edit bootstrap')
    configure.add_argument('path', type=Path)
    configure.add_argument('--config', type=Path, required=True, help='Complete replacement configuration JSON (version + 1)')
    configure.add_argument('--expected-event-id', required=True, help='Current config event ID from project status')
    configure.add_argument('--created-by', required=True, help='Stable configuration producer ID')
    status = project.add_parser("status")
    status.add_argument("path", type=Path)
    models = sub.add_parser('models', help='Optional explicit model adapters; status is local-only').add_subparsers(dest='operation', required=True)
    for operation in ('status', 'plan', 'authorize', 'execute', 'inspect', 'resume'):
        command = models.add_parser(operation)
        command.add_argument('path', type=Path)
        if operation == 'plan':
            command.add_argument('--workflow', required=True)
            command.add_argument('--spec', type=Path, required=True, help='Provider-independent TaskSpec JSON')
            command.add_argument('--run-id', required=True)
            command.add_argument('--paper-id', required=True)
            command.add_argument('--mode', choices=('metadata', 'abstract', 'selected_passages', 'full_text'), default='abstract',
                                 help='Exact evidence depth transmitted; no automatic fallback or full-text expansion')
            command.add_argument('--representation-id', help='Explicit verified document-body representation event ID')
            command.add_argument('--passage', action='append', default=[], help='Explicit character start:end, repeated for selected passages')
            command.add_argument('--out', help='New project-relative plan file; never overwritten')
        elif operation in ('authorize', 'execute'):
            command.add_argument('--plan', required=True, help='Project-relative frozen plan file')
            if operation == 'authorize':
                command.add_argument('--actor', required=True, help='Stable consent actor, optionally pseudonymous')
                command.add_argument('--expected-plan-sha256', required=True, help='Hash of the exact plan you inspected')
                command.add_argument('--confirm-external', action='store_true', required=True)
            else:
                command.add_argument('--consent-event-id', help='Plan-bound explicit external-transfer authorization')
                command.add_argument('--execute', action='store_true', required=True)
        elif operation in ('inspect', 'resume'):
            command.add_argument('--run-id', required=True)
    upgrade = project.add_parser("upgrade")
    upgrade.add_argument("path", type=Path)
    upgrade.add_argument("--backup", required=True)
    discovery = sub.add_parser("discover")
    discovery.add_argument("path", type=Path)
    discovery.add_argument("--provider", required=True)
    discovery.add_argument("--run-id", required=True)
    discovery.add_argument("--query")
    discovery.add_argument("--concept-id")
    discovery.add_argument("--page-size", type=int, default=20)
    discovery.add_argument("--max-pages", type=int, default=1)
    discovery.add_argument("--max-attempts", type=int, default=1)
    discovery.add_argument("--execute", action="store_true")
    discovery.add_argument("--confirm-external", action="store_true")
    candidates = sub.add_parser("candidates")
    candidates.add_argument("path", type=Path)
    candidates.add_argument("--run-id")
    candidates.add_argument("--canonicalize", action="store_true")
    candidates.add_argument("--approve-identities", action="store_true")
    candidates.add_argument("--approve-aliases", action="store_true")
    evidence = sub.add_parser("evidence")
    evidence.add_argument("path", type=Path)
    evidence.add_argument("--paper-id", required=True)
    evidence.add_argument("--resolve", action="store_true")
    evidence.add_argument("--confirm-external", action="store_true")
    corpus = sub.add_parser('corpus')
    corpus.add_argument('path',type=Path)
    corpus.add_argument('--state',action='append')
    review = sub.add_parser('review').add_subparsers(dest='operation',required=True)
    for operation in ('prepare','status','serve','bind-ranking'):
        command = review.add_parser(operation)
        command.add_argument('path',type=Path)
        command.add_argument('--session-id',required=True)
        if operation=='prepare':
            command.add_argument('--reviewer',required=True)
            command.add_argument('--paper-id',action='append')
            command.add_argument('--mode',choices=('method-blind','operational'),default='method-blind')
            command.add_argument('--authoritative',action='store_true')
        elif operation=='serve':
            command.add_argument('--port',type=int,default=8765)
        elif operation=='bind-ranking':
            command.add_argument('--run-id',required=True)
    prioritize = sub.add_parser('prioritize').add_subparsers(dest='operation',required=True)
    train = prioritize.add_parser('train')
    train.add_argument('path',type=Path)
    train.add_argument('--label-cutoff',required=True)
    train.add_argument('--parent-model-id')
    rank = prioritize.add_parser('rank')
    rank.add_argument('path',type=Path)
    rank.add_argument('--model-id',required=True)
    rank.add_argument('--run-id',required=True)
    rank.add_argument('--paper-id',action='append')
    rank.add_argument('--previous-run-id')
    inspect = prioritize.add_parser('inspect')
    inspect.add_argument('path',type=Path)
    inspect.add_argument('--run-id',required=True)
    knowledge = sub.add_parser('knowledge').add_subparsers(dest='operation',required=True)
    for operation in ('show','query','conflicts','sets','vocabulary','verify','assert','plan','apply'):
        command = knowledge.add_parser(operation)
        command.add_argument('path',type=Path)
        if operation in ('show','conflicts'):
            command.add_argument('--paper-id',required=operation=='show')
        if operation=='query':
            command.add_argument('--predicate',required=True)
            command.add_argument('--value-json',required=True)
        if operation in ('assert','plan'):
            command.add_argument('--input',type=Path,required=True)
        if operation=='apply':
            command.add_argument('--plan',type=Path,required=True)
            command.add_argument('--human-authorization',type=Path)
            command.add_argument('--apply',action='store_true',required=True)
    export = sub.add_parser('export').add_subparsers(dest='integration',required=True)
    asreview = export.add_parser('asreview').add_subparsers(dest='operation',required=True)
    for operation in ('preview','plan','create','inspect','map','mapping'):
        command=asreview.add_parser(operation)
        command.add_argument('path',type=Path)
        if operation in ('plan','inspect','map'):
            command.add_argument('--export-id',required=True)
        if operation=='plan':
            command.add_argument('--created-at')
            command.add_argument('--software-commit')
            command.add_argument('--out',help='Project-relative immutable snapshot path')
        if operation=='create':
            command.add_argument('--snapshot',required=True,help='Project-relative snapshot path')
        if operation in ('map','mapping'):
            command.add_argument('--review-id',required=True)
            command.add_argument('--mapping-id',required=True)
        if operation=='map':
            command.add_argument('--results',type=Path,required=True)
            command.add_argument('--question-id',required=True)
            command.add_argument('--asreview-version',required=True)
            command.add_argument('--created-at')
    # Describe shared flags without changing any execution or authority default.
    flag_help = {
        'path': 'Explicit project directory; no working-directory/ancestor lookup',
        '--project-id': 'Stable project identifier (required unless --config is supplied)',
        '--name': 'Project name (required unless --config is supplied)',
        '--description': 'Broad-topic corpus scope (required unless --config is supplied)',
        '--config': 'Configuration JSON; paths inside it are project-relative, secrets use env names',
        '--run-id': 'Unique run ID; retain it from JSON output; changed runs never overwrite history',
        '--paper-id': 'Exact canonical ID from candidates/corpus; never a title or row number',
        '--session-id': 'Stable session ID chosen at prepare time; reuse to resume',
        '--model-id': 'Model ID returned by prioritize train (ordering only)',
        '--label-cutoff': 'Timezone-qualified cutoff; only eligible human broad-corpus labels train',
        '--confirm-external': 'Explicit authorization to send this request to the configured provider',
        '--execute': 'Execute the displayed discovery plan; otherwise plan only',
        '--canonicalize': 'Exact identity enrollment only; not corpus inclusion',
        '--approve-identities': 'Explicitly approve minting new canonical identities',
        '--approve-aliases': 'Explicitly approve exact co-occurring identifier aliases',
        '--resolve': 'Run configured legitimate evidence resolvers (requires external confirmation)',
        '--authoritative': 'Record human-authorized membership; reviewer must be authorized by config',
        '--mode': 'method-blind hides methods/scores; operational may show ordering aids',
        '--apply': 'Explicit scientific write of the validated plan; original assertions remain immutable',
        '--backup': 'New project-relative backup path required before an explicit schema upgrade',
        '--port': 'Local review port; binds only to 127.0.0.1',
        '--provider': 'Configured adapter: openalex, crossref, europepmc or semantic_scholar',
        '--query': 'Exact query sent to provider; no silent synonym expansion',
        '--concept-id': 'Configured concept ID; uses its label only, not aliases automatically',
        '--page-size': 'Provider result cap per logical page (default 20)',
        '--max-pages': 'Maximum logical page requests; failures consume budget (default 1)',
        '--max-attempts': 'Maximum physical attempts per page, at most three (default 1)',
        '--created-by': 'Stable producer identifier, optionally pseudonymous',
        '--reviewer': 'Stable reviewer identifier; no real-world identity required',
    }
    command_help = {
        'project': 'Initialize, inspect or explicitly configure/upgrade a project',
        'discover': 'Plan first; external execution needs two explicit flags',
        'candidates': 'Inspect observations/canonical IDs or explicitly enroll identities',
        'evidence': 'Inspect trust/evidence or explicitly resolve legitimate sources',
        'corpus': 'Read broad-corpus membership; distinct from ASReview eligibility',
        'review': 'Prepare/resume local human broad-corpus curation',
        'prioritize': 'Optional non-authoritative ordering; never excludes or stops',
        'knowledge': 'Provenance-rich observations; plan/apply writes, not automatic truth',
        'export': 'Unlabelled bibliography for independent downstream reviews',
        'assert': 'Plan one assertion ONLY; use knowledge apply for an explicit write',
        'plan': 'Plan/freeze only; inspect before explicit creation/application',
    }

    def describe(current):
        for action in current._actions:
            if isinstance(action, argparse._SubParsersAction):
                for label, child in action.choices.items():
                    child.description = child.description or command_help.get(label)
                    describe(child)
                # Existing and new command groups appear in --help with summaries.
                described = {a.dest for a in action._choices_actions}
                for label in action.choices:
                    if label not in described and label in command_help:
                        action._choices_actions.append(action._ChoicesPseudoAction(label, (), command_help[label]))
            elif not action.help:
                action.help = flag_help.get(action.option_strings[0] if action.option_strings else action.dest)

    describe(parser)
    args = parser.parse_args(argv)
    try:
        if args.command == "project" and args.operation == "init":
            if args.config:
                if any((args.project_id, args.name, args.description)):
                    raise ContractError("use --config or explicit project fields, not both")
                config = ProjectConfig.from_dict(json.loads(args.config.read_text(encoding="utf-8")))
            else:
                if not all((args.project_id, args.name, args.description)):
                    raise ContractError('project init requires --config or all of --project-id, --name, --description')
                config = ProjectConfig(args.project_id, args.name, args.description)
            instance = Project.create(args.path, config, created_by=args.created_by)
        elif args.command == "project" and args.operation == "upgrade":
            instance = Project.upgrade(args.path, backup=args.backup)
        else:
            instance = Project.open(args.path)
        result = instance.status()
        if args.command == 'project' and args.operation == 'configure':
            config = ProjectConfig.from_dict(json.loads(args.config.read_text(encoding='utf-8')))
            event_id = instance.configure(config, expected_event_id=args.expected_event_id, created_by=args.created_by)
            result = {'config_event_id': event_id, 'status': instance.status()}
        if args.command == "discover":
            from dataclasses import asdict
            from corpustrail.providers import metadata_provider
            provider = metadata_provider(args.provider)
            plan = instance.discovery.plan(provider, run_id=args.run_id, query=args.query, concept_id=args.concept_id,
                page_size=args.page_size, max_pages=args.max_pages, max_attempts=args.max_attempts)
            result = {"plan_id": plan.plan_id, "plan": asdict(plan)}
            if args.execute:
                result["execution"] = instance.discovery.execute(plan, provider, confirm_external=args.confirm_external)
        elif args.command == "candidates":
            if args.canonicalize:
                if not args.run_id:
                    raise ContractError("canonicalization requires a run ID")
                result = instance.discovery.canonicalize(args.run_id, approve_new_identities=args.approve_identities,
                                                        approve_aliases=args.approve_aliases)
            else:
                result = {"observations": instance.discovery.observations(args.run_id),
                          "canonical_papers": [instance.discovery.metadata(x) for x in instance.identities.papers()]}
        elif args.command == "evidence":
            result = instance.evidence.status(args.paper_id)
            if args.resolve:
                result = instance.evidence.acquire(instance.evidence.plan(args.paper_id), confirm_external=args.confirm_external)
        elif args.command=='corpus':
            result=instance.reviews.corpus(states=args.state)
        elif args.command=='review':
            service=instance.review_sessions
            if args.operation=='prepare':
                result=service.prepare(args.session_id,reviewer_id=args.reviewer,paper_ids=args.paper_id,
                    mode=args.mode,authority_state='human_authorized' if args.authoritative else 'non_authoritative')
            elif args.operation=='serve':
                from corpustrail.curation.http import serve
                serve(instance,args.session_id,port=args.port)
                return 0
            elif args.operation=='bind-ranking':
                result=service.update(args.session_id,expected_revision=service.view(args.session_id)['revision'],
                                      action='bind_ranking',value=args.run_id)
            else:
                result=service.view(args.session_id)
        elif args.command=='export':
            service=instance.asreview
            if args.operation=='preview':result=service.preview()
            elif args.operation=='plan':
                snapshot=service.plan(args.export_id,created_at=args.created_at,software_commit=args.software_commit)
                result=service.write_snapshot(snapshot,args.out) if args.out else {'snapshot':snapshot}
                result['records_count']=len(snapshot['records'])
            elif args.operation=='create':result=service.create_from_path(args.snapshot)
            elif args.operation=='inspect':result=service.inspect(args.export_id)
            elif args.operation=='map':
                result=service.map_results(args.export_id,results=args.results,review_id=args.review_id,
                    question_id=args.question_id,mapping_id=args.mapping_id,
                    asreview_version=args.asreview_version,created_at=args.created_at)
            else:result=service.mapping(args.review_id,args.mapping_id)
        elif args.command=='knowledge':
            view, store = instance.knowledge, instance.knowledge_store
            if args.operation=='show': result=view.observations(args.paper_id)
            elif args.operation=='query': result=view.query(args.predicate,json.loads(args.value_json))
            elif args.operation=='conflicts': result=view.conflicts(args.paper_id)
            elif args.operation=='sets': result=view.paper_sets()
            elif args.operation=='vocabulary': result=view.vocabulary()
            elif args.operation=='verify': result=store.verify()
            elif args.operation in ('assert','plan'):
                raw=json.loads(args.input.read_text(encoding='utf-8'))
                result=store.plan_batch([raw]) if args.operation=='assert' else store.plan_batch(**raw)
            else:
                plan=json.loads(args.plan.read_text(encoding='utf-8'))
                authorization=json.loads(args.human_authorization.read_text(encoding='utf-8')) if args.human_authorization else None
                result=store.apply(plan,human_authorization=authorization)
                result['verification']=store.verify()
        elif args.command == 'models':
            from corpustrail.models import TaskSpec
            service = instance.models
            if args.operation == 'status':
                result = service.status()
            elif args.operation == 'plan':
                spec = TaskSpec.from_dict(json.loads(args.spec.read_text(encoding='utf-8')))
                passages = [tuple(int(v) for v in p.split(':')) for p in args.passage]
                plan = service.plan(args.workflow, spec, run_id=args.run_id, paper_id=args.paper_id,
                                    mode=args.mode, representation_id=args.representation_id, passages=passages)
                result = service.write_plan(plan, args.out) if args.out else plan
            elif args.operation in ('authorize', 'execute'):
                plan = service.read_plan(args.plan)
                if args.operation == 'authorize':
                    if args.expected_plan_sha256 != plan['plan_sha256']:
                        raise ContractError('consent hash does not match the inspected plan')
                    result = {'consent_event_id': service.authorize(plan, actor_id=args.actor,
                                                                  confirm_external=args.confirm_external)}
                else:
                    result = service.execute(plan, consent_event_id=args.consent_event_id)
            elif args.operation == 'resume':
                result = service.resume(args.run_id)
            else:
                result = service.inspect(args.run_id)
        elif args.command=='prioritize':
            service=instance.prioritization
            if args.operation=='train':
                parent=None
                if args.parent_model_id:
                    parent=service.artifact(args.parent_model_id)['training_snapshot_id']
                snapshot=service.snapshot(label_cutoff=args.label_cutoff,parent_snapshot_id=parent)
                model=service.train(snapshot['artifact_id'],parent_model_id=args.parent_model_id)
                result={'snapshot_id':snapshot['artifact_id'],'model_id':model['artifact_id'],
                        'notice':'Non-authoritative review ordering only.'}
            elif args.operation=='rank':
                result=service.rank(args.model_id,run_id=args.run_id,paper_ids=args.paper_id,
                                    previous_run_id=args.previous_run_id)
            else:
                result={'ranking':service.run(args.run_id),'provenance':service.run_provenance(args.run_id)}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (ContractError, OSError, TypeError, ValueError, KeyError, ImportError) as exc:
        print("corpustrail: " + str(exc), file=sys.stderr)
        return 2
