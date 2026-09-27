"""Explicit application bootstrap; imports never read credentials or enable AI.

Existing process variables take precedence over the project's local .env.
Neither an inference opt-in nor a provider is invented here. Actual calls still
require the application's existing consent and explicit user action.
"""

from pathlib import Path


def load_runtime_config(dotenv_path: str | Path | None = None) -> bool:
    """Load local configuration without logging values or expanding variables.

    An explicit path also allows isolated tests with a temporary, fictitious
    configuration. python-dotenv honors PYTHON_DOTENV_DISABLED. Restart the app
    after editing the file: values already present in the process are preserved.
    """
    from dotenv import load_dotenv

    path = Path(dotenv_path) if dotenv_path is not None else Path(__file__).resolve().parents[1] / '.env'
    return load_dotenv(path, override=False, verbose=False, interpolate=False)
