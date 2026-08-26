#!/usr/bin/env python3

import argparse
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
from dotenv import load_dotenv
from faker import Faker

from funciones_v1 import (
    obtener_ascendentes,
    obtener_hermanos,
    sortear_hermanos,
)


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
# UUID REPRODUCIBLE CON FORMATO V4
# ============================================================

def generar_uuid(rng):
    return str(
        uuid.UUID(
            int=rng.getrandbits(128),
            version=4
        )
    )


# ============================================================
# GENERAR ÁRBOL
# ============================================================

def generar_arbol(
    total,
    fundadores,
    max_hijos,
    max_profundidad,
    semilla
):

    if fundadores < 1:
        raise ValueError(
            "Debe existir al menos un fundador."
        )

    if fundadores > total:
        raise ValueError(
            "Los fundadores no pueden superar el total."
        )

    rng = random.Random(semilla)

    ids = [
        generar_uuid(rng)
        for _ in range(total)
    ]

    usuarios = []

    # ------------------------------------
    # Génesis
    # ------------------------------------

    for i in range(fundadores):

        usuarios.append({
            "id": ids[i],
            "inviter_id": None,
            "profundidad": 0
        })

    cantidad_hijos = {
        usuario["id"]: 0
        for usuario in usuarios
    }

    # ------------------------------------
    # Resto de la red
    # ------------------------------------

    for i in range(fundadores, total):

        posibles_padres = [
            usuario
            for usuario in usuarios
            if usuario["profundidad"] < max_profundidad
            and cantidad_hijos.get(
                usuario["id"], 0
            ) < max_hijos
        ]

        if not posibles_padres:
            raise RuntimeError(
                "No quedan usuarios disponibles "
                "para seguir generando la red."
            )

        padre = rng.choice(posibles_padres)

        nuevo = {
            "id": ids[i],
            "inviter_id": padre["id"],
            "profundidad":
                padre["profundidad"] + 1
        }

        usuarios.append(nuevo)

        cantidad_hijos[padre["id"]] += 1

        cantidad_hijos[nuevo["id"]] = 0

    return usuarios


# ============================================================
# LIMPIAR DATOS DE V1
# ============================================================

def limpiar_v1(cur):

    cur.execute(
        "DELETE FROM sibling_assignments;"
    )

    cur.execute(
        "DELETE FROM votes;"
    )

    cur.execute(
        "DELETE FROM invitations;"
    )

    cur.execute(
        "DELETE FROM users;"
    )


# ============================================================
# INSERTAR RED
# ============================================================

def insertar_red(
    cur,
    usuarios,
    semilla
):

    fake = Faker("es_CL")
    Faker.seed(semilla)
    fake.seed_instance(semilla)

    fecha_base = datetime(
        2026,
        1,
        1,
        12,
        0,
        tzinfo=timezone.utc
    )

    # Contiene solamente quienes ya ingresaron.
    usuarios_admitidos = {}

    for posicion, usuario in enumerate(usuarios):

        fecha_ingreso = (
            fecha_base
            + timedelta(days=posicion)
        )

        # --------------------------------
        # Insertar usuario
        # --------------------------------

        cur.execute(
            """
            INSERT INTO users
            (
                id,
                display_name,
                inviter_id,
                principles_accepted_at,
                status
            )
            VALUES (%s, %s, %s, %s, 'active')
            """,
            (
                usuario["id"],
                fake.name(),
                usuario["inviter_id"],
                fecha_ingreso
            )
        )

        # Ahora esta persona ya pertenece
        # oficialmente a la red.
        usuarios_admitidos[
            usuario["id"]
        ] = usuario

        # --------------------------------
        # Fundadores
        # --------------------------------

        if usuario["inviter_id"] is None:
            continue

        # --------------------------------
        # Ascendentes
        # --------------------------------

        ascendentes = obtener_ascendentes(
            usuarios_admitidos,
            usuario["id"]
        )

        cantidad_hermanos = len(
            ascendentes
        )

        # --------------------------------
        # Hermanos existentes AL INGRESAR
        # --------------------------------

        hermanos = obtener_hermanos(
            usuarios_admitidos,
            usuario["id"]
        )

        # --------------------------------
        # Sorteo determinista
        # --------------------------------

        hermanos_sorteados = sortear_hermanos(
            semilla,
            usuario["id"],
            hermanos,
            cantidad_hermanos
        )

        # --------------------------------
        # Persistir selección
        # --------------------------------

        for hermano_id in hermanos_sorteados:

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
                    usuario["id"],
                    hermano_id,
                    fecha_ingreso
                )
            )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Generador de red sintética v1"
    )

    parser.add_argument(
        "--total",
        type=int,
        default=15
    )

    parser.add_argument(
        "--fundadores",
        type=int,
        default=5
    )

    parser.add_argument(
        "--semilla",
        type=int,
        default=42
    )

    parser.add_argument(
        "--max-hijos",
        type=int,
        default=4
    )

    parser.add_argument(
        "--max-profundidad",
        type=int,
        default=4
    )

    parser.add_argument(
        "--borrar",
        action="store_true"
    )

    args = parser.parse_args()

    usuarios = generar_arbol(
        total=args.total,
        fundadores=args.fundadores,
        max_hijos=args.max_hijos,
        max_profundidad=args.max_profundidad,
        semilla=args.semilla
    )

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    conn.autocommit = False

    cur = conn.cursor()

    try:

        if args.borrar:
            limpiar_v1(cur)

        insertar_red(
            cur,
            usuarios,
            args.semilla
        )

        conn.commit()

        cur.execute(
            "SELECT COUNT(*) FROM users"
        )

        total_usuarios = cur.fetchone()[0]

        cur.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE inviter_id IS NULL
            """
        )

        total_fundadores = (
            cur.fetchone()[0]
        )

        cur.execute(
            """
            SELECT COUNT(*)
            FROM sibling_assignments
            """
        )

        total_hermanos = (
            cur.fetchone()[0]
        )

        print()
        print("RED V1 GENERADA")
        print("============================")
        print(
            f"Usuarios: {total_usuarios}"
        )
        print(
            f"Fundadores: {total_fundadores}"
        )
        print(
            f"Asignaciones de hermanos: "
            f"{total_hermanos}"
        )
        print(
            f"Semilla: {args.semilla}"
        )
        print("============================")

    except Exception as error:

        conn.rollback()

        print(
            "Error al generar la red:"
        )

        print(error)

        raise

    finally:

        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
