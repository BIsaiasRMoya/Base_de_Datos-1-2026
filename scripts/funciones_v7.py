import math
from collections import Counter


# ============================================================
# CUÓRUM DE AUTO-GOBERNANZA
# ============================================================

def calcular_cuorum_regla(
    total_activos
):
    """
    Una modificación del reglamento
    requiere 2/3 de la red activa.

    Ejemplos:

    36 activos -> 24 SI
    40 activos -> 27 SI
    100 activos -> 67 SI
    """

    if total_activos < 0:

        raise ValueError(
            "total_activos no puede "
            "ser negativo."
        )

    if total_activos == 0:

        return 0

    return math.ceil(
        (2 * total_activos) / 3
    )


# ============================================================
# VALIDAR PLAZO DE DISCUSIÓN
# ============================================================

def plazo_discusion_valido(
    opened_at,
    closes_at
):
    """
    Una propuesta de regla debe permanecer
    abierta al menos 14 días.
    """

    duracion = (
        closes_at
        - opened_at
    )

    return (
        duracion.total_seconds()
        >= 14 * 24 * 60 * 60
    )


# ============================================================
# CONTAR VOTOS
# ============================================================

def contar_votos_regla(
    votos
):
    """
    votos:

    [
        "yes",
        "no",
        "abstain",
        ...
    ]
    """

    conteo = Counter(
        votos
    )

    return {
        "yes":
            conteo.get(
                "yes",
                0
            ),

        "no":
            conteo.get(
                "no",
                0
            ),

        "abstain":
            conteo.get(
                "abstain",
                0
            ),
    }


# ============================================================
# RESOLVER PROPUESTA
# ============================================================

def resolver_propuesta_regla(
    votos,
    total_activos
):
    """
    La aprobación requiere que los votos YES
    alcancen 2/3 de TODA la red activa.

    No basta con obtener 2/3 de quienes
    efectivamente votaron.
    """

    conteo = contar_votos_regla(
        votos
    )

    quorum = calcular_cuorum_regla(
        total_activos
    )

    aprobada = (
        conteo["yes"]
        >= quorum
    )

    return {
        "aprobada":
            aprobada,

        "quorum":
            quorum,

        "yes":
            conteo["yes"],

        "no":
            conteo["no"],

        "abstain":
            conteo["abstain"],
    }


# ============================================================
# SIGUIENTE VERSIÓN
# ============================================================

def siguiente_version(
    versiones
):
    """
    versiones:
    iterable de números de versión existentes.
    """

    versiones = list(
        versiones
    )

    if not versiones:

        return 1

    return (
        max(versiones)
        + 1
    )
