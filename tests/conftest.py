"""Keep Streamlit's offline UI tests independent of installed OAuth secrets."""
from unittest.mock import patch


def pytest_configure(config):
    from streamlit.runtime.secrets import Secrets

    # AppTest and st.user hold separate Secrets references. Patch their shared
    # loader before collection, so neither opens local or user secrets.toml.
    # OAuth identities and login/logout are explicitly simulated in UI tests.
    empty_secrets = patch.object(Secrets, '_parse', return_value={})
    empty_secrets.start()
    config.add_cleanup(empty_secrets.stop)
