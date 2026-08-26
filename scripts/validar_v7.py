#!/usr/bin/env python3

import math
import os

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
# CUÓRUM
# ============================================================

def calcular_cuorum(total):

    if total <= 0:
        return 0

    return math.ceil(
        (2 * total) / 3
    )


# ============================================================
# MAIN
# ============================================================

def main():

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    cur = conn.cursor()

    errores = []

    reglas_revisadas = 0
    propuestas_revisadas = 0
    votos_revisados = 0

    # ========================================================
    # 1. VALIDAR VERSIONES DE REGLAS
    # ========================================================

    cur.execute(
        """
        SELECT DISTINCT rule_key
        FROM rules
        ORDER BY rule_key
        """
    )

    rule_keys = [
        fila[0]
        for fila in cur.fetchall()
    ]

    for rule_key in rule_keys:

        cur.execute(
            """
            SELECT
                id,
                version,
                body,
                effective_from,
                effective_until

            FROM rules

            WHERE rule_key = %s

            ORDER BY version
            """,
            (rule_key,)
        )

        versiones = cur.fetchall()

        reglas_revisadas += len(
            versiones
        )

        if not versiones:

            continue

        # ----------------------------------------------------
        # Las versiones deben ser 1, 2, 3, ...
        # ----------------------------------------------------

        numeros = [
            fila[1]
            for fila in versiones
        ]

        esperadas = list(
            range(
                1,
                len(versiones) + 1
            )
        )

        if numeros != esperadas:

            errores.append(
                f"Regla {rule_key}: "
                f"versiones no consecutivas. "
                f"Encontradas={numeros}"
            )

        # ----------------------------------------------------
        # Debe existir exactamente una versión vigente.
        # ----------------------------------------------------

        vigentes = [
            fila
            for fila in versiones
            if fila[4] is None
        ]

        if len(vigentes) != 1:

            errores.append(
                f"Regla {rule_key}: "
                f"debe existir exactamente "
                f"una versión vigente."
            )

        # ----------------------------------------------------
        # La vigente debe ser la última versión.
        # ----------------------------------------------------

        if vigentes:

            version_vigente = (
                vigentes[0][1]
            )

            version_maxima = max(
                numeros
            )

            if (
                version_vigente
                != version_maxima
            ):

                errores.append(
                    f"Regla {rule_key}: "
                    f"la versión vigente "
                    f"no es la más reciente."
                )

        # ----------------------------------------------------
        # Comprobar continuidad temporal.
        #
        # v1.effective_until
        # =
        # v2.effective_from
        # ----------------------------------------------------

        for indice in range(
            len(versiones) - 1
        ):

            actual = versiones[
                indice
            ]

            siguiente = versiones[
                indice + 1
            ]

            actual_until = (
                actual[4]
            )

            siguiente_from = (
                siguiente[3]
            )

            if actual_until is None:

                errores.append(
                    f"Regla {rule_key} "
                    f"v{actual[1]}: "
                    f"versión histórica "
                    f"sin effective_until."
                )

                continue

            if (
                actual_until
                != siguiente_from
            ):

                errores.append(
                    f"Regla {rule_key}: "
                    f"hay discontinuidad "
                    f"entre v{actual[1]} "
                    f"y v{siguiente[1]}."
                )

    # ========================================================
    # 2. VALIDAR PROPUESTAS
    # ========================================================

    cur.execute(
        """
        SELECT
            rp.id,
            rp.proposer_id,
            rp.current_rule_id,
            rp.proposed_body,
            rp.opened_at,
            rp.closes_at,
            rp.status,

            r.rule_key,
            r.version,
            r.effective_from,
            r.effective_until

        FROM rule_proposals rp

        JOIN rules r
            ON r.id =
               rp.current_rule_id

        ORDER BY rp.opened_at
        """
    )

    propuestas = cur.fetchall()

    for (
        proposal_id,
        proposer_id,
        current_rule_id,
        proposed_body,
        opened_at,
        closes_at,
        status,
        rule_key,
        current_version,
        current_effective_from,
        current_effective_until
    ) in propuestas:

        propuestas_revisadas += 1

        # ----------------------------------------------------
        # Discusión mínima: 14 días.
        # ----------------------------------------------------

        duracion = (
            closes_at
            - opened_at
        )

        if (
            duracion.total_seconds()
            < 14 * 24 * 60 * 60
        ):

            errores.append(
                f"Propuesta {proposal_id}: "
                f"discusión menor a 14 días."
            )

        # ----------------------------------------------------
        # La regla referenciada debía existir
        # al abrir la propuesta.
        # ----------------------------------------------------

        if (
            current_effective_from
            > opened_at
        ):

            errores.append(
                f"Propuesta {proposal_id}: "
                f"referencia una regla que "
                f"todavía no estaba vigente."
            )

        if (
            current_effective_until
            is not None
            and current_effective_until
            < opened_at
        ):

            errores.append(
                f"Propuesta {proposal_id}: "
                f"referencia una regla que "
                f"ya no estaba vigente."
            )

        # ====================================================
        # 3. VOTOS
        # ====================================================

        cur.execute(
            """
            SELECT
                voter_id,
                choice,
                voted_at

            FROM rule_votes

            WHERE proposal_id = %s
            """,
            (proposal_id,)
        )

        votos = cur.fetchall()

        votos_revisados += len(
            votos
        )

        yes = 0
        no = 0
        abstain = 0

        for (
            voter_id,
            choice,
            voted_at
        ) in votos:

            # --------------------------------------------
            # Voto dentro del período.
            # --------------------------------------------

            if not (
                opened_at
                <= voted_at
                <= closes_at
            ):

                errores.append(
                    f"Propuesta {proposal_id}: "
                    f"voto fuera del período."
                )

            choice = str(
                choice
            )

            if choice == "yes":

                yes += 1

            elif choice == "no":

                no += 1

            elif choice == "abstain":

                abstain += 1

            else:

                errores.append(
                    f"Propuesta {proposal_id}: "
                    f"opción de voto inválida "
                    f"{choice}."
                )

        # ----------------------------------------------------
        # En nuestra simulación todos los miembros
        # activos del momento emiten un registro de voto.
        #
        # Por eso el total de rule_votes funciona como
        # snapshot del electorado activo.
        #
        # El esquema de la propuesta no almacena
        # active_member_count directamente.
        # ----------------------------------------------------

        total_electorado = len(
            votos
        )

        quorum = calcular_cuorum(
            total_electorado
        )

        aprobada = (
            yes >= quorum
        )

        # ----------------------------------------------------
        # Estado consistente
        # ----------------------------------------------------

        if (
            str(status) == "approved"
            and not aprobada
        ):

            errores.append(
                f"Propuesta {proposal_id}: "
                f"approved sin alcanzar 2/3. "
                f"YES={yes}, quorum={quorum}"
            )

        if (
            str(status) == "rejected"
            and aprobada
        ):

            errores.append(
                f"Propuesta {proposal_id}: "
                f"rejected aunque alcanzó 2/3."
            )

        # ====================================================
        # 4. PROPUESTA APROBADA
        # ====================================================

        if str(status) == "approved":

            nueva_version = (
                current_version + 1
            )

            cur.execute(
                """
                SELECT
                    id,
                    body,
                    effective_from,
                    effective_until

                FROM rules

                WHERE rule_key = %s
                  AND version = %s
                """,
                (
                    rule_key,
                    nueva_version
                )
            )

            nueva_regla = (
                cur.fetchone()
            )

            if nueva_regla is None:

                errores.append(
                    f"Propuesta {proposal_id}: "
                    f"aprobada pero no existe "
                    f"{rule_key} "
                    f"v{nueva_version}."
                )

            else:

                (
                    new_rule_id,
                    new_body,
                    new_effective_from,
                    new_effective_until
                ) = nueva_regla

                if (
                    new_body
                    != proposed_body
                ):

                    errores.append(
                        f"Propuesta {proposal_id}: "
                        f"el cuerpo de la nueva "
                        f"regla no coincide con "
                        f"la propuesta."
                    )

                if (
                    new_effective_from
                    != closes_at
                ):

                    errores.append(
                        f"Propuesta {proposal_id}: "
                        f"la nueva versión no "
                        f"comienza al cierre "
                        f"de la propuesta."
                    )

            # --------------------------------------------
            # La regla anterior debe cerrar
            # exactamente en ese instante.
            # --------------------------------------------

            if (
                current_effective_until
                != closes_at
            ):

                errores.append(
                    f"Propuesta {proposal_id}: "
                    f"la versión anterior no "
                    f"termina al cierre "
                    f"de la propuesta."
                )

    # ========================================================
    # 5. PROPUESTAS CON current_rule_id INEXISTENTE
    # ========================================================
    #
    # La FK ya debería impedir esto,
    # pero verificamos igualmente.
    # ========================================================

    cur.execute(
        """
        SELECT COUNT(*)

        FROM rule_proposals rp

        LEFT JOIN rules r
            ON r.id = rp.current_rule_id

        WHERE r.id IS NULL
        """
    )

    if cur.fetchone()[0] != 0:

        errores.append(
            "Existen propuestas apuntando "
            "a reglas inexistentes."
        )

    # ========================================================
    # 6. VOTOS SIN PROPUESTA
    # ========================================================

    cur.execute(
        """
        SELECT COUNT(*)

        FROM rule_votes rv

        LEFT JOIN rule_proposals rp
            ON rp.id = rv.proposal_id

        WHERE rp.id IS NULL
        """
    )

    if cur.fetchone()[0] != 0:

        errores.append(
            "Existen votos asociados "
            "a propuestas inexistentes."
        )

    # ========================================================
    # 7. MÉTRICAS
    # ========================================================

    cur.execute(
        """
        SELECT COUNT(*)
        FROM rule_proposals
        WHERE status = 'approved'
        """
    )

    aprobadas = (
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM rule_proposals
        WHERE status = 'rejected'
        """
    )

    rechazadas = (
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM rules
        WHERE effective_until IS NULL
        """
    )

    reglas_vigentes = (
        cur.fetchone()[0]
    )

    cur.close()
    conn.close()

    # ========================================================
    # RESULTADO
    # ========================================================

    print()
    print("VALIDACIÓN V7")
    print(
        "================================"
    )

    print(
        f"Versiones de reglas revisadas: "
        f"{reglas_revisadas}"
    )

    print(
        f"Reglas vigentes: "
        f"{reglas_vigentes}"
    )

    print(
        f"Propuestas revisadas: "
        f"{propuestas_revisadas}"
    )

    print(
        f"Propuestas aprobadas: "
        f"{aprobadas}"
    )

    print(
        f"Propuestas rechazadas: "
        f"{rechazadas}"
    )

    print(
        f"Votos revisados: "
        f"{votos_revisados}"
    )

    print()

    if errores:

        print(
            f"❌ Se encontraron "
            f"{len(errores)} errores:"
        )

        for error in errores:

            print(
                f" - {error}"
            )

    else:

        print(
            "✅ Todas las invariantes "
            "de v7 se cumplen."
        )

    print(
        "================================"
    )


if __name__ == "__main__":
    main()
