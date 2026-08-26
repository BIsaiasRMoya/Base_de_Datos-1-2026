from funciones_v1 import calcular_cuorum


# ============================================================
# SEPARAR VECINDARIO SEGÚN ACTIVIDAD
# ============================================================

def separar_vecindario_por_actividad(
    usuarios,
    vecindario
):
    """
    Divide el vecindario en miembros activos e inactivos.

    usuarios:
    {
        id: {
            "status": "active" | "inactive",
            ...
        }
    }
    """

    activos = set()
    inactivos = set()

    for user_id in vecindario:

        datos = usuarios.get(user_id)

        if datos is None:
            continue

        if datos["status"] == "active":

            activos.add(user_id)

        elif datos["status"] == "inactive":

            inactivos.add(user_id)

    return {
        "activos": activos,
        "inactivos": inactivos,
    }


# ============================================================
# CUÓRUM V4
# ============================================================

def calcular_cuorum_v4(
    vecindario_activo
):
    """
    En v4 los miembros inactivos no bloquean.

    Por ello el cuórum se calcula sobre
    los miembros activos del vecindario.
    """

    return calcular_cuorum(
        len(vecindario_activo)
    )
