from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
from supabase import create_client
from datetime import date
import os

app = FastAPI()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

COMISION_TUU = 0.0237  # 2.37%

sesiones = {}

PASOS = ["efectivo", "transferencia", "debito_credito", "numero_ventas"]

PREGUNTAS = {
    "efectivo":       "¿Cuánto recibiste en *efectivo* hoy? (ej: 25000)",
    "transferencia":  "¿Cuánto por *transferencia*? (ej: 48000)",
    "debito_credito": "¿Cuánto por *débito/crédito*? (ej: 67000)",
    "numero_ventas":  "¿Cuántas *ventas* hiciste en total? (ej: 34)",
}


def guardar_cierre(numero, datos):
    efectivo      = datos["efectivo"]
    transferencia = datos["transferencia"]
    debito        = datos["debito_credito"]
    num_ventas    = datos["numero_ventas"]

    venta_total   = efectivo + transferencia + debito
    comision      = round(venta_total * COMISION_TUU)
    venta_neta    = venta_total - comision

    supabase.table("cierres_diarios").insert({
        "fecha":          str(date.today()),
        "efectivo":       efectivo,
        "transferencia":  transferencia,
        "debito_credito": debito,
        "venta_total":    venta_total,
        "comision_tuu":   comision,
        "venta_neta":     venta_neta,
        "numero_ventas":  num_ventas,
        "telefono":       numero,
    }).execute()

    return venta_total, comision, venta_neta


def formatear_pesos(n):
    return f"${n:,.0f}".replace(",", ".")


@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(Body: str = Form(...), From: str = Form(...)):
    texto  = Body.strip().lower()
    numero = From.strip()

    if texto == "cierre":
        sesiones[numero] = {"paso": 0, "datos": {}}
        primer_paso = PASOS[0]
        return f"Hola 👋 Vamos con el cierre de hoy.\n\n{PREGUNTAS[primer_paso]}"

    if numero not in sesiones:
        return "Escribe *cierre* para registrar las ventas del día. 🍦"

    sesion = sesiones[numero]
    paso_actual = PASOS[sesion["paso"]]

    texto_limpio = texto.replace(".", "").replace(",", "").replace("$", "").strip()
    if not texto_limpio.isdigit():
        return f"Por favor ingresa solo el número, sin letras ni símbolos.\n\n{PREGUNTAS[paso_actual]}"

    sesion["datos"][paso_actual] = int(texto_limpio)
    sesion["paso"] += 1

    if sesion["paso"] < len(PASOS):
        siguiente = PASOS[sesion["paso"]]
        return PREGUNTAS[siguiente]

    venta_total, comision, venta_neta = guardar_cierre(numero, sesion["datos"])
    del sesiones[numero]

    return (
        f"✅ *Cierre guardado*\n\n"
        f"💵 Efectivo:       {formatear_pesos(sesion['datos']['efectivo'])}\n"
        f"📲 Transferencia:  {formatear_pesos(sesion['datos']['transferencia'])}\n"
        f"💳 Débito/Crédito: {formatear_pesos(sesion['datos']['debito_credito'])}\n"
        f"🧾 Ventas:         {sesion['datos']['numero_ventas']}\n"
        f"──────────────────\n"
        f"📊 Venta total:    {formatear_pesos(venta_total)}\n"
        f"📉 Comisión TUU:   {formatear_pesos(comision)}\n"
        f"✨ Venta neta:     {formatear_pesos(venta_neta)}\n\n"
        f"Buenas noches 🍦"
    )
