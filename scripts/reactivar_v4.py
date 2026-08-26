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

    parser = argparse.ArgumentParser(
        description=
        "Reactivar usuario al aceptar recordatorio"
    )

    parser.add_argument(
        "--usuario",
        required=True,
        help="UUID del usuario"
    )

    args = parser.parse_args()

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    cur = conn.cursor()

    ahora = datetime.now(
        timezone.utc
    )

    cur.execute(
        """
        UPDATE users

        SET
            status = 'active',
            last_active_at = %s

        WHERE id = %s
          AND status = 'inactive'
        """,
        (
            ahora,
            args.usuario
        )
    )

    actualizados = cur.rowcount

    conn.commit()

    if actualizados == 1:

        print(
            "✅ Usuario reactivado correctamente."
        )

    else:

        print(
            "No se encontró un usuario inactive "
            "con ese UUID."
        )

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
