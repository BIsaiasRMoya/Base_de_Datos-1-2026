#!/usr/bin/env python3

import argparse
import os
from datetime import datetime, timezone

import psycopg2
from dotenv import load_dotenv


load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "gob"),
    "user": os.getenv("DB_USER", "benjamin"),
    "password": os.getenv("DB_PASSWORD", "4321"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}


def main():

    parser = argparse.ArgumentParser(
        description=
        "Validación de invariantes v4"
    )

    parser.add_argument(
        "--meses",
        type=int,
        default=4
    )

    parser.add_argument(
        "--fecha-referencia",
        type=str,
        default=None
    )

    args = parser.parse_args()

    if args.fecha_referencia:

        referencia = datetime.strptime(
            args.fecha_referencia,
            "%Y-%m-%d"
        ).replace(
            tzinfo=timezone.utc
        )

    else:

        referencia = datetime.now(
            timezone.utc
        )

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    cur = conn.cursor()

    errores = []

    # ========================================================
    # 1. last_active_at nunca puede ser NULL
    # ========================================================

    cur.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE last_active_at IS NULL
        """
    )

    if cur.fetchone()[0] != 0:

        errores.append(
            "Existen usuarios con "
            "last_active_at NULL."
        )

    # ========================================================
    # 2. Inactivos realmente superan el umbral
    # ========================================================

    cur.execute(
        """
        SELECT
            id,
            display_name,
            last_active_at

        FROM users

        WHERE status = 'inactive'

          AND last_active_at >=
              %s - (%s * INTERVAL '1 month')
        """,
        (
            referencia,
            args.meses
        )
    )

    for (
        user_id,
        nombre,
        last_active
    ) in cur.fetchall():

        errores.append(
            f"{nombre}: está inactive "
            f"pero su actividad es reciente."
        )

    # ========================================================
    # 3. Inactivos no pueden proponer invitaciones v4
    # ========================================================

    cur.execute(
        """
        SELECT
            i.id,
            u.display_name

        FROM invitations i

        JOIN users u
            ON u.id = i.proposer_id

        WHERE i.candidate_email
              LIKE 'candidato_v4_%'

          AND u.status = 'inactive'
        """
    )

    for invitation_id, nombre in cur.fetchall():

        errores.append(
            f"Invitación {invitation_id}: "
            f"proponente {nombre} está inactive."
        )

    # ========================================================
    # 4. Votos v4 dentro del plazo
    # ========================================================

    cur.execute(
        """
        SELECT
            v.invitation_id,
            v.voter_id

        FROM votes v

        JOIN invitations i
            ON i.id = v.invitation_id

        WHERE i.candidate_email
              LIKE 'candidato_v4_%'

          AND (
                v.cast_at < i.opened_at
                OR v.cast_at > i.closes_at
              )
        """
    )

    for invitation_id, voter_id in cur.fetchall():

        errores.append(
            f"Invitación {invitation_id}: "
            f"voto fuera del período."
        )

    # ========================================================
    # 5. Reemplazos de hermanos conservan historial
    # ========================================================

    cur.execute(
        """
        SELECT
            user_id,
            sibling_id,
            replaced_by,
            replaced_at

        FROM sibling_assignments

        WHERE replaced_by IS NOT NULL
           OR replaced_at IS NOT NULL
        """
    )

    for (
        user_id,
        sibling_id,
        replaced_by,
        replaced_at
    ) in cur.fetchall():

        if (
            replaced_by is None
            or replaced_at is None
        ):

            errores.append(
                f"Asignación {user_id}/{sibling_id}: "
                f"reemplazo histórico incompleto."
            )

    # ========================================================
    # 6. Ningún reemplazo activo puede ser el mismo usuario
    # ========================================================

    cur.execute(
        """
        SELECT
            user_id,
            sibling_id

        FROM sibling_assignments

        WHERE replaced_at IS NULL
          AND user_id = sibling_id
        """
    )

    for user_id, sibling_id in cur.fetchall():

        errores.append(
            f"{user_id}: asignado como "
            f"su propio hermano."
        )

    # ========================================================
    # RESULTADO
    # ========================================================

    cur.execute(
        """
        SELECT COUNT(*)
        FROM invitations
        WHERE candidate_email
              LIKE 'candidato_v4_%'
        """
    )

    invitaciones_v4 = (
        cur.fetchone()[0]
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE status = 'inactive'
        """
    )

    inactivos = (
        cur.fetchone()[0]
    )

    cur.close()
    conn.close()

    print()
    print("VALIDACIÓN V4")
    print("================================")

    print(
        f"Invitaciones v4: "
        f"{invitaciones_v4}"
    )

    print(
        f"Miembros inactive: "
        f"{inactivos}"
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
            "de v4 se cumplen."
        )

    print("================================")


if __name__ == "__main__":
    main()
