#!/usr/bin/env python3

import argparse
import os
from datetime import timedelta

import psycopg2
from dotenv import load_dotenv

from funciones_v3 import (
    calcular_vecindario_v3,
)

from funciones_v5 import (
    sortear_jurado_disciplinario,
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
# USUARIOS
# ============================================================

def cargar_usuarios(cur):

    cur.execute(
        """
        SELECT
            id,
            inviter_id,
            rama_root_id,
            status

        FROM users
        """
    )

    usuarios = {}

    for (
        user_id,
        inviter_id,
        rama_root_id,
        status
    ) in cur.fetchall():

        usuarios[str(user_id)] = {

            "inviter_id":
                str(inviter_id)
                if inviter_id is not None
                else None,

            "rama_root_id":
                str(rama_root_id)
                if rama_root_id is not None
                else None,

            "status":
                str(status),
        }

    return usuarios


def cargar_hermanos(
    cur,
    user_id
):

    cur.execute(
        """
        SELECT sibling_id
        FROM sibling_assignments
        WHERE user_id = %s
          AND replaced_at IS NULL
        """,
        (user_id,)
    )

    return {
        str(row[0])
        for row in cur.fetchall()
    }


def cargar_persistentes(
    cur,
    user_id
):

    cur.execute(
        """
        SELECT neighbor_id
        FROM inter_rama_assignments
        WHERE user_id = %s
          AND replaced_at IS NULL
        """,
        (user_id,)
    )

    return {
        str(row[0])
        for row in cur.fetchall()
    }


def obtener_vecindario(
    cur,
    usuarios,
    user_id,
    semilla
):

    resultado = calcular_vecindario_v3(

        usuarios=usuarios,

        user_id=user_id,

        semilla=semilla,

        hermanos_persistidos=
            cargar_hermanos(
                cur,
                user_id
            ),

        vecinos_persistentes=
            cargar_persistentes(
                cur,
                user_id
            )
    )

    return set(
        resultado["total"]
    )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Segundo jurado de revisión v5"
    )

    parser.add_argument(
        "--semilla",
        type=int,
        default=42
    )

    parser.add_argument(
        "--ratificar",
        action="store_true",
        help=
        "El segundo jurado ratifica "
        "la expulsión"
    )

    args = parser.parse_args()

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    conn.autocommit = False

    cur = conn.cursor()

    try:

        # ====================================================
        # PROCESO PENDIENTE MÁS RECIENTE
        # ====================================================

        cur.execute(
            """
            SELECT
                id,
                complainant_id,
                accused_id

            FROM disciplinary_processes

            WHERE status =
                  'pending_expulsion_review'

            ORDER BY opened_at DESC

            LIMIT 1
            """
        )

        proceso = cur.fetchone()

        if proceso is None:

            raise RuntimeError(
                "No existe una expulsión "
                "pendiente de revisión."
            )

        (
            process_id,
            complainant_id,
            accused_id
        ) = proceso

        process_id = str(process_id)

        complainant_id = str(
            complainant_id
        )

        accused_id = str(
            accused_id
        )

        # ====================================================
        # FECHA DE LA PRIMERA DECISIÓN
        # ====================================================

        cur.execute(
            """
            SELECT MAX(decided_at)
            FROM jury_decisions
            WHERE process_id = %s
            """,
            (process_id,)
        )

        primera_resolucion = (
            cur.fetchone()[0]
        )

        if primera_resolucion is None:

            raise RuntimeError(
                "El proceso no tiene "
                "decisión del primer jurado."
            )

        # Simulamos la solicitud de revisión
        # 10 días después.
        review_at = (
            primera_resolucion
            + timedelta(days=10)
        )

        limite_revision = (
            primera_resolucion
            + timedelta(days=30)
        )

        if review_at > limite_revision:

            raise RuntimeError(
                "La revisión está fuera "
                "del plazo de 30 días."
            )

        # ====================================================
        # PRIMER JURADO
        # ====================================================

        cur.execute(
            """
            SELECT juror_id
            FROM juries
            WHERE process_id = %s
            """,
            (process_id,)
        )

        primer_jurado = {
            str(row[0])
            for row in cur.fetchall()
        }

        # ====================================================
        # RED Y VECINDARIOS
        # ====================================================

        usuarios = cargar_usuarios(
            cur
        )

        vecindario_denunciante = (
            obtener_vecindario(
                cur,
                usuarios,
                complainant_id,
                args.semilla
            )
        )

        vecindario_denunciado = (
            obtener_vecindario(
                cur,
                usuarios,
                accused_id,
                args.semilla
            )
        )

        # ====================================================
        # SEGUNDO JURADO
        # ====================================================

        segundo_jurado = (
            sortear_jurado_disciplinario(

                usuarios=usuarios,

                complainant_id=
                    complainant_id,

                accused_id=
                    accused_id,

                vecindario_complainant=
                    vecindario_denunciante,

                vecindario_accused=
                    vecindario_denunciado,

                semilla=args.semilla,

                process_id=
                    f"{process_id}:revision",

                cantidad=7,

                excluir=primer_jurado
            )
        )

        # Garantía importante.
        if (
            set(segundo_jurado)
            & primer_jurado
        ):

            raise RuntimeError(
                "El segundo jurado comparte "
                "miembros con el primero."
            )

        for juror_id in segundo_jurado:

            cur.execute(
                """
                INSERT INTO juries
                (
                    process_id,
                    juror_id,
                    sorted_at,
                    recused
                )
                VALUES
                (%s, %s, %s, FALSE)
                """,
                (
                    process_id,
                    juror_id,
                    review_at
                )
            )

        # ====================================================
        # VOTOS DEL SEGUNDO JURADO
        # ====================================================

        votos_expulsion = 0

        for indice, juror_id in enumerate(
            segundo_jurado
        ):

            if args.ratificar:

                if indice < 5:
                    decision = "expulsion"
                    votos_expulsion += 1

                else:
                    decision = "archive"

            else:

                if indice < 4:
                    decision = "archive"

                else:
                    decision = "expulsion"
                    votos_expulsion += 1

            cur.execute(
                """
                INSERT INTO jury_decisions
                (
                    process_id,
                    juror_id,
                    decision,
                    reasoning,
                    decided_at
                )
                VALUES
                (%s, %s, %s, %s, %s)
                """,
                (
                    process_id,
                    juror_id,
                    decision,
                    (
                        "Decisión del segundo "
                        "jurado de revisión."
                    ),
                    review_at
                    + timedelta(days=5)
                )
            )

        # ====================================================
        # RESULTADO DE REVISIÓN
        # ====================================================

        if votos_expulsion >= 5:

            cur.execute(
                """
                UPDATE users
                SET status = 'expelled'
                WHERE id = %s
                """,
                (accused_id,)
            )

            cur.execute(
                """
                UPDATE disciplinary_processes
                SET status =
                    'resolved_expulsion'
                WHERE id = %s
                """,
                (process_id,)
            )

            resultado = (
                "EXPULSIÓN RATIFICADA"
            )

        else:

            # Nuestra representación para una
            # expulsión que no logra ratificación
            # es cerrar el proceso sin expulsión.
            cur.execute(
                """
                UPDATE disciplinary_processes
                SET status =
                    'resolved_archived'
                WHERE id = %s
                """,
                (process_id,)
            )

            resultado = (
                "EXPULSIÓN NO RATIFICADA"
            )

        conn.commit()

        print()
        print("REVISIÓN DE EXPULSIÓN V5")
        print("================================")

        print(
            f"Proceso: {process_id}"
        )

        print(
            f"Primer jurado registrado: "
            f"{len(primer_jurado)}"
        )

        print(
            "Segundo jurado: 7"
        )

        print(
            f"Votos por expulsión: "
            f"{votos_expulsion}/7"
        )

        print()
        print(resultado)

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
