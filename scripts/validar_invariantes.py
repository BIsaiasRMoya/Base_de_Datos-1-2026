#!/usr/bin/env python3

import argparse
import os

import psycopg2
from dotenv import load_dotenv

from funciones_v1 import (
    calcular_vecindario_local,
    calcular_cuorum,
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
# CARGAR USUARIOS EXISTENTES EN UNA FECHA
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
        "Validación de invariantes de v1"
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

    # ========================================================
    # 1. VALIDAR ESTRUCTURA DEL ÁRBOL
    # ========================================================

    cur.execute(
        """
        SELECT
            id,
            inviter_id,
            principles_accepted_at
        FROM users
        ORDER BY principles_accepted_at
        """
    )

    usuarios_previos = set()

    for user_id, inviter_id, fecha in cur.fetchall():

        uid = str(user_id)

        inviter = (
            str(inviter_id)
            if inviter_id is not None
            else None
        )

        # Un usuario no puede invitarse a sí mismo.
        if uid == inviter:

            errores.append(
                f"Usuario {uid}: "
                f"se invita a sí mismo."
            )

        # Si no es fundador, su inviter
        # debe haber ingresado antes.
        if inviter is not None:

            if inviter not in usuarios_previos:

                errores.append(
                    f"Usuario {uid}: "
                    f"su inviter no pertenecía "
                    f"a la red previamente."
                )

        usuarios_previos.add(uid)

    # ========================================================
    # 2. VALIDAR SIBLING_ASSIGNMENTS
    # ========================================================

    cur.execute(
        """
        SELECT
            s.user_id,
            s.sibling_id,
            u.inviter_id,
            h.inviter_id
        FROM sibling_assignments s

        JOIN users u
            ON u.id = s.user_id

        JOIN users h
            ON h.id = s.sibling_id
        """
    )

    for (
        user_id,
        sibling_id,
        inviter_usuario,
        inviter_hermano
    ) in cur.fetchall():

        if user_id == sibling_id:

            errores.append(
                f"{user_id}: "
                f"fue asignado como su "
                f"propio hermano."
            )

        if inviter_usuario != inviter_hermano:

            errores.append(
                f"{user_id} y {sibling_id}: "
                f"no tienen el mismo inviter."
            )

    # ========================================================
    # 3. VALIDAR INVITACIONES Y VOTOS
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

        proposer = str(
            proposer_id
        )

        # ----------------------------------------------------
        # Reconstruir la red como era al abrir la invitación
        # ----------------------------------------------------

        usuarios = cargar_usuarios_hasta(
            cur,
            opened_at
        )

        if proposer not in usuarios:

            errores.append(
                f"Invitación {invitation_id}: "
                f"el proponente no pertenecía "
                f"a la red al abrirla."
            )

            continue

        # ----------------------------------------------------
        # Hermanos persistentes existentes en ese momento
        # ----------------------------------------------------

        hermanos = cargar_hermanos_en_fecha(
            cur,
            proposer,
            opened_at
        )

        # ----------------------------------------------------
        # Calcular vecindario correcto
        # ----------------------------------------------------

        vecindario = calcular_vecindario_local(
            usuarios,
            proposer,
            args.semilla,
            hermanos_persistidos=hermanos
        )

        cuorum = calcular_cuorum(
            len(vecindario)
        )

        # ----------------------------------------------------
        # Obtener votos
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                voter_id,
                choice,
                cast_at
            FROM votes
            WHERE invitation_id = %s
            """,
            (invitation_id,)
        )

        votos_si = 0

        for (
            voter_id,
            choice,
            cast_at
        ) in cur.fetchall():

            votos_revisados += 1

            voter = str(
                voter_id
            )

            # INVARIANTE PRINCIPAL:
            # solo puede votar alguien
            # perteneciente al vecindario.
            if voter not in vecindario:

                errores.append(
                    f"Invitación {invitation_id}: "
                    f"el usuario {voter} votó "
                    f"sin pertenecer al vecindario."
                )

            # El voto debe realizarse
            # durante el período correspondiente.
            if not (
                opened_at
                <= cast_at
                <= closes_at
            ):

                errores.append(
                    f"Invitación {invitation_id}: "
                    f"voto emitido fuera "
                    f"del período permitido."
                )

            if choice == "yes":

                votos_si += 1

        # ----------------------------------------------------
        # Validar resultado
        # ----------------------------------------------------

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
                f"pero debería ser "
                f"{estado_esperado}. "
                f"SI={votos_si}, "
                f"cuórum={cuorum}."
            )

    # ========================================================
    # RESULTADO
    # ========================================================

    cur.close()
    conn.close()

    print()
    print("VALIDACIÓN DE V1")
    print("==============================")
    print(
        f"Invitaciones revisadas: "
        f"{invitaciones_revisadas}"
    )
    print(
        f"Votos revisados: "
        f"{votos_revisados}"
    )

    if errores:

        print()
        print(
            f"❌ Se encontraron "
            f"{len(errores)} errores:"
        )

        for error in errores:

            print(
                f" - {error}"
            )

    else:

        print()
        print(
            "✅ Todas las invariantes "
            "de v1 se cumplen."
        )

    print("==============================")


if __name__ == "__main__":
    main()
