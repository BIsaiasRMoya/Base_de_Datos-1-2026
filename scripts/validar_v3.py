#!/usr/bin/env python3

import argparse
import os

import psycopg2
from dotenv import load_dotenv

from funciones_v1 import (
    calcular_cuorum,
)

from funciones_v2 import (
    obtener_raiz_rama,
)

from funciones_v3 import (
    calcular_vecindario_v3,
)


load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "gob"),
    "user": os.getenv("DB_USER", "benjamin"),
    "password": os.getenv("DB_PASSWORD", "4321"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}


# ============================================================
# CARGAR RED EN UNA FECHA
# ============================================================

def cargar_usuarios_hasta(
    cur,
    fecha
):

    cur.execute(
        """
        SELECT
            id,
            inviter_id,
            rama_root_id,
            status

        FROM users

        WHERE principles_accepted_at <= %s
        """,
        (fecha,)
    )

    usuarios = {}

    for (
        uid,
        inviter,
        rama,
        status
    ) in cur.fetchall():

        usuarios[str(uid)] = {

            "inviter_id":
                str(inviter)
                if inviter is not None
                else None,

            "rama_root_id":
                str(rama)
                if rama is not None
                else None,

            "status":
                str(status),
        }

    return usuarios


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


def cargar_persistentes_en_fecha(
    cur,
    user_id,
    fecha
):

    cur.execute(
        """
        SELECT neighbor_id

        FROM inter_rama_assignments

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

    parser = argparse.ArgumentParser()

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

    # ========================================================
    # 1. VALIDAR RAMA_ROOT_ID
    # ========================================================

    cur.execute(
        """
        SELECT
            id,
            inviter_id,
            rama_root_id
        FROM users
        """
    )

    filas = cur.fetchall()

    usuarios_simple = {}

    ramas_guardadas = {}

    for (
        user_id,
        inviter_id,
        rama_root_id
    ) in filas:

        uid = str(user_id)

        usuarios_simple[uid] = {
            "inviter_id":
                str(inviter_id)
                if inviter_id is not None
                else None
        }

        ramas_guardadas[uid] = (
            str(rama_root_id)
            if rama_root_id is not None
            else None
        )

    for uid in usuarios_simple:

        raiz_calculada = (
            obtener_raiz_rama(
                usuarios_simple,
                uid
            )
        )

        if ramas_guardadas[uid] != raiz_calculada:

            errores.append(
                f"{uid}: rama_root_id "
                f"incorrecto."
            )

    # ========================================================
    # 2. VALIDAR ASIGNACIONES ACTIVAS
    # ========================================================

    cur.execute(
        """
        SELECT
            a.id,
            a.user_id,
            a.neighbor_id,
            a.other_rama_root_id,
            u.rama_root_id,
            n.rama_root_id,
            n.status

        FROM inter_rama_assignments a

        JOIN users u
            ON u.id = a.user_id

        JOIN users n
            ON n.id = a.neighbor_id

        WHERE a.replaced_at IS NULL
        """
    )

    for (
        assignment_id,
        user_id,
        neighbor_id,
        other_root,
        user_root,
        neighbor_root,
        neighbor_status
    ) in cur.fetchall():

        # No puede ser misma rama.
        if user_root == neighbor_root:

            errores.append(
                f"Asignación {assignment_id}: "
                f"vecino de la misma rama."
            )

        # other_rama_root_id debe coincidir.
        if other_root != neighbor_root:

            errores.append(
                f"Asignación {assignment_id}: "
                f"other_rama_root_id incorrecto."
            )

        if str(neighbor_status) != "active":

            errores.append(
                f"Asignación {assignment_id}: "
                f"vecino no activo."
            )

    # ========================================================
    # 3. EXACTAMENTE UNA ASIGNACIÓN POR RAMA EXTERNA
    # ========================================================

    cur.execute(
        """
        SELECT
            user_id,
            other_rama_root_id,
            COUNT(*)

        FROM inter_rama_assignments

        WHERE replaced_at IS NULL

        GROUP BY
            user_id,
            other_rama_root_id

        HAVING COUNT(*) <> 1
        """
    )

    duplicadas = cur.fetchall()

    for (
        user_id,
        rama,
        cantidad
    ) in duplicadas:

        errores.append(
            f"{user_id}: tiene "
            f"{cantidad} vecinos activos "
            f"para la rama {rama}."
        )

    # ========================================================
    # 4. VALIDAR DELEGACIONES
    # ========================================================

    cur.execute(
        """
        SELECT
            d.id,
            d.delegator_id,
            d.delegate_to_id,
            d.accepted,
            d.decided_at,
            a.replaced_by,
            a.replaced_at,
            u1.rama_root_id,
            u2.rama_root_id

        FROM delegation_requests d

        JOIN inter_rama_assignments a
            ON a.id = d.assignment_id

        JOIN users u1
            ON u1.id = d.delegator_id

        JOIN users u2
            ON u2.id = d.delegate_to_id
        """
    )

    for (
        request_id,
        delegator_id,
        delegate_to_id,
        accepted,
        decided_at,
        replaced_by,
        replaced_at,
        rama1,
        rama2
    ) in cur.fetchall():

        # Delegador y delegado deben pertenecer
        # a la misma rama.
        if rama1 != rama2:

            errores.append(
                f"Delegación {request_id}: "
                f"delegador y delegado "
                f"pertenecen a ramas distintas."
            )

        # ----------------------------------------
        # Solicitud aceptada
        # ----------------------------------------

        if accepted is True:

            if replaced_by != delegate_to_id:

                errores.append(
                    f"Delegación {request_id}: "
                    f"aceptada pero no aplicada."
                )

            if replaced_at is None:

                errores.append(
                    f"Delegación {request_id}: "
                    f"aceptada pero sin fecha "
                    f"de reemplazo."
                )

        # ----------------------------------------
        # Solicitud rechazada
        # ----------------------------------------

        elif accepted is False:

            # Solo sería un error si el reemplazo
            # ya hubiera ocurrido al momento
            # de rechazar esta solicitud.
            #
            # Un reemplazo POSTERIOR puede provenir
            # de otra solicitud aceptada.
            if (
                replaced_by == delegate_to_id
                and replaced_at is not None
                and replaced_at <= decided_at
            ):

                errores.append(
                    f"Delegación {request_id}: "
                    f"rechazada pero fue aplicada "
                    f"antes o al momento del rechazo."
                )




    # ========================================================
    # 5. VALIDAR INVITACIONES V3
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

        WHERE candidate_email
              LIKE 'candidato_v3_%'

        ORDER BY opened_at
        """
    )

    invitaciones = cur.fetchall()

    votos_revisados = 0

    for (
        invitation_id,
        proposer_id,
        opened_at,
        closes_at,
        status
    ) in invitaciones:

        proposer = str(
            proposer_id
        )

        usuarios = cargar_usuarios_hasta(
            cur,
            opened_at
        )

        hermanos = cargar_hermanos_en_fecha(
            cur,
            proposer,
            opened_at
        )

        persistentes = (
            cargar_persistentes_en_fecha(
                cur,
                proposer,
                opened_at
            )
        )

        resultado = calcular_vecindario_v3(
            usuarios=usuarios,
            user_id=proposer,
            semilla=args.semilla,
            hermanos_persistidos=hermanos,
            vecinos_persistentes=persistentes
        )

        locales = resultado[
            "locales"
        ]

        persistentes = resultado[
            "persistentes"
        ]

        total = resultado[
            "total"
        ]

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

        votos_si = 0
        votantes = set()

        for (
            voter_id,
            voter_role,
            choice,
            cast_at
        ) in cur.fetchall():

            votos_revisados += 1

            voter = str(voter_id)

            votantes.add(voter)

            if voter not in total:

                errores.append(
                    f"Invitación {invitation_id}: "
                    f"votante fuera del vecindario."
                )

            if voter in locales:

                if str(voter_role) != "local":

                    errores.append(
                        f"Invitación {invitation_id}: "
                        f"rol local incorrecto."
                    )

            elif voter in persistentes:

                if str(voter_role) != "persistente":

                    errores.append(
                        f"Invitación {invitation_id}: "
                        f"rol persistente incorrecto."
                    )

            if not (
                opened_at
                <= cast_at
                <= closes_at
            ):

                errores.append(
                    f"Invitación {invitation_id}: "
                    f"voto fuera del plazo."
                )

            if str(choice) == "yes":
                votos_si += 1

        if votantes != total:

            errores.append(
                f"Invitación {invitation_id}: "
                f"conjunto de votantes "
                f"no coincide con vecindario."
            )

        cuorum = calcular_cuorum(
            len(total)
        )

        esperado = (
            "closed_approved"
            if votos_si >= cuorum
            else "expired"
        )

        if str(status) != esperado:

            errores.append(
                f"Invitación {invitation_id}: "
                f"estado incorrecto."
            )

    # ========================================================
    # RESULTADO
    # ========================================================

    cur.close()
    conn.close()

    print()
    print("VALIDACIÓN V3")
    print("================================")

    print(
        f"Invitaciones v3 revisadas: "
        f"{len(invitaciones)}"
    )

    print(
        f"Votos revisados: "
        f"{votos_revisados}"
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
            "de v3 se cumplen."
        )

    print("================================")


if __name__ == "__main__":
    main()
