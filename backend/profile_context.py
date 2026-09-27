"""Explicit questionnaire choices allowed in a personalized summary, never identity."""
from collections.abc import Mapping

from backend.profiles import QUESTIONNAIRE


def summary_profile(answers):
    if not isinstance(answers, Mapping):
        return {}
    return {key: answers[key] for key, (_, choices) in QUESTIONNAIRE.items()
            if isinstance(answers.get(key), str) and answers[key] in choices
            and answers[key] != 'Autre'}
