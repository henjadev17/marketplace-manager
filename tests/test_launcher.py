import importlib.util
from pathlib import Path
import subprocess
import os
import shutil

import pytest


def launcher():
    spec = importlib.util.spec_from_file_location('project_launcher', Path(__file__).parents[1] / 'scripts' / 'start.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'project with spaces'
    root.mkdir()
    (root / 'requirements.txt').write_text('Pillow>=11\n')
    (root / 'requirements-dev.txt').write_text('-r requirements.txt\npytest>=8\n')
    return root


def test_first_start_prepares_environment_then_launches(project, monkeypatch):
    module = launcher()
    calls = []
    monkeypatch.setattr(module.subprocess, 'run', lambda args, **kwargs: calls.append((args, kwargs)))
    assert module.start(project) == 0
    assert [args[args.index('-m') + 1] for args, _ in calls] == ['venv', 'pip', 'app.main']
    assert all(kwargs['cwd'] == project for _, kwargs in calls)
    assert (project / '.venv' / '.requirements.sha256').is_file()


def test_repeat_start_skips_install_until_requirements_change(project, monkeypatch):
    module = launcher()
    python = project / '.venv' / 'Scripts' / 'python.exe'
    python.parent.mkdir(parents=True)
    python.touch()
    calls = []
    monkeypatch.setattr(module.subprocess, 'run', lambda args, **kwargs: calls.append(args))
    module.start(project)
    calls.clear()
    module.start(project)
    assert len(calls) == 1 and calls[0][-1] == 'app.main'
    (project / 'requirements.txt').write_text('Pillow>=11,<12\n')
    calls.clear()
    module.start(project)
    assert [args[args.index('-m') + 1] for args in calls] == ['pip', 'app.main']


def test_failed_install_does_not_launch_or_mark_success(project, monkeypatch):
    module = launcher()
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if 'pip' in args:
            raise subprocess.CalledProcessError(1, args)
    monkeypatch.setattr(module.subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        module.start(project)
    assert not (project / '.venv' / '.requirements.sha256').exists()
    assert all('app.main' not in args for args in calls)


@pytest.mark.skipif(os.name != 'nt', reason='Windows launchers')
@pytest.mark.parametrize('kind', ['cmd', 'bash'])
def test_entry_points_find_project_with_spaces(project, tmp_path, kind):
    scripts = project / 'scripts'
    scripts.mkdir()
    # Stub the bootstrap so this executes the real wrapper without starting Qt.
    (scripts / 'start.py').write_text("print('BOOTSTRAP_OK')\n")
    repository = Path(__file__).parents[1]
    if kind == 'cmd':
        shutil.copyfile(repository / 'Iniciar.cmd', project / 'Iniciar.cmd')
        command = ['cmd.exe', '/c', str(project / 'Iniciar.cmd')]
    else:
        git = shutil.which('git')
        bash = Path(git).parent.parent / 'bin' / 'bash.exe' if git else Path('missing')
        if not bash.is_file():
            pytest.skip('Git Bash unavailable')
        shutil.copyfile(repository / 'scripts' / 'start.sh', scripts / 'start.sh')
        command = [str(bash), (scripts / 'start.sh').as_posix()]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert 'BOOTSTRAP_OK' in result.stdout
