"""The active profile is session-scoped and never consults OAuth identity."""
from unittest.mock import Mock

from streamlit.testing.v1 import AppTest

from frontend import profile
from src.contracts import ROOT


def test_active_profile_ignores_google_and_isolated_sessions(monkeypatch, tmp_path):
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setattr(profile, 'PROFILE_PATH', tmp_path / 'unused.sqlite3')
    user = Mock()
    user.get.side_effect = AssertionError('OAuth identity must not be read')
    monkeypatch.setattr(profile.st, 'user', user)
    login = Mock(side_effect=AssertionError('No login'))
    monkeypatch.setattr(profile.st, 'login', login)
    assert profile.current_identity() is None
    app = AppTest.from_file(str(ROOT / 'app.py')).run()
    app.radio(key='b_page').set_value('Mon profil').run()
    assert not app.exception
    app.text_input(key='profile_display_name').set_value('Camille')
    app.selectbox(key='profile_answer_logement').set_value('Locataire')
    next(button for button in app.button if button.label == 'Enregistrer mon profil').click().run()
    app.radio(key='b_page').set_value('Recherche').run()
    app.radio(key='b_page').set_value('Mon profil').run()
    assert app.text_input(key='profile_display_name').value == 'Camille'
    assert app.selectbox(key='profile_answer_logement').value == 'Locataire'
    other = AppTest.from_file(str(ROOT / 'app.py')).run()
    other.radio(key='b_page').set_value('Mon profil').run()
    assert not other.exception
    assert other.text_input(key='profile_display_name').value == 'Mon profil'
    user.get.assert_not_called()
    login.assert_not_called()
    assert not profile.PROFILE_PATH.exists()
