"""Bootstrap tests use fictitious files and a fully isolated environment mapping."""

import builtins
import importlib
import os
from pathlib import Path
import runpy
from types import SimpleNamespace
from unittest.mock import Mock

import dotenv
import pytest

from src import runtime_config


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    # Do not read/copy real environment values; restore only the original object.
    monkeypatch.setattr(os, 'environ', {'PYTHON_DOTENV_DISABLED': '0'})
    real_load = dotenv.load_dotenv

    def fake_files_only(path, **kwargs):
        assert Path(path).parent == tmp_path, 'A test must never read the real project .env'
        return real_load(path, **kwargs)

    monkeypatch.setattr(dotenv, 'load_dotenv', fake_files_only)


def fake_file(tmp_path, content):
    path = tmp_path / 'configuration-factice.env'
    path.write_text(content, encoding='utf-8')
    return path


def test_explicit_bootstrap_loads_fictitious_configuration_without_output(tmp_path, capsys, caplog):
    path = fake_file(tmp_path,
        'ENABLE_PIPELEX_CALLS=true\nPIPELEX_EXECUTION_MODE=local\n'
        'OPENAI_API_KEY=fake-never-real-key\nPOLITICAL_DATA_SOURCE=official\n')
    assert runtime_config.load_runtime_config(path) is True
    assert os.environ['ENABLE_PIPELEX_CALLS'] == 'true'
    assert os.environ['PIPELEX_EXECUTION_MODE'] == 'local'
    assert os.environ['OPENAI_API_KEY'] == 'fake-never-real-key'
    assert capsys.readouterr() == ('', '')
    assert 'fake-never-real-key' not in caplog.text


def test_explicit_process_false_and_provider_override_file_values(tmp_path):
    os.environ.update(ENABLE_PIPELEX_CALLS='false', PIPELEX_EXECUTION_MODE='hosted',
                      OPENAI_API_KEY='fake-process-key')
    path = fake_file(tmp_path,
        'ENABLE_PIPELEX_CALLS=true\nPIPELEX_EXECUTION_MODE=local\nOPENAI_API_KEY=fake-file-key\n')
    runtime_config.load_runtime_config(path)
    assert os.environ['ENABLE_PIPELEX_CALLS'] == 'false'
    assert os.environ['PIPELEX_EXECUTION_MODE'] == 'hosted'
    assert os.environ['OPENAI_API_KEY'] == 'fake-process-key'


def test_file_false_remains_false_without_any_automatic_activation(tmp_path):
    path = fake_file(tmp_path, 'ENABLE_PIPELEX_CALLS=false\nOPENAI_API_KEY=fake-never-real-key\n')
    runtime_config.load_runtime_config(path)
    assert os.environ['ENABLE_PIPELEX_CALLS'] == 'false'
    assert 'PIPELEX_EXECUTION_MODE' not in os.environ


def test_key_alone_does_not_choose_provider_or_enable_calls(tmp_path):
    runtime_config.load_runtime_config(fake_file(tmp_path, 'OPENAI_API_KEY=fake-never-real-key\n'))
    assert 'ENABLE_PIPELEX_CALLS' not in os.environ
    assert 'PIPELEX_EXECUTION_MODE' not in os.environ


@pytest.mark.parametrize('disabled', ['1', 'true', 'yes'])
def test_dotenv_disable_switch_prevents_file_loading(tmp_path, monkeypatch, disabled):
    path = fake_file(tmp_path, 'ENABLE_PIPELEX_CALLS=true\nOPENAI_API_KEY=fake-never-real-key\n')
    os.environ['PYTHON_DOTENV_DISABLED'] = disabled
    opened = Mock(side_effect=AssertionError('Disabled dotenv must not open its file'))
    monkeypatch.setattr('dotenv.main.DotEnv._get_stream', opened)
    assert runtime_config.load_runtime_config(path) is False
    opened.assert_not_called()
    assert 'OPENAI_API_KEY' not in os.environ
    assert 'ENABLE_PIPELEX_CALLS' not in os.environ


def test_missing_local_configuration_keeps_defaults_disabled(tmp_path, capsys):
    assert runtime_config.load_runtime_config(tmp_path / 'missing-factice.env') is False
    assert 'ENABLE_PIPELEX_CALLS' not in os.environ
    assert 'PIPELEX_EXECUTION_MODE' not in os.environ
    assert capsys.readouterr() == ('', '')


def test_values_are_not_interpolated_from_other_variables(tmp_path):
    os.environ['FAKE_SOURCE'] = 'fake-never-real-key'
    path = fake_file(tmp_path, 'OPENAI_API_KEY=${FAKE_SOURCE}\nENABLE_PIPELEX_CALLS=${FAKE_SOURCE}\n')
    runtime_config.load_runtime_config(path)
    assert os.environ['OPENAI_API_KEY'] == '${FAKE_SOURCE}'
    assert os.environ['ENABLE_PIPELEX_CALLS'] == '${FAKE_SOURCE}'


def test_default_location_is_exact_project_file_and_options_are_explicit(monkeypatch):
    mocked = Mock(return_value=False)
    monkeypatch.setattr(dotenv, 'load_dotenv', mocked)
    assert runtime_config.load_runtime_config() is False
    mocked.assert_called_once_with(ROOT / '.env', override=False, verbose=False, interpolate=False)


def test_importing_helper_or_app_does_not_bootstrap_or_import_frontend(monkeypatch):
    mocked = Mock(side_effect=AssertionError('Import must not load dotenv'))
    monkeypatch.setattr(dotenv, 'load_dotenv', mocked)
    real_import = builtins.__import__

    def importing(name, *args, **kwargs):
        if name == 'frontend.interface_b':
            raise AssertionError('Importing app must not initialize the frontend')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', importing)
    importlib.reload(runtime_config)
    namespace = runpy.run_path(str(ROOT / 'app.py'), run_name='imported_app_for_test')
    assert callable(namespace['main'])
    mocked.assert_not_called()
    assert 'ENABLE_PIPELEX_CALLS' not in os.environ


def test_application_bootstraps_before_frontend_import_and_render(monkeypatch):
    events = []
    monkeypatch.setattr(runtime_config, 'load_runtime_config', lambda: events.append('configuration'))
    real_import = builtins.__import__

    def importing(name, *args, **kwargs):
        if name == 'frontend.interface_b':
            assert events == ['configuration']
            events.append('import frontend')
            return SimpleNamespace(main=lambda: events.append('render'))
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', importing)
    runpy.run_path(str(ROOT / 'app.py'), run_name='__main__')
    assert events == ['configuration', 'import frontend', 'render']
