#!/usr/bin/env python3

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


# ============================================================
# REGLAS INICIALES
# ============================================================

REGLAS = {

    "admission_quorum":
        (
            "Las admisiones requieren "
            "el cuórum definido sobre "
            "el vecindario correspondiente."
        ),

    "inactivity_threshold":
        (
            "Una persona puede ser marcada "
            "inactive tras cuatro meses "
            "sin actividad significativa."
        ),

    "technical_revocation":
        (
            "Un mandato técnico puede ser "
            "revocado con dos tercios "
            "de la red activa."
        ),

    "rule_change_quorum":
        (
            "Una modificación al reglamento "
            "requiere dos tercios "
            "de la red activa."
        ),
}


def main():

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    conn.autocommit = False

    cur = conn.cursor()

    try:

        cur.execute(
            """
            SELECT COUNT(*)
            FROM rules
            """
        )

        existentes = (
            cur.fetchone()[0]
        )

        if existentes > 0:

            raise RuntimeError(
                "Ya existen reglas. "
                "No vuelvas a ejecutar "
                "poblar_reglas_v7.py."
            )

        ahora = datetime.now(
            timezone.utc
        )

        for (
            rule_key,
            body
        ) in REGLAS.items():

            cur.execute(
                """
                INSERT INTO rules
                (
                    version,
                    rule_key,
                    body,
                    effective_from,
                    effective_until
                )
                VALUES
                (
                    1,
                    %s,
                    %s,
                    %s,
                    NULL
                )
                """,
                (
                    rule_key,
                    body,
                    ahora
                )
            )

        conn.commit()

        print()
        print("REGLAMENTO INICIAL V7")
        print("==============================")

        print(
            f"Reglas creadas: "
            f"{len(REGLAS)}"
        )

        for rule_key in REGLAS:

            print(
                f"- {rule_key} v1"
            )

        print()
        print(
            "✅ Reglamento inicial creado."
        )

        print("==============================")

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
