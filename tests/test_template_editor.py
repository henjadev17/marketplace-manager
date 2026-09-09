import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app.ui.template_manager_dialog import TemplateManagerDialog


@pytest.fixture(scope='module')
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def editor(db, qt_app):
    db.create_template('Second', 'Second body')
    dialog = TemplateManagerDialog(db)
    yield dialog
    dialog.deleteLater()
    qt_app.processEvents()


@pytest.fixture
def answer(monkeypatch):
    real_exec = QMessageBox.exec
    def choose(label):
        prompts = []
        def execute(box):
            prompts.append(box.windowTitle())
            def click():
                for button in box.buttons():
                    if button.text() == label:
                        button.click()
                        return
                box.reject()
            QTimer.singleShot(0, click)
            return real_exec(box)
        monkeypatch.setattr(QMessageBox, 'exec', execute)
        return prompts
    return choose


def second_row(editor):
    return next(i for i in range(editor.list.count())
                if editor.list.item(i).data(Qt.UserRole) != editor.selected_id())


@pytest.mark.parametrize('choice', ['Guardar', 'Descartar', 'Cancelar'])
def test_switch_protects_draft(editor, db, answer, choice):
    original_id = editor.selected_id()
    original = db.get_template(original_id)
    row = second_row(editor)
    target_id = editor.list.item(row).data(Qt.UserRole)
    editor.name.setText('Edited name')
    editor.body.setPlainText('New body\n\nLine two')
    answer(choice)
    editor.list.setCurrentRow(row)
    if choice == 'Cancelar':
        assert editor.selected_id() == original_id
        assert editor.name.text() == 'Edited name'
        assert editor.body.toPlainText() == 'New body\n\nLine two'
    else:
        assert editor.selected_id() == target_id
        assert editor.body.toPlainText() == 'Second body'
    saved = db.get_template(original_id)
    assert saved['body'] == ('New body\n\nLine two' if choice == 'Guardar' else original['body'])
    assert saved['name'] == ('Edited name' if choice == 'Guardar' else original['name'])


@pytest.mark.parametrize('action', ['accept', 'reject', 'close'])
@pytest.mark.parametrize('choice', ['Guardar', 'Descartar', 'Cancelar'])
def test_close_protects_draft(editor, db, answer, action, choice):
    template_id = editor.selected_id()
    original = db.get_template(template_id)['body']
    editor.show()
    editor.body.setPlainText('Draft')
    answer(choice)
    getattr(editor, action)()
    assert editor.isVisible() == (choice == 'Cancelar')
    assert db.get_template(template_id)['body'] == ('Draft' if choice == 'Guardar' else original)
    if choice == 'Cancelar':
        assert editor.body.toPlainText() == 'Draft'


def test_failed_save_keeps_draft_and_selection(editor, db, answer, monkeypatch):
    template_id = editor.selected_id()
    row = second_row(editor)
    editor.show()
    editor.name.setText('')  # Real database validation failure.
    editor.body.setPlainText('Keep this draft')
    answer('Guardar')
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: None)
    editor.list.setCurrentRow(row)
    assert editor.selected_id() == template_id
    assert editor.body.toPlainText() == 'Keep this draft'
    assert editor.name.text() == ''
    assert editor.isVisible()


@pytest.mark.parametrize('action', ['new_template', 'duplicate_template', 'delete_template'])
def test_cancel_protects_draft_from_toolbar_actions(editor, db, answer, monkeypatch, action):
    before = db.list_templates()
    template_id = editor.selected_id()
    editor.body.setPlainText('Draft')
    answer('Cancelar')
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    getattr(editor, action)()
    assert db.list_templates() == before
    assert editor.selected_id() == template_id
    assert editor.body.toPlainText() == 'Draft'


def test_set_default_does_not_discard_draft(editor, db):
    editor.list.setCurrentRow(second_row(editor))
    template_id = editor.selected_id()
    editor.body.setPlainText('Draft')
    editor.set_default()
    assert db.get_default_template_id() == template_id
    assert editor.body.toPlainText() == 'Draft'


def test_name_only_edit_is_saved_before_close(editor, db, answer):
    template_id = editor.selected_id()
    editor.name.setText('Renamed')
    answer('Guardar')
    editor.accept()
    assert db.get_template(template_id)['name'] == 'Renamed'


def test_manual_save_resets_dirty_state(editor, db, answer):
    template_id = editor.selected_id()
    editor.body.setPlainText('Saved\n\nText')
    prompts = answer('Cancelar')
    editor.save_current()
    editor.show()
    editor.accept()
    assert not editor.isVisible()
    assert prompts == []
    assert db.get_template(template_id)['body'] == 'Saved\n\nText'


def test_unchanged_or_reverted_text_does_not_prompt(editor, answer):
    original = editor.body.toPlainText()
    editor.body.setPlainText('Temporary edit')
    editor.body.setPlainText(original)
    prompts = answer('Cancelar')
    target_row = second_row(editor)
    target_id = editor.list.item(target_row).data(Qt.UserRole)
    editor.list.setCurrentRow(target_row)
    assert editor.selected_id() == target_id
    assert prompts == []


@pytest.mark.parametrize('action', ['accept', 'reject', 'close'])
def test_failed_save_prevents_closing(editor, db, answer, monkeypatch, action):
    template_id = editor.selected_id()
    original = db.get_template(template_id)
    editor.show()
    editor.name.setText('Second')  # Real SQLite UNIQUE constraint failure.
    editor.body.setPlainText('Draft')
    answer('Guardar')
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: None)
    getattr(editor, action)()
    assert editor.isVisible()
    assert editor.body.toPlainText() == 'Draft'
    assert db.get_template(template_id) == original


def test_escape_can_cancel_closing(editor, answer):
    from PySide6.QtTest import QTest
    editor.show()
    editor.body.setPlainText('Draft')
    prompts = answer('Cancelar')
    QTest.keyClick(editor, Qt.Key_Escape)
    assert editor.isVisible()
    assert editor.body.toPlainText() == 'Draft'
    assert len(prompts) == 1


def test_duplicate_after_save_includes_latest_text(editor, db, answer):
    editor.body.setPlainText('Latest draft')
    answer('Guardar')
    editor.duplicate_template()
    saved = db.get_template(editor.selected_id())
    assert saved['name'] == 'General copia'
    assert saved['body'] == 'Latest draft'


@pytest.mark.parametrize('input_method', ['mouse', 'keyboard'])
def test_cancel_selection_from_real_input_restores_current_item(editor, answer, qt_app, input_method):
    from PySide6.QtTest import QTest
    editor.show()
    qt_app.processEvents()
    original_id = editor.selected_id()
    target = editor.list.item(second_row(editor))
    editor.body.setPlainText('Draft')
    prompts = answer('Cancelar')
    if input_method == 'mouse':
        QTest.mouseClick(editor.list.viewport(), Qt.LeftButton,
                         pos=editor.list.visualItemRect(target).center())
    else:
        editor.list.setFocus()
        QTest.keyClick(editor.list, Qt.Key_Down)
    qt_app.processEvents()
    assert editor.selected_id() == original_id
    assert editor.list.selectedItems() == [editor.list.currentItem()]
    assert editor.body.toPlainText() == 'Draft'
    assert len(prompts) == 1
