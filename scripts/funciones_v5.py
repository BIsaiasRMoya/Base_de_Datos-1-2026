import hashlib


# ============================================================
# HASH DETERMINISTA
# ============================================================

def hash_determinista_v5(
    semilla,
    user_id,
    contexto
):
    """
    Hash reproducible para el sorteo disciplinario.
    """

    texto = (
        f"{semilla}|"
        f"{user_id}|"
        f"{contexto}"
    )

    digest = hashlib.sha256(
        texto.encode("utf-8")
    ).hexdigest()

    return int(digest, 16)


# ============================================================
# CANDIDATOS ELEGIBLES
# ============================================================

def obtener_candidatos_jurado(
    usuarios,
    complainant_id,
    accused_id,
    vecindario_complainant,
    vecindario_accused,
    excluir=None
):
    """
    Obtiene las personas elegibles para un jurado.

    Reglas:

    - solamente miembros active;
    - fuera del vecindario del denunciante;
    - fuera del vecindario del denunciado;
    - denunciante y denunciado no participan;
    - permite excluir jurados anteriores,
      útil para recusaciones o revisión.
    """

    if excluir is None:
        excluir = set()

    excluidos = set(
        vecindario_complainant
    )

    excluidos.update(
        vecindario_accused
    )

    # Salvaguarda de implementación:
    # las partes del conflicto tampoco
    # pueden formar parte del jurado.
    excluidos.add(
        complainant_id
    )

    excluidos.add(
        accused_id
    )

    excluidos.update(
        excluir
    )

    candidatos = []

    for user_id, datos in usuarios.items():

        if datos["status"] != "active":
            continue

        if user_id in excluidos:
            continue

        candidatos.append(
            user_id
        )

    return sorted(
        candidatos
    )


# ============================================================
# SORTEO DE JURADO
# ============================================================

def sortear_jurado_disciplinario(
    usuarios,
    complainant_id,
    accused_id,
    vecindario_complainant,
    vecindario_accused,
    semilla,
    process_id,
    cantidad=7,
    excluir=None
):
    """
    Sortea un jurado disciplinario reproducible.

    Devuelve exactamente `cantidad` miembros.
    Si la red no tiene suficientes personas
    elegibles, lanza una excepción.
    """

    candidatos = obtener_candidatos_jurado(
        usuarios=usuarios,
        complainant_id=complainant_id,
        accused_id=accused_id,
        vecindario_complainant=
            vecindario_complainant,
        vecindario_accused=
            vecindario_accused,
        excluir=excluir
    )

    if len(candidatos) < cantidad:

        raise ValueError(
            "No existen suficientes miembros "
            "elegibles para formar un jurado "
            f"de {cantidad} personas. "
            f"Disponibles: {len(candidatos)}."
        )

    ordenados = sorted(
        candidatos,
        key=lambda candidato:
            hash_determinista_v5(
                semilla,
                candidato,
                (
                    f"jurado-disciplinario:"
                    f"{process_id}"
                )
            )
    )

    return ordenados[
        :cantidad
    ]
