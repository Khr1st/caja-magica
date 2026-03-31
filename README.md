# Caja Mágica

Tu tesorería personal inteligente.

Registra ingresos, egresos, ahorros y proyecciones con lenguaje natural. Clasificación automática, exportación Excel, semáforo de caja y PWA instalable.

## Stack

- **Backend:** Python 3.11+ · FastAPI · Uvicorn
- **Frontend:** HTML + CSS + JS vanilla (single file)
- **Persistencia:** JSON local
- **Excel:** openpyxl
- **Deploy:** Railway.app compatible

## Ejecutar local

```bash
pip install -r requirements.txt
python main.py
# Abrir http://localhost:8000
```

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| PORT | 8000 | Puerto del servidor |
| TASA_COP_USD | 4200 | Tasa de conversión COP/USD |
| CAJA_MINIMA_COP | 800000 | Umbral mínimo de caja |

## Deploy en Railway

1. Conectar este repo en [railway.app](https://railway.app)
2. Railway detecta automáticamente Python + Procfile
3. Configurar variables de entorno si se desean valores distintos
