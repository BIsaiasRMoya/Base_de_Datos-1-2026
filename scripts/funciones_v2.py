import hashlib

from funciones_v1 import (
    calcular_vecindario_local,
)


# ============================================================
# HASH DETERMINISTA
# ============================================================

def hash_determinista_v2(
    semilla,
    user_id,
    contexto
):
    """
    Hash reproducible utilizado para el sorteo
    de jurados inter-rama.
    """

    texto = (
        f"{semilla}|"
        f"{user_id}|"
        f"{contexto}"
    )

    digest = hashlib.sha256(
        texto.encode("utf-8")
    ).hexdigest()

    return int(
        digest,
        16
    )


# ============================================================
# RAÍZ DE LA RAMA
# ============================================================

def obtener_raiz_rama(
    usuarios,
    user_id
):
    """
    Devuelve el fundador que constituye
    la raíz de la rama del usuario.

    En v2 la raíz NO está almacenada.
    Se calcula siguiendo inviter_id.
    """

    if user_id not in usuarios:
        return None

    actual = user_id

    visitados = set()

    while True:

        # Protección ante ciclos inválidos.
        if actual in visitados:
            raise ValueError(
                "Se detectó un ciclo "
                "en el grafo de invitaciones."
            )

        visitados.add(
            actual
        )

        datos = usuarios.get(
            actual
        )

        if datos is None:
            return None

        inviter_id = datos[
            "inviter_id"
        ]

        # Llegamos al fundador.
        if inviter_id is None:
            return actual

        actual = inviter_id


# ============================================================
# AGRUPAR USUARIOS POR RAMA
# ============================================================

def agrupar_por_rama(
    usuarios
):
    """
    Devuelve:

    {
        raiz_A: [usuarios rama A],
        raiz_B: [usuarios rama B],
        ...
    }
    """

    ramas = {}

    for user_id in usuarios:

        raiz = obtener_raiz_rama(
            usuarios,
            user_id
        )

        if raiz is None:
            continue

        if raiz not in ramas:
            ramas[raiz] = []

        ramas[raiz].append(
            user_id
        )

    for raiz in ramas:

        ramas[raiz] = sorted(
            ramas[raiz]
        )

    return ramas


# ============================================================
# JURADO INTER-RAMA
# ============================================================

def sortear_jurado_inter_rama(
    usuarios,
    proposer_id,
    semilla,
    contexto
):
    """
    Selecciona determinísticamente:

    UNA persona de CADA rama distinta
    a la del proponente.

    El contexto debe identificar la admisión,
    para que distintas invitaciones puedan
    producir jurados distintos.
    """

    if proposer_id not in usuarios:
        return set()

    rama_proponente = obtener_raiz_rama(
        usuarios,
        proposer_id
    )

    ramas = agrupar_por_rama(
        usuarios
    )

    jurados = set()

    for raiz_rama, miembros in sorted(
        ramas.items()
    ):

        # No se selecciona alguien
        # de la misma rama.
        if raiz_rama == rama_proponente:
            continue

        if not miembros:
            continue

        ordenados = sorted(
            miembros,
            key=lambda candidato:
                hash_determinista_v2(
                    semilla,
                    candidato,
                    (
                        f"jurado:"
                        f"{contexto}:"
                        f"{raiz_rama}"
                    )
                )
        )

        elegido = ordenados[0]

        jurados.add(
            elegido
        )

    return jurados


# ============================================================
# VECINDARIO DE VOTACIÓN V2
# ============================================================

def calcular_vecindario_v2(
    usuarios,
    proposer_id,
    semilla,
    contexto,
    hermanos_persistidos=None
):
    """
    v2:

    vecindario de votación =
        vecindario local
        +
        jurado inter-rama
    """

    locales = calcular_vecindario_local(
        usuarios,
        proposer_id,
        semilla,
        hermanos_persistidos
    )

    jurados = sortear_jurado_inter_rama(
        usuarios,
        proposer_id,
        semilla,
        contexto
    )

    vecindario = (
        set(locales)
        | set(jurados)
    )

    vecindario.discard(
        proposer_id
    )

    return {
        "locales": set(locales),
        "jurados": set(jurados),
        "total": vecindario,
    }
