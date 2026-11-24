import os
import re
import unicodedata
import requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

app = FastAPI()

MENSAJE_BIENVENIDA = (
    "¡Hola! Bienvenido a *Farmacia Unitas Norte* (RIF: *J-298120886*).\n"
    "Escríbeme el nombre del medicamento o producto que deseas consultar.\n"
    "Si necesitas atención personalizada, escribe *asesor* y nuestro equipo te atendera."
)

MENSAJE_DESPEDIDA = (
    "¡Gracias por preferir a *Farmacia Unitas Norte* (RIF: *J-298120886*)! "
    "Estamos a tu orden. Si deseas consultar otro producto, solo escríbeme su nombre, "
    "o escribe *asesor* y seras atendido en unos momentos por nuestro personal. ¡Que tengas un excelente día!"
)

MENSAJE_ASESOR = (
    "En un momento te comunicaremos con un asesor de *Farmacia Unitas Norte* "
    "(RIF: *J-298120886*) para ayudarte."
)

INVENTARIO = []
TASA_BS = 0.0


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().lower()


def procesar_mensaje_usuario(texto: str):
    texto_limpio = (texto or "").strip()
    minuscula = _normalizar(texto_limpio)

    saludos = (
        "buenos dias", "buen dia", "buenas tardes", "buena tarde",
        "buenas noches", "buena noche", "que tal", "buenas", "saludos", "hola"
    )
    despedidas_exactas = {
        "gracias", "muchas gracias", "adios",
        "hasta luego", "chao", "bye", "listo gracias"
    }

    sin_signos = re.sub(r"[^\w\s,;\n]", " ", minuscula)
    sin_signos = re.sub(r"[ \t]+", " ", sin_signos).strip()

    if not sin_signos:
        return MENSAJE_BIENVENIDA, None

    sin_comas = re.sub(r"[,;\n]+", " ", sin_signos)
    sin_comas = re.sub(r"\s+", " ", sin_comas).strip()

    if sin_comas in despedidas_exactas:
        return MENSAJE_DESPEDIDA, None

    if sin_comas in ("asesor", "humano", "agente", "persona"):
        return MENSAJE_ASESOR, None

    frase = sin_signos
    cambio = True
    while cambio and frase:
        cambio = False
        frase_limpia_saludo = re.sub(r"[,;\n]+", " ", frase).strip()
        frase_limpia_saludo = re.sub(r"\s+", " ", frase_limpia_saludo)
        if frase_limpia_saludo in saludos:
            return MENSAJE_BIENVENIDA, None
        for s in saludos:
            if re.match(rf"^{re.escape(s)}(?:[\s,;]+|$)", frase):
                frase = re.sub(rf"^{re.escape(s)}[\s,;]*", "", frase, count=1).strip()
                cambio = True
                break

    relleno = {
        "tienen", "tiene", "tenes", "tenés", "hay", "habra", "habrá",
        "disponible", "disponibles", "disponibilidad",
        "busco", "buscar", "buscando", "andaba", "estoy", "ando",
        "necesito", "necesita", "quiero", "quisiera", "deseo",
        "saber", "si", "me", "puedes", "podrias", "podrías", "puede", "podria", "podría",
        "decir", "decirme", "consultar", "averiguar",
        "precio", "precios", "cuanto", "cuánto", "cuesta", "cuestan", "vale", "valen",
        "en", "existencia", "existencias", "stock",
        "de", "del", "la", "el", "los", "las",
        "un", "una", "unos", "unas",
        "por", "favor", "porfa", "plis",
        "te", "se", "para", "con", "algun", "algún", "alguna", "algunos", "algunas"
    }

    segmentos_crudos = re.split(r"[,;\n]+|\s+(?:y|e)\s+", frase)
    terminos = []

    for seg in segmentos_crudos:
        palabras = [p for p in seg.split() if p not in relleno]
        limpio = " ".join(palabras).strip()
        if limpio and limpio not in saludos:
            terminos.append(limpio)

    if not terminos:
        frase_sin_relleno = " ".join(p for p in sin_comas.split() if p not in relleno).strip()
        if not frase_sin_relleno or frase_sin_relleno in saludos:
            return MENSAJE_BIENVENIDA, None
        return None, [frase_sin_relleno]

    return None, terminos


def _a_numero(valor, por_defecto=0.0) -> float:
    if valor is None:
        return por_defecto
    if isinstance(valor, (int, float)):
        return float(valor)
    limpio = re.sub(r"[^\d.,-]", "", str(valor)).strip()
    if not limpio:
        return por_defecto
    if "," in limpio and "." in limpio:
        if limpio.rfind(",") > limpio.rfind("."):
            limpio = limpio.replace(".", "").replace(",", ".")
        else:
            limpio = limpio.replace(",", "")
    elif "," in limpio:
        partes = limpio.split(",")
        if len(partes[-1]) == 2:
            limpio = limpio.replace(",", ".")
        else:
            limpio = limpio.replace(",", "")
    try:
        return float(limpio)
    except ValueError:
        return por_defecto


def buscar_productos(termino: str, limite: int = 8) -> list:
    termino_norm = _normalizar(termino)
    if not termino_norm or not INVENTARIO:
        return []

    palabras = [p for p in termino_norm.split() if len(p) >= 2]
    if not palabras:
        palabras = [termino_norm]

    coincidencias = []
    for item in INVENTARIO:
        codigo = str(item.get("codigo") or item.get("code") or "").strip()
        desc = str(
            item.get("descripcion")
            or item.get("description")
            or item.get("nombre")
            or ""
        ).strip()
        desc_norm = _normalizar(desc)
        codigo_norm = _normalizar(codigo)

        if all(pal in desc_norm or pal in codigo_norm for pal in palabras):
            usd = _a_numero(item.get("usd") if item.get("usd") is not None else item.get("precio_usd"))
            cop = _a_numero(item.get("cop") if item.get("cop") is not None else item.get("precio_cop"))
            bs = _a_numero(item.get("bs") if item.get("bs") is not None else item.get("precio_bs"))
            if bs <= 0 and usd > 0 and TASA_BS > 0:
                bs = round(usd * TASA_BS, 2)

            coincidencias.append({
                "codigo": codigo or "N/A",
                "descripcion": desc or "Producto",
                "usd": usd,
                "bs": bs,
                "cop": cop,
            })
            if len(coincidencias) >= limite:
                break

    return coincidencias


def formatear_respuesta_productos(termino: str, productos: list) -> str:
    if not productos:
        return (
            f"No encontré resultados para *{termino}* en este momento. "
            f"Verifica el nombre del producto o escribe *asesor* y pronto seras atendido por nuestro personal.\n\n"
            f"{MENSAJE_DESPEDIDA}"
        )

    lineas = [
        f"{MENSAJE_BIENVENIDA}\n",
        f"Resultados para *{termino}*:\n",
    ]
    for p in productos[:5]:
        usd = float(p.get("usd") or 0.0)
        bs = float(p.get("bs") or 0.0)
        cop = float(p.get("cop") or 0.0)
        desc = str(p.get("descripcion") or "Producto")
        codigo = str(p.get("codigo") or "N/A")
        lineas.append(
            f"• *{desc}* (Cód: {codigo})\n"
            f"  USD: ${usd:.2f} | Bs. {bs:,.2f} | COP {cop:,.0f}"
        )

    lineas.append(f"\n{MENSAJE_DESPEDIDA}")
    texto_final = "\n".join(lineas)
    return texto_final[:3800]


def responder_consulta_productos(termino_o_lista) -> str:
    terminos = termino_o_lista if isinstance(termino_o_lista, list) else [termino_o_lista]

    if len(terminos) == 1:
        termino = terminos[0]
        encontrados = buscar_productos(termino)
        return formatear_respuesta_productos(termino, encontrados)

    bloques = [f"{MENSAJE_BIENVENIDA}\n"]
    for term in terminos:
        encontrados = buscar_productos(term)
        bloques.append(f"*Consulta: {term}*")
        if not encontrados:
            bloques.append(f"No encontré resultados para *{term}* en este momento.\n")
        else:
            for p in encontrados[:4]:
                usd = float(p.get("usd") or 0.0)
                bs = float(p.get("bs") or 0.0)
                cop = float(p.get("cop") or 0.0)
                desc = str(p.get("descripcion") or "Producto")
                codigo = str(p.get("codigo") or "N/A")
                bloques.append(
                    f"• *{desc}* (Cód: {codigo})\n"
                    f"  USD: ${usd:.2f} | Bs. {bs:,.2f} | COP {cop:,.0f}"
                )
            bloques.append("")

    bloques.append(MENSAJE_DESPEDIDA)
    return "\n".join(bloques)[:3800]


def enviar_mensaje_whatsapp(telefono_destino: str, mensaje: str):
    token = (os.getenv("WHATSAPP_TOKEN") or "").strip()
    phone_number_id = (os.getenv("PHONE_NUMBER_ID") or "").strip()
    if not token or not phone_number_id:
        print("[WARN] Faltan WHATSAPP_TOKEN o PHONE_NUMBER_ID en variables de entorno.")
        return

    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono_destino,
        "type": "text",
        "text": {"body": mensaje},
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        if resp.status_code >= 400:
            print(f"[ERROR] WhatsApp API {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[ERROR] Enviando mensaje a WhatsApp: {e}")


@app.get("/")
def inicio():
    return {
        "status": "ok",
        "servicio": "Farmacia Unitas Norte Bot",
        "productos_cargados": len(INVENTARIO),
        "tasa_bs": TASA_BS,
    }


@app.post("/api/sincronizar")
async def sincronizar_inventario(request: Request):
    api_token_esperado = (os.getenv("API_TOKEN_SYNC") or "").strip()
    if api_token_esperado:
        auth_header = (request.headers.get("Authorization") or "").replace("Bearer ", "").strip()
        token_header = (request.headers.get("x-api-token") or "").strip()
        if api_token_esperado not in (auth_header, token_header):
            return {"ok": False, "error": "No autorizado"}

    try:
        data = await request.json()
    except Exception:
        data = {}

    global INVENTARIO, TASA_BS

    if isinstance(data, list):
        INVENTARIO = data
    elif isinstance(data, dict):
        productos = (
            data.get("productos")
            or data.get("inventario")
            or data.get("items")
            or data.get("data")
        )
        if isinstance(productos, list):
            INVENTARIO = productos

        tasa = (
            data.get("tasa_bs")
            if data.get("tasa_bs") is not None
            else data.get("tasa")
        )
        if tasa is not None:
            nueva_tasa = _a_numero(tasa, por_defecto=TASA_BS)
            if nueva_tasa > 0:
                TASA_BS = nueva_tasa

    return {
        "ok": True,
        "total_productos": len(INVENTARIO),
        "tasa_bs": TASA_BS,
    }


@app.get("/webhook")
def verificar_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    verify_token_esperado = (os.getenv("VERIFY_TOKEN") or "").strip()

    if mode == "subscribe" and token and token == verify_token_esperado and challenge:
        return PlainTextResponse(content=challenge, status_code=200)
    return PlainTextResponse(content="Token invalido", status_code=403)


@app.post("/webhook")
async def recibir_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        return {"status": "ignored"}

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                remitente = msg.get("from")
                tipo = msg.get("type")

                if not remitente:
                    continue

                try:
                    if tipo == "text":
                        texto_usuario = (msg.get("text") or {}).get("body", "")
                        respuesta_directa, termino = procesar_mensaje_usuario(texto_usuario)

                        if respuesta_directa:
                            enviar_mensaje_whatsapp(remitente, respuesta_directa)
                        elif not INVENTARIO:
                            enviar_mensaje_whatsapp(
                                remitente,
                                "El inventario de la farmacia aún se está sincronizando. "
                                "Por favor intenta de nuevo en unos minutos o escribe *asesor* "
                                "para hablar con nuestro equipo."
                            )
                        else:
                            respuesta = responder_consulta_productos(termino)
                            enviar_mensaje_whatsapp(remitente, respuesta)
                    else:
                        enviar_mensaje_whatsapp(
                            remitente,
                            "Por el momento solo puedo leer mensajes de texto. "
                            "Escríbeme el nombre del producto que buscas o escribe *asesor* "
                            "para hablar con nuestro equipo."
                        )
                except Exception as e:
                    print(f"[ERROR] Procesando mensaje de {remitente}: {e}")
                    enviar_mensaje_whatsapp(
                        remitente,
                        "Tuve un inconveniente al consultar ese producto. "
                        "Por favor intenta escribiendo solo el nombre del medicamento o *asesor*."
                    )

    return {"status": "ok"}
