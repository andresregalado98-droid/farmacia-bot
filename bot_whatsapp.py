import base64
import json
import os
import re
import time
import traceback
import unicodedata
import requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

app = FastAPI()

TASA_COP_POR_USD = float(os.getenv("TASA_COP_POR_USD") or "0")
NUMERO_FARMACIA = re.sub(r"\D", "", os.getenv("NUMERO_FARMACIA") or "584121717703")

MENSAJE_BIENVENIDA_UNITY = (
    "¡Hola! 👋😊 Qué alegría saludarte. Soy *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨* al servicio de todos los clientes de *Farmacia Unitas Norte* (RIF: *J-298120886*) 🏥💙.\n\n"
    "Estoy aquí desde este primer mensaje para ayudarte y hacerte todo más fácil ✨. ¡Aprovecha al máximo todo lo que puedo hacer por ti!\n\n"
    "🔍 *1. Precios y disponibilidad al instante:* Escríbeme el nombre de uno o varios productos y te consulto su precio y disponibilidad al momento 💊✨.\n"
    "🩺 *2. Orientación en malestares leves:* Cuéntame si tienes algún malestar común (dolor de cabeza, acidez, congestión, etc.) y te oriento con opciones habituales y cuidados generales 🌿💧.\n"
    "🎙️ *3. ¡También entiendo notas de voz!:* Si vas ocupado o prefieres hablar, envíame un audio y te respondo igual de rápido 🗣️✨.\n"
    "📸 *4. Lectura de récipes y fotos:* Envíame una foto de tu récipe médico, caja o lista y reviso los medicamentos en inventario al momento 📋💊.\n"
    "📍 *5. Ubicación, horario y cómo llegar:* Pregúntame dónde estamos y te envío nuestra dirección exacta, enlace de Google Maps 🗺️ y horario (*Lunes a Sábado: 7:00 AM a 10:30 PM | Domingo: Cerrado* ⏰).\n"
    "👩‍⚕️ *6. Atención personalizada:* Si necesitas hablar con nuestro equipo de mostrador, solo escribe *asesor* en cualquier momento 🤝.\n\n"
    "⚠️ *Compromiso sanitario (MPPS / Ley Orgánica de Drogas):* Puedo informarte precios y disponibilidad de inventario, pero por normativa vigente los *antibióticos*, *psicotrópicos* y *estupefacientes* nunca se recomiendan ni se indican por este medio; requieren prescripción e indicación de un *médico*.\n\n"
    "¿Qué producto buscas o en qué te puedo ayudar hoy? 💬😊"
)

MENSAJE_BIENVENIDA_PRODUCTO = (
    "¡Hola! 👋😊 Soy *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨* en *Farmacia Unitas Norte* (RIF: *J-298120886*) 🏥. Aquí tienes lo que encontré para ti:\n"
)

MENSAJE_DESPEDIDA = (
    "¡Muchas gracias por confiar en *Farmacia Unitas Norte* (RIF: *J-298120886*)! 💙✨\n"
    "📍 *Nos encuentras en:* Calle 5 entre carreras 11 y 12 de La Concordia, media cuadra bajando del Hospital Central.\n"
    "⏰ *Horario de atención:* Lunes a Sábado de *7:00 AM a 10:30 PM* | Domingo: *Cerrado*.\n\n"
    "Recuerda que sigo aquí como *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨* al servicio del cliente 🙌😊. "
    "Puedes escribirme o enviarme un audio 🎙️ con otro producto 💊, hacerme una consulta sobre algún malestar leve 🩺, "
    "o escribir *asesor* para recibir atención personalizada de nuestro equipo 👩‍⚕️. ¡Que tengas un excelente día! ☀️💛"
)

MENSAJE_ASESOR = (
    "¡Con mucho gusto! 🤝😊 En un momento te atenderá un asesor de *Farmacia Unitas Norte* "
    "(RIF: *J-298120886*) para brindarte atención personalizada 👩‍⚕️💬.\n\n"
    "🤖 _Mientras conversas con nuestro equipo en mostrador, quedaré en pausa para no interrumpir. "
    "Si deseas volver a hablar con *✨🤖 UNITY — TU GUÍA DE FARMACIA 🩺✨* en cualquier momento, solo escribe *unity* o *menu*._"
)

MENSAJE_PAUSA_POR_TRABAJADOR = (
    "👩‍⚕️🤝 Un asesor de *Farmacia Unitas Norte* te está atendiendo directamente por aquí, así que quedaré en pausa para no interrumpir la conversación 😊.\n\n"
    "🤖 _Si deseas volver a hablar con *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨* para consultar precios o disponibilidad al instante, solo escribe *unity* o *menu*._"
)

MENSAJE_BLOQUEO_CONTROLADOS = (
    "⚠️ *Aviso importante de salud (MPPS / Ley Orgánica de Drogas):*\n"
    "Como *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨* al servicio del cliente, cuido tu bienestar y cumplo con la regulación farmacéutica vigente 💙. "
    "Puedo informarte precios y disponibilidad de inventario, pero no puedo recomendar, indicar ni dar pautas o dosis de uso sobre *antibióticos, psicotrópicos ni estupefacientes* 🚫💊.\n\n"
    "Estos fármacos requieren valoración e indicación directa de un *médico* y cumplir con los requisitos de dispensación establecidos 🩺.\n"
    "Si deseas consultar disponibilidad exacta en mostrador o atención personalizada de nuestro equipo, escribe *asesor* 👩‍⚕️🤝."
)

NOTA_DISPENSACION_RESTRINGIDOS = (
    "\n📋 *Nota de dispensación:* Los *antibióticos, psicotrópicos y estupefacientes* mostrados son únicamente consulta de precio y disponibilidad; "
    "su entrega en mostrador requiere indicación y récipe médico vigente 🩺."
)

INVENTARIO = []
TASA_BS = 0.0
SESIONES_UNITY = {}
TIMEOUT_UNITY_SEGUNDOS = 30 * 60

# Control de chats atendidos por un trabajador humano: {telefono: {"expira": float, "aviso_enviado": bool}}
CHATS_EN_ATENCION_HUMANA = {}
PAUSA_ASESOR_SEGUNDOS = 45 * 60

# Caché de equivalencias marca -> principio activo para no repetir llamadas
CACHE_PRINCIPIO_ACTIVO = {}

MENSAJES_PROCESADOS = {}
TTL_MENSAJES_SEGUNDOS = 300

PALABRAS_CONTROLADOS_Y_ANTIBIOTICOS = {
    # Categorías regulatorias exclusivas: antibióticos, psicotrópicos y estupefacientes
    "antibiotico", "antibioticos", "antimicrobiano", "antimicrobianos",
    "psicotropico", "psicotropicos", "estupefaciente", "estupefacientes",
    # Estupefacientes / opioides / analgésicos estupefacientes
    "morfina", "oxicodona", "fentanilo", "metadona", "buprenorfina", "tapentadol",
    "petidina", "meperidina", "hidromorfona", "codeina", "tramadol", "tramal",
    # Psicotrópicos: ansiolíticos, sedantes, hipnóticos, estimulantes, barbitúricos
    "alprazolam", "tafil", "clonazepam", "rivotril", "diazepam", "valium",
    "lorazepam", "ativan", "bromazepam", "lexotanil", "midazolam", "clobazam",
    "zolpidem", "stilnox", "zopiclona", "eszopiclona", "fenobarbital",
    "metilfenidato", "ritalin", "concerta", "lisdexanfetamina", "modafinilo",
    # Psicotrópicos / neurofármacos sujetos a control especial
    "sertralina", "fluoxetina", "escitalopram", "citalopram", "paroxetina",
    "venlafaxina", "desvenlafaxina", "duloxetina", "amitriptilina", "bupropion",
    "mirtazapina", "trazodona", "quetiapina", "risperidona", "olanzapina",
    "haloperidol", "aripiprazol", "clozapina", "carbamazepina", "valproato",
    "acido valproico", "levetiracetam", "lamotrigina", "fenitoina",
    "pregabalina", "gabapentina",
    # Antibióticos comunes y marcas frecuentes
    "amoxicilina", "ampicilina", "azitromicina", "claritromicina", "eritromicina",
    "ciprofloxacina", "ciprofloxacino", "levofloxacina", "levofloxacino",
    "moxifloxacino", "norfloxacina", "cefalexina", "cefadroxilo", "cefixima",
    "longacef", "ceftriaxona", "cefuroxima", "doxiciclina", "tetraciclina",
    "minociclina", "clindamicina", "metronidazol", "tinidazol", "secnidazol",
    "ornidazol", "trimetoprim", "sulfametoxazol", "bactrim", "bactron",
    "gentamicina", "amikacina", "penicilina", "sultamicilina", "unasyn",
    "augmentin", "nitrofurantoina", "fosfomicina", "meropenem", "vancomicina",
    "linezolid",
}


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().lower()


def _coincide_palabra_exacta(palabra: str, texto_norm: str) -> bool:
    if not palabra or not texto_norm:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(palabra)}(?![a-z0-9])", texto_norm))


def _activar_pausa_humano(telefono_cliente: str, motivo: str = "", notificar_cliente: bool = False):
    tel = re.sub(r"\D", "", telefono_cliente or "")
    if not tel or (NUMERO_FARMACIA and tel == NUMERO_FARMACIA):
        return

    ahora = time.time()
    estado_previo = CHATS_EN_ATENCION_HUMANA.get(tel)
    ya_en_pausa = bool(estado_previo and ahora <= estado_previo.get("expira", 0))
    aviso_ya_enviado = bool(estado_previo and estado_previo.get("aviso_enviado", False)) if ya_en_pausa else False

    debe_avisar = notificar_cliente and not aviso_ya_enviado

    CHATS_EN_ATENCION_HUMANA[tel] = {
        "expira": ahora + PAUSA_ASESOR_SEGUNDOS,
        "aviso_enviado": True if (aviso_ya_enviado or debe_avisar or motivo == "cliente_pidio_asesor") else False,
    }
    print(f"[HANDOVER] Unity pausado para {tel} ({motivo}) por {PAUSA_ASESOR_SEGUNDOS // 60} min.")

    if debe_avisar:
        enviar_mensaje_whatsapp(telefono_cliente, MENSAJE_PAUSA_POR_TRABAJADOR)


def _desactivar_pausa_humano(telefono_cliente: str):
    tel = re.sub(r"\D", "", telefono_cliente or "")
    if tel in CHATS_EN_ATENCION_HUMANA:
        CHATS_EN_ATENCION_HUMANA.pop(tel, None)
        print(f"[HANDOVER] Unity reactivado manualmente para {tel}.")


def _esta_en_atencion_humana(telefono_cliente: str) -> bool:
    tel = re.sub(r"\D", "", telefono_cliente or "")
    if not tel:
        return False
    estado = CHATS_EN_ATENCION_HUMANA.get(tel)
    if not estado:
        return False
    if time.time() > estado.get("expira", 0):
        CHATS_EN_ATENCION_HUMANA.pop(tel, None)
        return False
    return True


def _ya_procesado(msg_id: str) -> bool:
    if not msg_id:
        return False
    ahora = time.time()
    expirados = [
        mid for mid, ts in MENSAJES_PROCESADOS.items()
        if ahora - ts > TTL_MENSAJES_SEGUNDOS
    ]
    for mid in expirados:
        MENSAJES_PROCESADOS.pop(mid, None)

    if msg_id in MENSAJES_PROCESADOS:
        return True
    MENSAJES_PROCESADOS[msg_id] = ahora
    return False


def _limpiar_sesiones_expiradas():
    ahora = time.time()
    expirados = [
        tel for tel, data in SESIONES_UNITY.items()
        if ahora - data.get("ultimo_uso", 0) > TIMEOUT_UNITY_SEGUNDOS
    ]
    for tel in expirados:
        SESIONES_UNITY.pop(tel, None)


def _obtener_sesion_unity(remitente: str) -> dict:
    _limpiar_sesiones_expiradas()
    sesion = SESIONES_UNITY.setdefault(remitente, {"ultimo_uso": time.time(), "historial": []})
    sesion["ultimo_uso"] = time.time()
    return sesion


def _registrar_turno_unity(remitente: str, mensaje_usuario: str, respuesta_bot: str):
    sesion = _obtener_sesion_unity(remitente)
    historial = sesion.get("historial", [])
    historial.append({"role": "user", "text": mensaje_usuario.strip()})
    historial.append({"role": "model", "text": respuesta_bot.strip()})
    sesion["historial"] = historial[-8:]


def _reiniciar_sesion_unity(remitente: str):
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


def _pide_recomendacion_o_dosis_restringido(texto: str) -> bool:
    """Solo devuelve True si menciona un restringido Y pide explícitamente recomendar, recetar o dar dosis."""
    if not _contiene_medicamento_restringido(texto):
        return False
    norm = _normalizar(texto)
    norm_plano = re.sub(r"[^\w\s]", " ", norm)
    norm_plano = re.sub(r"\s+", " ", norm_plano).strip()
    patrones_receta_o_dosis = (
        "recomienda", "recomiendas", "recomiendame", "sugiere", "recetame", "receta",
        "que puedo tomar", "que me tomo", "como se toma", "como tomar",
        "cada cuanto", "dosis", "cuantas pastillas", "cuantos dias", "pauta"
    )
    return any(p in norm_plano for p in patrones_receta_o_dosis)


def _es_solo_consulta_precio_o_disponibilidad(texto: str) -> bool:
    """Detecta si el cliente consulta precio/existencia sin pedir recomendación ni dosis."""
    if _pide_recomendacion_o_dosis_restringido(texto):
        return False

    norm = _normalizar(texto)
    norm_plano = re.sub(r"[^\w\s]", " ", norm)
    norm_plano = re.sub(r"\s+", " ", norm_plano).strip()

    verbos_sintomas = (
        "me duele", "tengo infeccion", "tengo gripe", "tengo fiebre",
        "tengo dolor", "tengo tos", "malestar", "sintoma"
    )
    if any(v in norm_plano for v in verbos_sintomas):
        return False

    indicadores_precio_stock = (
        "precio", "precios", "cuanto cuesta", "cuanto vale", "cuesta", "vale",
        "tienen", "tiene", "tenes", "hay", "disponible", "disponibles",
        "disponibilidad", "existencia", "existencias", "stock", "busco", "necesito",
        "imagen", "recipe", "receta"
    )
    if any(ind in norm_plano for ind in indicadores_precio_stock):
        return True

    if len(norm_plano.split()) <= 5:
        return True

    return False


def _es_consulta_conversacional(texto_norm: str) -> bool:
    """Detecta si el usuario está haciendo una pregunta abierta, pidiendo orientación de síntomas, funciones, horario o ubicación."""
    indicadores_conversacion = (
        "?", "¿", "dolor", "fiebre", "gripe", "tos", "acidez", "alergia",
        "malestar", "sintoma", "síntoma", "mareo", "nausea", "náusea",
        "diarrea", "estomago", "estómago", "cabeza", "garganta", "congestion",
        "congestión", "recomienda", "recomiendas", "sirve para", "que puedo tomar",
        "qué puedo tomar", "que me tomo", "qué me tomo", "como se toma",
        "cómo se toma", "para que sirve", "para qué sirve", "ubicacion",
        "ubicación", "direccion", "dirección", "donde quedan", "dónde quedan",
        "como llegar", "cómo llegar", "horario", "abiertos", "abierto", "cierran",
        "cerrado", "domingo", "trabajan", "pesos", "colombianos", "cop",
        "bolivares", "bolívares", "tasa", "que haces", "qué haces",
        "funciones", "ayudar", "quien eres", "quién eres"
    )
    return any(ind in texto_norm for ind in indicadores_conversacion)


def procesar_mensaje_usuario(texto: str):
    texto_limpio = (texto or "").strip()
    if not texto_limpio:
        return MENSAJE_BIENVENIDA_UNITY, None

    minuscula = _normalizar(texto_limpio)

    saludos = (
        "buenos dias", "buen dia", "buenas tardes", "buena tarde",
        "buenas noches", "buena noche", "que tal", "buenas", "saludos", "hola",
        "unity", "hola unity", "guia de farmacia", "amigo de salud", "asistente",
        "asistente virtual", "menu", "inicio"
    )
    despedidas_exactas = {
        "gracias", "muchas gracias", "adios",
        "hasta luego", "chao", "bye", "listo gracias", "mil gracias"
    }

    texto_plano = re.sub(r"[^\w\s]", " ", minuscula)
    texto_plano = re.sub(r"\s+", " ", texto_plano).strip()

    if not texto_plano or texto_plano in saludos:
        return MENSAJE_BIENVENIDA_UNITY, None

    if texto_plano in despedidas_exactas:
        return MENSAJE_DESPEDIDA, None

    if texto_plano in ("asesor", "humano", "agente", "persona"):
        return MENSAJE_ASESOR, None

    if _es_consulta_conversacional(minuscula) and not _es_solo_consulta_precio_o_disponibilidad(texto_limpio):
        return None, None

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
        "y", "e", "pesos", "colombianos", "cop", "bolivares", "bolívares", "dolares", "dólares", "usd"
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
        palabras_sueltas = [p for p in texto_plano.split() if p not in relleno and p not in saludos]
        if not palabras_sueltas:
            return MENSAJE_BIENVENIDA_UNITY, None
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


def _clasificar_presentacion(descripcion: str) -> str:
    """Clasifica un producto en 'tabletas', 'suspension' o 'otras' según su descripción en inventario."""
    norm = _normalizar(descripcion)
    norm_plano = re.sub(r"[^\w\s]", " ", norm)
    norm_plano = re.sub(r"\s+", " ", norm_plano).strip()
    palabras = set(norm_plano.split())

    palabras_suspension = {
        "susp", "suspension", "jbe", "jarabe", "gotas", "gts",
        "sol", "solucion", "elixir", "ped", "pediatrico", "pediatrica"
    }
    palabras_tabletas = {
        "tab", "tabl", "tableta", "tabletas", "cap", "caps",
        "capsula", "capsulas", "comp", "comprimido", "comprimidos",
        "grag", "gragea", "grageas", "blister", "capleta", "capletas"
    }

    if palabras.intersection(palabras_suspension) or re.search(r"\b(susp|jbe|jarabe|gotas)\b", norm_plano):
        return "suspension"
    if palabras.intersection(palabras_tabletas) or re.search(r"\b(tab|tabl|cap|caps|comp|grag)\b", norm_plano):
        return "tabletas"
    return "otras"


def _agrupar_productos_por_presentacion(productos: list) -> dict:
    grupos = {"tabletas": [], "suspension": [], "otras": []}
    for p in productos:
        cat = _clasificar_presentacion(str(p.get("descripcion") or ""))
        grupos[cat].append(p)
    return grupos


def _formatear_item_producto(p: dict) -> str:
    usd = float(p.get("usd") or 0.0)
    bs = float(p.get("bs") or 0.0)
    cop = float(p.get("cop") or 0.0)
    desc = str(p.get("descripcion") or "Producto")
    codigo = str(p.get("codigo") or "N/A")
    return (
        f"• *{desc}* (Cód: {codigo})\n"
        f"  💵 USD: ${usd:.2f} | 🇻🇪 Bs. {bs:,.2f} | 🇨🇴 COP {cop:,.0f}"
    )


def _limpiar_termino_para_equivalente(nombre_medicamento: str) -> str:
    clave = _normalizar(nombre_medicamento)
    clave = re.sub(r"(\d+)([a-z]+)", r"\1 \2", clave)
    clave = re.sub(r"([a-z]+)(\d+)", r"\1 \2", clave)
    clave = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:mg|ml|gr|g|mcg|ui)\b", "", clave)
    clave = re.sub(r"\b(?:tab|tabl|tabletas|caps|capsulas|jarabe|susp|farma)\b", "", clave)
    clave = re.sub(r"\s+", " ", clave).strip()
    return clave


def _resolver_principio_activo_gemini(nombre_medicamento: str) -> str:
    """Devuelve el principio activo o nombre genérico de una marca comercial."""
    clave = _limpiar_termino_para_equivalente(nombre_medicamento)
    if not clave or len(clave) < 3:
        return ""
    if clave in CACHE_PRINCIPIO_ACTIVO:
        return CACHE_PRINCIPIO_ACTIVO[clave]

    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return ""

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            f"Indica ÚNICAMENTE el principio activo o nombre genérico en español (una o dos palabras, en minúsculas, sin dosis ni explicaciones) "
                            f"correspondiente al medicamento o marca: '{clave}'. "
                            f"Ejemplos: 'longacef' -> 'cefixima'; 'tafil' -> 'alprazolam'; 'atamel' -> 'acetaminofen'. "
                            f"Si ya es genérico o no es un medicamento reconocible, responde exactamente 'NINGUNO'."
                        )
                    }
                ]
            }
        ],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 25},
    }
    try:
        data = _llamar_gemini_con_reintentos(payload, timeout=12, max_reintentos=1)
        candidatos = data.get("candidates") or []
        if not candidatos:
            CACHE_PRINCIPIO_ACTIVO[clave] = ""
            return ""
        partes = ((candidatos[0].get("content") or {}).get("parts")) or []
        resp = " ".join(p.get("text", "") for p in partes if p.get("text")).strip()
        resp_norm = re.sub(r"[^\w\s]", "", _normalizar(resp)).strip()
        if not resp_norm or resp_norm == "ninguno" or resp_norm == clave or len(resp_norm.split()) > 3:
            CACHE_PRINCIPIO_ACTIVO[clave] = ""
            return ""
        CACHE_PRINCIPIO_ACTIVO[clave] = resp_norm
        return resp_norm
    except Exception:
        return ""


def buscar_productos(termino: str, limite: int = 15) -> list:
    termino_norm = _normalizar(termino)
    termino_norm = re.sub(r"(\d+)([a-z]+)", r"\1 \2", termino_norm)
    termino_norm = re.sub(r"([a-z]+)(\d+)", r"\1 \2", termino_norm)
    termino_norm = re.sub(r"[^\w\s]", " ", termino_norm)
    termino_norm = re.sub(r"\s+", " ", termino_norm).strip()

    if not termino_norm or not INVENTARIO:
        return []

    ignorar = {
        "para", "uso", "de", "del", "la", "el", "los", "las",
        "adulto", "adultos", "adulta", "adultas",
        "pediatrico", "pediatricos", "pediatrica", "pediatricas",
        "infantil", "infantiles",
        "nino", "ninos", "nina", "ninas",
        "tab", "tabl", "tableta", "tabletas", "cap", "caps", "capsula", "capsulas",
        "susp", "suspension", "jbe", "jarabe", "mg", "ml", "gr", "g", "ui", "mcg",
        "amp", "ampolla", "fco", "farma", "sin", "azucar", "libre"
    }

    palabras = [p for p in termino_norm.split() if len(p) >= 2 and p not in ignorar]
    if not palabras:
        palabras = [p for p in termino_norm.split() if len(p) >= 2 and p != "farma"]
    if not palabras:
        return []

    es_consulta_calcio_suplemento = ("calcio" in palabras and "dobesilato" not in palabras)

    def _filtrar(pals: list) -> list:
        hallados = []
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
            desc_norm = re.sub(r"[^\w\s]", " ", desc_norm)
            desc_norm = re.sub(r"\s+", " ", desc_norm).strip()
            codigo_norm = _normalizar(codigo)

            if es_consulta_calcio_suplemento and "dobesilato" in desc_norm:
                continue

            if all(
                _coincide_palabra_exacta(pal, desc_norm) or _coincide_palabra_exacta(pal, codigo_norm)
                for pal in pals
            ):
                usd = _a_numero(item.get("usd") if item.get("usd") is not None else item.get("precio_usd"))
                cop = _a_numero(item.get("cop") if item.get("cop") is not None else item.get("precio_cop"))
                if cop <= 0 and usd > 0 and TASA_COP_POR_USD > 0:
                    cop = round(usd * TASA_COP_POR_USD, 0)
                bs = _a_numero(item.get("bs") if item.get("bs") is not None else item.get("precio_bs"))
                if bs <= 0 and usd > 0 and TASA_BS > 0:
                    bs = round(usd * TASA_BS, 2)

                hallados.append({
                    "codigo": codigo or "N/A",
                    "descripcion": desc or "Producto",
                    "usd": usd,
                    "bs": bs,
                    "cop": cop,
                })
                if len(hallados) >= limite:
                    break
        return hallados

    coincidencias = _filtrar(palabras)
    if not coincidencias and len(palabras) > 1:
        sin_dosis = [p for p in palabras if not p.isdigit() and len(p) >= 3]
        if sin_dosis and sin_dosis != palabras:
            coincidencias = _filtrar(sin_dosis)

    return coincidencias


def buscar_productos_con_equivalente(termino: str, limite: int = 15) -> tuple[list, str]:
    """Busca primero por el término exacto; si no hay, resuelve el principio activo (ej. Longacef -> Cefixima) y busca alternativas."""
    directos = buscar_productos(termino, limite=limite)
    if directos:
        return directos, ""

    principio = _resolver_principio_activo_gemini(termino)
    if principio:
        alternativos = buscar_productos(principio, limite=limite)
        if alternativos:
            return alternativos, principio

    return [], ""


def formatear_respuesta_productos(termino: str, productos: list, principio_equivalente: str = "") -> str:
    es_restringido = (
        _contiene_medicamento_restringido(termino)
        or _contiene_medicamento_restringido(principio_equivalente)
        or any(_contiene_medicamento_restringido(str(p.get("descripcion") or "")) for p in productos)
    )
    grupos = _agrupar_productos_por_presentacion(productos)
    if principio_equivalente:
        encabezado_busqueda = (
            f"🔎 *Consulta: {termino}*\n"
            f"ℹ️ No tenemos *{termino}* disponible en este momento, pero contamos con otras opciones con su mismo principio activo (*{principio_equivalente.capitalize()}*):\n"
        )
    else:
        encabezado_busqueda = f"🔎 *Resultados para {termino}:* (✅ Disponible en inventario)\n"

    lineas = [
        f"{MENSAJE_BIENVENIDA_PRODUCTO}",
        encabezado_busqueda,
    ]

    if grupos["tabletas"]:
        lineas.append("💊 *Tabletas / Cápsulas:*")
        for p in grupos["tabletas"][:5]:
            lineas.append(_formatear_item_producto(p))
        lineas.append("")

    if grupos["suspension"]:
        lineas.append("🧴 *Suspensión / Jarabe:*")
        for p in grupos["suspension"][:5]:
            lineas.append(_formatear_item_producto(p))
        lineas.append("")

    if grupos["otras"]:
        titulo_otras = "📦 *Otras presentaciones:*" if (grupos["tabletas"] or grupos["suspension"]) else "📦 *Presentaciones disponibles:*"
        lineas.append(titulo_otras)
        for p in grupos["otras"][:5]:
            lineas.append(_formatear_item_producto(p))
        lineas.append("")

    if es_restringido:
        lineas.append(NOTA_DISPENSACION_RESTRINGIDOS)

    lineas.append(f"\n{MENSAJE_DESPEDIDA}")
    texto_final = "\n".join(lineas)
    return texto_final[:3800]


def responder_consulta_productos(termino_o_lista):
    """Devuelve texto formateado si encuentra productos (o sus equivalentes por principio activo) en inventario."""
    terminos = termino_o_lista if isinstance(termino_o_lista, list) else [termino_o_lista]

    if len(terminos) == 1:
        termino = terminos[0]
        encontrados, eq = buscar_productos_con_equivalente(termino)
        if not encontrados:
            return None
        return formatear_respuesta_productos(termino, encontrados, principio_equivalente=eq)

    alguno_encontrado = False
    alguno_restringido = False
    bloques = [f"{MENSAJE_BIENVENIDA_PRODUCTO}"]
    for term in terminos:
        encontrados, eq = buscar_productos_con_equivalente(term)
        bloques.append(f"🔎 *Consulta: {term}*")
        if not encontrados:
            bloques.append(f"No encontré coincidencias disponibles para *{term}* en este momento 😅.\n")
        else:
            alguno_encontrado = True
            if eq:
                bloques.append(
                    f"ℹ️ No tenemos *{term}* en existencia, pero contamos con opciones con su mismo principio activo (*{eq.capitalize()}*):"
                )
            if _contiene_medicamento_restringido(term) or _contiene_medicamento_restringido(eq):
                alguno_restringido = True
            grupos = _agrupar_productos_por_presentacion(encontrados)

            if grupos["tabletas"]:
                bloques.append("💊 *Tabletas / Cápsulas:*")
                for p in grupos["tabletas"][:4]:
                    if _contiene_medicamento_restringido(str(p.get("descripcion") or "")):
                        alguno_restringido = True
                    bloques.append(_formatear_item_producto(p))

            if grupos["suspension"]:
                bloques.append("🧴 *Suspensión / Jarabe:*")
                for p in grupos["suspension"][:4]:
                    if _contiene_medicamento_restringido(str(p.get("descripcion") or "")):
                        alguno_restringido = True
                    bloques.append(_formatear_item_producto(p))

            if grupos["otras"]:
                titulo_otras = "📦 *Otras presentaciones:*" if (grupos["tabletas"] or grupos["suspension"]) else "📦 *Disponibles:*"
                bloques.append(titulo_otras)
                for p in grupos["otras"][:4]:
                    if _contiene_medicamento_restringido(str(p.get("descripcion") or "")):
                        alguno_restringido = True
                    bloques.append(_formatear_item_producto(p))

            bloques.append("")

    if not alguno_encontrado:
        return None

    if alguno_restringido:
        bloques.append(NOTA_DISPENSACION_RESTRINGIDOS)

    bloques.append(MENSAJE_DESPEDIDA)
    return "\n".join(bloques)[:3800]


def _extraer_palabras_clave_inventario(consulta: str) -> list:
    norm = _normalizar(consulta)
    norm_plano = re.sub(r"[^\w\s]", " ", norm)
    stop = {
        "hola", "unity", "tienen", "tiene", "hay", "busco", "necesito", "quiero",
        "precio", "precios", "cuanto", "cuesta", "vale", "pesos", "colombianos",
        "cop", "bolivares", "dolares", "para", "como", "donde", "que", "con",
        "sin", "por", "favor", "una", "uno", "unos", "unas", "los", "las", "del"
    }
    return [p for p in norm_plano.split() if len(p) >= 3 and p not in stop][:5]


def _buscar_contexto_inventario_para_unity(consulta: str) -> str:
    if not INVENTARIO:
        return ""
    palabras = _extraer_palabras_clave_inventario(consulta)
    if not palabras:
        return ""
    resultados = []
    for term in palabras:
        encontrados, eq = buscar_productos_con_equivalente(term, limite=6)
        for p in encontrados:
            cop_val = float(p.get("cop") or 0.0)
            if cop_val <= 0 and p["usd"] > 0 and TASA_COP_POR_USD > 0:
                cop_val = round(p["usd"] * TASA_COP_POR_USD, 0)
            parte_cop = f" | COP {cop_val:,.0f}" if cop_val > 0 else " | COP no disponible en contexto"
            cat = _clasificar_presentacion(p["descripcion"])
            etiq_cat = "TABLETAS/CÁPSULAS" if cat == "tabletas" else ("SUSPENSIÓN/JARABE" if cat == "suspension" else "OTRA PRESENTACIÓN")
            nota_eq = f" [EQUIVALENTE A '{term}' POR PRINCIPIO ACTIVO '{eq}']" if eq else ""
            etiqueta_rest = " [ANTIBIÓTICO/PSICOTRÓPICO/ESTUPEFACIENTE - INFORMAR PRECIO Y DISPONIBILIDAD, NUNCA RECOMENDAR NI DAR DOSIS]" if _contiene_medicamento_restringido(p["descripcion"]) else ""
            linea = f"- [{etiq_cat}] {p['descripcion']} (USD ${p['usd']:.2f} | Bs. {p['bs']:,.2f}{parte_cop}){nota_eq}{etiqueta_rest}"
            if linea not in resultados:
                resultados.append(linea)
    if not resultados:
        return ""
    return "Productos disponibles en el inventario actual de Farmacia Unitas Norte:\n" + "\n".join(resultados[:10])


def _llamar_gemini_con_reintentos(payload: dict, timeout: int = 25, max_reintentos: int = 2) -> dict:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Falta GEMINI_API_KEY")

    modelo = "gemini-3.5-flash-lite"
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{modelo}:generateContent?key={api_key}"
    )

    ultimo_error = None
    for intento in range(max_reintentos):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            if resp.status_code == 429:
                raise RuntimeError("HTTP 429 Too Many Requests (cuota por minuto alcanzada)")
            if resp.status_code >= 500:
                ultimo_error = RuntimeError(f"HTTP {resp.status_code} Error del servidor Gemini")
                if intento < max_reintentos - 1:
                    time.sleep(0.8)
                    continue
                raise ultimo_error
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            return resp.json()
        except (requests.Timeout, requests.ConnectionError) as exc:
            ultimo_error = RuntimeError(f"Error de red/timeout con Gemini: {type(exc).__name__}")
            if intento < max_reintentos - 1:
                time.sleep(0.8)
                continue
            raise ultimo_error

    raise ultimo_error


def consultar_asistente_unity(remitente: str, mensaje_usuario: str) -> str:
    if _pide_recomendacion_o_dosis_restringido(mensaje_usuario):
        return MENSAJE_BLOQUEO_CONTROLADOS

    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return (
            "¡Hola! 👋 Soy *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨*. En este momento estoy en mantenimiento técnico 🔧😊. "
            "Escribe *asesor* para recibir atención personalizada de nuestro equipo 👩‍⚕️🤝."
        )

    sesion = _obtener_sesion_unity(remitente)
    historial = sesion.get("historial", [])

    contexto_inv = _buscar_contexto_inventario_para_unity(mensaje_usuario)

    instrucciones_sistema = (
        "Eres *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨*, cercano, ameno y humanizado al servicio de todos los clientes de Farmacia Unitas Norte (RIF: J-298120886) en Venezuela. "
        "Atiendes al cliente desde el inicio de la conversación. Cada vez que menciones tu nombre, resáltalo con estilo y emoticones como *✨🤖 UNITY — TU GUÍA DE FARMACIA 🩺✨*. "
        "Operas bajo los criterios generales de orientación sanitaria alineados con la normativa del Ministerio del Poder Popular para la Salud (MPPS) y la Ley Orgánica de Drogas en Venezuela. "
        "Responde siempre en español con un tono muy humano, cercano, cálido, empático y conversacional para WhatsApp (unos 140-190 palabras), usando viñetas claras, negritas simples con *asteriscos* y bastantes emoticones naturales y expresivos (como 👋, 😊, 🩺, 💊, 🧴, 💧, 🌿, 📍, ⏰, ✨, 💙, 🎙️, 👩‍⚕️, ⚠️). "
        "NUNCA uses expresiones como 'medicamentos sencillos' ni 'productos sencillos', ni te presentes como médico.\n\n"
        "FUNCIONES DE UNITY (PARA EXPLICARLAS SI EL CLIENTE PREGUNTA QUÉ HACES O CÓMO APROVECHARTE):\n"
        "- Consulta rápida de precios y disponibilidad de inventario al momento, separando presentaciones como tabletas y suspensión 💊🧴✨.\n"
        "- Orientación cercana sobre malestares comunes leves y opciones habituales de venta libre (OTC) 🩺🌿.\n"
        "- Comprensión de notas de voz/audios enviados por WhatsApp 🎙️.\n"
        "- Lectura de fotos de récipes médicos, cajas y listas de medicamentos 📋💊.\n"
        "- Envío de la ubicación exacta, enlace de Google Maps 📍 y horario de atención ⏰.\n"
        "- Atención personalizada con nuestro equipo escribiendo *asesor* 👩‍⚕️.\n\n"
        "UBICACIÓN Y HORARIO DE LA FARMACIA:\n"
        "- Si el usuario pregunta dónde queda, la dirección o cómo llegar a Farmacia Unitas Norte, respóndele con mucho entusiasmo dando la dirección exacta: *Calle 5 entre carreras 11 y 12 de La Concordia, media cuadra bajando del Hospital Central* 📍, e incluye siempre este enlace directo de Google Maps: https://maps.app.goo.gl/4gkAosGHE3Swu4js5\n"
        "- Si el usuario pregunta por el horario de trabajo, si están abiertos o si abren los domingos, infórmale con claridad:\n"
        "  • *Lunes a Sábado:* 7:00 AM a 10:30 PM ⏰\n"
        "  • *Domingo:* Cerrado 🛌\n\n"
        "REGLAS NORMATIVAS Y DE SEGURIDAD:\n"
        "1. SEPARACIÓN DE PRESENTACIONES EN INVENTARIO: Cuando menciones productos del contexto de inventario que tengan tabletas/cápsulas y suspensión/jarabe, sepáralos claramente en dos bloques (*💊 Tabletas / Cápsulas* y *🧴 Suspensión / Jarabe*).\n"
        "2. OPCIONES CON EL MISMO PRINCIPIO ACTIVO: Si el cliente pregunta por una marca comercial que no tenemos (por ejemplo Longacef) y en el contexto aparecen opciones con su mismo principio activo (por ejemplo Cefixima), indícale con amabilidad que no tenemos esa marca pero sí contamos con opciones con el mismo principio activo y dale sus precios y disponibilidad.\n"
        "3. PRECIOS Y DISPONIBILIDAD DE ANTIBIÓTICOS, PSICOTRÓPICOS Y ESTUPEFACIENTES: SIEMPRE que un récipe o consulta incluya un antibiótico, psicotrópico o estupefaciente, informa su precio y disponibilidad según el inventario, SIN recetar, SIN recomendarlo y SIN dar dosis ni pautas de uso. Indica brevemente que su dispensación requiere prescripción médica vigente. Si no aparece cargado en este momento, indícalo con amabilidad y sugiere escribir *asesor* para confirmar en mostrador.\n"
        "4. PROHIBICIÓN DE RECETAR O RECOMENDAR ANTIBIÓTICOS, PSICOTRÓPICOS Y ESTUPEFACIENTES: NUNCA recomiendes, sugieras, recetes ni des dosis o pautas de uso de antibióticos, psicotrópicos o estupefacientes. NUNCA exijas ni menciones récipe médico para antiinflamatorios, analgésicos (como meloxicam, ibuprofeno, diclofenac, acetaminofén), antialérgicos ni otros medicamentos de uso cotidiano.\n"
        "5. Ante malestares leves comunes o consultas sobre analgésicos/antiinflamatorios cotidianos (como meloxicam, dolor de cabeza leve, malestar estomacal ocasional, acidez, congestión leve o cansancio), desarrolla una respuesta amena y empática explicando su uso general, opciones habituales y medidas de alivio (sin diagnosticar ni dar dosis fijas como consulta médica).\n"
        "6. Al mencionar medicamentos de uso cotidiano o de venta libre, recuerda revisar el prospecto y consultar al médico o farmacéutico en caso de embarazo, lactancia, niños, adultos mayores o condiciones crónicas.\n"
        "7. Si hay señales de alarma o gravedad, recomienda buscar atención médica de inmediato.\n"
        "8. NUNCA calcules, estimes ni inventes precios en pesos colombianos (COP). Usa únicamente el monto en COP que aparezca explícitamente en el contexto de inventario; si no aparece un monto en COP disponible, indica el precio en USD y Bs. y sugiere escribir *asesor* para confirmar el monto en COP.\n"
        "9. Cierra siempre de forma cercana recordando que sigues a su servicio como *✨🤖 UNITY — TU GUÍA DE FARMACIA 🩺✨* y que puede enviarte otro producto, una nota de voz 🎙️ o escribir *asesor* para atención personalizada 👩‍⚕️."
    )

    prompt_usuario = mensaje_usuario.strip()
    if contexto_inv:
        prompt_usuario = f"{prompt_usuario}\n\n[Contexto interno de inventario]\n{contexto_inv}"

    contents = []
    for turno in historial[-8:]:
        contents.append({"role": turno["role"], "parts": [{"text": turno["text"]}]})
    contents.append({"role": "user", "parts": [{"text": prompt_usuario}]})

    payload = {
        "system_instruction": {"parts": [{"text": instrucciones_sistema}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.45,
            "maxOutputTokens": 950,
        },
    }

    try:
        data = _llamar_gemini_con_reintentos(payload, timeout=25, max_reintentos=2)
    except Exception as e:
        print(f"[ERROR UNITY API] {e}")
        return (
            "¡Hola! 😊 Soy *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨*. Mi conexión está un poquito ocupada en este instante 🔄. "
            "Por favor intenta de nuevo en unos segundos o escribe *asesor* para recibir atención personalizada de nuestro equipo 👩‍⚕️💙."
        )

    candidatos = data.get("candidates") or []
    if not candidatos:
        bloqueo = (data.get("promptFeedback") or {}).get("blockReason")
        print(f"[WARN UNITY] Sin candidatos. blockReason={bloqueo}")
        return (
            "Por normativa y seguridad sanitaria, no pude procesar esa consulta de forma automática ⚠️😊. "
            "Escribe *asesor* para recibir atención personalizada de nuestro equipo 👩‍⚕️🤝."
        )

    cand0 = candidatos[0]
    fin = cand0.get("finishReason")
    partes = ((cand0.get("content") or {}).get("parts")) or []
    respuesta_texto = " ".join(
        p.get("text", "") for p in partes
        if isinstance(p, dict) and p.get("text") and not p.get("thought")
    ).strip()

    if not respuesta_texto:
        print(f"[WARN UNITY] Texto vacío. finishReason={fin}")
        return (
            "¡Disculpa! 😊 No logré completar esa orientación ahora mismo. "
            "Intenta escribirla de otra forma o escribe *asesor* para recibir atención personalizada de nuestro equipo 👩‍⚕️💙."
        )

    _registrar_turno_unity(remitente, mensaje_usuario, respuesta_texto)
    return respuesta_texto[:3800]


def descargar_media_whatsapp(media_id: str, mime_por_defecto: str = "application/octet-stream"):
    token = (os.getenv("WHATSAPP_TOKEN") or "").strip()
    if not token or not media_id:
        return None, None

    headers = {"Authorization": f"Bearer {token}"}
    meta_url = f"https://graph.facebook.com/v21.0/{media_id}"
    resp_meta = requests.get(meta_url, headers=headers, timeout=15)
    resp_meta.raise_for_status()
    info = resp_meta.json()

    download_url = info.get("url")
    mime_type = (info.get("mime_type") or mime_por_defecto).split(";")[0].strip()
    if not download_url:
        return None, None

    resp_media = requests.get(download_url, headers=headers, timeout=25)
    resp_media.raise_for_status()
    return resp_media.content, mime_type


def descargar_audio_whatsapp(media_id: str):
    return descargar_media_whatsapp(media_id, mime_por_defecto="audio/ogg")


def transcribir_audio_gemini(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key or not audio_bytes:
        return ""

    b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
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
    try:
        data = _llamar_gemini_con_reintentos(payload, timeout=25, max_reintentos=2)
    except Exception as e:
        print(f"[ERROR AUDIO API] {e}")
        return ""

    candidatos = data.get("candidates") or []
    if not candidatos:
        return ""
    partes = ((candidatos[0].get("content") or {}).get("parts")) or []
    return " ".join(p.get("text", "") for p in partes if p.get("text")).strip()


def extraer_medicamentos_de_imagen_gemini(
    image_bytes: bytes, mime_type: str = "image/jpeg", caption: str = ""
) -> dict:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key or not image_bytes:
        return {"medicamentos": [], "ilegibles": False}

    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    instruccion = (
        "Eres el lector visual de récipes y productos de Farmacia Unitas Norte. "
        "Lee el texto manuscrito o impreso de la imagen (récipe médico, caja, blíster o lista) para consultar inventario.\n"
        "Reglas estrictas:\n"
        "1. Extrae UN SOLO término limpio por cada ítem/línea del récipe (nunca dividas un mismo medicamento en varias consultas).\n"
        "2. Prioriza el principio activo o nombre claro + dosis/concentración si es legible (ej. 'Vitamina D 2000 UI', 'Omega 3 1000 mg', 'Calcibon').\n"
        "3. Si una palabra es ambigua o está escrita en letra cursiva médica, usa la dosis, presentación y contexto para leerla con precisión:\n"
        "   - Si dice algo como 'Om... 3 caps 1000 mg', escribe 'Omega 3 1000 mg' (no 'Omacor').\n"
        "   - Si dice algo como 'Cal... / Calcio tab', escribe 'Calcibon' (no 'Calaxin').\n"
        "   - Si dice 'Vit D' o 'Farma D (Vit D) 2000 ui', escribe 'Vitamina D 2000 UI'.\n"
        "4. Nunca censures ni omitas medicamentos por ser antibióticos o psicotrópicos.\n"
        "5. Si un ítem es totalmente indescifrable y no se puede deducir, no lo inventes y pon 'ilegibles': true.\n"
        '6. Responde SOLO con un objeto JSON válido con esta estructura exacta: {"medicamentos": ["..."], "ilegibles": true/false}.'
    )
    if caption:
        instruccion += f"\nTexto acompañante enviado por el cliente: {caption}"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type or "image/jpeg",
                            "data": b64_img,
                        }
                    },
                    {"text": instruccion},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }

    try:
        data = _llamar_gemini_con_reintentos(payload, timeout=25, max_reintentos=2)
    except Exception as e:
        print(f"[ERROR IMAGEN API] {e}")
        return {"medicamentos": [], "ilegibles": True}

    candidatos = data.get("candidates") or []
    if not candidatos:
        return {"medicamentos": [], "ilegibles": True}

    partes = ((candidatos[0].get("content") or {}).get("parts")) or []
    texto_json = " ".join(
        p.get("text", "") for p in partes
        if isinstance(p, dict) and p.get("text") and not p.get("thought")
    ).strip()

    texto_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto_json, flags=re.IGNORECASE).strip()
    try:
        parsed = json.loads(texto_json)
        meds = parsed.get("medicamentos") or []
        if not isinstance(meds, list):
            meds = []
        meds_limpios = []
        for m in meds:
            val = re.sub(r"\s+", " ", str(m)).strip()
            if val and _normalizar(val) not in {_normalizar(x) for x in meds_limpios}:
                meds_limpios.append(val)
        return {
            "medicamentos": meds_limpios,
            "ilegibles": bool(parsed.get("ilegibles", False)),
        }
    except Exception:
        return {"medicamentos": [], "ilegibles": True}


def _manejar_imagen_entrante(remitente: str, media_id: str, mime_type: str = "image/jpeg", caption: str = ""):
    if not media_id:
        return

    if not (os.getenv("GEMINI_API_KEY") or "").strip():
        print("[ERROR] Falta GEMINI_API_KEY en variables de entorno.")
        enviar_mensaje_whatsapp(
            remitente,
            "¡Hola! 😊 Soy *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨*. En este momento no puedo analizar imágenes 🔧. "
            "Escríbeme el nombre del medicamento que buscas 💊 o escribe *asesor* para recibir atención personalizada 👩‍⚕️🤝."
        )
        return

    try:
        img_bytes, mime_real = descargar_media_whatsapp(media_id, mime_por_defecto=mime_type or "image/jpeg")
    except Exception as e:
        print(f"[ERROR] Descargando imagen de WhatsApp: {e}")
        traceback.print_exc()
        enviar_mensaje_whatsapp(
            remitente,
            "¡Hola! 😊 Soy *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨*. No logré descargar tu imagen en este momento 📸😅. "
            "Por favor inténtalo de nuevo, escríbeme el nombre del medicamento 💊 o escribe *asesor* 👩‍⚕️🤝."
        )
        return

    if not img_bytes:
        enviar_mensaje_whatsapp(
            remitente,
            "¡Hola! 😊 Soy *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨*. Recibí el archivo pero no pude abrir la imagen 📸😅. "
            "¿Me la envías nuevamente o me escribes qué producto necesitas? 💬"
        )
        return

    resultado_ocr = extraer_medicamentos_de_imagen_gemini(img_bytes, mime_real or "image/jpeg", caption=caption)
    medicamentos = resultado_ocr.get("medicamentos") or []
    hay_ilegibles = bool(resultado_ocr.get("ilegibles"))

    if not medicamentos and not hay_ilegibles:
        msg_sin_meds = (
            "¡Hola! 👋😊 Soy *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨*. "
            "Recibí tu foto 📸, pero no logré identificar nombres de medicamentos ni un récipe legible.\n\n"
            "Puedes enviarme una imagen más clara del récipe o la caja 📋💊, escribirme el producto que buscas 💬 "
            "o escribir *asesor* para recibir atención personalizada 👩‍⚕️🤝."
        )
        _registrar_turno_unity(remitente, f"[Imagen enviada: {caption or 'sin texto'}]", msg_sin_meds)
        enviar_mensaje_whatsapp(remitente, msg_sin_meds)
        return

    if medicamentos and INVENTARIO:
        respuesta_inv = responder_consulta_productos(medicamentos)
        if respuesta_inv:
            if hay_ilegibles:
                nota_ileg = (
                    "\n⚠️ *Nota sobre el récipe:* Algunos términos de la imagen no se leyeron con claridad y preferí no adivinarlos por seguridad. "
                    "Si gustas, escríbelos por aquí o acércate a nuestra sede para revisarlo con nuestro equipo 🩺.\n"
                )
                respuesta_inv = respuesta_inv.replace(
                    MENSAJE_DESPEDIDA,
                    f"{nota_ileg}\n{MENSAJE_DESPEDIDA}",
                    1,
                )
            _registrar_turno_unity(
                remitente,
                f"[Imagen con medicamentos: {', '.join(medicamentos)}]",
                respuesta_inv,
            )
            enviar_mensaje_whatsapp(remitente, respuesta_inv)
            return

    lista_formateada = "\n".join(f"• *{m}*" for m in medicamentos) if medicamentos else "• *(Texto poco legible en imagen)*"
    tiene_restringidos = any(_contiene_medicamento_restringido(m) for m in medicamentos)

    lineas_resp = [
        f"{MENSAJE_BIENVENIDA_PRODUCTO}",
        "📸 *Medicamentos identificados en tu récipe/imagen:*\n",
        lista_formateada,
        "\n⚠️ En este momento no encontré disponibilidad cargada en línea para estos productos en inventario.",
        "💬 Escribe *asesor* para confirmar disponibilidad y precio en *USD*, *Bs.* y *COP* en mostrador 👩‍⚕️🤝.",
    ]
    if hay_ilegibles:
        lineas_resp.append(
            "\n📋 *Nota de legibilidad:* Algunos términos de la imagen no eran claros y no se adivinaron para evitar errores 🩺."
        )
    if tiene_restringidos:
        lineas_resp.append(NOTA_DISPENSACION_RESTRINGIDOS)
    lineas_resp.append(f"\n{MENSAJE_DESPEDIDA}")

    respuesta_directa_img = "\n".join(lineas_resp)[:3800]
    _registrar_turno_unity(
        remitente,
        f"[Imagen con medicamentos: {', '.join(medicamentos)}]",
        respuesta_directa_img,
    )
    enviar_mensaje_whatsapp(remitente, respuesta_directa_img)


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
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code >= 400:
            print(f"[ERROR] WhatsApp API {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[ERROR] Enviando mensaje a WhatsApp: {e}")


def _manejar_texto_entrante(remitente: str, texto_usuario: str):
    texto_limpio = (texto_usuario or "").strip()
    norm_plano = re.sub(r"[^\w\s]", " ", _normalizar(texto_limpio))
    norm_plano = re.sub(r"\s+", " ", norm_plano).strip()

    # Permitir reactivar a Unity manualmente si el cliente escribe "unity" o "menu"
    if norm_plano in ("unity", "hola unity", "menu", "inicio", "reactivar"):
        _desactivar_pausa_humano(remitente)
        _registrar_turno_unity(remitente, texto_limpio, MENSAJE_BIENVENIDA_UNITY)
        enviar_mensaje_whatsapp(remitente, MENSAJE_BIENVENIDA_UNITY)
        return

    # Si un trabajador está atendiendo este chat, Unity no interviene ni repite su saludo
    if _esta_en_atencion_humana(remitente):
        print(f"[SILENCIO UNITY] Chat con {remitente} en atención humana; mensaje ignorado por el bot.")
        return

    if norm_plano in ("asesor", "humano", "agente", "persona"):
        _reiniciar_sesion_unity(remitente)
        _activar_pausa_humano(remitente, motivo="cliente_pidio_asesor", notificar_cliente=False)
        enviar_mensaje_whatsapp(remitente, MENSAJE_ASESOR)
        return

    respuesta_directa, terminos = procesar_mensaje_usuario(texto_limpio)
    if respuesta_directa:
        _registrar_turno_unity(remitente, texto_limpio, respuesta_directa)
        enviar_mensaje_whatsapp(remitente, respuesta_directa)
        return

    if terminos and INVENTARIO:
        respuesta_productos = responder_consulta_productos(terminos)
        if respuesta_productos:
            _registrar_turno_unity(remitente, texto_limpio, respuesta_productos)
            enviar_mensaje_whatsapp(remitente, respuesta_productos)
            return

    respuesta_unity = consultar_asistente_unity(remitente, texto_limpio)
    enviar_mensaje_whatsapp(remitente, respuesta_unity)


@app.get("/")
def inicio():
    return {
        "status": "ok",
        "servicio": "Farmacia Unitas Norte Bot",
        "productos_cargados": len(INVENTARIO),
        "tasa_bs": TASA_BS,
        "tasa_cop_por_usd": TASA_COP_POR_USD,
        "asistente_unity": "modo_principal_activo",
        "modelo_ia": "gemini-3.5-flash-lite",
        "chats_en_atencion_humana": len(CHATS_EN_ATENCION_HUMANA),
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
            field = change.get("field", "")

            # 1. Detectar mensajes enviados manualmente por un trabajador (WhatsApp Business App / Coexistence Echoes)
            for echo in value.get("message_echoes", []):
                destinatario_cliente = str(echo.get("to") or "").strip()
                if destinatario_cliente:
                    _activar_pausa_humano(
                        destinatario_cliente,
                        motivo="eco_trabajador_whatsapp",
                        notificar_cliente=True,
                    )

            # 2. Revisar eventos smb_message_echoes
            if field == "smb_message_echoes":
                for msg in value.get("messages", []):
                    dest = str(msg.get("to") or "").strip()
                    if dest:
                        _activar_pausa_humano(
                            dest,
                            motivo="smb_message_echo",
                            notificar_cliente=True,
                        )
                continue

            for msg in value.get("messages", []):
                msg_id = str(msg.get("id") or "").strip()
                if _ya_procesado(msg_id):
                    continue

                remitente = str(msg.get("from") or "").strip()
                destinatario = str(msg.get("to") or "").strip()
                tipo = msg.get("type")

                if not remitente:
                    continue

                # Si el mensaje viene desde el propio número de la farmacia hacia un cliente, un trabajador respondió
                remitente_digitos = re.sub(r"\D", "", remitente)
                if NUMERO_FARMACIA and remitente_digitos == NUMERO_FARMACIA:
                    if destinatario:
                        _activar_pausa_humano(
                            destinatario,
                            motivo="mensaje_saliente_trabajador",
                            notificar_cliente=True,
                        )
                    continue

                # Si el chat está pausado porque un trabajador lo está atendiendo, no responder (salvo que escriba 'unity' o 'menu')
                if _esta_en_atencion_humana(remitente):
                    if tipo == "text":
                        texto_check = _normalizar((msg.get("text") or {}).get("body", ""))
                        texto_check = re.sub(r"[^\w\s]", " ", texto_check).strip()
                        if texto_check in ("unity", "hola unity", "menu", "inicio", "reactivar"):
                            _desactivar_pausa_humano(remitente)
                        else:
                            print(f"[SILENCIO UNITY] Ignorando texto de {remitente} (atendido por asesor).")
                            continue
                    else:
                        print(f"[SILENCIO UNITY] Ignorando {tipo} de {remitente} (atendido por asesor).")
                        continue

                try:
                    if tipo == "text":
                        texto_usuario = (msg.get("text") or {}).get("body", "")
                        _manejar_texto_entrante(remitente, texto_usuario)

                    elif tipo == "image":
                        img_data = msg.get("image") or {}
                        media_id = str(img_data.get("id") or "").strip()
                        mime_type = (img_data.get("mime_type") or "image/jpeg").split(";")[0].strip()
                        caption = (img_data.get("caption") or "").strip()
                        _manejar_imagen_entrante(remitente, media_id, mime_type=mime_type, caption=caption)

                    elif tipo == "audio":
                        media_id = ((msg.get("audio") or {}).get("id") or "").strip()
                        if not (os.getenv("GEMINI_API_KEY") or "").strip():
                            print("[ERROR] Falta GEMINI_API_KEY en variables de entorno.")
                            texto_audio = ""
                        else:
                            audio_bytes, mime_type = descargar_audio_whatsapp(media_id)
                            texto_audio = transcribir_audio_gemini(audio_bytes, mime_type) if audio_bytes else ""

                        if not texto_audio:
                            enviar_mensaje_whatsapp(
                                remitente,
                                "¡Hola! 😊 Soy *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨*. No logré escuchar bien tu nota de voz 🎙️😅. "
                                "Por favor envíamela de nuevo más cerquita del micrófono, escríbeme lo que necesitas o escribe *asesor* para recibir atención personalizada 👩‍⚕️💙."
                            )
                        else:
                            _manejar_texto_entrante(remitente, texto_audio)

                    else:
                        enviar_mensaje_whatsapp(
                            remitente,
                            "¡Hola! 👋😊 Soy *✨🤖 UNITY — TU GUÍA DE FARMACIA Y ASISTENTE VIRTUAL 🩺✨* al servicio de *Farmacia Unitas Norte* 🏥. "
                            "Por el momento puedo atender mensajes de texto, notas de voz y fotos de récipes o medicamentos 💬🎙️📸. "
                            "Escríbeme el producto que buscas 💊, cuéntame tu consulta de bienestar 🩺 o escribe *asesor* para recibir atención personalizada 👩‍⚕️."
                        )
                except Exception as e:
                    print(f"[ERROR] Procesando mensaje de {remitente}: {e}")
                    traceback.print_exc()

    return {"status": "ok"}
