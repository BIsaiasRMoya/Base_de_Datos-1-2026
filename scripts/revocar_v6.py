#!/usr/bin/env python3

import argparse
import math
import os
from datetime import timedelta

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
# CUÓRUM
# ============================================================

def calcular_dos_tercios(
    total
):

    return math.ceil(
        (2 * total) / 3
    )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Revocación de mandato técnico v6"
    )

    parser.add_argument(
        "--votos-si",
        type=int,
        default=None
    )

    args = parser.parse_args()

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    conn.autocommit = False

    cur = conn.cursor()

    try:

        # ====================================================
        # MANDATO VIGENTE
        # ====================================================

        cur.execute(
            """
            SELECT
                tr.user_id,
                u.display_name,
                tr.granted_at,
                tr.granted_until

            FROM technical_roles tr

            JOIN users u
                ON u.id = tr.user_id

            WHERE tr.revoked_at IS NULL

            ORDER BY tr.granted_at DESC

            LIMIT 1
            """
        )

        mandato = cur.fetchone()

        if mandato is None:

            raise RuntimeError(
                "No existe mandato técnico "
                "sin revocar."
            )

        (
            technical_user_id,
            technical_name,
            granted_at,
            granted_until
        ) = mandato

        # ====================================================
        # RED ACTIVA
        # ====================================================

        cur.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE status = 'active'
            """
        )

        total_activos = (
            cur.fetchone()[0]
        )

        quorum = calcular_dos_tercios(
            total_activos
        )

        if args.votos_si is None:

            votos_si = quorum

        else:

            votos_si = (
                args.votos_si
            )

        if votos_si < 0:

            raise ValueError(
                "Los votos no pueden "
                "ser negativos."
            )

        if votos_si > total_activos:

            raise ValueError(
                "Los votos SI no pueden "
                "superar la red activa."
            )

        # ====================================================
        # PROPONENTE DE REVOCACIÓN
        # ====================================================

        cur.execute(
            """
            SELECT
                id,
                display_name

            FROM users

            WHERE status = 'active'
              AND id <> %s

            ORDER BY id

            LIMIT 1
            """,
            (technical_user_id,)
        )

        proponente = cur.fetchone()

        if proponente is None:

            raise RuntimeError(
                "No existe otro miembro "
                "activo para proponer "
                "la revocación."
            )

        (
            proposer_id,
            proposer_name
        ) = proponente

        # ====================================================
        # RESULTADO
        # ====================================================

        aprobada = (
            votos_si >= quorum
        )

        if aprobada:

            # Simulación:
            # la revocación ocurre 30 días
            # después del comienzo del mandato.
            revoked_at = (
                granted_at
                + timedelta(days=30)
            )

            if revoked_at > granted_until:

                revoked_at = (
                    granted_until
                    - timedelta(seconds=1)
                )

            cur.execute(
                """
                UPDATE technical_roles

                SET
                    revoked_at = %s,
                    revoked_by = %s

                WHERE user_id = %s
                  AND granted_at = %s
                  AND revoked_at IS NULL
                """,
                (
                    revoked_at,
                    proposer_id,
                    technical_user_id,
                    granted_at
                )
            )

        conn.commit()

        print()
        print("REVOCACIÓN V6")
        print(
            "================================"
        )

        print(
            f"Técnico: "
            f"{technical_name}"
        )

        print(
            f"Propuesta por: "
            f"{proposer_name}"
        )

        print()
        print(
            f"Red activa: "
            f"{total_activos}"
        )

        print(
            f"Cuórum 2/3: "
            f"{quorum}"
        )

        print(
            f"Votos SI: "
            f"{votos_si}"
        )

        print()

        if aprobada:

            print(
                "✅ Mandato técnico revocado."
            )

        else:

            print(
                "❌ Revocación rechazada."
            )

            print(
                "El mandato continúa vigente."
            )

        print(
            "================================"
        )

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
