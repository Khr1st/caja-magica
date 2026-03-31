import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from clasificador import clasificar
import excel_export

app = FastAPI(title="Caja Mágica", version="1.0.0")

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "movimientos.json"
DATA_FILE.parent.mkdir(exist_ok=True)

TASA_COP_USD = int(os.environ.get("TASA_COP_USD", 4200))
CAJA_MINIMA_COP = int(os.environ.get("CAJA_MINIMA_COP", 800_000))


class EntradaTexto(BaseModel):
    texto: str


class ConfigUpdate(BaseModel):
    tasa_cop_usd: Optional[int] = None
    caja_minima_cop: Optional[int] = None


def cargar_movimientos() -> list:
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def guardar_movimientos(lista: list):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(lista, f, indent=2, ensure_ascii=False)


def mes_actual() -> str:
    return datetime.now().strftime("%Y-%m")


def calcular_resumen(movimientos: list) -> dict:
    """Calcula el resumen financiero de una lista de movimientos del mismo mes."""
    global TASA_COP_USD, CAJA_MINIMA_COP

    ingresos_cop = sum(m["monto_cop"] for m in movimientos if m["tipo"] == "ingreso")
    egresos_cop = sum(m["monto_cop"] for m in movimientos if m["tipo"] in ("egreso", "ahorro"))
    ahorros_cop = sum(m["monto_cop"] for m in movimientos if m["tipo"] == "ahorro")
    neto = ingresos_cop - egresos_cop

    if len(movimientos) == 0:
        semaforo = "sin_datos"
    elif neto < CAJA_MINIMA_COP:
        semaforo = "rojo"
    elif neto < CAJA_MINIMA_COP * 2:
        semaforo = "amarillo"
    else:
        semaforo = "verde"

    mensajes_semaforo = {
        "sin_datos": "Sin movimientos aún",
        "rojo": "Caja por debajo del mínimo — revisa egresos",
        "amarillo": "Caja ajustada — monitorea esta semana",
        "verde": "Caja saludable — vas bien",
    }

    runway_meses = 99
    if egresos_cop > 0:
        gasto_diario = egresos_cop / 30
        runway_meses = round(neto / gasto_diario, 1) if gasto_diario > 0 else 99

    por_categoria: dict = {}
    for m in movimientos:
        cat = m.get("categoria", "otro")
        por_categoria[cat] = por_categoria.get(cat, 0) + m["monto_cop"]

    return {
        "ingresos_cop": ingresos_cop,
        "egresos_cop": egresos_cop,
        "ahorros_cop": ahorros_cop,
        "neto_cop": neto,
        "semaforo": semaforo,
        "semaforo_mensaje": mensajes_semaforo.get(semaforo, ""),
        "runway_meses": runway_meses,
        "por_categoria": por_categoria,
        "total_movimientos": len(movimientos),
        "tasa_cop_usd": TASA_COP_USD,
        "caja_minima_cop": CAJA_MINIMA_COP,
    }


@app.get("/")
async def root():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/api/movimiento")
async def crear_movimiento(entrada: EntradaTexto):
    resultado = clasificar(entrada.texto)
    if resultado.error:
        return {"ok": False, "mensaje": resultado.error}

    mes = mes_actual()
    movimiento = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "mes": mes,
        "texto_original": entrada.texto,
        "tipo": resultado.tipo,
        "categoria": resultado.categoria,
        "descripcion": resultado.descripcion,
        "monto_cop": resultado.monto_cop,
        "monto_original": resultado.monto_original,
        "moneda": resultado.moneda,
        "es_proyeccion": resultado.es_proyeccion,
        "confianza": resultado.confianza,
    }

    todos = cargar_movimientos()
    todos.append(movimiento)
    guardar_movimientos(todos)

    # Sync Excel automático
    movimientos_mes = [m for m in todos if m.get("mes") == mes]
    resumen = calcular_resumen(movimientos_mes)
    excel_export.sincronizar(movimientos_mes, resumen, mes)

    return {"ok": True, "movimiento": movimiento, "mensaje": resultado.mensaje_respuesta}


@app.get("/api/movimientos")
async def listar_movimientos(mes: str = None, tipo: str = None):
    if mes is None:
        mes = mes_actual()
    movimientos = cargar_movimientos()
    filtrados = [m for m in movimientos if m.get("mes") == mes]
    if tipo:
        filtrados = [m for m in filtrados if m.get("tipo") == tipo]
    filtrados.sort(key=lambda m: m.get("timestamp", ""), reverse=True)
    return filtrados


@app.get("/api/resumen")
async def resumen(mes: str = None):
    if mes is None:
        mes = mes_actual()
    movimientos = [m for m in cargar_movimientos() if m.get("mes") == mes]
    data = calcular_resumen(movimientos)
    data["mes"] = mes
    return data


@app.delete("/api/movimiento/{mov_id}")
async def eliminar_movimiento(mov_id: str):
    todos = cargar_movimientos()
    original_len = len(todos)
    todos = [m for m in todos if m.get("id") != mov_id]
    if len(todos) == original_len:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    guardar_movimientos(todos)

    # Sync Excel automático
    mes = mes_actual()
    movimientos_mes = [m for m in todos if m.get("mes") == mes]
    resumen = calcular_resumen(movimientos_mes)
    excel_export.sincronizar(movimientos_mes, resumen, mes)

    return {"ok": True, "mensaje": "Movimiento eliminado"}


@app.get("/api/exportar")
async def exportar(mes: str = None):
    if mes is None:
        mes = mes_actual()
    ruta = BASE_DIR / "data" / f"CajaMagica_{mes}.xlsx"

    if not ruta.exists():
        movimientos = [m for m in cargar_movimientos() if m.get("mes") == mes]
        resumen = calcular_resumen(movimientos)
        ruta = excel_export.sincronizar(movimientos, resumen, mes)

    return FileResponse(
        path=str(ruta),
        filename=f"CajaMagica_{mes}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="CajaMagica_{mes}.xlsx"'},
    )


@app.get("/api/config")
async def get_config():
    return {"tasa_cop_usd": TASA_COP_USD, "caja_minima_cop": CAJA_MINIMA_COP}


@app.post("/api/config")
async def update_config(config: ConfigUpdate):
    global TASA_COP_USD, CAJA_MINIMA_COP
    if config.tasa_cop_usd is not None:
        TASA_COP_USD = config.tasa_cop_usd
    if config.caja_minima_cop is not None:
        CAJA_MINIMA_COP = config.caja_minima_cop
    return {"tasa_cop_usd": TASA_COP_USD, "caja_minima_cop": CAJA_MINIMA_COP}


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "mes_actual": mes_actual()}


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
