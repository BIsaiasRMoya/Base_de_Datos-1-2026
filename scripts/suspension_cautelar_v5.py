#!/usr/bin/env python3

import argparse
import os
from datetime import (
    datetime,
    timedelta,
    timezone,
)

import psycopg2
from dotenv import load_dotenv


load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "gob"),
    "user": os.getenv("DB_USER", "benjamin"),
    "password": os.getenv("DB_PASSWORD", "4321"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}


# ============================================================
# RATIFICADORES PERMITIDOS
# ============================================================

def obtener_ratificadores(
    cur,
    user_id
):

    permitidos = set()

    # --------------------------------------------------------
    # Madrina / inviter
    # --------------------------------------------------------

    cur.execute(
        """
        SELECT inviter_id
        FROM users
        WHERE id = %s
        """,
        (user_id,)
    )

    fila = cur.fetchone()

    if fila is None:

        return set()

    inviter_id = fila[0]

    if inviter_id is not None:

        permitidos.add(
            str(inviter_id)
        )

        # ----------------------------------------------------
        # Abuela / inviter del inviter
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT inviter_id
            FROM users
            WHERE id = %s
            """,
            (inviter_id,)
        )

        fila_abuela = (
            cur.fetchone()
        )

        if (
            fila_abuela is not None
            and fila_abuela[0]
            is not None
        ):

            permitidos.add(
                str(fila_abuela[0])
            )

    # --------------------------------------------------------
    # Génesis
    # --------------------------------------------------------

    cur.execute(
        """
        SELECT id
        FROM users
        WHERE inviter_id IS NULL
          AND status = 'active'
        """
    )

    for row in cur.fetchall():

        permitidos.add(
            str(row[0])
        )

    return permitidos


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Suspensión cautelar v5"
    )

    parser.add_argument(
        "--dias",
        type=int,
        default=30
    )

    args = parser.parse_args()

    if (
        args.dias < 1
        or args.dias > 30
    ):

        raise ValueError(
            "La suspensión cautelar debe "
            "durar entre 1 y 30 días."
        )

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    conn.autocommit = False

    cur = conn.cursor()

    try:

        # ====================================================
        # ELEGIR PERSONA A SUSPENDER
        # ====================================================

        cur.execute(
            """
            SELECT id, display_name

            FROM users

            WHERE status = 'active'

              AND inviter_id IS NOT NULL

            ORDER BY id

            LIMIT 1
            """
        )

        objetivo = cur.fetchone()

        if objetivo is None:

            raise RuntimeError(
                "No existe usuario activo "
                "apto para la prueba."
            )

        (
            user_id,
            nombre_objetivo
        ) = objetivo

        user_id = str(user_id)

        # ====================================================
        # SOLICITANTE
        # ====================================================

        cur.execute(
            """
            SELECT id, display_name

            FROM users

            WHERE status = 'active'
              AND id <> %s

            ORDER BY id DESC

            LIMIT 1
            """,
            (user_id,)
        )

        solicitante = cur.fetchone()

        if solicitante is None:

            raise RuntimeError(
                "No existe solicitante."
            )

        (
            requested_by,
            nombre_solicitante
        ) = solicitante

        requested_by = str(
            requested_by
        )

        # ====================================================
        # RATIFICADOR VÁLIDO
        # ====================================================

        permitidos = obtener_ratificadores(
            cur,
            user_id
        )

        if not permitidos:

            raise RuntimeError(
                "No existe ratificador válido."
            )

        cur.execute(
            """
            SELECT id, display_name

            FROM users

            WHERE id = ANY(%s::uuid[])
              AND status = 'active'

            ORDER BY id

            LIMIT 1
            """,
            (list(permitidos),)
        )

        ratificador = cur.fetchone()

        if ratificador is None:

            raise RuntimeError(
                "No existe ratificador "
                "activo disponible."
            )

        (
            ratified_by,
            nombre_ratificador
        ) = ratificador

        ratified_by = str(
            ratified_by
        )

        # ====================================================
        # CREAR SUSPENSIÓN
        # ====================================================

        started_at = datetime.now(
            timezone.utc
        )

        expires_at = (
            started_at
            + timedelta(
                days=args.dias
            )
        )

        cur.execute(
            """
            INSERT INTO cautelary_suspensions
            (
                user_id,
                requested_by,
                ratified_by,
                started_at,
                expires_at,
                lifted_at
            )
            VALUES
            (%s, %s, %s, %s, %s, NULL)
            """,
            (
                user_id,
                requested_by,
                ratified_by,
                started_at,
                expires_at
            )
        )

        cur.execute(
            """
            UPDATE users
            SET status =
                'suspended_cautelar'
            WHERE id = %s
            """,
            (user_id,)
        )

        conn.commit()

        print()
        print("SUSPENSIÓN CAUTELAR V5")
        print("================================")

        print(
            f"Persona: "
            f"{nombre_objetivo}"
        )

        print(
            f"Solicitada por: "
            f"{nombre_solicitante}"
        )

        print(
            f"Ratificada por: "
            f"{nombre_ratificador}"
        )

        print(
            f"Duración: "
            f"{args.dias} días"
        )

        print()
        print(
            "✅ Suspensión cautelar activa."
        )

        print("================================")

    except Exception as error:

        conn.rollback()

        print()
        print("Error:")
        print(error)

        raise

    finally:

        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
