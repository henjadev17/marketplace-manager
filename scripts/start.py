"""Shared Windows bootstrap for the Git Bash and double-click launchers."""
import hashlib
from pathlib import Path
import subprocess
import sys


def start(root):
    root = Path(root).resolve()
    environment = root / '.venv'
    python = environment / 'Scripts' / 'python.exe'
    stamp = environment / '.requirements.sha256'
    fresh = not python.is_file()
    if fresh:
        print('Preparando entorno virtual...', flush=True)
        subprocess.run([sys.executable, '-m', 'venv', str(environment)], cwd=root, check=True)
    digest = hashlib.sha256()
    for filename in ('requirements.txt', 'requirements-dev.txt'):
        digest.update(filename.encode())
        digest.update((root / filename).read_bytes())
    expected = digest.hexdigest()
    if fresh or not stamp.is_file() or stamp.read_text(encoding='ascii') != expected:
        print('Instalando dependencias (requiere Internet)...', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', 'requirements-dev.txt'],
                       cwd=root, check=True)
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(expected, encoding='ascii')
    print('Iniciando Marketplace Manager...', flush=True)
    subprocess.run([str(python), '-m', 'app.main'], cwd=root, check=True)
    return 0


if __name__ == '__main__':
    try:
        if sys.version_info < (3, 11):
            raise RuntimeError('Instala Python 3.11 o superior para iniciar la aplicacion.')
        sys.exit(start(Path(__file__).resolve().parent.parent))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'No se pudo iniciar Marketplace Manager: {exc}', file=sys.stderr)
        sys.exit(1)
