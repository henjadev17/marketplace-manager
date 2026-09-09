# Marketplace Manager

Aplicación de escritorio para Windows que organiza productos, fotografías y textos
para publicar manualmente en Marketplace. Versión estable: **v0.9.2**.
Incluye formulario adaptable, apariencia clara/oscura/sistema, plantillas, valores
predeterminados, fotos, cuadrícula Publicar/Copiar y exportación XLSX.

## Arquitectura

- `app/main.py`: entrada de Qt; ejecutar con `python -m app.main`.
- `app/config.py`: rutas de datos, extensiones de imagen y plantilla inicial.
- `app/data/database.py`: SQLite, migraciones aditivas, configuración, plantillas,
  productos y copia/renombrado de fotos administradas.
- `app/services/`: plantillas, XLSX con openpyxl y miniaturas con Pillow y tareas Qt.
- `app/ui/`: ventana principal, formularios, galería, temas y diálogos.
- `tests/`: regresiones de negocio y una comprobación de errores de inicio con Qt sin pantalla.
- `scripts/`: comandos PowerShell de desarrollo y empaquetado.
- `.github/workflows/tests.yml`: validación en Windows.

Se conserva la estructura y comportamiento de v0.9.2. Las dependencias siguen en
`requirements.txt`; `requirements-dev.txt` agrega pytest. `pyproject.toml` lee las
dependencias del archivo existente y configura pytest.

## Instalación

Usar Windows, Git y Python 3.11 o superior con el lanzador `py`. CI usa Python 3.11.
Desde PowerShell:

```powershell
git clone https://github.com/henjadev17/marketplace-manager.git
cd marketplace-manager
.\scripts\setup.ps1
.\scripts\run.ps1
```

Setup crea `.venv` si falta, la activa e instala las dependencias de aplicación y
desarrollo. Los scripts resuelven la raíz desde su ubicación y propagan errores.
Si una política local bloquea scripts, consultar la política de PowerShell del equipo.
Instalación manual equivalente:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m app.main
```

El lanzador heredado `run.bat` sigue disponible.

## Comandos de desarrollo

| Comando | Acción |
| --- | --- |
| `.\scripts\setup.ps1` | Preparar entorno y dependencias |
| `.\scripts\run.ps1` | Iniciar la aplicación |
| `.\scripts\test.ps1` | Ejecutar pytest |
| `.\scripts\test.ps1 -k template` | Filtrar pruebas |
| `.\scripts\build.ps1` | Generar distribución PyInstaller para Windows |

Build genera `dist/MarketplaceManager/MarketplaceManager.exe`, archivos de trabajo
en `build/` y un `.spec` local ignorado. Puede reemplazar una distribución previa en
`dist/`; no incorpora ni limpia datos personales. Es una base de empaquetado, no un
instalador firmado: validar manualmente el ejecutable antes de distribuirlo.

## Datos de usuario

Los datos se guardan **fuera del repositorio**:

```text
%USERPROFILE%\Documents\MarketplaceManager\
├── marketplace.db
├── media\
├── cache\
│   └── thumbnails\
└── exports\
```

La implementación utiliza `Path.home() / "Documents" / "MarketplaceManager"`.
Las fotos seleccionadas se copian a `media/PROD-XXXX/PROD-XXXX-01.ext`.
Eliminar un producto elimina sus copias administradas; las fotos originales
externas se conservan. No usar la carpeta de copias administradas como fuente de originales.

Nunca agregar, mover, borrar o modificar la base de producción ni sus medios durante
limpieza del repositorio. Setup, pruebas y build no operan sobre esa carpeta.
Ejecutar la aplicación normalmente sí utiliza los datos reales.

## Pruebas

### Guardado seguro de fotos

Al guardar el orden o cambiar fotos de un producto existente, la aplicación prepara
y verifica las copias antes de reemplazarlas. Conserva la carpeta anterior hasta
confirmar las referencias nuevas en SQLite. Si falla el guardado, restaura el
estado anterior. Al abrir la aplicación recupera operaciones interrumpidas:
conserva las fotos nuevas si SQLite confirmó el guardado, o recupera las anteriores
si no lo confirmó. Si la recuperación no puede completarse, muestra un mensaje
antes de cerrar, conservando los archivos pendientes.

Los archivos temporales de recuperación se guardan dentro de
`media/.photo-operations/`, separados por base de datos. No borrar esta carpeta
manualmente: puede contener el respaldo necesario para una operación pendiente.
Si Windows mantiene un archivo bloqueado, cerrar los programas que lo usan y
volver a abrir la aplicación. Si el registro está dañado, se conservan los archivos
y se detiene la recuperación para evitar una eliminación insegura.

No se permite seleccionar `media` ni sus copias como fuentes de fotos nuevas.
Un escaneo recursivo de una carpeta superior omite esos archivos. Las fotos ya
asociadas pueden seguir usando sus propias copias si falta el original externo.

Esta protección cubre errores de guardado y cierre abrupto del proceso; no sustituye
un respaldo general frente a fallos físicos de disco. No cambia los códigos de
producto ni el flujo de creación/eliminación de productos, salvo la validación de
fuentes y la recuperación pendiente antes de eliminar.

### Ejecutar la suite

```powershell
.\.venv\Scripts\Activate.ps1
python -m compileall app
pytest
```

La suite cubre códigos de producto, saltos de línea, información de plantilla,
copias y renombrado, reordenamiento (incluido original ausente), eliminación segura,
fallos parciales de creación, migraciones y valores iniciales.

`tests/conftest.py` sustituye home antes de recolectar pruebas, porque la configuración
fija rutas al importar módulos. Una fixture automática redirige rutas y el argumento
predeterminado de Database a almacenamiento temporal por prueba. Las imágenes se
crean con Pillow y las bases SQLite son temporales. La prueba del mensaje de inicio
utiliza Qt en modo `offscreen`, un home temporal y un error simulado antes de abrir
la ventana principal. Para nuevos módulos que importen rutas por
valor, redirigir también esas referencias. CI ejecuta sintaxis y pytest en
`windows-latest`; no valida diseño visual.

## Flujo Git y versiones

Crear ramas desde `main`, mantener cambios enfocados y abrir un pull request hacia
`main`. No desarrollar directamente sobre `main`. Esta infraestructura usa
`chore/project-infrastructure`. Antes de subir cambios, ejecutar sintaxis y pytest.

```powershell
git switch main
git pull --ff-only
git switch -c chore/nombre-del-cambio
# Editar y validar
git add <archivos-revisados>
git commit -m "chore: describir el cambio"
git push -u origin chore/nombre-del-cambio
```

Usar versiones `MAJOR.MINOR.PATCH` y etiquetas `vX.Y.Z`: PATCH para correcciones
compatibles, MINOR para funciones compatibles y MAJOR para cambios incompatibles.
Registrar cambios en `CHANGELOG.md` bajo Unreleased; al publicar, crear la sección
de versión y sincronizar metadatos y título de ventana. Esta infraestructura
mantiene 0.9.2 y no crea una nueva publicación.

## Aspectos existentes para tareas futuras

- Database mezcla persistencia con archivos y crea directorios globales incluso
  al recibir una base personalizada.
- SQLite y los archivos siguen siendo sistemas separados; el guardado de fotos
  existentes ahora utiliza un registro recuperable. La creación y eliminación
  de productos podrían recibir una protección equivalente en una tarea futura.
- Los códigos usan MAX + 1, pueden reutilizarse tras borrar el último producto
  y no coordinan creaciones concurrentes.
- `products.template_id` no tiene clave foránea; borrar plantillas puede dejar
  referencias antiguas, aunque la interfaz dispone de valores alternativos.
- El diálogo heredado `template_dialog.py` llama a `save_template_settings`, que
  ya no existe; la ventana principal utiliza `TemplateManagerDialog`.

Estos puntos se documentan sin refactorizar ni cambiar el comportamiento estable.
