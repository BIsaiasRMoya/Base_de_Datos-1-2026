import hashlib

from funciones_v1 import (
    calcular_vecindario_local,
)


# ============================================================
# HASH DETERMINISTA
# ============================================================

def hash_determinista_v3(
    semilla,
    user_id,
    contexto
):
    """
    Devuelve un número reproducible mediante SHA-256.
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
# BALANCEO DE UNA RAMA
# ============================================================

def seleccionar_menos_cargado(
    candidatos,
    cargas,
    semilla,
    contexto
):
    """
    Selecciona al usuario con menor cantidad
    de asignaciones activas.

    Si existe empate, se utiliza hash
    determinista.
    """

    if not candidatos:
        return None

    carga_minima = min(
        cargas.get(
            candidato,
            0
        )
        for candidato in candidatos
    )

    empatados = [
        candidato
        for candidato in candidatos
        if cargas.get(
            candidato,
            0
        ) == carga_minima
    ]

    elegido = min(
        empatados,
        key=lambda candidato:
            hash_determinista_v3(
                semilla,
                candidato,
                contexto
            )
    )

    return elegido


# ============================================================
# ASIGNAR VECINOS INTER-RAMA
# ============================================================

def calcular_vecinos_persistentes(
    usuarios,
    user_id,
    cargas,
    semilla
):
    """
    Selecciona una persona de cada rama distinta
    a la del usuario.

    Parámetros:

    usuarios = {
        id: {
            "rama_root_id": ...,
            "status": ...
        }
    }

    cargas = {
        id: cantidad_asignaciones_activas
    }

    Devuelve:

    {
        raiz_rama: vecino_elegido
    }
    """

    if user_id not in usuarios:
        return {}

    rama_usuario = usuarios[
        user_id
    ]["rama_root_id"]

    # ----------------------------------------
    # Agrupar miembros activos por rama
    # ----------------------------------------

    ramas = {}

    for uid, datos in usuarios.items():

        if datos.get(
            "status"
        ) != "active":

            continue

        raiz = datos[
            "rama_root_id"
        ]

        if raiz not in ramas:
            ramas[raiz] = []

        ramas[raiz].append(uid)

    resultado = {}

    # ----------------------------------------
    # Elegir uno por cada OTRA rama
    # ----------------------------------------

    for raiz in sorted(ramas):

        if raiz == rama_usuario:
            continue

        candidatos = ramas[
            raiz
        ]

        elegido = seleccionar_menos_cargado(
            candidatos=candidatos,
            cargas=cargas,
            semilla=semilla,
            contexto=(
                f"persistente:"
                f"{user_id}:"
                f"{raiz}"
            )
        )

        if elegido is not None:

            resultado[raiz] = elegido

            # Muy importante:
            # actualizar la carga EN MEMORIA
            # para mantener el balance.
            cargas[elegido] = (
                cargas.get(elegido, 0)
                + 1
            )

    return resultado


# ============================================================
# VECINDARIO EXPANDIDO V3
# ============================================================

def calcular_vecindario_v3(
    usuarios,
    user_id,
    semilla,
    hermanos_persistidos,
    vecinos_persistentes
):
    """
    Vecindario v3:

    vecindario local
    +
    vecinos inter-rama persistentes
    """

    usuarios_local = {
        uid: {
            "inviter_id":
                datos["inviter_id"]
        }
        for uid, datos in usuarios.items()
    }

    locales = calcular_vecindario_local(
        usuarios_local,
        user_id,
        semilla,
        hermanos_persistidos=
            hermanos_persistidos
    )

    persistentes = set(
        vecinos_persistentes
    )

    # Si una persona ya aparece como local,
    # no debe votar dos veces.
    persistentes = (
        persistentes
        - locales
    )

    total = (
        set(locales)
        | persistentes
    )

    total.discard(
        user_id
    )

    return {
        "locales": set(locales),
        "persistentes": persistentes,
        "total": total,
    }
