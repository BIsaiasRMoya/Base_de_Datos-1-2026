#!/usr/bin/env python3

import argparse
import os
from datetime import (
    datetime,
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


def main():

    parser = argparse.ArgumentParser()

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

    conn.autocommit = False

    cur = conn.cursor()

    try:

        # ====================================================
        # BUSCAR CAUTELARES VENCIDAS
        # ====================================================

        cur.execute(
            """
            SELECT user_id

            FROM cautelary_suspensions

            WHERE lifted_at IS NULL
              AND expires_at <= %s
            """,
            (referencia,)
        )

        usuarios = [
            row[0]
            for row in cur.fetchall()
        ]

        # ====================================================
        # LEVANTARLAS
        # ====================================================

        for user_id in usuarios:

            cur.execute(
                """
                UPDATE cautelary_suspensions

                SET lifted_at = %s

                WHERE user_id = %s
                  AND lifted_at IS NULL
                  AND expires_at <= %s
                """,
                (
                    referencia,
                    user_id,
                    referencia
                )
            )

            # Solo regresar a active si sigue
            # exactamente en cautelar.
            cur.execute(
                """
                UPDATE users

                SET status = 'active'

                WHERE id = %s
                  AND status =
                      'suspended_cautelar'
                """,
                (user_id,)
            )

        conn.commit()

        print()
        print("CAUTELARES V5")
        print("================================")

        print(
            f"Suspensiones levantadas: "
            f"{len(usuarios)}"
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
