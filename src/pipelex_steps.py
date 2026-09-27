"""Opérateurs du parcours local ; importés uniquement par le processus Pipelex."""
import json

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func, func_registry

from src.openai_research import Run, ResearchFailure

_run: Run | None = None


def bind_run(run: Run) -> None:
    global _run
    _run = run
    for function in (collect_sources, assess_gaps, complete_sources, write_report):
        func_registry.register_function(function)


def current() -> Run:
    if _run is None:
        raise RuntimeError('Recherche non initialisée')
    return _run


@pipe_func()
async def collect_sources(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=await current().research())


@pipe_func()
async def assess_gaps(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=json.dumps(await current().review(), ensure_ascii=False))


@pipe_func()
async def complete_sources(working_memory: WorkingMemory) -> TextContent:
    review = json.loads(working_memory.get_stuff_as_text('assessment').text)
    if review['needs_more']:
        run = current()
        try:
            await run.research(review['followup_query'])
        except ResearchFailure as exc:
            # Only an optional, token-truncated supplement may be discarded.
            # research() appends notes/sources only after a completed response.
            if (exc.code != 'format' or exc.reason != 'max_output_tokens'
                    or not run.notes or not run.source_urls):
                raise
            run.limitations.append(
                'La recherche complémentaire a été interrompue à la limite de tokens. '
                'Son contenu partiel est écarté, sans nouvel essai. Ce rapport repose '
                'uniquement sur la recherche initiale ; les informations manquantes '
                'identifiées n’ont pas pu être complétées.'
            )
    return TextContent(text=current().corpus())


@pipe_func()
async def write_report(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=json.dumps(await current().finish(), ensure_ascii=False))
