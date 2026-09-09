"""A headless Qt subprocess verifies the startup error is visible to the user."""
import json
import os
import subprocess
import sys
import textwrap


def test_startup_explains_blocked_photo_recovery(tmp_path):
    script = textwrap.dedent('''
        import json, sys
        from pathlib import Path
        Path.home = classmethod(lambda cls: Path(sys.argv[1]))
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QMessageBox
        from app import main
        from app.services.photo_storage import PhotoRecoveryError
        shown = []
        def dismiss():
            for window in QApplication.topLevelWidgets():
                if isinstance(window, QMessageBox):
                    shown.append(window.text())
                    window.accept()
        def blocked_window():
            QTimer.singleShot(0, dismiss)
            raise PhotoRecoveryError('Recovery files retained; close locked files and retry.')
        main.MainWindow = blocked_window
        try:
            main.main()
        except SystemExit as exc:
            print(json.dumps({'exit': exc.code, 'shown': shown}))
    ''')
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], env=env,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        'exit': 1,
        'shown': ['Recovery files retained; close locked files and retry.'],
    }
