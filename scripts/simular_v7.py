#!/usr/bin/env python3

import argparse
import hashlib
import math
import os
import random
import uuid
from datetime import timedelta

import psycopg2
from dotenv import load_dotenv

from funciones_v7 import (
    calcular_cuorum_regla,
    siguiente_version,
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
# PROPUESTAS DE DEMOSTRACIÓN
# ============================================================

PROPUESTAS_DEMO = {

    "inactivity_threshold":
        (
            "Una persona puede ser marcada "
            "inactive tras cinco meses "
            "sin actividad significativa."
        ),

    "technical_revocation":
        (
            "Un mandato técnico puede ser "
            "revocado con tres quintos "
            "de la red activa."
        ),

    "admission_quorum":
        (
            "Las admisiones requieren "
            "mayoría del vecindario "
            "correspondiente y al menos "
            "un voto inter-rama."
        ),

    "rule_change_quorum":
        (
            "Una modificación al reglamento "
            "requiere dos tercios "
            "de la red activa."
        ),
}


# ============================================================
# UUID DETERMINISTA
# ============================================================

def uuid_determinista(
    semilla,
    contexto
):

    texto = (
        f"{semilla}|"
        f"{contexto}"
    )

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
# USUARIOS ACTIVOS
# ============================================================

def cargar_usuarios_activos(cur):

    cur.execute(
        """
        SELECT
            id,
            display_name

        FROM users

        WHERE status = 'active'

        ORDER BY id
        """
    )

    return [
        (
            str(user_id),
            display_name
        )
        for user_id, display_name
        in cur.fetchall()
    ]


# ============================================================
# REGLA VIGENTE
# ============================================================

def cargar_regla_actual(
    cur,
    rule_key
):

    cur.execute(
        """
        SELECT
            id,
            version,
            body,
            effective_from

        FROM rules

        WHERE rule_key = %s
          AND effective_until IS NULL
        """,
        (rule_key,)
    )

    return cur.fetchone()


# ============================================================
# FECHA BASE
# ============================================================

def obtener_fecha_base(cur):

    fechas = []

    consultas = [

        """
        SELECT MAX(effective_from)
        FROM rules
        """,

        """
        SELECT MAX(closes_at)
        FROM rule_proposals
        """,

        """
        SELECT MAX(executed_at)
        FROM technical_action_log
        """,

        """
        SELECT MAX(closes_at)
        FROM invitations
        """,

        """
        SELECT MAX(decided_at)
        FROM jury_decisions
        """,
    ]

    for consulta in consultas:

        cur.execute(
            consulta
        )

        fecha = cur.fetchone()[0]

        if fecha is not None:

            fechas.append(
                fecha
            )

    if not fechas:

        raise RuntimeError(
            "No existe una fecha base."
        )

    return (
        max(fechas)
        + timedelta(days=1)
    )


# ============================================================
# DISTRIBUIR VOTOS
# ============================================================

def generar_votos(
    usuarios,
    quorum,
    resultado,
    semilla
):
    """
    Todos los miembros activos participan.

    Para aprobación:
        exactamente quorum votos YES.

    Para rechazo:
        quorum - 1 votos YES.

    Los votos restantes se distribuyen
    entre NO y ABSTAIN.
    """

    rng = random.Random(
        semilla
    )

    votantes = list(
        usuarios
    )

    rng.shuffle(
        votantes
    )

    if resultado == "approved":

        cantidad_si = quorum

    else:

        cantidad_si = max(
            quorum - 1,
            0
        )

    restantes = (
        len(votantes)
        - cantidad_si
    )

    cantidad_no = (
        math.ceil(
            restantes / 2
        )
    )

    votos = {}

    for indice, (
        user_id,
        nombre
    ) in enumerate(votantes):

        if indice < cantidad_si:

            votos[user_id] = "yes"

        elif indice < (
            cantidad_si
            + cantidad_no
        ):

            votos[user_id] = "no"

        else:

            votos[user_id] = (
                "abstain"
            )

    return votos


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Simulación de auto-gobernanza v7"
    )

    parser.add_argument(
        "--regla",
        choices=sorted(
            PROPUESTAS_DEMO.keys()
        ),
        required=True
    )

    parser.add_argument(
        "--resultado",
        choices=[
            "approved",
            "rejected",
        ],
        required=True
    )

    parser.add_argument(
        "--semilla",
        type=int,
        default=42
    )

    args = parser.parse_args()

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    conn.autocommit = False

    cur = conn.cursor()

    try:

        # ====================================================
        # 1. RED ACTIVA
        # ====================================================

        usuarios = cargar_usuarios_activos(
            cur
        )

        total_activos = len(
            usuarios
        )

        if total_activos == 0:

            raise RuntimeError(
                "No existen usuarios activos."
            )

        quorum = calcular_cuorum_regla(
            total_activos
        )

        # ====================================================
        # 2. REGLA ACTUAL
        # ====================================================

        regla_actual = cargar_regla_actual(
            cur,
            args.regla
        )

        if regla_actual is None:

            raise RuntimeError(
                f"No existe regla vigente "
                f"para {args.regla}."
            )

        (
            current_rule_id,
            current_version,
            current_body,
            effective_from
        ) = regla_actual

        current_rule_id = str(
            current_rule_id
        )

        # ====================================================
        # 3. PROPONENTE
        # ====================================================

        usuarios_ordenados = sorted(
            usuarios,
            key=lambda fila:
                hashlib.sha256(
                    (
                        f"{args.semilla}|"
                        f"{fila[0]}|"
                        f"proponente-v7"
                    ).encode(
                        "utf-8"
                    )
                ).hexdigest()
        )

        (
            proposer_id,
            proposer_name
        ) = usuarios_ordenados[0]

        # ====================================================
        # 4. FECHAS
        # ====================================================

        opened_at = obtener_fecha_base(
            cur
        )

        # La propuesta exige AL MENOS 14 días.
        closes_at = (
            opened_at
            + timedelta(days=14)
        )

        # ====================================================
        # 5. CREAR PROPUESTA
        # ====================================================

        propuesta_numero = 0

        cur.execute(
            """
            SELECT COUNT(*)
            FROM rule_proposals
            """
        )

        propuesta_numero = (
            cur.fetchone()[0]
        )

        proposal_id = uuid_determinista(
            args.semilla,
            (
                f"rule-proposal:"
                f"{args.regla}:"
                f"{propuesta_numero}"
            )
        )

        proposed_body = (
            PROPUESTAS_DEMO[
                args.regla
            ]
        )

        cur.execute(
            """
            INSERT INTO rule_proposals
            (
                id,
                proposer_id,
                current_rule_id,
                proposed_body,
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
                %s,
                'open'
            )
            """,
            (
                proposal_id,
                proposer_id,
                current_rule_id,
                proposed_body,
                opened_at,
                closes_at
            )
        )

        # ====================================================
        # 6. GENERAR VOTOS
        # ====================================================

        votos = generar_votos(
            usuarios=usuarios,
            quorum=quorum,
            resultado=args.resultado,
            semilla=args.semilla
        )

        cantidad_si = 0
        cantidad_no = 0
        cantidad_abstain = 0

        for indice, (
            voter_id,
            choice
        ) in enumerate(
            votos.items(),
            start=1
        ):

            # Distribuimos los votos dentro
            # del período de discusión.
            voted_at = (
                opened_at
                + timedelta(
                    days=(
                        1
                        + (
                            (indice - 1)
                            % 13
                        )
                    ),
                    minutes=indice
                )
            )

            cur.execute(
                """
                INSERT INTO rule_votes
                (
                    proposal_id,
                    voter_id,
                    choice,
                    voted_at
                )
                VALUES
                (%s, %s, %s, %s)
                """,
                (
                    proposal_id,
                    voter_id,
                    choice,
                    voted_at
                )
            )

            if choice == "yes":

                cantidad_si += 1

            elif choice == "no":

                cantidad_no += 1

            else:

                cantidad_abstain += 1

        # ====================================================
        # 7. RESOLVER
        # ====================================================

        aprobada = (
            cantidad_si >= quorum
        )

        if aprobada:

            estado_final = "approved"

        else:

            estado_final = "rejected"

        cur.execute(
            """
            UPDATE rule_proposals

            SET status = %s

            WHERE id = %s
            """,
            (
                estado_final,
                proposal_id
            )
        )

        # ====================================================
        # 8. SI SE APRUEBA:
        #
        # Cerrar versión anterior
        # y crear la nueva.
        # ====================================================

        nueva_version = None

        if aprobada:

            effective_at = (
                closes_at
            )

            # --------------------------------------------
            # Cerrar la regla anterior
            # --------------------------------------------

            cur.execute(
                """
                UPDATE rules

                SET effective_until = %s

                WHERE id = %s
                  AND effective_until
                      IS NULL
                """,
                (
                    effective_at,
                    current_rule_id
                )
            )

            if cur.rowcount != 1:

                raise RuntimeError(
                    "No se pudo cerrar "
                    "la versión anterior."
                )

            # --------------------------------------------
            # Calcular versión siguiente
            # --------------------------------------------

            cur.execute(
                """
                SELECT version

                FROM rules

                WHERE rule_key = %s

                ORDER BY version
                """,
                (args.regla,)
            )

            versiones = [
                fila[0]
                for fila
                in cur.fetchall()
            ]

            nueva_version = (
                siguiente_version(
                    versiones
                )
            )

            # --------------------------------------------
            # Crear versión nueva
            # --------------------------------------------

            new_rule_id = (
                uuid_determinista(
                    args.semilla,
                    (
                        f"rule:"
                        f"{args.regla}:"
                        f"v{nueva_version}"
                    )
                )
            )

            cur.execute(
                """
                INSERT INTO rules
                (
                    id,
                    version,
                    rule_key,
                    body,
                    effective_from,
                    effective_until
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    NULL
                )
                """,
                (
                    new_rule_id,
                    nueva_version,
                    args.regla,
                    proposed_body,
                    effective_at
                )
            )

        conn.commit()

        # ====================================================
        # RESULTADO
        # ====================================================

        print()
        print("AUTO-GOBERNANZA V7")
        print(
            "================================"
        )

        print(
            f"Regla: "
            f"{args.regla}"
        )

        print(
            f"Versión actual: "
            f"v{current_version}"
        )

        print(
            f"Proponente: "
            f"{proposer_name}"
        )

        print()

        print(
            f"Miembros activos: "
            f"{total_activos}"
        )

        print(
            f"Cuórum 2/3: "
            f"{quorum}"
        )

        print()

        print(
            f"YES: "
            f"{cantidad_si}"
        )

        print(
            f"NO: "
            f"{cantidad_no}"
        )

        print(
            f"ABSTAIN: "
            f"{cantidad_abstain}"
        )

        print()

        print(
            f"Estado: "
            f"{estado_final}"
        )

        if aprobada:

            print(
                f"Nueva versión: "
                f"v{nueva_version}"
            )

            print(
                "✅ Reglamento actualizado."
            )

        else:

            print(
                "❌ Propuesta rechazada."
            )

            print(
                "La regla vigente "
                "no fue modificada."
            )

        print(
            "================================"
        )

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
