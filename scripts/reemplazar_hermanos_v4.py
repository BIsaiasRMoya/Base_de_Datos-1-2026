#!/usr/bin/env python3

import argparse
import hashlib
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


# ============================================================
# HASH DETERMINISTA
# ============================================================

def hash_determinista(
    semilla,
    candidato,
    contexto
):

    texto = (
        f"{semilla}|"
        f"{candidato}|"
        f"{contexto}"
    )

    digest = hashlib.sha256(
        texto.encode("utf-8")
    ).hexdigest()

    return int(digest, 16)


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Reemplazar hermanos vecinales inactivos v4"
    )

    parser.add_argument(
        "--semilla",
        type=int,
        default=42
    )

    parser.add_argument(
        "--fecha-referencia",
        type=str,
        default=None
    )

    args = parser.parse_args()

    if args.fecha_referencia:

        fecha = datetime.strptime(
            args.fecha_referencia,
            "%Y-%m-%d"
        ).replace(
            tzinfo=timezone.utc
        )

    else:

        fecha = datetime.now(
            timezone.utc
        )

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    conn.autocommit = False

    cur = conn.cursor()

    reemplazos = 0
    sin_reemplazo = 0

    try:

        # ====================================================
        # ASIGNACIONES CUYO HERMANO ESTÁ INACTIVO
        # ====================================================

        cur.execute(
            """
            SELECT
                s.user_id,
                s.sibling_id,
                u.inviter_id,
                u.display_name,
                h.display_name

            FROM sibling_assignments s

            JOIN users u
                ON u.id = s.user_id

            JOIN users h
                ON h.id = s.sibling_id

            WHERE s.replaced_at IS NULL
              AND h.status = 'inactive'

            ORDER BY s.user_id
            """
        )

        asignaciones = cur.fetchall()

        for (
            user_id,
            sibling_id,
            inviter_id,
            nombre_usuario,
            nombre_inactivo
        ) in asignaciones:

            # ================================================
            # CANDIDATOS
            # ================================================

            cur.execute(
                """
                SELECT c.id, c.display_name

                FROM users c

                WHERE c.status = 'active'

                  AND c.id <> %s

                  AND c.inviter_id
                      IS NOT DISTINCT FROM %s

                  AND c.principles_accepted_at <= %s

                  AND NOT EXISTS
                  (
                      SELECT 1
                      FROM sibling_assignments historial

                      WHERE historial.user_id = %s
                        AND historial.sibling_id = c.id
                  )
                """,
                (
                    user_id,
                    inviter_id,
                    fecha,
                    user_id
                )
            )

            candidatos = cur.fetchall()

            if not candidatos:

                sin_reemplazo += 1

                print(
                    f"Sin reemplazo disponible: "
                    f"{nombre_usuario} "
                    f"(hermano inactivo: "
                    f"{nombre_inactivo})"
                )

                continue

            # ================================================
            # SORTEO DETERMINISTA
            # ================================================

            contexto = (
                f"reemplazo-hermano:"
                f"{user_id}:"
                f"{sibling_id}"
            )

            candidatos = sorted(
                candidatos,
                key=lambda fila:
                    hash_determinista(
                        args.semilla,
                        str(fila[0]),
                        contexto
                    )
            )

            reemplazo_id = (
                candidatos[0][0]
            )

            reemplazo_nombre = (
                candidatos[0][1]
            )

            # ================================================
            # CERRAR ASIGNACIÓN ANTERIOR
            # ================================================

            cur.execute(
                """
                UPDATE sibling_assignments

                SET
                    replaced_by = %s,
                    replaced_at = %s

                WHERE user_id = %s
                  AND sibling_id = %s
                  AND replaced_at IS NULL
                """,
                (
                    reemplazo_id,
                    fecha,
                    user_id,
                    sibling_id
                )
            )

            # ================================================
            # CREAR NUEVA ASIGNACIÓN
            # ================================================

            cur.execute(
                """
                INSERT INTO sibling_assignments
                (
                    user_id,
                    sibling_id,
                    assigned_at
                )
                VALUES (%s, %s, %s)
                """,
                (
                    user_id,
                    reemplazo_id,
                    fecha
                )
            )

            reemplazos += 1

            print(
                f"{nombre_usuario}: "
                f"{nombre_inactivo} -> "
                f"{reemplazo_nombre}"
            )

        conn.commit()

        print()
        print("REEMPLAZO DE HERMANOS V4")
        print("================================")

        print(
            f"Reemplazos realizados: "
            f"{reemplazos}"
        )

        print(
            f"Sin candidato disponible: "
            f"{sin_reemplazo}"
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
