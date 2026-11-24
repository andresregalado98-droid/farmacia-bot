import re
from fastapi import FastAPI
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


def procesar_mensaje_usuario(texto: str):
    texto_limpio = texto.strip()
    minuscula = texto_limpio.lower()

    saludos = (
        "hola", "buenos dias", "buenos días",
        "buenas tardes", "buenas noches", "buenas"
    )
    despedidas = (
        "gracias", "muchas gracias", "adios", "adiós",
        "hasta luego", "chao", "bye", "listo gracias"
    )

    sin_signos = re.sub(r"[¡!¿?.,]+$", "", minuscula).strip()

    if sin_signos in saludos:
        return MENSAJE_BIENVENIDA, None

    if sin_signos in despedidas:
        return MENSAJE_DESPEDIDA, None

    # Si empieza con saludo seguido de consulta (ej. "Buenas noches! Tienen airon de 4mg")
    consulta = minuscula
    for s in sorted(saludos, key=len, reverse=True):
        if consulta.startswith(s):
            consulta = re.sub(r"^[\s,!¡¿?.:-]+", "", consulta[len(s):]).strip()
            break

    consulta = re.sub(
        r"\b(tienen|tiene|hay|disponible|precio|precios|de|del|la|el|los|las|un|una|por favor)\b",
        " ",
        consulta
    )
    consulta = re.sub(r"\s+", " ", consulta).strip()

    return None, (consulta if consulta else texto_limpio)


def formatear_respuesta_productos(termino: str, productos: list) -> str:
    # 'productos' es tu lista de diccionarios/objetos con codigo, descripcion, usd, bs, cop
    if not productos:
        return (
            f"No encontré resultados para *{termino}* en este momento. "
            f"Verifica el nombre del producto o escribe *asesor* y pronto seras atendido por nuestro personal.\n\n"
            f"{MENSAJE_DESPEDIDA}"
        )

    lineas = [f"Resultados para *{termino}*:\n"]
    for p in productos:
        # Se omite intencionalmente el campo de stock
        lineas.append(
            f"• *{p['descripcion']}* (Cód: {p['codigo']})\n"
            f"  USD: ${p['usd']:.2f} | Bs. {p['bs']:,.2f} | COP {p['cop']:,.0f}"
        )

    lineas.append(f"\n{MENSAJE_DESPEDIDA}")
    return "\n".join(lineas)
