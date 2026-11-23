import os
from typing import Any, Dict
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
import requests

app = FastAPI(title="Farmacia WhatsApp Bot")

# Memoria temporal del inventario sincronizado desde la PC local
INVENTARIO: Dict[str, Dict[str, Any]] = {}
TASA_BS: float = 0.0

API_TOKEN_SYNC = os.getenv("API_TOKEN_SYNC", "")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "farmacia_verify_token")


def formatear_numero(valor: Any, decimales: int = 2) -> str:
    try:
        num = float(valor)
        return f"{num:,.{decimales}f}"
    except (TypeError, ValueError):
        return str(valor)


def enviar_mensaje_whatsapp(to: str, texto: str) -> None:
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        return
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": texto},
    }
    try:
        requests.post(url, headers=headers, json=payload, timeout=15)
    except Exception:
        pass


def buscar_productos(consulta: str) -> list[Dict[str, Any]]:
    termino = consulta.strip().lower()
    if not termino:
        return []
    coincidencias = []
    for item in INVENTARIO.values():
        codigo = str(item.get("codigo", "")).lower()
        descripcion = str(item.get("descripcion", "")).lower()
        if termino == codigo or termino in descripcion:
            coincidencias.append(item)
    return coincidencias[:5]


def construir_respuesta_inventario(consulta: str) -> str:
    if not INVENTARIO:
        return (
            "El inventario de la farmacia aún se está sincronizando. "
            "Por favor intenta de nuevo en unos minutos o escribe *asesor* para hablar con nuestro equipo."
        )

    resultados = buscar_productos(consulta)
    if not resultados:
        return (
            f"No encontré disponibilidad para *{consulta}* en este momento. "
            "Verifica el nombre del producto, o escribe *asesor* para que te asesoren."
        )

    lineas = [f"Resultados para *{consulta}*:\n"]
    for prod in resultados:
        codigo = prod.get("codigo", "-")
        desc = prod.get("descripcion", "Producto")
        stock = prod.get("stock", 0)
        precio_usd = prod.get("precio_usd")
        precio_cop = prod.get("precio_cop")

        try:
            usd_num = float(precio_usd) if precio_usd is not None else None
        except (TypeError, ValueError):
            usd_num = None

        try:
            cop_num = float(precio_cop) if precio_cop is not None else None
        except (TypeError, ValueError):
            cop_num = None

        bs_texto = "No disponible"
        if usd_num is not None and TASA_BS > 0:
            bs_texto = f"Bs. {formatear_numero(usd_num * TASA_BS, 2)}"

        usd_texto = f"${formatear_numero(usd_num, 2)}" if usd_num is not None else "No disponible"
        cop_texto = f"COP {formatear_numero(cop_num, 0)}" if cop_num is not None else "No disponible"

        lineas.append(
            f"• *{desc}* (Cód: {codigo})\n"
            f"  Stock: {stock} | USD: {usd_texto} | {bs_texto} | {cop_texto}"
        )

    lineas.append("\nSi necesitas ayuda adicional, escribe *asesor* y te comunicamos con el personal.")
    return "\n".join(lineas)


@app.get("/")
def inicio():
    return {
        "estado": "activo",
        "productos_cargados": len(INVENTARIO),
        "tasa_bs": TASA_BS,
    }


@app.post("/api/sincronizar")
async def sincronizar_inventario(
    request: Request,
    x_api_token: str | None = Header(default=None),
):
    global INVENTARIO, TASA_BS

    if API_TOKEN_SYNC and x_api_token != API_TOKEN_SYNC:
        raise HTTPException(status_code=401, detail="Token no autorizado")

    datos = await request.json()
    productos = datos.get("productos", [])
    tasa = datos.get("tasa_bs", 0)

    try:
        TASA_BS = float(tasa)
    except (TypeError, ValueError):
        TASA_BS = 0.0

    nuevo_inventario: Dict[str, Dict[str, Any]] = {}
    for prod in productos:
        codigo = str(prod.get("codigo", "")).strip()
        descripcion = str(prod.get("descripcion", "")).strip()
        clave = codigo if codigo else descripcion.lower()
        if clave:
            nuevo_inventario[clave] = {
                "codigo": codigo,
                "descripcion": descripcion,
                "stock": prod.get("stock", 0),
                "precio_cop": prod.get("precio_cop"),
                "precio_usd": prod.get("precio_usd"),
            }

    INVENTARIO = nuevo_inventario
    return {
        "ok": True,
        "total_productos": len(INVENTARIO),
        "tasa_bs": TASA_BS,
    }


@app.get("/webhook")
def verificar_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN and hub_challenge:
        return PlainTextResponse(content=hub_challenge, status_code=200)
    raise HTTPException(status_code=403, detail="Verificación fallida")


@app.post("/webhook")
async def recibir_whatsapp(request: Request):
    cuerpo = await request.json()
    entries = cuerpo.get("entry", [])

    for entry in entries:
        for change in entry.get("changes", []):
            valor = change.get("value", {})
            for mensaje in valor.get("messages", []):
                remitente = mensaje.get("from")
                tipo = mensaje.get("type")

                if not remitente:
                    continue

                if tipo == "text":
                    texto_usuario = mensaje.get("text", {}).get("body", "").strip()
                    if texto_usuario.lower() in {"asesor", "humano", "persona", "ayuda"}:
                        enviar_mensaje_whatsapp(
                            remitente,
                            "Perfecto,he avisado a nuestro equipo para que te atienda.",
                        )
                    else:
                        respuesta = construir_respuesta_inventario(texto_usuario)
                        enviar_mensaje_whatsapp(remitente, respuesta)
                else:
                    # Audios, imágenes, notas de voz o documentos pasan a atención humana
                    enviar_mensaje_whatsapp(
                        remitente,
                        "Recibimos tu mensaje, el personal atendera tu requerimiento en cualquier momento.",
                    )

    return {"status": "recibido"}
