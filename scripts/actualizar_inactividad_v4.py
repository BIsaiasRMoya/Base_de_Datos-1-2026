#!/usr/bin/env python3

import argparse
import os
from datetime import datetime, timezone

import psycopg2
from dotenv import load_dotenv


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
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Actualizar usuarios inactivos v4"
    )

    parser.add_argument(
        "--meses",
        type=int,
        default=4,
        help=
        "Meses sin actividad para marcar inactive"
    )

    parser.add_argument(
        "--fecha-referencia",
        type=str,
        default=None,
        help=
        "Fecha de referencia YYYY-MM-DD. "
        "Si no se indica se utiliza la fecha actual UTC."
    )

    args = parser.parse_args()

    if args.meses <= 0:
        raise ValueError(
            "--meses debe ser mayor que 0."
        )

    if args.fecha_referencia:

        referencia = datetime.strptime(
            args.fecha_referencia,
            "%Y-%m-%d"
        ).replace(
            tzinfo=timezone.utc
        )

    else:

        referencia = datetime.now(
            timezone.utc
        )

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    conn.autocommit = False

    cur = conn.cursor()

    try:

        # ----------------------------------------------------
        # Mostrar quiénes serán marcados
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                id,
                display_name,
                last_active_at

            FROM users

            WHERE status = 'active'

              AND last_active_at
                  < %s
                    - (%s * INTERVAL '1 month')

            ORDER BY last_active_at
            """,
            (
                referencia,
                args.meses
            )
        )

        candidatos = cur.fetchall()

        # ----------------------------------------------------
        # Actualizar estado
        # ----------------------------------------------------

        cur.execute(
            """
            UPDATE users

            SET status = 'inactive'

            WHERE status = 'active'

              AND last_active_at
                  < %s
                    - (%s * INTERVAL '1 month')
            """,
            (
                referencia,
                args.meses
            )
        )

        actualizados = (
            cur.rowcount
        )

        conn.commit()

        print()
        print("ACTUALIZACIÓN DE INACTIVIDAD V4")
        print("================================")

        print(
            "Fecha de referencia:",
            referencia.date()
        )

        print(
            "Umbral:",
            f"{args.meses} meses"
        )

        print(
            "Miembros marcados inactive:",
            actualizados
        )

        if candidatos:

            print()
            print("Miembros afectados:")

            for (
                user_id,
                nombre,
                ultima_actividad
            ) in candidatos:

                print(
                    f"- {nombre}: "
                    f"{ultima_actividad.date()}"
                )

        print("================================")

    except Exception:

        conn.rollback()
        raise

    finally:

        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
