#!/usr/bin/env python3

import argparse
import hashlib
import os
import uuid
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
# UUID DETERMINISTA
# ============================================================

def uuid_determinista(semilla, contexto):

    texto = f"{semilla}|{contexto}"

    digest = bytearray(
        hashlib.sha256(
            texto.encode("utf-8")
        ).digest()[:16]
    )

    digest[6] = (digest[6] & 0x0F) | 0x40
    digest[8] = (digest[8] & 0x3F) | 0x80

    return str(
        uuid.UUID(bytes=bytes(digest))
    )


# ============================================================
# BUSCAR PERSONA MÁS CARGADA
# ============================================================

def buscar_delegador(cur):

    cur.execute(
        """
        SELECT
            u.id,
            u.display_name,
            u.rama_root_id,
            c.assignment_count
        FROM users u

        JOIN inter_rama_assignment_count c
            ON c.user_id = u.id

        WHERE u.status = 'active'
          AND c.assignment_count > 0

        ORDER BY
            c.assignment_count DESC,
            u.id

        LIMIT 1
        """
    )

    return cur.fetchone()


# ============================================================
# BUSCAR UNA ASIGNACIÓN DEL DELEGADOR
# ============================================================

def buscar_asignacion(cur, delegator_id):

    cur.execute(
        """
        SELECT
            id,
            user_id,
            other_rama_root_id
        FROM inter_rama_assignments

        WHERE neighbor_id = %s
          AND replaced_at IS NULL

        ORDER BY assigned_at

        LIMIT 1
        """,
        (delegator_id,)
    )

    return cur.fetchone()


# ============================================================
# BUSCAR PERSONA MENOS CARGADA
# DE LA MISMA RAMA
# ============================================================

def buscar_delegado(
    cur,
    delegator_id,
    rama_root_id
):

    cur.execute(
        """
        SELECT
            u.id,
            u.display_name,
            c.assignment_count

        FROM users u

        JOIN inter_rama_assignment_count c
            ON c.user_id = u.id

        WHERE u.status = 'active'

          AND u.rama_root_id = %s

          AND u.id <> %s

        ORDER BY
            c.assignment_count ASC,
            u.id

        LIMIT 1
        """,
        (
            rama_root_id,
            delegator_id
        )
    )

    return cur.fetchone()


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Simular una delegación voluntaria v3"
    )

    parser.add_argument(
        "--semilla",
        type=int,
        default=42
    )

    parser.add_argument(
        "--aceptar",
        action="store_true",
        help=
        "La persona propuesta acepta "
        "la delegación."
    )

    args = parser.parse_args()

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    conn.autocommit = False

    cur = conn.cursor()

    try:

        # ====================================================
        # 1. Persona más cargada
        # ====================================================

        delegador = buscar_delegador(
            cur
        )

        if delegador is None:

            raise RuntimeError(
                "No existen usuarios con "
                "asignaciones para delegar."
            )

        (
            delegator_id,
            delegator_name,
            rama_root_id,
            carga_delegador
        ) = delegador

        # ====================================================
        # 2. Una responsabilidad que posee
        # ====================================================

        asignacion = buscar_asignacion(
            cur,
            delegator_id
        )

        if asignacion is None:

            raise RuntimeError(
                "El usuario seleccionado no "
                "posee asignaciones activas."
            )

        (
            assignment_id,
            user_id,
            other_rama_root_id
        ) = asignacion

        # ====================================================
        # 3. Persona menos cargada misma rama
        # ====================================================

        delegado = buscar_delegado(
            cur,
            delegator_id,
            rama_root_id
        )

        if delegado is None:

            raise RuntimeError(
                "No existe otra persona activa "
                "en la misma rama."
            )

        (
            delegate_to_id,
            delegate_name,
            carga_delegado
        ) = delegado

        # Debe ser realmente menos cargado.
        if carga_delegado >= carga_delegador:

            raise RuntimeError(
                "No existe una persona menos "
                "cargada en la misma rama."
            )

        # ====================================================
        # 4. Crear solicitud
        # ====================================================

        request_id = uuid_determinista(
            args.semilla,
            (
                f"delegacion:"
                f"{assignment_id}:"
                f"{delegate_to_id}"
            )
        )

        ahora = datetime.now(
            timezone.utc
        )

        cur.execute(
            """
            INSERT INTO delegation_requests
            (
                id,
                delegator_id,
                assignment_id,
                delegate_to_id,
                accepted,
                decided_at
            )
            VALUES
            (%s, %s, %s, %s, %s, %s)
            """,
            (
                request_id,
                delegator_id,
                assignment_id,
                delegate_to_id,
                args.aceptar,
                ahora
            )
        )

        # ====================================================
        # 5. Si acepta, transferir responsabilidad
        # ====================================================

        if args.aceptar:

            # Marcar asignación anterior como reemplazada.
            cur.execute(
                """
                UPDATE inter_rama_assignments

                SET
                    replaced_by = %s,
                    replaced_at = %s

                WHERE id = %s
                """,
                (
                    delegate_to_id,
                    ahora,
                    assignment_id
                )
            )

            # Crear la nueva asignación activa.
            nueva_asignacion_id = (
                uuid_determinista(
                    args.semilla,
                    (
                        f"delegacion-nueva:"
                        f"{assignment_id}:"
                        f"{delegate_to_id}"
                    )
                )
            )

            cur.execute(
                """
                INSERT INTO inter_rama_assignments
                (
                    id,
                    user_id,
                    neighbor_id,
                    other_rama_root_id,
                    assigned_at
                )
                VALUES
                (%s, %s, %s, %s, %s)
                """,
                (
                    nueva_asignacion_id,
                    user_id,
                    delegate_to_id,
                    other_rama_root_id,
                    ahora
                )
            )

        conn.commit()

        print()
        print("DELEGACIÓN V3")
        print("================================")

        print(
            f"Delegador: {delegator_name}"
        )

        print(
            f"Carga delegador: "
            f"{carga_delegador}"
        )

        print(
            f"Propuesto: {delegate_name}"
        )

        print(
            f"Carga propuesta: "
            f"{carga_delegado}"
        )

        if args.aceptar:

            print()
            print(
                "✅ Delegación aceptada."
            )

            print(
                "La responsabilidad fue "
                "transferida."
            )

        else:

            print()
            print(
                "❌ Delegación rechazada."
            )

            print(
                "La asignación original "
                "permanece activa."
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
