#!/usr/bin/env python3

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
# MAIN
# ============================================================

def main():

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    cur = conn.cursor()

    errores = []

    procesos_revisados = 0
    jurados_revisados = 0
    decisiones_revisadas = 0
    cautelares_revisadas = 0

    # ========================================================
    # 1. PROCESOS DISCIPLINARIOS
    # ========================================================

    cur.execute(
        """
        SELECT
            id,
            complainant_id,
            accused_id,
            opened_at,
            status

        FROM disciplinary_processes

        ORDER BY opened_at
        """
    )

    procesos = cur.fetchall()

    for (
        process_id,
        complainant_id,
        accused_id,
        opened_at,
        status
    ) in procesos:

        procesos_revisados += 1

        # ----------------------------------------------------
        # Denunciante y denunciado deben ser distintos
        # ----------------------------------------------------

        if complainant_id == accused_id:

            errores.append(
                f"Proceso {process_id}: "
                f"denunciante y denunciado "
                f"son la misma persona."
            )

        # ----------------------------------------------------
        # Descargo
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                submitted_at

            FROM defense_responses

            WHERE process_id = %s
            """,
            (process_id,)
        )

        descargo = cur.fetchone()

        if descargo is not None:

            submitted_at = descargo[0]

            if submitted_at < opened_at:

                errores.append(
                    f"Proceso {process_id}: "
                    f"descargo anterior "
                    f"a la denuncia."
                )

            # La propuesta concede 14 días.
            if submitted_at > (
                opened_at
                + psycopg2.extensions.adapt(
                    None
                ).getquoted()
                if False else opened_at
            ):
                pass

            dias_descargo = (
                submitted_at
                - opened_at
            ).total_seconds() / 86400

            if dias_descargo > 14:

                errores.append(
                    f"Proceso {process_id}: "
                    f"descargo presentado "
                    f"después de 14 días."
                )

        # ----------------------------------------------------
        # Jurados registrados
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                juror_id,
                sorted_at,
                recused,
                recusal_reason

            FROM juries

            WHERE process_id = %s

            ORDER BY sorted_at, juror_id
            """,
            (process_id,)
        )

        filas_jurado = cur.fetchall()

        jurados_revisados += len(
            filas_jurado
        )

        # ----------------------------------------------------
        # Un recusado debe tener motivo
        # ----------------------------------------------------

        for (
            juror_id,
            sorted_at,
            recused,
            recusal_reason
        ) in filas_jurado:

            if (
                recused is True
                and not recusal_reason
            ):

                errores.append(
                    f"Proceso {process_id}: "
                    f"jurado {juror_id} recusado "
                    f"sin motivo."
                )

        # ----------------------------------------------------
        # Agrupar jurados por momento de sorteo
        #
        # Puede existir:
        #
        # - primer jurado
        # - reemplazo por recusación
        # - segundo jurado de revisión
        # ----------------------------------------------------

        momentos = {}

        for (
            juror_id,
            sorted_at,
            recused,
            recusal_reason
        ) in filas_jurado:

            if sorted_at not in momentos:

                momentos[sorted_at] = []

            momentos[sorted_at].append(
                (
                    str(juror_id),
                    recused
                )
            )

        # ----------------------------------------------------
        # Decisiones
        # ----------------------------------------------------

        cur.execute(
            """
            SELECT
                jd.juror_id,
                jd.decision,
                jd.decided_at,
                j.recused

            FROM jury_decisions jd

            JOIN juries j
                ON j.process_id =
                   jd.process_id
               AND j.juror_id =
                   jd.juror_id

            WHERE jd.process_id = %s
            """,
            (process_id,)
        )

        decisiones = cur.fetchall()

        decisiones_revisadas += len(
            decisiones
        )

        # Un jurado recusado no debe decidir.
        for (
            juror_id,
            decision,
            decided_at,
            recused
        ) in decisiones:

            if recused is True:

                errores.append(
                    f"Proceso {process_id}: "
                    f"jurado recusado "
                    f"{juror_id} emitió decisión."
                )

        # ----------------------------------------------------
        # Si el proceso ya pasó por jurado,
        # debe haber al menos 7 jurados efectivos
        # en la primera deliberación.
        # ----------------------------------------------------

        estados_con_jurado = {
            "jury",
            "resolved_archived",
            "resolved_warning",
            "resolved_suspension",
            "pending_expulsion_review",
            "resolved_expulsion",
        }

        if str(status) in estados_con_jurado:

            efectivos_totales = {
                str(juror_id)
                for (
                    juror_id,
                    sorted_at,
                    recused,
                    reason
                ) in filas_jurado
                if recused is False
            }

            if len(efectivos_totales) < 7:

                errores.append(
                    f"Proceso {process_id}: "
                    f"tiene menos de 7 "
                    f"jurados efectivos."
                )

        # ----------------------------------------------------
        # Las decisiones deben pertenecer
        # a jurados registrados.
        # ----------------------------------------------------

        jurados_registrados = {
            str(fila[0])
            for fila in filas_jurado
        }

        for (
            juror_id,
            decision,
            decided_at,
            recused
        ) in decisiones:

            if (
                str(juror_id)
                not in jurados_registrados
            ):

                errores.append(
                    f"Proceso {process_id}: "
                    f"decisión de jurado "
                    f"no registrado."
                )

        # ----------------------------------------------------
        # Resolver conteo de la primera decisión
        # ----------------------------------------------------

        if decisiones:

            fechas_decision = sorted(
                {
                    fila[2]
                    for fila in decisiones
                }
            )

            primera_fecha = (
                fechas_decision[0]
            )

            primera_ronda = [
                fila
                for fila in decisiones
                if fila[2] == primera_fecha
            ]

            conteo = {
                "archive": 0,
                "warning": 0,
                "suspension": 0,
                "expulsion": 0,
            }

            for (
                juror_id,
                decision,
                decided_at,
                recused
            ) in primera_ronda:

                decision = str(
                    decision
                )

                if decision in conteo:

                    conteo[decision] += 1

            # --------------------------------------------
            # Suspensión necesita al menos 5/7
            # --------------------------------------------

            if (
                str(status)
                == "resolved_suspension"
                and conteo[
                    "suspension"
                ] < 5
            ):

                errores.append(
                    f"Proceso {process_id}: "
                    f"suspensión sin 5/7."
                )

            # --------------------------------------------
            # Una expulsión pendiente debe haber
            # recibido inicialmente 5/7.
            # --------------------------------------------

            if (
                str(status)
                == "pending_expulsion_review"
                and conteo[
                    "expulsion"
                ] < 5
            ):

                errores.append(
                    f"Proceso {process_id}: "
                    f"expulsión pendiente "
                    f"sin 5/7 inicial."
                )

        # ----------------------------------------------------
        # Expulsión resuelta
        # ----------------------------------------------------

        if (
            str(status)
            == "resolved_expulsion"
        ):

            cur.execute(
                """
                SELECT status
                FROM users
                WHERE id = %s
                """,
                (accused_id,)
            )

            usuario = cur.fetchone()

            if (
                usuario is None
                or str(usuario[0])
                != "expelled"
            ):

                errores.append(
                    f"Proceso {process_id}: "
                    f"expulsión resuelta pero "
                    f"usuario no está expelled."
                )

            # Deben existir al menos dos
            # grupos temporales de decisión:
            # primer jurado + revisión.
            cur.execute(
                """
                SELECT COUNT(
                    DISTINCT decided_at
                )

                FROM jury_decisions

                WHERE process_id = %s
                """,
                (process_id,)
            )

            rondas_decision = (
                cur.fetchone()[0]
            )

            if rondas_decision < 2:

                errores.append(
                    f"Proceso {process_id}: "
                    f"expulsión resuelta sin "
                    f"segundo jurado de revisión."
                )

        # ----------------------------------------------------
        # Jurado activo al momento actual
        # ----------------------------------------------------
        #
        # No consideramos error que un jurado
        # haya quedado inactive posteriormente.
        # Solo detectamos estados claramente
        # incompatibles al formar procesos nuevos
        # mediante la lógica del sorteo.
        # ----------------------------------------------------

    # ========================================================
    # 2. SUSPENSIONES CAUTELARES
    # ========================================================

    cur.execute(
        """
        SELECT
            user_id,
            requested_by,
            ratified_by,
            started_at,
            expires_at,
            lifted_at

        FROM cautelary_suspensions
        """
    )

    cautelares = cur.fetchall()

    for (
        user_id,
        requested_by,
        ratified_by,
        started_at,
        expires_at,
        lifted_at
    ) in cautelares:

        cautelares_revisadas += 1

        duracion = (
            expires_at
            - started_at
        )

        if duracion.total_seconds() <= 0:

            errores.append(
                f"Cautelar de {user_id}: "
                f"duración no positiva."
            )

        # 30 días reales = 720 horas.
        if duracion.total_seconds() > (
            720 * 60 * 60
        ):

            errores.append(
                f"Cautelar de {user_id}: "
                f"supera 30 días."
            )

        if (
            lifted_at is not None
            and lifted_at < started_at
        ):

            errores.append(
                f"Cautelar de {user_id}: "
                f"levantada antes de comenzar."
            )

        # ----------------------------------------------------
        # Ratificador permitido:
        #
        # - inviter
        # - inviter del inviter
        # - génesis
        # ----------------------------------------------------

        permitidos = set()

        cur.execute(
            """
            SELECT inviter_id
            FROM users
            WHERE id = %s
            """,
            (user_id,)
        )

        fila = cur.fetchone()

        if fila is not None:

            inviter_id = fila[0]

            if inviter_id is not None:

                permitidos.add(
                    str(inviter_id)
                )

                cur.execute(
                    """
                    SELECT inviter_id
                    FROM users
                    WHERE id = %s
                    """,
                    (inviter_id,)
                )

                abuela = cur.fetchone()

                if (
                    abuela is not None
                    and abuela[0]
                    is not None
                ):

                    permitidos.add(
                        str(abuela[0])
                    )

        cur.execute(
            """
            SELECT id
            FROM users
            WHERE inviter_id IS NULL
            """
        )

        for fundador in cur.fetchall():

            permitidos.add(
                str(fundador[0])
            )

        if (
            str(ratified_by)
            not in permitidos
        ):

            errores.append(
                f"Cautelar de {user_id}: "
                f"ratificador no válido."
            )

    # ========================================================
    # 3. CONSISTENCIA DE ESTADOS
    # ========================================================

    # --------------------------------------------------------
    # suspended_cautelar debe tener una
    # cautelar activa.
    # --------------------------------------------------------

    cur.execute(
        """
        SELECT
            u.id,
            u.display_name

        FROM users u

        WHERE u.status =
              'suspended_cautelar'

          AND NOT EXISTS
          (
              SELECT 1

              FROM cautelary_suspensions c

              WHERE c.user_id = u.id
                AND c.lifted_at IS NULL
          )
        """
    )

    for user_id, nombre in cur.fetchall():

        errores.append(
            f"{nombre}: aparece "
            f"suspended_cautelar sin "
            f"cautelar activa."
        )

    # --------------------------------------------------------
    # expelled debe provenir de proceso resuelto
    # --------------------------------------------------------

    cur.execute(
        """
        SELECT
            u.id,
            u.display_name

        FROM users u

        WHERE u.status = 'expelled'

          AND NOT EXISTS
          (
              SELECT 1

              FROM disciplinary_processes p

              WHERE p.accused_id = u.id

                AND p.status =
                    'resolved_expulsion'
          )
        """
    )

    for user_id, nombre in cur.fetchall():

        errores.append(
            f"{nombre}: status=expelled "
            f"sin proceso de expulsión "
            f"resuelto."
        )

    # ========================================================
    # 4. MÉTRICAS
    # ========================================================

    cur.execute(
        """
        SELECT COUNT(*)
        FROM defense_responses
        """
    )

    descargos = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE status =
              'suspended_sanction'
        """
    )

    suspendidos_sancion = (
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE status = 'expelled'
        """
    )

    expulsados = cur.fetchone()[0]

    cur.close()
    conn.close()

    # ========================================================
    # RESULTADO
    # ========================================================

    print()
    print("VALIDACIÓN V5")
    print("================================")

    print(
        f"Procesos revisados: "
        f"{procesos_revisados}"
    )

    print(
        f"Descargos: {descargos}"
    )

    print(
        f"Filas de jurado: "
        f"{jurados_revisados}"
    )

    print(
        f"Decisiones revisadas: "
        f"{decisiones_revisadas}"
    )

    print(
        f"Cautelares revisadas: "
        f"{cautelares_revisadas}"
    )

    print(
        f"Suspendidos por sanción: "
        f"{suspendidos_sancion}"
    )

    print(
        f"Expulsados: "
        f"{expulsados}"
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
            "de v5 se cumplen."
        )

    print("================================")


if __name__ == "__main__":
    main()
