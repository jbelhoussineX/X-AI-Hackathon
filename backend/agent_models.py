"""Strict application checks for the new agent, independent of report v1."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=800)]
Query = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=100)]


class Checked(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


def check_query(value):
    if any(ord(char) < 32 for char in value) or not any(char.isalnum() for char in value) or '://' in value:
        raise ValueError('Invalid search query')
    return value


class Plan(Checked):
    queries: list[Query] = Field(min_length=1, max_length=2)

    @field_validator('queries')
    @classmethod
    def queries_valid(cls, values):
        if len({query.casefold() for query in values}) != len(values):
            raise ValueError('Duplicate queries')
        return [check_query(query) for query in values]


class Evaluation(Checked):
    coverage: Literal['suffisant', 'partiel', 'vide']
    relevant_sources: list[str] = Field(max_length=18)
    gaps: list[ShortText] = Field(max_length=4)
    followup_query: str = Field(max_length=100)

    @field_validator('followup_query')
    @classmethod
    def followup_valid(cls, value):
        value = value.strip()
        if value and len(value) < 3:
            raise ValueError('Short query')
        return check_query(value) if value else ''


class AssessedItem(Checked):
    source_id: str = Field(min_length=1, max_length=30)
    quote_id: str = Field(min_length=1, max_length=30)
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
    relevance: Annotated[str, StringConstraints(strip_whitespace=True, max_length=800)] = ''
    relevance_fields: list[Literal['genre', 'couple', 'emploi', 'enfants', 'animaux', 'logement']] = Field(default_factory=list, max_length=6)
    uncertainty: ShortText


class AgentBrief(Checked):
    items: list[AssessedItem] = Field(max_length=6)
    limitations: list[ShortText] = Field(max_length=8)


OUTPUTS = {'plan': Plan, 'evaluate': Evaluation, 'summarize': AgentBrief}


class Selection(Checked):
    # These are display labels, not lexical queries used by a search engine.
    # An empty selection may have no labels; short topics such as IA are valid.
    queries: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]] = Field(max_length=8)
    event_ids: list[Annotated[str, StringConstraints(min_length=1, max_length=20)]] = Field(max_length=6)

    @field_validator('queries')
    @classmethod
    def labels_valid(cls, values):
        return list(dict.fromkeys(check_query(value) for value in values))


OUTPUTS['select'] = Selection
