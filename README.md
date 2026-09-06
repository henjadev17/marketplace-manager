# Marketplace Manager v0.9.2 — layout estable

Esta versión corrige el descuadre del panel derecho al cambiar el tamaño de la ventana.

## Cambios

- Panel de creación de producto dentro de un `QScrollArea`.
- El formulario ya no se aplasta cuando falta altura.
- Ancho mínimo estable para el panel derecho.
- Alturas mínimas reales en:
  - plantilla
  - título
  - precio
  - categoría
  - ubicación
  - estado
- Descripción con mayor altura mínima.
- Vista previa con mayor altura.
- Splitter con límites para evitar colapsos.
- Ventana con tamaño mínimo razonable.

## Qué se mantiene

- dark mode / claro / sistema;
- plantillas;
- valores predeterminados;
- galería y miniaturas;
- copia y renombrado de fotos;
- edición de productos;
- lista Publicar / Copiar;
- Excel;
- SQLite.

## Ejecutar

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

O usa `run.bat`.
