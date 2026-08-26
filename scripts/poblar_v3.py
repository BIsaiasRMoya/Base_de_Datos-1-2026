#!/usr/bin/env python3

import argparse
import hashlib
import os
import uuid
from datetime import timedelta

import psycopg2
from dotenv import load_dotenv

from funciones_v3 import calcular_vecinos_persistentes


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
# CARGAR USUARIOS
# ============================================================

def cargar_usuarios(cur):

    cur.execute(
        """
        SELECT
            id,
            inviter_id,
            rama_root_id,
            status,
            principles_accepted_at
        FROM users
        WHERE status = 'active'
        ORDER BY principles_accepted_at, id
        """
    )

    usuarios = {}

    orden = []

    for (
        user_id,
        inviter_id,
        rama_root_id,
        status,
        fecha
    ) in cur.fetchall():

        uid = str(user_id)

        usuarios[uid] = {
            "inviter_id":
                str(inviter_id)
                if inviter_id is not None
                else None,

            "rama_root_id":
                str(rama_root_id)
                if rama_root_id is not None
                else None,

            "status": str(status),

            "fecha": fecha,
        }

        orden.append(uid)

    return usuarios, orden


# ============================================================
# CARGAR CARGAS ACTUALES
# ============================================================

def cargar_cargas(cur):

    cur.execute(
        """
        SELECT
            user_id,
            assignment_count
        FROM inter_rama_assignment_count
        """
    )

    return {
        str(user_id): int(cantidad)
        for user_id, cantidad
        in cur.fetchall()
    }


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Poblar vecinos persistentes v3"
    )

    parser.add_argument(
        "--semilla",
        type=int,
        default=42
    )

    parser.add_argument(
        "--borrar",
        action="store_true",
        help=
        "Borra asignaciones v3 existentes "
        "antes de reconstruirlas"
    )

    args = parser.parse_args()

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    conn.autocommit = False

    cur = conn.cursor()

    try:

        # ----------------------------------------------------
        # Limpiar v3 si se solicita
        # ----------------------------------------------------

        if args.borrar:

            cur.execute(
                "DELETE FROM delegation_requests;"
            )

            cur.execute(
                "DELETE FROM inter_rama_assignments;"
            )

        # ----------------------------------------------------
        # Evitar duplicar asignaciones
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT COUNT(*)
            FROM inter_rama_assignments
            WHERE replaced_at IS NULL
            """
        )

        existentes = cur.fetchone()[0]

        if existentes > 0:

            raise RuntimeError(
                "Ya existen vecinos persistentes. "
                "Usa --borrar si quieres reconstruirlos."
            )

        # ----------------------------------------------------
        # Usuarios
        # ----------------------------------------------------

        usuarios, orden = cargar_usuarios(
            cur
        )

        if not usuarios:

            raise RuntimeError(
                "No hay usuarios activos."
            )

        # Todas las personas deben tener rama.
        sin_rama = [
            uid
            for uid, datos in usuarios.items()
            if datos["rama_root_id"] is None
        ]

        if sin_rama:

            raise RuntimeError(
                "Hay usuarios sin rama_root_id."
            )

        # ----------------------------------------------------
        # Fecha de activación de v3
        # ----------------------------------------------------

        ultima_fecha = max(
            datos["fecha"]
            for datos in usuarios.values()
        )

        fecha_v3 = (
            ultima_fecha
            + timedelta(days=1)
        )

        # ----------------------------------------------------
        # Cargas iniciales
        # ----------------------------------------------------

        cargas = cargar_cargas(
            cur
        )

        total_asignaciones = 0

        # ----------------------------------------------------
        # Asignar uno por cada otra rama
        # ----------------------------------------------------

        for posicion, user_id in enumerate(orden):

            seleccionados = (
                calcular_vecinos_persistentes(
                    usuarios=usuarios,
                    user_id=user_id,
                    cargas=cargas,
                    semilla=args.semilla
                )
            )

            assigned_at = (
                fecha_v3
                + timedelta(seconds=posicion)
            )

            for (
                rama_root,
                neighbor_id
            ) in seleccionados.items():

                assignment_id = (
                    uuid_determinista(
                        args.semilla,
                        (
                            f"inter-rama:"
                            f"{user_id}:"
                            f"{rama_root}"
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
                        assignment_id,
                        user_id,
                        neighbor_id,
                        rama_root,
                        assigned_at
                    )
                )

                total_asignaciones += 1

        conn.commit()

        # ----------------------------------------------------
        # Métricas
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT COUNT(DISTINCT rama_root_id)
            FROM users
            WHERE status = 'active'
            """
        )

        total_ramas = cur.fetchone()[0]

        print()
        print("VECINOS PERSISTENTES V3")
        print("================================")

        print(
            f"Usuarios activos: {len(usuarios)}"
        )

        print(
            f"Ramas: {total_ramas}"
        )

        print(
            f"Asignaciones creadas: "
            f"{total_asignaciones}"
        )

        print(
            "Vecinos esperados por usuario: "
            f"{max(total_ramas - 1, 0)}"
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
