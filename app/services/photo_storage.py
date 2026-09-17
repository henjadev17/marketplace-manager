"""Recoverable photo-folder replacement coordinated by a SQLite commit marker.

Call prepare/install/recover while holding BEGIN IMMEDIATE on the owning database.
The filesystem journal precedes every directory swap; the SQLite marker commits
with the new photo rows. Recovery therefore never guesses from filenames alone.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import uuid

from PIL import Image, ImageOps


def rotate_staged_photo(path, degrees):
    """Rotate only a staged copy, normalizing camera orientation first."""
    with Image.open(path) as source:
        if getattr(source, 'n_frames', 1) != 1:
            raise ValueError('No se pueden girar imágenes animadas o de varias páginas.')
        image_format = source.format
        image = ImageOps.exif_transpose(source).rotate(-degrees, expand=True)
        options = {}
        if image_format == 'JPEG':
            options.update(quality=95, subsampling=0)
        if image_format in ('JPEG', 'PNG', 'WEBP'):
            options['exif'] = image.getexif().tobytes()
            if source.info.get('icc_profile'):
                options['icc_profile'] = source.info['icc_profile']
    try:
        image.save(path, format=image_format, **options)
    finally:
        image.close()


class PhotoRecoveryError(RuntimeError):
    """Keep recovery evidence intact and stop writes until it can be recovered."""


class PhotoDestinationExists(FileExistsError):
    """A new product must reserve another code without touching this entry."""


def is_managed_source(path, media_dir):
    return Path(path).resolve().is_relative_to(Path(media_dir).resolve())


def validate_original(path, media_dir):
    if is_managed_source(path, media_dir):
        raise ValueError(
            "No se pueden usar fotos de la carpeta administrada media como originales. "
            "Selecciona las imágenes desde su carpeta original."
        )


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class PhotoStorage:
    def __init__(self, media_dir, db_path):
        self.media = Path(media_dir).absolute()
        self.database = os.path.normcase(str(Path(db_path).resolve()))
        database_key = hashlib.sha256(self.database.encode('utf-8')).hexdigest()
        self.operations = self.media / '.photo-operations' / database_key

    def validate_original(self, path):
        validate_original(path, self.media)

    def is_managed_source(self, path):
        return is_managed_source(path, self.media)

    def next_available_number(self, number):
        while os.path.lexists(self.media / f'PROD-{number:04d}'):
            number += 1
        return number

    def _checked(self, path):
        """Never rename or remove outside media or through a symlink/junction."""
        path = Path(path).absolute()
        if not path.is_relative_to(self.media) or '..' in path.parts:
            raise PhotoRecoveryError('La ruta de fotos está fuera de la carpeta administrada.')
        for part in [self.media, *reversed(path.parents), path]:
            if not part.is_relative_to(self.media):
                continue
            if part.is_symlink():
                raise PhotoRecoveryError(f'No se modificará una carpeta enlazada: {part}')
            if part.exists():
                attributes = getattr(part.lstat(), 'st_file_attributes', 0)
                if attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
                    raise PhotoRecoveryError(f'No se modificará una carpeta enlazada: {part}')
        return path

    def product_folder(self, code):
        if not isinstance(code, str) or not re.fullmatch(r'PROD-\d{4,}', code):
            raise PhotoRecoveryError('El código del producto no permite una ruta de fotos segura.')
        return self._checked(self.media / code)

    def _remove_tree(self, path):
        path = self._checked(path)
        if not path.exists():
            return
        # Inspect descendants before rmtree, including Windows junctions.
        for current, directories, files in os.walk(path, followlinks=False):
            for name in directories + files:
                self._checked(Path(current) / name)
        shutil.rmtree(path)

    def _cleanup(self, operation):
        # Keep the journal until every backup/staged file has been removed.
        for name in ('stage', 'discard', 'backup'):
            self._remove_tree(operation / name)
        for name in ('manifest.tmp', 'manifest.json', 'cancelled'):
            self._checked(operation / name).unlink(missing_ok=True)
        operation.rmdir()

    def _mark_cancelled(self, operation):
        with self._checked(operation / 'cancelled').open('wb') as stream:
            stream.flush()
            os.fsync(stream.fileno())

    def prepare(self, code, sources, rotations=None, create_only=False):
        """sources: ordered (photo_id, source_path); return operation and filenames."""
        final = self.product_folder(code)
        if create_only and os.path.lexists(final):
            raise PhotoDestinationExists(str(final))
        self._checked(self.operations).mkdir(parents=True, exist_ok=True)
        operation = self.operations / uuid.uuid4().hex
        stage = operation / 'stage'
        stage.mkdir(parents=True)
        files = {}
        staged = []
        for position, (photo_id, source) in enumerate(sources, 1):
            source = Path(source)
            filename = f'{code}-{position:02d}{source.suffix.lower() or ".jpg"}'
            destination = stage / filename
            expected = file_digest(source)
            shutil.copy2(source, destination)
            if file_digest(destination) != expected:
                raise OSError(f'No se pudo verificar la copia de: {source.name}')
            degrees = (rotations or {}).get(photo_id, 0) % 360
            if degrees:
                rotate_staged_photo(destination, degrees)
                expected = file_digest(destination)
            with destination.open('r+b') as stream:
                os.fsync(stream.fileno())
            files[filename] = expected
            staged.append((photo_id, filename))
        manifest = dict(version=1, database=self.database, code=code,
                        had_original=final.exists(), files=files)
        if create_only:
            manifest.update(kind='create', had_original=False)
        temporary = operation / 'manifest.tmp'
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(manifest, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(operation / 'manifest.json')
        return operation, staged

    def install_new(self, operation, code):
        """Windows directory rename fails atomically if the target exists."""
        final = self.product_folder(code)
        if os.path.lexists(final):
            raise PhotoDestinationExists(str(final))
        try:
            self._checked(operation / 'stage').rename(final)
        except FileExistsError as exc:
            raise PhotoDestinationExists(str(final)) from exc

    def prepare_delete(self, code, copied_paths):
        """Journal and quarantine only this product's registered copies."""
        final = self.product_folder(code)
        allowed = set()
        for value in copied_paths:
            if not value:
                continue
            path = self._checked(Path(value))
            if path.parent != final or not re.fullmatch(re.escape(code) + r'-\d{2,}\.[a-zA-Z0-9]+', path.name):
                raise PhotoRecoveryError('La copia no pertenece a la carpeta del producto.')
            allowed.add(path.name)
        files = {}
        if final.exists():
            for entry in final.iterdir():
                self._checked(entry)
                if entry.name not in allowed or not entry.is_file():
                    raise PhotoRecoveryError('La carpeta contiene archivos ajenos; no se eliminará.')
                files[entry.name] = file_digest(entry)
        self._checked(self.operations).mkdir(parents=True, exist_ok=True)
        operation = self.operations / uuid.uuid4().hex
        operation.mkdir()
        manifest = dict(version=1, database=self.database, code=code, kind='delete',
                        had_original=final.exists(), files=files)
        temporary = operation / 'manifest.tmp'
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(manifest, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(operation / 'manifest.json')
        if manifest['had_original']:
            final.rename(self._checked(operation / 'backup'))
        return operation

    def _recover_delete(self, operation, manifest, committed):
        final = self.product_folder(manifest['code'])
        backup = self._checked(operation / 'backup')
        if committed and backup.exists():
            # A previous cleanup can have removed only some registered files.
            # Validate the remaining subset before removing anything else.
            entries = list(backup.iterdir())
            for entry in entries:
                self._checked(entry)
                if (entry.name not in manifest['files'] or not entry.is_file()
                        or file_digest(entry) != manifest['files'][entry.name]):
                    raise ValueError('El respaldo contiene archivos desconocidos o modificados.')
            for entry in entries:
                entry.unlink()
            backup.rmdir()
        elif not committed:
            if backup.exists():
                if os.path.lexists(final):
                    raise ValueError('La carpeta de destino está ocupada; se conserva el respaldo.')
                backup.rename(final)
            elif manifest['had_original'] and not final.exists():
                raise ValueError('No se encuentra la carpeta para restaurar el producto.')
        # Never touch a new directory appearing at the old product path after commit.
        self._cleanup(operation)

    def install(self, operation, code):
        final = self.product_folder(code)
        if final.exists():
            final.rename(self._checked(operation / 'backup'))
        self._checked(operation / 'stage').rename(final)

    def recover(self, con):
        """Idempotently finish committed saves or restore uncommitted ones."""
        self._checked(self.operations)
        if not self.operations.exists():
            return
        for operation in sorted(self.operations.iterdir()):
            try:
                self._recover_one(con, self._checked(operation))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise PhotoRecoveryError(
                    'No se pudo recuperar una operación de fotos. Se conservan los '
                    f'archivos de recuperación en:\n{operation}\n\n{exc}'
                ) from exc
        # A crash after removing a journal but before SQL cleanup leaves harmless
        # markers. All existing journals have now been reconciled.
        con.execute('DELETE FROM photo_file_commits')

    def _recover_one(self, con, operation):
        if not re.fullmatch(r'[0-9a-f]{32}', operation.name) or not operation.is_dir():
            raise ValueError('Registro de recuperación desconocido.')
        manifest_path = self._checked(operation / 'manifest.json')
        if not manifest_path.exists():
            if (operation / 'backup').exists():
                raise ValueError('Falta el registro del respaldo; no se eliminará.')
            self._cleanup(operation)  # Interrupted preparation; no swap occurred.
            return
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if (manifest['version'] != 1 or manifest['database'] != self.database
                or type(manifest['had_original']) is not bool):
            raise ValueError('El registro no corresponde a esta base de datos.')
        code = manifest['code']
        final = self.product_folder(code)
        backup = self._checked(operation / 'backup')
        stage = self._checked(operation / 'stage')
        discard = self._checked(operation / 'discard')
        committed = con.execute('SELECT 1 FROM photo_file_commits WHERE operation_id = ?',
                                (operation.name,)).fetchone()
        if manifest.get('kind') == 'delete':
            self._recover_delete(operation, manifest, committed)
            return
        cancelled = self._checked(operation / 'cancelled')
        if (not committed and manifest.get('kind') == 'create'
                and (stage.exists() or discard.exists() or cancelled.exists())):
            # Persist "never installed" before removing stage. Otherwise a crash
            # during cleanup could mistake a collision for our installed folder.
            self._mark_cancelled(operation)
            self._cleanup(operation)
            return
        if committed:
            # Verify the new files before destroying the last previous copies.
            if not final.is_dir() or not isinstance(manifest['files'], dict):
                raise ValueError('No se encuentran las fotos confirmadas.')
            for name, expected in manifest['files'].items():
                if not re.fullmatch(re.escape(code) + r'-\d{2,}\.[a-zA-Z0-9]+', name):
                    raise ValueError('Nombre de foto inválido en el registro.')
                if file_digest(self._checked(final / name)) != expected:
                    raise ValueError('Las fotos confirmadas no coinciden con el registro.')
        elif backup.exists():
            if final.exists():
                final.rename(discard)
            backup.rename(final)
        elif not manifest['had_original'] and not stage.exists() and final.exists():
            if manifest.get('kind') == 'create':
                # Do not remove unrecognized files added after an interruption.
                if set(p.name for p in final.iterdir()) != set(manifest['files']):
                    raise ValueError('La carpeta de creación contiene archivos desconocidos.')
                for name, expected in manifest['files'].items():
                    if not re.fullmatch(re.escape(code) + r'-\d{2,}\.[a-zA-Z0-9]+', name):
                        raise ValueError('Nombre de foto inválido en el registro.')
                    if file_digest(self._checked(final / name)) != expected:
                        raise ValueError('La foto de creación cambió; se conserva para revisión.')
            final.rename(discard)
        elif manifest['had_original'] and not final.exists():
            raise ValueError('No se encuentra la carpeta anterior ni su respaldo.')
        if not committed and manifest.get('kind') == 'create':
            self._mark_cancelled(operation)
        self._cleanup(operation)
