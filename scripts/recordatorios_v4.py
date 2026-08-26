#!/usr/bin/env python3

import argparse
import os
from datetime import datetime, timezone

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


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--meses-recordatorio",
        type=int,
        default=3
    )

    parser.add_argument(
        "--meses-inactividad",
        type=int,
        default=4
    )

    parser.add_argument(
        "--fecha-referencia",
        type=str,
        default=None
    )

    args = parser.parse_args()

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

    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            display_name,
            last_active_at

        FROM users

        WHERE status = 'active'

          AND last_active_at
              < %s
                - (%s * INTERVAL '1 month')

          AND last_active_at
              >= %s
                - (%s * INTERVAL '1 month')

        ORDER BY last_active_at
        """,
        (
            referencia,
            args.meses_recordatorio,
            referencia,
            args.meses_inactividad
        )
    )

    usuarios = cur.fetchall()

    print()
    print("RECORDATORIOS V4")
    print("================================")

    for nombre, ultima_actividad in usuarios:

        print()
        print(
            f"{nombre}:"
        )

        print(
            "Hace varios meses que no participas. "
            "Te invitamos a volver cuando puedas."
        )

        print(
            "Última actividad:",
            ultima_actividad.date()
        )

    print()
    print(
        f"Recordatorios pendientes: "
        f"{len(usuarios)}"
    )

    print("================================")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
