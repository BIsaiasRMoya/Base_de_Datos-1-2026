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
    obtener_ascendentes,
    obtener_hermanos,
    sortear_hermanos,
)

from funciones_v3 import (
    calcular_vecindario_v3,
    calcular_vecinos_persistentes,
)

from funciones_v4 import (
    separar_vecindario_por_actividad,
    calcular_cuorum_v4,
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
# VECINOS INTER-RAMA
# ============================================================

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


# ============================================================
# CARGAS
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
        str(uid): int(cantidad)
        for uid, cantidad
        in cur.fetchall()
    }


# ============================================================
# HERMANOS PARA NUEVO USUARIO
# ============================================================

def asignar_hermanos_nuevo(
    cur,
    user_id,
    semilla,
    fecha
):

    usuarios = cargar_usuarios(cur)

    estructura = {
        uid: {
            "inviter_id":
                datos["inviter_id"]
        }
        for uid, datos in usuarios.items()
    }

    ascendentes = obtener_ascendentes(
        estructura,
        user_id
    )

    hermanos = obtener_hermanos(
        estructura,
        user_id
    )

    # En v4 evitamos elegir hermanos inactivos.
    hermanos = [
        uid
        for uid in hermanos
        if usuarios[uid]["status"] == "active"
    ]

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
# VECINOS V3 PARA NUEVO USUARIO
# ============================================================

def asignar_persistentes_nuevo(
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
        rama,
        vecino
    ) in seleccionados.items():

        assignment_id = uuid_determinista(
            semilla,
            (
                f"inter-rama:"
                f"{user_id}:"
                f"{rama}"
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
                vecino,
                rama,
                fecha
            )
        )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Simulación de admisiones v4"
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
        default=2029
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

    total_prob = (
        args.prob_si
        + args.prob_no
        + args.prob_abstencion
    )

    if abs(total_prob - 1.0) > 0.0001:

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

    votos_emitidos = 0
    abstenciones_automaticas = 0

    try:

        # ====================================================
        # FECHA DE INICIO
        # ====================================================

        cur.execute(
            """
            SELECT MAX(last_active_at)
            FROM users
            """
        )

        fecha_actividad = cur.fetchone()[0]

        cur.execute(
            """
            SELECT MAX(closes_at)
            FROM invitations
            """
        )

        fecha_invitacion = cur.fetchone()[0]

        fechas = [
            fecha
            for fecha in (
                fecha_actividad,
                fecha_invitacion
            )
            if fecha is not None
        ]

        fecha_inicio = (
            max(fechas)
            + timedelta(days=1)
        )

        cur.execute(
            """
            SELECT COUNT(*)
            FROM invitations
            WHERE candidate_email
                  LIKE 'candidato_v4_%'
            """
        )

        offset = cur.fetchone()[0]

        # ====================================================
        # SIMULAR
        # ====================================================

        for numero in range(
            args.num_invitaciones
        ):

            indice = offset + numero

            usuarios = cargar_usuarios(
                cur
            )

            # Solo miembros activos pueden proponer.
            proponentes = [
                uid
                for uid, datos
                in usuarios.items()
                if datos["status"] == "active"
            ]

            rng.shuffle(
                proponentes
            )

            proposer_id = None
            resultado = None
            actividad = None

            for posible in proponentes:

                hermanos = cargar_hermanos(
                    cur,
                    posible
                )

                persistentes = cargar_persistentes(
                    cur,
                    posible
                )

                vecindario = calcular_vecindario_v3(
                    usuarios=usuarios,
                    user_id=posible,
                    semilla=args.semilla_red,
                    hermanos_persistidos=hermanos,
                    vecinos_persistentes=persistentes
                )

                if not vecindario["total"]:
                    continue

                division = (
                    separar_vecindario_por_actividad(
                        usuarios,
                        vecindario["total"]
                    )
                )

                if not division["activos"]:
                    continue

                proposer_id = posible
                resultado = vecindario
                actividad = division

                break

            if proposer_id is None:

                raise RuntimeError(
                    "No existe proponente activo "
                    "con vecindario activo."
                )

            locales = set(
                resultado["locales"]
            )

            activos = set(
                actividad["activos"]
            )

            inactivos = set(
                actividad["inactivos"]
            )

            # =================================================
            # INVITACIÓN
            # =================================================

            invitation_id = uuid_determinista(
                args.semilla_simulacion,
                f"invitacion-v4:{indice}"
            )

            opened_at = (
                fecha_inicio
                + timedelta(days=numero * 8)
            )

            closes_at = (
                opened_at
                + timedelta(days=7)
            )

            candidate_email = (
                f"candidato_v4_"
                f"{args.semilla_simulacion}_"
                f"{indice}"
                f"@example.org"
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
            # VOTOS DE MIEMBROS ACTIVOS
            # =================================================

            votos_si = 0

            for voter_id in sorted(
                activos
            ):

                voter_role = (
                    "local"
                    if voter_id in locales
                    else "persistente"
                )

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

                votos_emitidos += 1

            # Los inactivos se consideran
            # abstención automática sin insertar
            # un voto artificial.
            abstenciones_automaticas += (
                len(inactivos)
            )

            # =================================================
            # CUÓRUM EFECTIVO
            # =================================================

            cuorum = calcular_cuorum_v4(
                activos
            )

            if votos_si >= cuorum:

                status = "closed_approved"
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
            # NUEVO MIEMBRO
            # =================================================

            if status == "closed_approved":

                nuevo_user_id = uuid_determinista(
                    args.semilla_simulacion,
                    f"usuario-v4:{indice}"
                )

                fecha_ingreso = (
                    closes_at
                    + timedelta(minutes=1)
                )

                rama_root = (
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
                        rama_root_id,
                        last_active_at
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        'active',
                        %s,
                        %s
                    )
                    """,
                    (
                        nuevo_user_id,
                        fake.name(),
                        proposer_id,
                        fecha_ingreso,
                        rama_root,
                        fecha_ingreso
                    )
                )

                asignar_hermanos_nuevo(
                    cur,
                    nuevo_user_id,
                    args.semilla_red,
                    fecha_ingreso
                )

                asignar_persistentes_nuevo(
                    cur,
                    nuevo_user_id,
                    args.semilla_red,
                    fecha_ingreso
                )

            print(
                f"Invitación {numero + 1}: "
                f"activos={len(activos)}, "
                f"inactivos={len(inactivos)}, "
                f"cuórum={cuorum}, "
                f"SI={votos_si}, "
                f"estado={status}"
            )

        conn.commit()

        print()
        print("SIMULACIÓN V4 COMPLETADA")
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
            f"Votos emitidos: "
            f"{votos_emitidos}"
        )

        print(
            f"Abstenciones automáticas "
            f"por inactividad: "
            f"{abstenciones_automaticas}"
        )

        print("================================")

    except Exception as error:

        conn.rollback()

        print()
        print("Error durante v4:")
        print(error)

        raise

    finally:

        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
