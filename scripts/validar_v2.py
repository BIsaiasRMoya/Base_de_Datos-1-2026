#!/usr/bin/env python3

import argparse
import os

import psycopg2
from dotenv import load_dotenv

from funciones_v1 import calcular_cuorum

from funciones_v2 import (
    calcular_vecindario_v2,
    obtener_raiz_rama,
    agrupar_por_rama,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "gob"),
    "user": os.getenv("DB_USER", "benjamin"),
    "password": os.getenv("DB_PASSWORD", "4321"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}


# ============================================================
# USUARIOS EXISTENTES EN UNA FECHA
# ============================================================

def cargar_usuarios_hasta(cur, fecha):

    cur.execute(
        """
        SELECT id, inviter_id
        FROM users
        WHERE principles_accepted_at <= %s
        """,
        (fecha,)
    )

    usuarios = {}

    for user_id, inviter_id in cur.fetchall():

        usuarios[str(user_id)] = {
            "inviter_id":
                str(inviter_id)
                if inviter_id is not None
                else None
        }

    return usuarios


# ============================================================
# HERMANOS PERSISTIDOS EN UNA FECHA
# ============================================================

def cargar_hermanos_en_fecha(
    cur,
    user_id,
    fecha
):

    cur.execute(
        """
        SELECT sibling_id
        FROM sibling_assignments
        WHERE user_id = %s
          AND assigned_at <= %s
          AND (
                replaced_at IS NULL
                OR replaced_at > %s
              )
        """,
        (
            user_id,
            fecha,
            fecha
        )
    )

    return {
        str(row[0])
        for row in cur.fetchall()
    }


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Validación de invariantes v2"
    )

    parser.add_argument(
        "--semilla",
        type=int,
        default=42
    )

    args = parser.parse_args()

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    cur = conn.cursor()

    errores = []

    invitaciones_revisadas = 0
    votos_revisados = 0
    votos_locales = 0
    votos_jurado = 0

    # ========================================================
    # LEER INVITACIONES V2
    # ========================================================

    cur.execute(
        """
        SELECT
            id,
            proposer_id,
            opened_at,
            closes_at,
            status
        FROM invitations
        ORDER BY opened_at
        """
    )

    invitaciones = cur.fetchall()

    for (
        invitation_id,
        proposer_id,
        opened_at,
        closes_at,
        status
    ) in invitaciones:

        invitaciones_revisadas += 1

        invitation_id_str = str(
            invitation_id
        )

        proposer = str(
            proposer_id
        )

        # ====================================================
        # RECONSTRUIR RED EN ESE MOMENTO
        # ====================================================

        usuarios = cargar_usuarios_hasta(
            cur,
            opened_at
        )

        if proposer not in usuarios:

            errores.append(
                f"Invitación {invitation_id}: "
                f"proponente fuera de la red."
            )

            continue

        hermanos = cargar_hermanos_en_fecha(
            cur,
            proposer,
            opened_at
        )

        # ====================================================
        # RECALCULAR VECINDARIO V2
        # ====================================================

        resultado = calcular_vecindario_v2(
            usuarios=usuarios,
            proposer_id=proposer,
            semilla=args.semilla,
            contexto=invitation_id_str,
            hermanos_persistidos=hermanos
        )

        locales = set(
            resultado["locales"]
        )

        jurados_originales = set(
            resultado["jurados"]
        )

        # Igual que en simular_v2.py:
        # si alguien ya pertenece al vecindario local,
        # se registra como local.
        jurados = (
            jurados_originales
            - locales
        )

        vecindario_total = (
            locales | jurados
        )

        # ====================================================
        # VALIDAR JURADO INTER-RAMA
        # ====================================================

        rama_proponente = obtener_raiz_rama(
            usuarios,
            proposer
        )

        ramas = agrupar_por_rama(
            usuarios
        )

        otras_ramas = {
            raiz
            for raiz in ramas
            if raiz != rama_proponente
        }

        ramas_jurado = set()

        for jurado_id in jurados_originales:

            rama_jurado = obtener_raiz_rama(
                usuarios,
                jurado_id
            )

            if rama_jurado == rama_proponente:

                errores.append(
                    f"Invitación {invitation_id}: "
                    f"jurado {jurado_id} pertenece "
                    f"a la misma rama del proponente."
                )

            ramas_jurado.add(
                rama_jurado
            )

        if ramas_jurado != otras_ramas:

            errores.append(
                f"Invitación {invitation_id}: "
                f"el jurado no representa "
                f"exactamente una persona "
                f"de cada rama externa."
            )

        # ====================================================
        # LEER VOTOS REALES
        # ====================================================

        cur.execute(
            """
            SELECT
                voter_id,
                voter_role,
                choice,
                cast_at
            FROM votes
            WHERE invitation_id = %s
            """,
            (invitation_id,)
        )

        votos = cur.fetchall()

        votantes_reales = set()

        votos_si = 0

        for (
            voter_id,
            voter_role,
            choice,
            cast_at
        ) in votos:

            votos_revisados += 1

            voter = str(
                voter_id
            )

            role = str(
                voter_role
            )

            votantes_reales.add(
                voter
            )

            # ================================================
            # VALIDAR QUE PERTENEZCA AL VECINDARIO
            # ================================================

            if voter not in vecindario_total:

                errores.append(
                    f"Invitación {invitation_id}: "
                    f"{voter} votó sin pertenecer "
                    f"al vecindario v2."
                )

            # ================================================
            # VALIDAR voter_role
            # ================================================

            if voter in locales:

                votos_locales += 1

                if role != "local":

                    errores.append(
                        f"Invitación {invitation_id}: "
                        f"{voter} debería tener "
                        f"voter_role=local."
                    )

            elif voter in jurados:

                votos_jurado += 1

                if role != "jurado":

                    errores.append(
                        f"Invitación {invitation_id}: "
                        f"{voter} debería tener "
                        f"voter_role=jurado."
                    )

            # ================================================
            # VALIDAR FECHA DEL VOTO
            # ================================================

            if not (
                opened_at
                <= cast_at
                <= closes_at
            ):

                errores.append(
                    f"Invitación {invitation_id}: "
                    f"voto fuera del período "
                    f"permitido."
                )

            if choice == "yes":

                votos_si += 1

        # ====================================================
        # ¿VOTARON EXACTAMENTE LOS QUE CORRESPONDÍAN?
        # ====================================================

        faltantes = (
            vecindario_total
            - votantes_reales
        )

        sobrantes = (
            votantes_reales
            - vecindario_total
        )

        if faltantes:

            errores.append(
                f"Invitación {invitation_id}: "
                f"faltaron votantes "
                f"{sorted(faltantes)}"
            )

        if sobrantes:

            errores.append(
                f"Invitación {invitation_id}: "
                f"sobraron votantes "
                f"{sorted(sobrantes)}"
            )

        # ====================================================
        # VALIDAR CUÓRUM
        # ====================================================

        cuorum = calcular_cuorum(
            len(vecindario_total)
        )

        if votos_si >= cuorum:

            estado_esperado = (
                "closed_approved"
            )

        else:

            estado_esperado = (
                "expired"
            )

        if status != estado_esperado:

            errores.append(
                f"Invitación {invitation_id}: "
                f"estado={status}, "
                f"esperado={estado_esperado}, "
                f"SI={votos_si}, "
                f"cuórum={cuorum}."
            )

    # ========================================================
    # RESULTADO FINAL
    # ========================================================

    cur.close()
    conn.close()

    print()
    print("VALIDACIÓN V2")
    print("================================")

    print(
        f"Invitaciones revisadas: "
        f"{invitaciones_revisadas}"
    )

    print(
        f"Votos revisados: "
        f"{votos_revisados}"
    )

    print(
        f"Votos locales: "
        f"{votos_locales}"
    )

    print(
        f"Votos jurado: "
        f"{votos_jurado}"
    )

    print()

    if errores:

        print(
            f"❌ Se encontraron "
            f"{len(errores)} errores:"
        )

        for error in errores:

            print(
                f" - {error}"
            )

    else:

        print(
            "✅ Todas las invariantes "
            "de v2 se cumplen."
        )

    print("================================")


if __name__ == "__main__":
    main()
