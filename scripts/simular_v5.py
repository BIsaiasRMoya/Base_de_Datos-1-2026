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

from funciones_v3 import calcular_vecindario_v3

from funciones_v5 import (
    obtener_candidatos_jurado,
    sortear_jurado_disciplinario,
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

            "status": str(status),
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
# VECINDARIO ACTUAL
# ============================================================

def obtener_vecindario(
    cur,
    usuarios,
    user_id,
    semilla
):

    hermanos = cargar_hermanos(
        cur,
        user_id
    )

    persistentes = cargar_persistentes(
        cur,
        user_id
    )

    resultado = calcular_vecindario_v3(
        usuarios=usuarios,
        user_id=user_id,
        semilla=semilla,
        hermanos_persistidos=hermanos,
        vecinos_persistentes=persistentes
    )

    return set(
        resultado["total"]
    )


# ============================================================
# BUSCAR CONFLICTO CON JURADO SUFICIENTE
# ============================================================

def seleccionar_conflicto(
    cur,
    usuarios,
    rng,
    semilla
):

    activos = [
        uid
        for uid, datos in usuarios.items()
        if datos["status"] == "active"
    ]

    rng.shuffle(
        activos
    )

    for complainant_id in activos:

        vecindario_denunciante = (
            obtener_vecindario(
                cur,
                usuarios,
                complainant_id,
                semilla
            )
        )

        acusados = [
            uid
            for uid in activos
            if uid != complainant_id
        ]

        rng.shuffle(
            acusados
        )

        for accused_id in acusados:

            vecindario_acusado = (
                obtener_vecindario(
                    cur,
                    usuarios,
                    accused_id,
                    semilla
                )
            )

            candidatos = (
                obtener_candidatos_jurado(
                    usuarios=usuarios,
                    complainant_id=
                        complainant_id,
                    accused_id=
                        accused_id,
                    vecindario_complainant=
                        vecindario_denunciante,
                    vecindario_accused=
                        vecindario_acusado
                )
            )

            if len(candidatos) >= 7:

                return {
                    "complainant":
                        complainant_id,

                    "accused":
                        accused_id,

                    "vecindario_complainant":
                        vecindario_denunciante,

                    "vecindario_accused":
                        vecindario_acusado,
                }

    return None


# ============================================================
# GENERAR DECISIONES
# ============================================================

def generar_decisiones(
    jurado,
    resultado
):

    decisiones = {}

    # --------------------------------------------------------
    # SUSPENSIÓN
    # --------------------------------------------------------

    if resultado == "suspension":

        for indice, juror_id in enumerate(
            jurado
        ):

            if indice < 5:

                decisiones[juror_id] = (
                    "suspension"
                )

            else:

                decisiones[juror_id] = (
                    "warning"
                )

    # --------------------------------------------------------
    # EXPULSIÓN
    # --------------------------------------------------------

    elif resultado == "expulsion":

        for indice, juror_id in enumerate(
            jurado
        ):

            if indice < 5:

                decisiones[juror_id] = (
                    "expulsion"
                )

            else:

                decisiones[juror_id] = (
                    "suspension"
                )

    # --------------------------------------------------------
    # ADVERTENCIA
    # --------------------------------------------------------

    elif resultado == "warning":

        for indice, juror_id in enumerate(
            jurado
        ):

            if indice < 4:

                decisiones[juror_id] = (
                    "warning"
                )

            else:

                decisiones[juror_id] = (
                    "archive"
                )

    # --------------------------------------------------------
    # ARCHIVO
    # --------------------------------------------------------

    else:

        for indice, juror_id in enumerate(
            jurado
        ):

            if indice < 4:

                decisiones[juror_id] = (
                    "archive"
                )

            else:

                decisiones[juror_id] = (
                    "warning"
                )

    return decisiones


# ============================================================
# RESOLVER RESULTADO
# ============================================================

def resolver_resultado(
    decisiones
):

    conteo = {
        "archive": 0,
        "warning": 0,
        "suspension": 0,
        "expulsion": 0,
    }

    for decision in decisiones.values():

        conteo[decision] += 1

    # --------------------------------------------------------
    # Expulsión requiere 5/7
    # --------------------------------------------------------

    if conteo["expulsion"] >= 5:

        return (
            "pending_expulsion_review",
            conteo
        )

    # --------------------------------------------------------
    # Suspensión requiere 5/7
    # --------------------------------------------------------

    if conteo["suspension"] >= 5:

        return (
            "resolved_suspension",
            conteo
        )

    # --------------------------------------------------------
    # Advertencia
    # --------------------------------------------------------

    if (
        conteo["warning"]
        > conteo["archive"]
    ):

        return (
            "resolved_warning",
            conteo
        )

    # --------------------------------------------------------
    # Archivo
    # --------------------------------------------------------

    return (
        "resolved_archived",
        conteo
    )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Simular proceso disciplinario v5"
    )

    parser.add_argument(
        "--semilla",
        type=int,
        default=42
    )

    parser.add_argument(
        "--resultado",
        choices=[
            "archive",
            "warning",
            "suspension",
            "expulsion",
        ],
        default="warning"
    )

    parser.add_argument(
        "--recusar-uno",
        action="store_true",
        help=
        "Recusa uno de los jurados y "
        "sortea un reemplazo determinista"
    )

    args = parser.parse_args()

    rng = random.Random(
        args.semilla
    )

    fake = Faker("es_CL")

    fake.seed_instance(
        args.semilla
    )

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    conn.autocommit = False

    cur = conn.cursor()

    try:

        # ====================================================
        # CARGAR RED
        # ====================================================

        usuarios = cargar_usuarios(
            cur
        )

        # ====================================================
        # BUSCAR DENUNCIANTE Y DENUNCIADO
        # ====================================================

        conflicto = seleccionar_conflicto(
            cur,
            usuarios,
            rng,
            args.semilla
        )

        if conflicto is None:

            raise RuntimeError(
                "No existe una combinación "
                "denunciante/denunciado con "
                "al menos 7 jurados elegibles."
            )

        complainant_id = (
            conflicto["complainant"]
        )

        accused_id = (
            conflicto["accused"]
        )

        vecindario_complainant = (
            conflicto[
                "vecindario_complainant"
            ]
        )

        vecindario_accused = (
            conflicto[
                "vecindario_accused"
            ]
        )

        # ====================================================
        # NUMERAR PROCESO
        # ====================================================

        cur.execute(
            """
            SELECT COUNT(*)
            FROM disciplinary_processes
            """
        )

        numero = cur.fetchone()[0]

        process_id = uuid_determinista(
            args.semilla,
            f"proceso-v5:{numero}"
        )

        # ====================================================
        # FECHA BASE
        # ====================================================

        cur.execute(
            """
            SELECT MAX(last_active_at)
            FROM users
            """
        )

        fecha_usuarios = (
            cur.fetchone()[0]
        )

        cur.execute(
            """
            SELECT MAX(closes_at)
            FROM invitations
            """
        )

        fecha_invitaciones = (
            cur.fetchone()[0]
        )

        fechas = [
            fecha
            for fecha in (
                fecha_usuarios,
                fecha_invitaciones
            )
            if fecha is not None
        ]

        if not fechas:

            raise RuntimeError(
                "No existen fechas válidas "
                "para iniciar el proceso."
            )

        opened_at = (
            max(fechas)
            + timedelta(days=1)
        )

        # ====================================================
        # 1. DENUNCIA
        # ====================================================

        complaint_body = (
            "Denuncia sintética generada "
            "para probar el flujo "
            "disciplinario de v5."
        )

        evidence_refs = [
            f"evidencia://v5/{numero}/1",
            f"evidencia://v5/{numero}/2",
        ]

        cur.execute(
            """
            INSERT INTO disciplinary_processes
            (
                id,
                complainant_id,
                accused_id,
                complaint_body,
                evidence_refs,
                opened_at,
                status
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                'open'
            )
            """,
            (
                process_id,
                complainant_id,
                accused_id,
                complaint_body,
                evidence_refs,
                opened_at
            )
        )

        # ====================================================
        # 2. DESCARGO
        # ====================================================
        #
        # El plazo es de 14 días.
        # Simulamos respuesta al día 7.
        # ====================================================

        submitted_at = (
            opened_at
            + timedelta(days=7)
        )

        cur.execute(
            """
            INSERT INTO defense_responses
            (
                process_id,
                body,
                submitted_at
            )
            VALUES
            (%s, %s, %s)
            """,
            (
                process_id,
                (
                    "Descargo sintético de "
                    "la persona denunciada."
                ),
                submitted_at
            )
        )

        cur.execute(
            """
            UPDATE disciplinary_processes
            SET status = 'defense'
            WHERE id = %s
            """,
            (process_id,)
        )

        # ====================================================
        # 3. SORTEAR JURADO INICIAL
        # ====================================================

        sorted_at = (
            opened_at
            + timedelta(days=14)
        )

        jurado_original = (
            sortear_jurado_disciplinario(
                usuarios=usuarios,
                complainant_id=
                    complainant_id,
                accused_id=
                    accused_id,
                vecindario_complainant=
                    vecindario_complainant,
                vecindario_accused=
                    vecindario_accused,
                semilla=args.semilla,
                process_id=process_id,
                cantidad=7
            )
        )

        for juror_id in jurado_original:

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
                (
                    %s,
                    %s,
                    %s,
                    FALSE
                )
                """,
                (
                    process_id,
                    juror_id,
                    sorted_at
                )
            )

        # Jurado que realmente deliberará.
        jurado_efectivo = list(
            jurado_original
        )

        # ====================================================
        # 4. RECUSACIÓN OPCIONAL
        # ====================================================

        if args.recusar_uno:

            jurado_recusado = (
                jurado_original[0]
            )

            # --------------------------------------------
            # Marcar recusación
            # --------------------------------------------

            cur.execute(
                """
                UPDATE juries

                SET
                    recused = TRUE,
                    recusal_reason = %s

                WHERE process_id = %s
                  AND juror_id = %s
                """,
                (
                    (
                        "Conflicto de interés "
                        "declarado."
                    ),
                    process_id,
                    jurado_recusado
                )
            )

            # --------------------------------------------
            # Buscar reemplazo.
            #
            # Ninguno de los 7 jurados originales
            # puede volver a ser elegido.
            # --------------------------------------------

            reemplazo = (
                sortear_jurado_disciplinario(
                    usuarios=usuarios,

                    complainant_id=
                        complainant_id,

                    accused_id=
                        accused_id,

                    vecindario_complainant=
                        vecindario_complainant,

                    vecindario_accused=
                        vecindario_accused,

                    semilla=args.semilla,

                    process_id=(
                        f"{process_id}:"
                        f"reemplazo:"
                        f"{jurado_recusado}"
                    ),

                    cantidad=1,

                    excluir=set(
                        jurado_original
                    )
                )[0]
            )

            # --------------------------------------------
            # Registrar reemplazo
            # --------------------------------------------

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
                (
                    %s,
                    %s,
                    %s,
                    FALSE
                )
                """,
                (
                    process_id,
                    reemplazo,
                    sorted_at
                )
            )

            # --------------------------------------------
            # Reconstruir jurado efectivo
            # --------------------------------------------

            jurado_efectivo = [
                uid
                for uid
                in jurado_original
                if uid != jurado_recusado
            ]

            jurado_efectivo.append(
                reemplazo
            )

            print()
            print(
                "RECUSACIÓN"
            )

            print(
                "Jurado recusado:",
                jurado_recusado
            )

            print(
                "Reemplazo:",
                reemplazo
            )

        # ====================================================
        # COMPROBAR QUE SIGAN SIENDO 7
        # ====================================================

        if len(jurado_efectivo) != 7:

            raise RuntimeError(
                "El jurado efectivo debe "
                "tener exactamente 7 miembros."
            )

        if len(
            set(jurado_efectivo)
        ) != 7:

            raise RuntimeError(
                "El jurado efectivo contiene "
                "personas duplicadas."
            )

        # ====================================================
        # PASAR A ETAPA DE JURADO
        # ====================================================

        cur.execute(
            """
            UPDATE disciplinary_processes
            SET status = 'jury'
            WHERE id = %s
            """,
            (process_id,)
        )

        # ====================================================
        # 5. DELIBERACIÓN
        # ====================================================
        #
        # La propuesta entrega 14 días.
        # Simulamos la decisión al día 10.
        # ====================================================

        decided_at = (
            sorted_at
            + timedelta(days=10)
        )

        decisiones = generar_decisiones(
            jurado_efectivo,
            args.resultado
        )

        for (
            juror_id,
            decision
        ) in decisiones.items():

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
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    process_id,
                    juror_id,
                    decision,
                    fake.sentence(
                        nb_words=10
                    ),
                    decided_at
                )
            )

        # ====================================================
        # 6. RESOLUCIÓN
        # ====================================================

        (
            estado_final,
            conteo
        ) = resolver_resultado(
            decisiones
        )

        cur.execute(
            """
            UPDATE disciplinary_processes

            SET status = %s

            WHERE id = %s
            """,
            (
                estado_final,
                process_id
            )
        )

        # ====================================================
        # CONSECUENCIA SOBRE EL USUARIO
        # ====================================================

        if estado_final == (
            "resolved_suspension"
        ):

            cur.execute(
                """
                UPDATE users

                SET status =
                    'suspended_sanction'

                WHERE id = %s
                """,
                (accused_id,)
            )

        # ----------------------------------------------------
        # EXPULSIÓN
        # ----------------------------------------------------
        #
        # No se aplica inmediatamente.
        #
        # Queda pending_expulsion_review
        # hasta completar el período de revisión
        # y, si corresponde, el segundo jurado.
        # ----------------------------------------------------

        conn.commit()

        # ====================================================
        # OBTENER NOMBRES
        # ====================================================

        cur.execute(
            """
            SELECT display_name
            FROM users
            WHERE id = %s
            """,
            (complainant_id,)
        )

        complainant_name = (
            cur.fetchone()[0]
        )

        cur.execute(
            """
            SELECT display_name
            FROM users
            WHERE id = %s
            """,
            (accused_id,)
        )

        accused_name = (
            cur.fetchone()[0]
        )

        # ====================================================
        # RESULTADO
        # ====================================================

        print()
        print(
            "PROCESO DISCIPLINARIO V5"
        )

        print(
            "================================"
        )

        print(
            f"Proceso: {process_id}"
        )

        print(
            f"Denunciante: "
            f"{complainant_name}"
        )

        print(
            f"Denunciado: "
            f"{accused_name}"
        )

        print()

        print(
            f"Jurados originales: "
            f"{len(jurado_original)}"
        )

        print(
            f"Jurados efectivos: "
            f"{len(jurado_efectivo)}"
        )

        print()

        print("Decisiones:")

        for opcion in (
            "archive",
            "warning",
            "suspension",
            "expulsion"
        ):

            print(
                f"  {opcion}: "
                f"{conteo[opcion]}"
            )

        print()

        print(
            f"Estado final: "
            f"{estado_final}"
        )

        print(
            "================================"
        )

    except Exception as error:

        conn.rollback()

        print()

        print(
            "Error durante proceso v5:"
        )

        print(error)

        raise

    finally:

        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
