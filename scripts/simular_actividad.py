#!/usr/bin/env python3

import argparse
import hashlib
import os
import random
import uuid
from datetime import timedelta

import psycopg2
from dotenv import load_dotenv
from faker import Faker

from funciones_v1 import (
    calcular_vecindario_local,
    calcular_cuorum,
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
# UUID DETERMINISTA
# ============================================================

def uuid_determinista(semilla, contexto):
    """
    Genera un UUID reproducible utilizando SHA-256.
    """

    texto = f"{semilla}|{contexto}"

    digest = bytearray(
        hashlib.sha256(
            texto.encode("utf-8")
        ).digest()[:16]
    )

    # Bits correspondientes a UUID v4
    digest[6] = (
        digest[6] & 0x0F
    ) | 0x40

    digest[8] = (
        digest[8] & 0x3F
    ) | 0x80

    return str(
        uuid.UUID(
            bytes=bytes(digest)
        )
    )


# ============================================================
# CARGAR GRAFO
# ============================================================

def cargar_usuarios(cur):

    cur.execute(
        """
        SELECT id, inviter_id
        FROM users
        WHERE status = 'active'
        """
    )

    usuarios = {}

    for user_id, inviter_id in cur.fetchall():

        usuarios[str(user_id)] = {
            "inviter_id":
                str(inviter_id)
                if inviter_id is not None
                else None
        }

    return usuarios


# ============================================================
# HERMANOS PERSISTIDOS
# ============================================================

def cargar_hermanos_persistidos(
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


# ============================================================
# VECINDARIO DESDE LA BD
# ============================================================

def obtener_vecindario(
    cur,
    user_id,
    semilla_red
):

    usuarios = cargar_usuarios(
        cur
    )

    hermanos = cargar_hermanos_persistidos(
        cur,
        user_id
    )

    return calcular_vecindario_local(
        usuarios,
        user_id,
        semilla_red,
        hermanos_persistidos=hermanos
    )


# ============================================================
# ASIGNAR HERMANOS A NUEVO MIEMBRO
# ============================================================

def asignar_hermanos_nuevo_usuario(
    cur,
    user_id,
    semilla_red,
    fecha
):

    usuarios = cargar_usuarios(
        cur
    )

    ascendentes = obtener_ascendentes(
        usuarios,
        user_id
    )

    hermanos = obtener_hermanos(
        usuarios,
        user_id
    )

    cantidad = len(
        ascendentes
    )

    seleccionados = sortear_hermanos(
        semilla_red,
        user_id,
        hermanos,
        cantidad
    )

    for hermano_id in seleccionados:

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
                hermano_id,
                fecha
            )
        )


# ============================================================
# SIMULACIÓN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Simulación de admisiones v1"
    )

    parser.add_argument(
        "--num-invitaciones",
        type=int,
        default=10
    )

    parser.add_argument(
        "--semilla-red",
        type=int,
        default=42
    )

    parser.add_argument(
        "--semilla-simulacion",
        type=int,
        default=2026
    )

    parser.add_argument(
        "--prob-si",
        type=float,
        default=0.65
    )

    parser.add_argument(
        "--prob-no",
        type=float,
        default=0.20
    )

    parser.add_argument(
        "--prob-abstencion",
        type=float,
        default=0.15
    )

    args = parser.parse_args()

    suma = (
        args.prob_si
        + args.prob_no
        + args.prob_abstencion
    )

    if abs(suma - 1.0) > 0.0001:

        raise ValueError(
            "Las probabilidades deben sumar 1."
        )

    rng = random.Random(
        args.semilla_simulacion
    )

    fake = Faker("es_CL")

    fake.seed_instance(
        args.semilla_simulacion
    )

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    conn.autocommit = False

    cur = conn.cursor()

    aprobadas = 0
    caducadas = 0
    total_votos = 0

    try:

        # ====================================
        # Fecha inicial de simulación
        # ====================================

        cur.execute(
            """
            SELECT MAX(principles_accepted_at)
            FROM users
            """
        )

        ultima_fecha = cur.fetchone()[0]

        if ultima_fecha is None:

            raise RuntimeError(
                "No existen usuarios. "
                "Ejecuta primero generar_red.py"
            )

        fecha_inicio = (
            ultima_fecha
            + timedelta(days=1)
        )

        # ====================================
        # Generar invitaciones
        # ====================================

        for numero in range(
            args.num_invitaciones
        ):

            usuarios = cargar_usuarios(
                cur
            )

            posibles_proponentes = list(
                usuarios.keys()
            )

            rng.shuffle(
                posibles_proponentes
            )

            proposer_id = None
            vecinos = None

            # Buscar alguien que tenga vecindario
            for candidato_proponente in posibles_proponentes:

                posible_vecindario = obtener_vecindario(
                    cur,
                    candidato_proponente,
                    args.semilla_red
                )

                if posible_vecindario:

                    proposer_id = (
                        candidato_proponente
                    )

                    vecinos = (
                        posible_vecindario
                    )

                    break

            if proposer_id is None:

                print(
                    "No existen proponentes "
                    "con vecindario."
                )

                break

            # ====================================
            # Datos de la invitación
            # ====================================

            invitation_id = uuid_determinista(
                args.semilla_simulacion,
                f"invitacion:{numero}"
            )

            candidate_email = (
                f"candidato_"
                f"{args.semilla_simulacion}_"
                f"{numero}"
                f"@example.org"
            )

            opened_at = (
                fecha_inicio
                + timedelta(
                    days=numero * 8
                )
            )

            closes_at = (
                opened_at
                + timedelta(days=7)
            )

            cur.execute(
                """
                INSERT INTO invitations
                (
                    id,
                    proposer_id,
                    candidate_email,
                    opened_at,
                    closes_at,
                    status
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'open'
                )
                """,
                (
                    invitation_id,
                    proposer_id,
                    candidate_email,
                    opened_at,
                    closes_at
                )
            )

            # ====================================
            # Votación
            # ====================================

            votos_si = 0

            for voter_id in sorted(vecinos):

                numero_azar = (
                    rng.random()
                )

                if numero_azar < args.prob_si:

                    choice = "yes"
                    reason = None
                    votos_si += 1

                elif numero_azar < (
                    args.prob_si
                    + args.prob_no
                ):

                    choice = "no"

                    reason = fake.sentence(
                        nb_words=8
                    )

                else:

                    choice = "abstain"
                    reason = None

                segundos = rng.randint(
                    1,
                    7 * 24 * 60 * 60 - 1
                )

                cast_at = (
                    opened_at
                    + timedelta(
                        seconds=segundos
                    )
                )

                cur.execute(
                    """
                    INSERT INTO votes
                    (
                        invitation_id,
                        voter_id,
                        choice,
                        reason,
                        cast_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        invitation_id,
                        voter_id,
                        choice,
                        reason,
                        cast_at
                    )
                )

                total_votos += 1

            # ====================================
            # Calcular cuórum
            # ====================================

            cuorum = calcular_cuorum(
                len(vecinos)
            )

            # ====================================
            # Resolver invitación
            # ====================================

            if votos_si >= cuorum:

                status = (
                    "closed_approved"
                )

                aprobadas += 1

            else:

                # La propuesta indica que
                # si no se alcanza cuórum,
                # la invitación caduca.
                status = "expired"

                caducadas += 1

            cur.execute(
                """
                UPDATE invitations
                SET status = %s
                WHERE id = %s
                """,
                (
                    status,
                    invitation_id
                )
            )

            # ====================================
            # Si fue aprobada, entra a la red
            # ====================================

            if status == "closed_approved":

                nuevo_user_id = (
                    uuid_determinista(
                        args.semilla_simulacion,
                        f"usuario:{numero}"
                    )
                )

                nombre = fake.name()

                fecha_aceptacion = (
                    closes_at
                    + timedelta(minutes=1)
                )

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
                    VALUES
                    (%s, %s, %s, %s, 'active')
                    """,
                    (
                        nuevo_user_id,
                        nombre,
                        proposer_id,
                        fecha_aceptacion
                    )
                )

                asignar_hermanos_nuevo_usuario(
                    cur,
                    nuevo_user_id,
                    args.semilla_red,
                    fecha_aceptacion
                )

            print(
                f"Invitación {numero + 1}: "
                f"vecindario={len(vecinos)}, "
                f"cuórum={cuorum}, "
                f"SI={votos_si}, "
                f"estado={status}"
            )

        conn.commit()

        print()
        print("SIMULACIÓN V1 COMPLETADA")
        print("============================")
        print(
            f"Invitaciones: "
            f"{args.num_invitaciones}"
        )
        print(
            f"Aprobadas: {aprobadas}"
        )
        print(
            f"Caducadas: {caducadas}"
        )
        print(
            f"Votos emitidos: {total_votos}"
        )
        print("============================")

    except Exception as error:

        conn.rollback()

        print(
            "Error durante la simulación:"
        )

        print(error)

        raise

    finally:

        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
