from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
from supabase import create_client
from datetime import date
import os

app = FastAPI()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Estado en memoria por número de teléfono
# { numero: { "paso": 0, "productos": [...], "ventas": {} } }
sesiones = {}

CHUNK_SIZE = 8  # productos por mensaje


def get_productos():
    res = supabase.table("productos").select("nombre").order("nombre").execute()
    return [r["nombre"] for r in res.data]


def guardar_cierre(numero, ventas):
    hoy = str(date.today())
    filas = [
        {
            "fecha": hoy,
            "producto_nombre": producto,
            "cantidad_vendida": int(datos["vendida"]),
            "cantidad_sobrante": int(datos["sobrante"]),
            "telefono": numero,
        }
        for producto, datos in ventas.items()
    ]
    supabase.table("cierres_diarios").insert(filas).execute()


def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def construir_pregunta(productos_chunk, numero_grupo, total_grupos):
    lineas = "\n".join(
        [f"{i+1}. {p}" for i, p in enumerate(productos_chunk)]
    )
    return (
        f"Grupo {numero_grupo}/{total_grupos} — responde con los *vendidos* separados por coma:\n\n"
        f"{lineas}\n\n"
        f"Ej: 12,5,0,3,8,0,2,1"
    )


@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(Body: str = Form(...), From: str = Form(...)):
    texto = Body.strip().lower()
    numero = From.strip()

    # --- INICIO ---
    if texto == "cierre":
        productos = get_productos()
        chunks = list(chunk_list(productos, CHUNK_SIZE))
        sesiones[numero] = {
            "paso": 0,
            "chunks": chunks,
            "productos": productos,
            "ventas": {},
            "esperando": "vendida",
        }
        primera = construir_pregunta(chunks[0], 1, len(chunks))
        return f"Hola 👋 Vamos con el cierre de hoy.\n\n{primera}"

    # --- FUERA DE SESIÓN ---
    if numero not in sesiones:
        return "Escribe *cierre* para registrar las ventas del día."

    sesion = sesiones[numero]
    paso = sesion["paso"]
    chunks = sesion["chunks"]
    chunk_actual = chunks[paso]
    esperando = sesion["esperando"]

    # --- PARSEAR RESPUESTA ---
    try:
        valores = [v.strip() for v in texto.split(",")]
        assert len(valores) == len(chunk_actual)
        assert all(v.isdigit() for v in valores)
    except Exception:
        return (
            f"Responde con {len(chunk_actual)} números separados por coma.\n"
            f"Ej: 12,5,0,3,8,0,2,1"
        )

    # --- GUARDAR VALORES ---
    for i, producto in enumerate(chunk_actual):
        if producto not in sesion["ventas"]:
            sesion["ventas"][producto] = {}
        sesion["ventas"][producto][esperando] = valores[i]

    # --- SIGUIENTE PASO ---
    if esperando == "vendida":
        # Preguntar sobrantes del mismo grupo
        sesion["esperando"] = "sobrante"
        lineas = "\n".join([f"{i+1}. {p}" for i, p in enumerate(chunk_actual)])
        return (
            f"Ahora los *sobrantes* del mismo grupo:\n\n{lineas}\n\n"
            f"Ej: 0,2,0,1,0,3,0,0"
        )
    else:
        # Avanzar al siguiente grupo
        sesion["esperando"] = "vendida"
        siguiente_paso = paso + 1
        sesion["paso"] = siguiente_paso

        if siguiente_paso < len(chunks):
            prox = construir_pregunta(chunks[siguiente_paso], siguiente_paso + 1, len(chunks))
            return f"Perfecto ✓\n\n{prox}"
        else:
            # Fin — guardar todo
            guardar_cierre(numero, sesion["ventas"])
            del sesiones[numero]
            total_vendido = sum(
                int(v["vendida"]) for v in sesion["ventas"].values()
            )
            return (
                f"✅ Cierre guardado.\n"
                f"Total unidades vendidas hoy: *{total_vendido}*\n\n"
                f"Buenas noches 🍦"
            )
