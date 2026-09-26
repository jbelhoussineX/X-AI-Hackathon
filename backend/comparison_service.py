"""Boundary for the future Dust/Pipelex integration. No SDK or API call here."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

from backend.comparison_validation import validate_report, validate_request


@dataclass(frozen=True)
class ComparisonResult:
    report: dict
    snapshot_to_store: dict | None


def compare_for_refresh(request: dict, analyze: Callable[[dict], dict]) -> ComparisonResult:
    """Validate around an injected analyzer, without writing to a database.

    The caller supplies a bare ComparisonRequest and a callable accepting the
    Pipelex envelope {"request": ...} and returning a bare ChangeReport.
    Exceptions propagate: the caller must record an error and preserve old data.
    An unconfirmed result never replaces the last verified snapshot.
    This function does not authenticate, schedule, deduplicate or persist.
    """
    safe_request = deepcopy(request)
    validate_request(safe_request)
    # Give the external analyzer its own copy so it cannot change the evidence
    # against which its response will be validated.
    report = analyze({"request": deepcopy(safe_request)})
    validate_report(safe_request, report)
    snapshot = None if report["change_type"] == "unconfirmed" else deepcopy(safe_request["current"])
    return ComparisonResult(deepcopy(report), snapshot)
