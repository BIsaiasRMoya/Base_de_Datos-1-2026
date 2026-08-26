import hashlib
import math


# ============================================================
# SORTEO DETERMINISTA
# ============================================================

def hash_determinista(semilla, user_id, contexto):
    """
    Genera un número reproducible utilizando SHA-256.

    Mismos parámetros -> mismo resultado.
    """
    texto = f"{semilla}|{user_id}|{contexto}"

    resultado = hashlib.sha256(
        texto.encode("utf-8")
    ).hexdigest()

    return int(resultado, 16)


def sortear_hermanos(semilla, user_id, hermanos, cantidad):
    """
    Selecciona hermanos de manera determinista.
    """

    if cantidad <= 0:
        return []

    if not hermanos:
        return []

    hermanos = sorted(hermanos)

    # Si existen menos hermanos que los necesarios,
    # se utilizan todos.
    if cantidad >= len(hermanos):
        return hermanos

    hermanos_ordenados = sorted(
        hermanos,
        key=lambda hermano: hash_determinista(
            semilla,
            user_id,
            f"hermano:{hermano}"
        )
    )

    return hermanos_ordenados[:cantidad]


# ============================================================
# GRAFO
# ============================================================

def obtener_ascendentes(usuarios, user_id):
    """
    Obtiene hasta dos ascendentes:

    1. Madrina/padrino
    2. Abuela/abuelo
    """

    ascendentes = []

    actual = user_id

    for _ in range(2):

        if actual not in usuarios:
            break

        inviter_id = usuarios[actual]["inviter_id"]

        if inviter_id is None:
            break

        ascendentes.append(inviter_id)

        actual = inviter_id

    return ascendentes


def obtener_hijos(usuarios, user_id):
    """
    Devuelve todos los usuarios invitados directamente
    por user_id.
    """

    return [
        uid
        for uid, datos in usuarios.items()
        if datos["inviter_id"] == user_id
    ]


def obtener_hermanos(usuarios, user_id):
    """
    Devuelve las personas que tienen la misma madrina/padrino.
    """

    if user_id not in usuarios:
        return []

    inviter_id = usuarios[user_id]["inviter_id"]

    # Los fundadores no tienen madrina/padrino.
    if inviter_id is None:
        return []

    return [
        uid
        for uid, datos in usuarios.items()
        if uid != user_id
        and datos["inviter_id"] == inviter_id
    ]


# ============================================================
# VECINDARIO LOCAL
# ============================================================

def calcular_vecindario_local(
    usuarios,
    user_id,
    semilla,
    hermanos_persistidos=None
):
    """
    Vecindario local:

    - ascendentes (máximo 2)
    - hijos
    - hermanos sorteados

    Caso especial del génesis:
    los demás fundadores también forman parte
    de su vecindario.
    """

    if user_id not in usuarios:
        return set()

    ascendentes = obtener_ascendentes(
        usuarios,
        user_id
    )

    hijos = obtener_hijos(
        usuarios,
        user_id
    )

    vecindario = set()

    # ========================================
    # Caso especial: fundador
    # ========================================

    if usuarios[user_id]["inviter_id"] is None:

        otros_fundadores = {
            uid
            for uid, datos in usuarios.items()
            if datos["inviter_id"] is None
            and uid != user_id
        }

        vecindario.update(
            otros_fundadores
        )

        vecindario.update(
            hijos
        )

        return vecindario

    # ========================================
    # Usuario normal
    # ========================================

    if hermanos_persistidos is not None:

        hermanos_sorteados = list(
            hermanos_persistidos
        )

    else:

        hermanos = obtener_hermanos(
            usuarios,
            user_id
        )

        cantidad = len(
            ascendentes
        )

        hermanos_sorteados = sortear_hermanos(
            semilla,
            user_id,
            hermanos,
            cantidad
        )

    vecindario.update(
        ascendentes
    )

    vecindario.update(
        hijos
    )

    vecindario.update(
        hermanos_sorteados
    )

    vecindario.discard(
        user_id
    )

    return vecindario


# ============================================================
# CUÓRUM
# ============================================================

def calcular_cuorum(tamano_vecindario):
    """
    Cuórum = ceil(tamaño del vecindario / 2)
    """

    if tamano_vecindario <= 0:
        return 0

    return math.ceil(
        tamano_vecindario / 2
    )
