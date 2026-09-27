"""Bounded decision loop around the existing official collector. No calls on import."""
import asyncio
from copy import deepcopy
from datetime import date
import json
import os

from pydantic import TypeAdapter

from backend.agent_models import OUTPUTS, Query, check_query
from backend.clients import require_enabled
from backend.data_sources.recent import collect_candidates, _period, _stable_key
from backend.generated.recent_brief.models import Request, Brief
from backend.pipelex_recent import RecentProviderError, run_hosted_method
from backend.recent_brief import BriefError, prepare, verify
from backend.profile_context import summary_profile
from backend.document_groups import document_key
from src.pipelex_client import PipelexError


class AgentError(BriefError):
    def __init__(self, message, result=None):
        super().__init__(message)
        self.result = result


def call_stage(stage, topic, data):
    """Only the fixed app stages may execute; no provider/method chosen by the LLM."""
    if stage not in OUTPUTS:
        raise BriefError('Étape IA inconnue.')
    request = Request(topic=topic, corpus_json=json.dumps(data, ensure_ascii=False))
    if len(request.model_dump_json()) > 200000:
        raise BriefError('Corpus trop volumineux. Aucun appel IA lancé pour cette étape.')
    if os.environ.get('PIPELEX_EXECUTION_MODE', 'hosted') == 'local':
        from src.recent_agent_worker import run_stage
        return run_stage(stage, request)
    from src.recent_agent_worker import method_contents
    return asyncio.run(run_hosted_method(request, method_contents(), 'recent_agent.' + stage, OUTPUTS[stage]))


def _merge(initial, extra):
    """Keep versions and procedural steps distinct; exact repetitions only are merged."""
    merged = deepcopy(initial)
    if (extra['start'], extra['end']) != (initial['start'], initial['end']):
        raise BriefError('Le complément ne respecte pas la période demandée.')
    for key in ('events', 'datasets'):
        distinct = {}
        for item in [*initial[key], *extra[key]]:
            distinct.setdefault(_stable_key(item), item)
        merged[key] = list(distinct.values())
    merged['events'].sort(key=lambda item: (item['event_date'], item['id']), reverse=True)
    merged['total_events'] = len(merged['events'])
    merged['limitations'] = list(dict.fromkeys([*initial['limitations'], *extra['limitations']]))
    return merged


def _final_corpus(result, initial_corpus, relevant, extra, queries, transport):
    # Retain evaluated evidence and reserve half the event budget for the supplement.
    supplement = None
    if extra:
        recent = deepcopy(extra)
        recent['topics'] = queries
        recent['events'] = recent['events'][:3]
        supplement = prepare(recent, transport=transport, semantic=True)
    kept = [source for source in initial_corpus['sources'] if source['source_id'] in relevant]
    initial_ids = list(dict.fromkeys(source['event_id'] for source in kept))[:3 if supplement and supplement['sources'] else 6]
    sources = [source for source in kept if source['event_id'] in initial_ids]
    limits = list(initial_corpus['limitations'])
    if supplement:
        sources.extend(supplement['sources'])
        limits.extend(supplement['limitations'])
    distinct = {}
    for source in sources:
        distinct.setdefault((source['event_id'], source['url'], source['sha256']), source)
    sources = [dict(source, source_id=f'f{index}') for index, source in enumerate(distinct.values())]
    limits.append('Évaluation initiale sur six événements au maximum. Si le complément apporte des passages : au plus trois événements initiaux et trois complémentaires pour la synthèse. Recherche non exhaustive.')
    return dict(topic=result['topic'], start=result['start'], end=result['end'],
                sources=[dict(source, document_key=document_key(source.get('dossier_url') or source['url'])) for source in sources],
                limitations=list(dict.fromkeys(limits)))


def select_candidates(inventory, topic, *, focus=''):
    """Only observed IDs can select events; model URLs and invented rows are rejected."""
    events = inventory['events']
    candidates = [dict(candidate_id=f'c{i}', title=event['title'][:300],
                       event_date=event['event_date'], event=str(event.get('event', ''))[:100],
                       category=event.get('category', 'procedure'),
                       themes=str(event.get('themes', ''))[:200],
                       description=str(event.get('description', ''))[:200],
                       passages=[text[:200] for text in event.get('content_passages', [])[:3]])
                  for i, event in enumerate(events)]
    selection = OUTPUTS['select'].model_validate(call_stage('select', topic, dict(
        start=inventory['start'], end=inventory['end'], candidates=candidates, focus=focus)).model_dump())
    allowed = {candidate['candidate_id']: event for candidate, event in zip(candidates, events)}
    if len(set(selection.event_ids)) != len(selection.event_ids) or not set(selection.event_ids) <= allowed.keys():
        raise BriefError('La sélection IA référence une notice absente ou répétée. Aucun résultat inventé accepté.')
    result = deepcopy(inventory)
    result['events'] = [deepcopy(allowed[key]) for key in selection.event_ids]
    result['total_events'] = len(result['events'])
    result['candidate_count'] = len(events)
    return result, list(selection.queries)


def research(topics, *, months=None, days=3, today=None, transport=None, profile_context=None):
    """Semantic selection, evidence review, optional second selection and summary. No retries."""
    profile_context = summary_profile(profile_context)
    topics = TypeAdapter(list[Query]).validate_python(topics)
    if not 1 <= len(topics) <= 8:
        raise ValueError('Choisir un à huit sujets.')
    topics = list(dict.fromkeys(check_query(topic) for topic in topics))
    today = today or date.today()
    start, end = _period(days, months, today)
    require_enabled('PIPELEX')
    engine = os.environ.get('PIPELEX_EXECUTION_MODE', 'hosted')
    if engine not in ('local', 'hosted'):
        raise AgentError('Configuration IA invalide. Aucun appel IA lancé.')
    key = 'OPENAI_API_KEY' if engine == 'local' else 'PIPELEX_API_KEY'
    if not os.environ.get(key, '').strip():
        raise AgentError(f'Clé {key} absente. Complète la configuration puis redémarre Streamlit. Aucun appel IA lancé.')
    topic = ' · '.join(topics)
    trace, queries = [], []
    result = None
    stage = 'collect'
    options = dict(months=months, days=days, today=today, transport=transport)
    try:
        inventory = collect_candidates(**options)
        inventory = deepcopy(inventory)
        inventory.update(topic=topic, topics=topics,
                         search_period={'amount': months if months is not None else days,
                                        'unit': 'mois' if months is not None else 'jours'})
        trace.append({'step': 'collect', 'status': 'completed'})
        # On selection failure, don't display unrelated candidate notices as matches.
        result = dict(inventory, events=[], total_events=0)
        if not inventory['events']:
            result['agent_analysis'] = dict(
                status='completed', queries=[], trace=trace, engine=engine,
                evaluation={'coverage': 'vide', 'relevant_sources': [], 'gaps': [], 'followup_query': ''},
                brief={'items': [], 'limitations': ['Aucune notice datée dans le corpus collecté ; aucun appel IA.']})
            return result
        stage = 'select'
        result, queries = select_candidates(inventory, topic)
        trace.append({'step': 'select', 'status': 'completed'})
        initial = deepcopy(result)
        initial['topics'] = list(dict.fromkeys([*topics, *queries]))
        corpus = prepare(initial, transport=transport, semantic=True)
        stage = 'evaluate'
        evaluation = OUTPUTS['evaluate'].model_validate(call_stage('evaluate', topic, {'corpus': corpus, 'queries': list(queries)}).model_dump())
        available = {source['source_id'] for source in corpus['sources']}
        relevant = evaluation.relevant_sources
        if (len(set(relevant)) != len(relevant) or not set(relevant) <= available
                or (evaluation.coverage == 'vide') != (not relevant)
                or (evaluation.coverage == 'suffisant' and evaluation.followup_query)):
            raise BriefError('Évaluation IA incohérente avec les sources collectées. Aucune relance automatique.')
        trace.append({'step': 'evaluate', 'status': 'completed'})
        extra = None
        followup = evaluation.followup_query
        if followup and followup.casefold() not in {query.casefold() for query in queries}:
            stage = 'complement'
            selected = {_stable_key(event) for event in result['events']}
            remaining = dict(inventory, events=[event for event in inventory['events']
                                               if _stable_key(event) not in selected])
            if remaining['events']:
                extra, _ = select_candidates(remaining, topic, focus=followup)
                result = _merge(result, extra)
                queries.append(followup)
                trace.append({'step': 'complement', 'status': 'completed'})
        final = _final_corpus(result, corpus, relevant, extra, [*topics, *queries], transport)
        stage = 'summarize'
        if final['sources']:
            if profile_context:
                final['profile_context'] = profile_context
            report = OUTPUTS['summarize'].model_validate(call_stage('summarize', topic, final).model_dump())
            brief = verify(Brief.model_validate(report.model_dump()), final)
            for item in brief['items']:
                assessment = next(entry for entry in report.items if entry.source_id == item['source_id'])
                fields = list(dict.fromkeys(assessment.relevance_fields))
                linked = bool(assessment.relevance and fields) and all(key in profile_context for key in fields)
                item.update(relevance=assessment.relevance if linked else '',
                            relevance_fields=fields if linked else [],
                            uncertainty=assessment.uncertainty)
            trace.append({'step': 'summarize', 'status': 'completed'})
        else:
            brief = verify(Brief(items=[], limitations=['Aucun passage pertinent exploitable dans le corpus consulté ; synthèse non générée.']), final)
            trace.append({'step': 'summarize', 'status': 'skipped'})
        result['agent_analysis'] = dict(status='completed', queries=queries, evaluation=evaluation.model_dump(),
                                       trace=trace, brief=brief, engine=engine)
        if profile_context and final['sources']:
            # Snapshot used by history and display, never the live mutable profile.
            result['agent_analysis']['profile_context'] = dict(profile_context)
        return result
    except Exception as exc:
        # Preserve collected sources on failure, never generate a fictitious replacement.
        detail = str(exc) if isinstance(exc, (BriefError, RecentProviderError, PipelexError)) else 'Erreur technique ou réponse IA invalide.'
        labels = {'plan': 'préparation', 'select': 'sélection des documents', 'collect': 'collecte', 'evaluate': 'évaluation',
                  'complement': 'complément', 'summarize': 'synthèse'}
        # Provider errors may already explain the no-retry policy.
        detail = detail.replace(' Aucun nouvel essai automatique.', '').replace(' Aucune relance automatique.', '')
        message = f"Analyse interrompue à l’étape {labels[stage]}. {detail} Aucune relance automatique."
        trace.append({'step': stage, 'status': 'failed'})
        if result is not None:
            result['agent_analysis'] = dict(status='failed', error=message, queries=queries, trace=trace, engine=engine)
        raise AgentError(message, result) from None
