def normalize_newlines(text: str) -> str:
    return (
        (text or "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u2028", "\n")
        .replace("\u2029", "\n")
    )


def format_price(price):
    return f"S/ {float(price):,.2f}"


def render_template(
    template,
    title,
    description,
    price,
    delivery_method,
    payment_method,
    contact_number,
):
    values = {
        "{NOMBRE_PRODUCTO}": normalize_newlines(title),
        "{DESCRIPCION}": normalize_newlines(description),
        "{PRECIO}": format_price(price),
        "{METODO_ENTREGA}": normalize_newlines(delivery_method),
        "{FORMA_PAGO}": normalize_newlines(payment_method),
        "{CONTACTO}": normalize_newlines(contact_number),
    }

    result = normalize_newlines(template)
    for placeholder, value in values.items():
        result = result.replace(placeholder, value)
    return result
