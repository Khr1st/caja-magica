"""Motor NLP para clasificación de movimientos financieros — sin dependencias externas."""

import re
from dataclasses import dataclass
from typing import Optional

TASA_COP_USD = 4200


@dataclass
class ResultadoClasificacion:
    tipo: str  # ingreso|egreso|ahorro|proyeccion
    categoria: str
    descripcion: str
    monto_cop: int
    monto_original: float
    moneda: str  # COP|USD
    es_proyeccion: bool
    mensaje_respuesta: str
    confianza: str  # alta|media|baja
    error: Optional[str] = None


# --- Extracción de monto ---

def _extraer_monto(texto: str) -> tuple[float, str, int]:
    """Devuelve (monto_original, moneda, monto_cop). Raises ValueError si no hay monto."""
    t = texto.lower().replace(",", ".")

    # 1. USD con sufijo
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:usd|dólares|dolares|dolar|dólar)', t)
    if m:
        val = float(m.group(1))
        return val, "USD", round(val * TASA_COP_USD)

    # 2. USD con prefijo $
    m = re.search(r'\$\s*(\d+(?:\.\d+)?)\s*(?:usd|dolares|dólares)', t)
    if m:
        val = float(m.group(1))
        return val, "USD", round(val * TASA_COP_USD)

    # 3. COP millones
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:millones?|millon)', t)
    if m:
        val = float(m.group(1)) * 1_000_000
        return val, "COP", round(val)

    # 4. COP miles k/mil
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:k|mil)\b', t)
    if m:
        val = float(m.group(1)) * 1_000
        return val, "COP", round(val)

    # 5. COP formato colombiano $900.000
    m = re.search(r'\$\s*(\d{1,3}(?:\.\d{3})+)', t)
    if m:
        val = float(m.group(1).replace(".", ""))
        return val, "COP", round(val)

    # 6. COP plano con pesos
    m = re.search(r'(\d{1,3}(?:\.\d{3})+)\s*(?:pesos?|cop)?', t)
    if m:
        val = float(m.group(1).replace(".", ""))
        return val, "COP", round(val)

    # 7. COP número largo sin sufijo
    m = re.search(r'\b(\d{4,})\b', t)
    if m:
        val = float(m.group(1))
        return val, "COP", round(val)

    raise ValueError("sin monto")


# --- Reglas de clasificación ---

REGLAS = [
    {
        "nombre": "ahorro_ibkr",
        "pattern": r'ibkr|etf|s&p|qqqm|iaum|inversión a largo|mercado de valores|acciones',
        "tipo": "ahorro",
        "categoria": "ibkr",
        "mensaje": "Registrado como ahorro IBKR. No toca la caja operativa — buen hábito.",
    },
    {
        "nombre": "ahorro_nu",
        "pattern": r'\bnu\b|cajita|cajitas|fondo nu|ahorro nu|nubank',
        "tipo": "ahorro",
        "categoria": "nu",
        "mensaje": "Anotado en cajitas Nu. Fondo de emergencia creciendo.",
    },
    {
        "nombre": "proyeccion_consultoria",
        "pattern": r'voy a facturar|espero cobrar|espero facturar|próximo cliente|estimado de|proyecto pendiente de pago|cliente me va a pagar',
        "tipo": "proyeccion",
        "categoria": "consultoria",
        "mensaje": "Proyección de consultoría anotada. Actualiza cuando el pago llegue.",
    },
    {
        "nombre": "proyeccion_gumroad",
        "pattern": r'voy a vender|espero vender|proyección gumroad|plantilla pendiente',
        "tipo": "proyeccion",
        "categoria": "gumroad",
        "mensaje": "Proyección de venta digital anotada.",
    },
    {
        "nombre": "proyeccion_general",
        "pattern": r'voy a|espero recibir|próximo mes|siguiente mes',
        "tipo": "proyeccion",
        "categoria": "otro",
        "mensaje": "Proyección registrada. Confirma cuando sea real.",
    },
    {
        "nombre": "ingreso_mesada",
        "pattern": r'papá|mamá|papa|mama|padres|familia|mesada|mandaron|pasaron|transfirieron|depositaron|me dieron|me mandaron',
        "tipo": "ingreso",
        "categoria": "mesada",
        "mensaje": "Ingreso familiar registrado.",
    },
    {
        "nombre": "ingreso_consultoria",
        "pattern": r'facturé|cobré|cliente pagó|consultoría|cfd|fea|simulación|proyecto entregado|upwork|workana',
        "tipo": "ingreso",
        "categoria": "consultoria",
        "mensaje": "Ingreso de consultoría registrado. Vas construyendo el historial de cliente.",
    },
    {
        "nombre": "ingreso_gumroad",
        "pattern": r'gumroad|plantilla|vendí|venta digital|producto digital|template',
        "tipo": "ingreso",
        "categoria": "gumroad",
        "mensaje": "Venta digital registrada. Cada venta es proof of concept del modelo.",
    },
    {
        "nombre": "ingreso_scooters",
        "pattern": r'scooter|publicidad campus|anunciante|uis publicidad',
        "tipo": "ingreso",
        "categoria": "scooters",
        "mensaje": "Ingreso de scooters / publicidad registrado.",
    },
    {
        "nombre": "egreso_tarjeta",
        "pattern": r'tarjeta|bancolombia|\btc\b|crédito|pago de tarjeta',
        "tipo": "egreso",
        "categoria": "tc_pago",
        "mensaje": "Pago de tarjeta registrado. Bien hecho pagarlo completo — así se construye historial sin pagar intereses.",
    },
    {
        "nombre": "egreso_alimentacion",
        "pattern": r'almuerzo|comida|mercado|restaurante|desayuno|cena|snack|domicilio|rappi|café|tinto',
        "tipo": "egreso",
        "categoria": "alimentacion",
        "mensaje": "Gasto de alimentación registrado.",
    },
    {
        "nombre": "egreso_transporte",
        "pattern": r'bus|transporte|uber|taxi|metro|gasolina|parqueadero',
        "tipo": "egreso",
        "categoria": "transporte",
        "mensaje": "Gasto de transporte registrado.",
    },
    {
        "nombre": "egreso_general",
        "pattern": r'gasté|pagué|compré|gasto|egreso|costo',
        "tipo": "egreso",
        "categoria": "otro",
        "mensaje": "Egreso registrado.",
    },
]


def clasificar(texto: str) -> ResultadoClasificacion:
    """Clasifica un texto en lenguaje natural en un movimiento financiero."""
    # Extraer monto
    try:
        monto_original, moneda, monto_cop = _extraer_monto(texto)
    except ValueError:
        return ResultadoClasificacion(
            tipo="",
            categoria="",
            descripcion="",
            monto_cop=0,
            monto_original=0,
            moneda="COP",
            es_proyeccion=False,
            mensaje_respuesta="",
            confianza="baja",
            error="No encontré el monto. Ejemplo: 'mis papás me pasaron 900k' o 'consultoría $25 USD'.",
        )

    texto_lower = texto.lower()

    # Evaluar reglas en orden
    for regla in REGLAS:
        if re.search(regla["pattern"], texto_lower):
            es_proy = regla["tipo"] == "proyeccion"
            return ResultadoClasificacion(
                tipo=regla["tipo"],
                categoria=regla["categoria"],
                descripcion=texto.strip(),
                monto_cop=monto_cop,
                monto_original=monto_original,
                moneda=moneda,
                es_proyeccion=es_proy,
                mensaje_respuesta=regla["mensaje"],
                confianza="alta",
            )

    # Fallback con monto
    return ResultadoClasificacion(
        tipo="egreso",
        categoria="otro",
        descripcion=texto.strip(),
        monto_cop=monto_cop,
        monto_original=monto_original,
        moneda=moneda,
        es_proyeccion=False,
        mensaje_respuesta="Registré el monto pero no pude clasificar bien. ¿Es un ingreso o egreso? Intenta ser más específico.",
        confianza="baja",
    )
