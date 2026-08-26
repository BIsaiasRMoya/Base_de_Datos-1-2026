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
    calcular_cuorum,
    obtener_ascendentes,
    obtener_hermanos,
    sortear_hermanos,
)

from funciones_v3 import (
    calcular_vecindario_v3,
    calcular_vecinos_persistentes,
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

def uuid_determinista(
    semilla,
    contexto
):

    texto = f"{semilla}|{contexto}"

    digest = bytearray(
        hashlib.sha256(
            texto.encode("utf-8")
        ).digest()[:16]
    )

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
# CARGAR USUARIOS
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
        WHERE status = 'active'
        """
    )

    usuarios = {}

    for (
        user_id,
        inviter_id,
        rama_root_id,
        status
    ) in cur.fetchall():

        uid = str(user_id)

        usuarios[uid] = {

            "inviter_id":
                str(inviter_id)
                if inviter_id is not None
                else None,

            "rama_root_id":
                str(rama_root_id),

            "status":
                str(status),
        }

    return usuarios


# ============================================================
# HERMANOS PERSISTIDOS
# ============================================================

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


# ============================================================
# VECINOS INTER-RAMA PERSISTENTES
# ============================================================

def cargar_vecinos_inter_rama(
    cur,
    user_id
):

    cur.execute(
        """
        SELECT a.neighbor_id
        FROM inter_rama_assignments a

        JOIN users n
            ON n.id = a.neighbor_id

        WHERE a.user_id = %s
          AND a.replaced_at IS NULL
          AND n.status = 'active'
        """,
        (user_id,)
    )

    return {
        str(row[0])
        for row in cur.fetchall()
    }


# ============================================================
# CARGA DE CADA USUARIO
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
        str(uid): int(carga)
        for uid, carga
        in cur.fetchall()
    }


# ============================================================
# ASIGNAR HERMANOS A NUEVO USUARIO
# ============================================================

def asignar_hermanos_nuevo(
    cur,
    user_id,
    semilla,
    fecha
):

    usuarios = cargar_usuarios(
        cur
    )

    usuarios_locales = {
        uid: {
            "inviter_id":
                datos["inviter_id"]
        }
        for uid, datos in usuarios.items()
    }

    ascendentes = obtener_ascendentes(
        usuarios_locales,
        user_id
    )

    hermanos = obtener_hermanos(
        usuarios_locales,
        user_id
    )

    seleccionados = sortear_hermanos(
        semilla,
        user_id,
        hermanos,
        len(ascendentes)
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
# ASIGNAR VECINOS PERSISTENTES A NUEVO USUARIO
# ============================================================

def asignar_vecinos_nuevo(
    cur,
    user_id,
    semilla,
    fecha
):

    usuarios = cargar_usuarios(
        cur
    )

    cargas = cargar_cargas(
        cur
    )

    seleccionados = (
        calcular_vecinos_persistentes(
            usuarios=usuarios,
            user_id=user_id,
            cargas=cargas,
            semilla=semilla
        )
    )

    for (
        rama_root,
        neighbor_id
    ) in seleccionados.items():

        assignment_id = (
            uuid_determinista(
                semilla,
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
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                assignment_id,
                user_id,
                neighbor_id,
                rama_root,
                fecha
            )
        )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Simulación de admisiones v3 "
        "con vecinos persistentes"
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
        default=2028
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
    votos_locales = 0
    votos_persistentes = 0

    try:

        # ====================================================
        # Verificar que v3 esté poblada
        # ====================================================

        cur.execute(
            """
            SELECT COUNT(*)
            FROM inter_rama_assignments
            WHERE replaced_at IS NULL
            """
        )

        if cur.fetchone()[0] == 0:

            raise RuntimeError(
                "No existen vecinos persistentes. "
                "Ejecuta primero poblar_v3.py."
            )

        # ====================================================
        # Fecha de inicio
        # ====================================================

        cur.execute(
            """
            SELECT MAX(principles_accepted_at)
            FROM users
            """
        )

        fecha_usuario = cur.fetchone()[0]

        cur.execute(
            """
            SELECT MAX(closes_at)
            FROM invitations
            """
        )

        fecha_invitacion = cur.fetchone()[0]

        cur.execute(
            """
            SELECT MAX(assigned_at)
            FROM inter_rama_assignments
            """
        )

        fecha_asignacion = cur.fetchone()[0]

        fechas = [
            fecha
            for fecha in (
                fecha_usuario,
                fecha_invitacion,
                fecha_asignacion
            )
            if fecha is not None
        ]

        fecha_inicio = (
            max(fechas)
            + timedelta(days=1)
        )

        # Cantidad de simulaciones v3 existentes
        cur.execute(
            """
            SELECT COUNT(*)
            FROM invitations
            WHERE candidate_email
                  LIKE 'candidato_v3_%'
            """
        )

        offset = cur.fetchone()[0]

        # ====================================================
        # SIMULAR
        # ====================================================

        for numero in range(
            args.num_invitaciones
        ):

            indice = (
                offset + numero
            )

            usuarios = cargar_usuarios(
                cur
            )

            candidatos_proponente = list(
                usuarios.keys()
            )

            rng.shuffle(
                candidatos_proponente
            )

            proposer_id = None
            resultado = None

            for posible in candidatos_proponente:

                hermanos = cargar_hermanos(
                    cur,
                    posible
                )

                persistentes = (
                    cargar_vecinos_inter_rama(
                        cur,
                        posible
                    )
                )

                posible_resultado = (
                    calcular_vecindario_v3(
                        usuarios=usuarios,
                        user_id=posible,
                        semilla=args.semilla_red,
                        hermanos_persistidos=
                            hermanos,
                        vecinos_persistentes=
                            persistentes
                    )
                )

                if posible_resultado[
                    "total"
                ]:

                    proposer_id = posible
                    resultado = posible_resultado
                    break

            if proposer_id is None:

                raise RuntimeError(
                    "No existe un proponente "
                    "con vecindario."
                )

            locales = set(
                resultado["locales"]
            )

            persistentes = set(
                resultado[
                    "persistentes"
                ]
            )

            total = (
                locales
                | persistentes
            )

            # =================================================
            # INVITACIÓN
            # =================================================

            invitation_id = (
                uuid_determinista(
                    args.semilla_simulacion,
                    f"invitacion-v3:{indice}"
                )
            )

            candidate_email = (
                f"candidato_v3_"
                f"{args.semilla_simulacion}_"
                f"{indice}"
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
                (%s, %s, %s, %s, %s, 'open')
                """,
                (
                    invitation_id,
                    proposer_id,
                    candidate_email,
                    opened_at,
                    closes_at
                )
            )

            # =================================================
            # VOTOS
            # =================================================

            votos_si = 0

            for voter_id in sorted(total):

                if voter_id in locales:

                    voter_role = "local"
                    votos_locales += 1

                else:

                    voter_role = "persistente"
                    votos_persistentes += 1

                azar = rng.random()

                if azar < args.prob_si:

                    choice = "yes"
                    reason = None
                    votos_si += 1

                elif azar < (
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
                        cast_at,
                        voter_role
                    )
                    VALUES
                    (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        invitation_id,
                        voter_id,
                        choice,
                        reason,
                        cast_at,
                        voter_role
                    )
                )

            # =================================================
            # CUÓRUM
            # =================================================

            cuorum = calcular_cuorum(
                len(total)
            )

            if votos_si >= cuorum:

                status = (
                    "closed_approved"
                )

                aprobadas += 1

            else:

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

            # =================================================
            # NUEVO USUARIO
            # =================================================

            if status == "closed_approved":

                nuevo_user_id = (
                    uuid_determinista(
                        args.semilla_simulacion,
                        f"usuario-v3:{indice}"
                    )
                )

                fecha_aceptacion = (
                    closes_at
                    + timedelta(minutes=1)
                )

                rama_root_id = (
                    usuarios[
                        proposer_id
                    ]["rama_root_id"]
                )

                cur.execute(
                    """
                    INSERT INTO users
                    (
                        id,
                        display_name,
                        inviter_id,
                        principles_accepted_at,
                        status,
                        rama_root_id
                    )
                    VALUES
                    (%s, %s, %s, %s, 'active', %s)
                    """,
                    (
                        nuevo_user_id,
                        fake.name(),
                        proposer_id,
                        fecha_aceptacion,
                        rama_root_id
                    )
                )

                # Hermanos v1
                asignar_hermanos_nuevo(
                    cur,
                    nuevo_user_id,
                    args.semilla_red,
                    fecha_aceptacion
                )

                # Vecinos persistentes v3
                asignar_vecinos_nuevo(
                    cur,
                    nuevo_user_id,
                    args.semilla_red,
                    fecha_aceptacion
                )

            print(
                f"Invitación {numero + 1}: "
                f"locales={len(locales)}, "
                f"persistentes={len(persistentes)}, "
                f"total={len(total)}, "
                f"cuórum={cuorum}, "
                f"SI={votos_si}, "
                f"estado={status}"
            )

        conn.commit()

        print()
        print("SIMULACIÓN V3 COMPLETADA")
        print("================================")

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
            f"Votos locales: "
            f"{votos_locales}"
        )

        print(
            f"Votos persistentes: "
            f"{votos_persistentes}"
        )

        print("================================")

    except Exception as error:

        conn.rollback()

        print()
        print(
            "Error durante simulación v3:"
        )

        print(error)

        raise

    finally:

        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
