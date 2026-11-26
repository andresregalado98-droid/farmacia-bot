import base64
import os
import re
import time
import unicodedata
import requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

app = FastAPI()

MENSAJE_BIENVENIDA = (
    "¡Hola! Bienvenido a *Farmacia Unitas Norte* (RIF: *J-298120886*).\n"
    "Escríbeme el nombre del medicamento o producto que deseas consultar.\n"
    "• Si quieres orientación general sobre un malestar leve o cómo usar un producto sencillo, escribe *Unity* para hablar con nuestro asistente virtual.\n"
    "• Si necesitas atención personalizada, escribe *asesor* y nuestro equipo te atenderá."
)

MENSAJE_BIENVENIDA_PRODUCTO = (
    "¡Hola! Gracias por escribir a *Farmacia Unitas Norte* (RIF: *J-298120886*).\n"
)

MENSAJE_DESPEDIDA = (
    "¡Gracias por preferir a *Farmacia Unitas Norte* (RIF: *J-298120886*)! "
    "Estamos a tu orden. Si deseas consultar otro producto, solo escríbeme su nombre, "
    "escribe *Unity* para consultar a nuestro asistente virtual, "
    "o escribe *asesor* y serás atendido por nuestro personal. ¡Que tengas un excelente día!"
)

MENSAJE_ASESOR = (
    "En un momento te comunicaremos con un asesor de *Farmacia Unitas Norte* "
    "(RIF: *J-298120886*) para ayudarte."
)

MENSAJE_BIENVENIDA_UNITY = (
    "¡Hola! Soy *Unity*, el asistente virtual de orientación de *Farmacia Unitas Norte* (RIF: *J-298120886*).\n\n"
    "Puedo ayudarte con:\n"
    "• Orientación informativa general sobre malestares leves o síntomas comunes.\n"
    "• Información general de uso de medicamentos sencillos de venta libre.\n"
    "• Consulta de disponibilidad y precios en nuestro inventario.\n\n"
    "⚠️ *Normativa sanitaria (MPPS / Ley Orgánica de Drogas):* Los *estupefacientes*, *psicotrópicos*, *medicamentos controlados*, *antibióticos* y fármacos de prescripción médica deben ser indicados estrictamente por un *médico* y dispensados conforme a la normativa vigente.\n\n"
    "¿Qué malestar leve o producto sencillo deseas consultar?\n"
    "_(Escribe *salir* para volver al buscador de productos o *asesor* para hablar con nuestro equipo)_."
)

MENSAJE_SALIDA_UNITY = (
    "Has salido del modo asistente *Unity*. "
    "Ahora puedes escribir directamente el nombre del producto que deseas consultar o escribir *asesor*."
)

MENSAJE_BLOQUEO_CONTROLADOS = (
    "⚠️ *Restricción sanitaria (MPPS / Ley Orgánica de Drogas):*\n"
    "De acuerdo con la regulación farmacéutica vigente, *Unity* no puede recomendar, indicar ni dar pautas de uso o dosificación sobre *medicamentos controlados, estupefacientes, psicotrópicos ni antibióticos*.\n\n"
    "Estos medicamentos requieren evaluación e indicación estricta de un *médico* y el cumplimiento de los requisitos de prescripción/dispensación establecidos.\n"
    "Si deseas hablar con nuestro equipo de farmacia, escribe *asesor* (o escribe *salir* para volver al buscador)."
)

INVENTARIO = []
TASA_BS = 0.0
SESIONES_UNITY = {}
TIMEOUT_UNITY_SEGUNDOS = 20 * 60

PALABRAS_CONTROLADOS_Y_ANTIBIOTICOS = {
    # Categorías regulatorias y control
    "antibiotico", "antibioticos", "antimicrobiano", "antimicrobianos",
    "psicotropico", "psicotropicos", "estupefaciente", "estupefacientes",
    "controlado", "controlados", "recipe", "receta",
    # Estupefacientes / opioides / analgésicos controlados
    "morfina", "oxicodona", "fentanilo", "metadona", "buprenorfina", "tapentadol",
    "petidina", "meperidina", "hidromorfona", "codeina", "tramadol", "tramal",
    # Psicotrópicos: ansiolíticos, sedantes, hipnóticos, estimulantes, barbitúricos
    "alprazolam", "tafil", "clonazepam", "rivotril", "diazepam", "valium",
    "lorazepam", "ativan", "bromazepam", "lexotanil", "midazolam", "clobazam",
    "zolpidem", "stilnox", "zopiclona", "eszopiclona", "fenobarbital",
    "metilfenidato", "ritalin", "concerta", "lisdexanfetamina", "modafinilo",
    # Antidepresivos, antipsicóticos y anticonvulsivantes habituales bajo prescripción
    "sertralina", "fluoxetina", "escitalopram", "citalopram", "paroxetina",
    "venlafaxina", "desvenlafaxina", "duloxetina", "amitriptilina", "bupropion",
    "mirtazapina", "trazodona", "quetiapina", "risperidona", "olanzapina",
    "haloperidol", "aripiprazol", "clozapina", "carbamazepina", "valproato",
    "acido valproico", "levetiracetam", "lamotrigina", "fenitoina",
    "pregabalina", "gabapentina",
    # Antibióticos comunes
    "amoxicilina", "ampicilina", "azitromicina", "claritromicina", "eritromicina",
    "ciprofloxacina", "ciprofloxacino", "levofloxacina", "levofloxacino",
    "moxifloxacino", "norfloxacina", "cefalexina", "cefadroxilo", "cefixima",
    "ceftriaxona", "cefuroxima", "doxiciclina", "tetraciclina", "minociclina",
    "clindamicina", "metronidazol", "tinidazol", "secnidazol", "ornidazol",
    "trimetoprim", "sulfametoxazol", "bactrim", "bactron", "gentamicina",
    "amikacina", "penicilina", "sultamicilina", "unasyn", "augmentin",
    "nitrofurantoina", "fosfomicina", "meropenem", "vancomicina", "linezolid",
}


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().lower()


def _limpiar_sesiones_expiradas():
    ahora = time.time()
    expirados = [
        tel for tel, data in SESIONES_UNITY.items()
        if ahora - data.get("ultimo_uso", 0) > TIMEOUT_UNITY_SEGUNDOS
    ]
    for tel in expirados:
        SESIONES_UNITY.pop(tel, None)


def _unity_activo(remitente: str) -> bool:
    _limpiar_sesiones_expiradas()
    sesion = SESIONES_UNITY.get(remitente)
    if not sesion:
        return False
    sesion["ultimo_uso"] = time.time()
    return True


def _activar_unity(remitente: str):
    SESIONES_UNITY[remitente] = {
        "ultimo_uso": time.time(),
        "historial": [],
    }


def _desactivar_unity(remitente: str):
    SESIONES_UNITY.pop(remitente, None)


def _contiene_medicamento_restringido(texto: str) -> bool:
    norm = _normalizar(texto)
    norm_plano = re.sub(r"[^\w\s]", " ", norm)
    norm_plano = re.sub(r"\s+", " ", norm_plano).strip()
    palabras = set(norm_plano.split())
    if palabras.intersection(PALABRAS_CONTROLADOS_Y_ANTIBIOTICOS):
        return True
    for frase in PALABRAS_CONTROLADOS_Y_ANTIBIOTICOS:
        if " " in frase and frase in norm_plano:
            return True
    return False


def procesar_mensaje_usuario(texto: str):
    texto_limpio = (texto or "").strip()
    if not texto_limpio:
        return MENSAJE_BIENVENIDA, None

    minuscula = _normalizar(texto_limpio)

    saludos = (
        "buenos dias", "buen dia", "buenas tardes", "buena tarde",
        "buenas noches", "buena noche", "que tal", "buenas", "saludos", "hola"
    )
    despedidas_exactas = {
        "gracias", "muchas gracias", "adios",
        "hasta luego", "chao", "bye", "listo gracias"
    }

    texto_plano = re.sub(r"[^\w\s]", " ", minuscula)
    texto_plano = re.sub(r"\s+", " ", texto_plano).strip()

    if not texto_plano:
        return MENSAJE_BIENVENIDA, None

    if texto_plano in despedidas_exactas:
        return MENSAJE_DESPEDIDA, None

    if texto_plano in ("asesor", "humano", "agente", "persona"):
        return MENSAJE_ASESOR, None

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
        "te", "se", "para", "con", "algun", "algún", "alguna", "algunos", "algunas",
        "y", "e"
    }

    terminos = []
    for linea_cruda in texto_limpio.splitlines():
        linea_norm = _normalizar(linea_cruda)
        if not linea_norm:
            continue

        linea_norm = re.sub(r"(\d+)([a-z]+)", r"\1 \2", linea_norm)
        linea_norm = re.sub(r"([a-z]+)(\d+)", r"\1 \2", linea_norm)

        linea_limpia = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", " ", linea_norm)
        linea_limpia = re.sub(r"[^\w\s,;]", " ", linea_limpia)
        linea_limpia = re.sub(r"\s+", " ", linea_limpia).strip()

        if not linea_limpia:
            continue

        cambio = True
        while cambio and linea_limpia:
            cambio = False
            if linea_limpia in saludos:
                linea_limpia = ""
                break
            for s in saludos:
                if re.match(rf"^{re.escape(s)}(?:[\s,;]+|$)", linea_limpia):
                    linea_limpia = re.sub(rf"^{re.escape(s)}[\s,;]*", "", linea_limpia, count=1).strip()
                    cambio = True
                    break

        if not linea_limpia:
            continue

        partes = re.split(r"[,;]+|\s+(?:y|e)\s+", linea_limpia)
        for parte in partes:
            palabras = [p for p in parte.split() if p not in relleno]
            termino = " ".join(palabras).strip()
            if termino and termino not in saludos and termino not in terminos:
                terminos.append(termino)

    if not terminos:
        if texto_plano in saludos:
            return MENSAJE_BIENVENIDA, None
        palabras_sueltas = [p for p in texto_plano.split() if p not in relleno and p not in saludos]
        if not palabras_sueltas:
            return MENSAJE_BIENVENIDA, None
        return None, [" ".join(palabras_sueltas)]

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
    termino_norm = re.sub(r"(\d+)([a-z]+)", r"\1 \2", termino_norm)
    termino_norm = re.sub(r"([a-z]+)(\d+)", r"\1 \2", termino_norm)
    termino_norm = re.sub(r"\s+", " ", termino_norm).strip()

    if not termino_norm or not INVENTARIO:
        return []

    ignorar = {
        "para", "uso", "de", "del", "la", "el", "los", "las",
        "adulto", "adultos", "adulta", "adultas",
        "pediatrico", "pediatricos", "pediatrica", "pediatricas",
        "infantil", "infantiles",
        "nino", "ninos", "nina", "ninas"
    }

    palabras = [p for p in termino_norm.split() if len(p) >= 1 and p not in ignorar]
    if not palabras:
        palabras = [p for p in termino_norm.split() if len(p) >= 1] or [termino_norm]

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
        desc_norm = re.sub(r"(\d+)([a-z]+)", r"\1 \2", desc_norm)
        desc_norm = re.sub(r"([a-z]+)(\d+)", r"\1 \2", desc_norm)
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
            f"{MENSAJE_BIENVENIDA_PRODUCTO}"
            f"No encontré resultados para *{termino}* en este momento. "
            f"Verifica el nombre del producto, escribe *Unity* para orientarte con nuestro asistente virtual, "
            f"o escribe *asesor* y pronto serás atendido por nuestro personal.\n\n"
            f"{MENSAJE_DESPEDIDA}"
        )

    lineas = [
        f"{MENSAJE_BIENVENIDA_PRODUCTO}",
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

    bloques = [f"{MENSAJE_BIENVENIDA_PRODUCTO}"]
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


def _buscar_contexto_inventario_para_unity(consulta: str) -> str:
    if not INVENTARIO:
        return ""
    _, terminos = procesar_mensaje_usuario(consulta)
    if not terminos:
        return ""
    resultados = []
    for term in terminos[:3]:
        for p in buscar_productos(term, limite=3):
            linea = f"- {p['descripcion']} (USD ${p['usd']:.2f} | Bs. {p['bs']:,.2f})"
            if linea not in resultados:
                resultados.append(linea)
    if not resultados:
        return ""
    return "Productos encontrados en el inventario actual de Farmacia Unitas Norte:\n" + "\n".join(resultados[:6])


def consultar_asistente_unity(remitente: str, mensaje_usuario: str) -> str:
    if _contiene_medicamento_restringido(mensaje_usuario):
        return MENSAJE_BLOQUEO_CONTROLADOS

    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return (
            "En este momento el asistente *Unity* no está disponible. "
            "Escribe *asesor* para hablar con nuestro equipo o *salir* para buscar productos."
        )

    sesion = SESIONES_UNITY.setdefault(remitente, {"ultimo_uso": time.time(), "historial": []})
    sesion["ultimo_uso"] = time.time()
    historial = sesion.get("historial", [])

    contexto_inv = _buscar_contexto_inventario_para_unity(mensaje_usuario)

    instrucciones_sistema = (
        "Eres Unity, el asistente virtual de orientación farmacéutica de Farmacia Unitas Norte (RIF: J-298120886) en Venezuela. "
        "Operas bajo los criterios generales de orientación sanitaria alineados con la normativa del Ministerio del Poder Popular para la Salud (MPPS) y la Ley Orgánica de Drogas en Venezuela. "
        "Responde siempre en español, de forma clara, cercana, empática y concisa (ideal para WhatsApp, máximo 120-160 palabras, usando viñetas cortas y negritas simples con *asteriscos*).\n\n"
        "REGLAS NORMATIVAS Y DE SEGURIDAD:\n"
        "1. NUNCA recomiendes, prescribas ni des dosis o pautas de uso de MEDICAMENTOS CONTROLADOS, ESTUPEFACIENTES, PSICOTRÓPICOS o ANTIBIÓTICOS, ni de fármacos sujetos a récipe médico. Si el usuario consulta sobre alguno, indica estrictamente que debe acudir a un médico y cumplir con los requisitos de prescripción/dispensación vigentes.\n"
        "2. SÍ puedes ofrecer orientación informativa general sobre malestares leves o síntomas comunes y explicar el uso general de medicamentos sencillos de venta libre (sin diagnosticar ni sustituir la valoración médica).\n"
        "3. Al explicar cómo se usa un medicamento de venta libre, entrega solo pautas generales orientativas y recuerda revisar el prospecto y consultar al médico o farmacéutico (especialmente en niños, embarazo, lactancia, adultos mayores o condiciones crónicas).\n"
        "4. Si hay síntomas de alarma o gravedad, recomienda atención médica inmediata.\n"
        "5. Si hay productos en el contexto de inventario y no están restringidos, puedes mencionarlos brevemente con su precio.\n"
        "6. Cierra recordando brevemente que puede escribir *asesor* para atención personalizada o *salir* para volver al buscador."
    )

    prompt_usuario = mensaje_usuario.strip()
    if contexto_inv:
        prompt_usuario = f"{prompt_usuario}\n\n[Contexto interno de inventario]\n{contexto_inv}"

    contents = []
    for turno in historial[-6:]:
        contents.append({"role": turno["role"], "parts": [{"text": turno["text"]}]})
    contents.append({"role": "user", "parts": [{"text": prompt_usuario}]})

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-4-hydrogen:generateContent?key={api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": instrucciones_sistema}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.35,
            "maxOutputTokens": 450,
        },
    }

    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    candidatos = data.get("candidates") or []
    if not candidatos:
        return (
            "No pude generar una respuesta en este momento. "
            "Por favor reformula tu consulta o escribe *asesor* para hablar con nuestro equipo."
        )

    partes = ((candidatos[0].get("content") or {}).get("parts")) or []
    respuesta_texto = " ".join(p.get("text", "") for p in partes if p.get("text")).strip()
    if not respuesta_texto:
        return (
            "No pude generar una respuesta en este momento. "
            "Por favor reformula tu consulta o escribe *asesor* para hablar con nuestro equipo."
        )

    historial.append({"role": "user", "text": mensaje_usuario.strip()})
    historial.append({"role": "model", "text": respuesta_texto})
    sesion["historial"] = historial[-6:]

    return respuesta_texto[:3800]


def descargar_audio_whatsapp(media_id: str):
    token = (os.getenv("WHATSAPP_TOKEN") or "").strip()
    if not token or not media_id:
        return None, None

    headers = {"Authorization": f"Bearer {token}"}
    meta_url = f"https://graph.facebook.com/v21.0/{media_id}"
    resp_meta = requests.get(meta_url, headers=headers, timeout=20)
    resp_meta.raise_for_status()
    info = resp_meta.json()

    download_url = info.get("url")
    mime_type = (info.get("mime_type") or "audio/ogg").split(";")[0].strip()
    if not download_url:
        return None, None

    resp_audio = requests.get(download_url, headers=headers, timeout=30)
    resp_audio.raise_for_status()
    return resp_audio.content, mime_type


def transcribir_audio_gemini(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key or not audio_bytes:
        return ""

    b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-4-hydrogen:generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "Transcribe exactamente lo que dice este audio en español. "
                            "Devuelve solo el texto transcrito, sin explicaciones ni comillas."
                        )
                    },
                    {
                        "inline_data": {
                            "mime_type": mime_type or "audio/ogg",
                            "data": b64_audio,
                        }
                    },
                ]
            }
        ]
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    candidatos = data.get("candidates") or []
    if not candidatos:
        return ""
    partes = ((candidatos[0].get("content") or {}).get("parts")) or []
    texto = " ".join(p.get("text", "") for p in partes if p.get("text")).strip()
    return texto


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


def _manejar_texto_entrante(remitente: str, texto_usuario: str):
    texto_limpio = (texto_usuario or "").strip()
    norm_plano = re.sub(r"[^\w\s]", " ", _normalizar(texto_limpio))
    norm_plano = re.sub(r"\s+", " ", norm_plano).strip()

    if norm_plano in ("asesor", "humano", "agente", "persona"):
        _desactivar_unity(remitente)
        enviar_mensaje_whatsapp(remitente, MENSAJE_ASESOR)
        return

    if norm_plano in ("unity", "hola unity", "asistente", "asistente virtual"):
        _activar_unity(remitente)
        enviar_mensaje_whatsapp(remitente, MENSAJE_BIENVENIDA_UNITY)
        return

    if _unity_activo(remitente):
        if norm_plano in ("salir", "menu", "volver", "cerrar", "fin", "terminar", "gracias", "muchas gracias", "adios", "chao"):
            _desactivar_unity(remitente)
            if norm_plano in ("gracias", "muchas gracias", "adios", "chao"):
                enviar_mensaje_whatsapp(remitente, MENSAJE_DESPEDIDA)
            else:
                enviar_mensaje_whatsapp(remitente, MENSAJE_SALIDA_UNITY)
            return

        try:
            respuesta_unity = consultar_asistente_unity(remitente, texto_limpio)
        except Exception as e:
            print(f"[ERROR] Consultando Unity para {remitente}: {e}")
            respuesta_unity = (
                "Tuve un inconveniente temporal con *Unity*. "
                "Intenta de nuevo en unos segundos, escribe *asesor* para hablar con nuestro equipo "
                "o *salir* para volver al buscador."
            )
        enviar_mensaje_whatsapp(remitente, respuesta_unity)
        return

    respuesta_directa, termino = procesar_mensaje_usuario(texto_limpio)
    if respuesta_directa:
        enviar_mensaje_whatsapp(remitente, respuesta_directa)
    elif not INVENTARIO:
        enviar_mensaje_whatsapp(
            remitente,
            "El inventario de la farmacia aún se está sincronizando. "
            "Por favor intenta de nuevo en unos minutos, escribe *Unity* para orientarte con nuestro asistente virtual, "
            "o escribe *asesor* para hablar con nuestro equipo."
        )
    else:
        respuesta = responder_consulta_productos(termino)
        enviar_mensaje_whatsapp(remitente, respuesta)


@app.get("/")
def inicio():
    return {
        "status": "ok",
        "servicio": "Farmacia Unitas Norte Bot",
        "productos_cargados": len(INVENTARIO),
        "tasa_bs": TASA_BS,
        "asistente_unity": "activo",
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
                        _manejar_texto_entrante(remitente, texto_usuario)

                    elif tipo == "audio":
                        media_id = ((msg.get("audio") or {}).get("id") or "").strip()
                        try:
                            if not (os.getenv("GEMINI_API_KEY") or "").strip():
                                print("[ERROR] Falta GEMINI_API_KEY en variables de entorno.")
                                texto_audio = ""
                            else:
                                audio_bytes, mime_type = descargar_audio_whatsapp(media_id)
                                print(f"[DEBUG] Audio {media_id} mime={mime_type} bytes={len(audio_bytes) if audio_bytes else 0}")
                                texto_audio = transcribir_audio_gemini(audio_bytes, mime_type) if audio_bytes else ""
                                print(f"[DEBUG] Transcripcion: {texto_audio!r}")
                        except Exception as e:
                            print(f"[ERROR] Procesando audio {media_id}: {e}")
                            texto_audio = ""

                        if not texto_audio:
                            enviar_mensaje_whatsapp(
                                remitente,
                                "No logré escuchar bien el audio. Por favor intenta de nuevo, "
                                "escribe el nombre del producto o escribe *asesor* para ayudarte."
                            )
                        else:
                            _manejar_texto_entrante(remitente, texto_audio)

                    else:
                        enviar_mensaje_whatsapp(
                            remitente,
                            "Por el momento solo puedo leer mensajes de texto o notas de voz. "
                            "Escríbeme el nombre del producto que buscas, escribe *Unity* para hablar con nuestro asistente virtual, "
                            "o escribe *asesor* para hablar con nuestro equipo."
                        )
                except Exception as e:
                    print(f"[ERROR] Procesando mensaje de {remitente}: {e}")
                    enviar_mensaje_whatsapp(
                        remitente,
                        "Tuve un inconveniente al procesar tu mensaje. "
                        "Por favor intenta de nuevo o escribe *asesor*."
                    )

    return {"status": "ok"}
