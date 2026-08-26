#!/usr/bin/env python3

import base64
import json
import os
from datetime import timezone
from pathlib import Path

import psycopg2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)
from dotenv import load_dotenv


load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "gob"),
    "user": os.getenv("DB_USER", "benjamin"),
    "password": os.getenv("DB_PASSWORD", "4321"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}


BASE_DIR = Path(
    __file__
).resolve().parents[1]

PUBLIC_KEYS_FILE = (
    BASE_DIR
    / "config"
    / "technical_public_keys.json"
)


# ============================================================
# MENSAJE CANÓNICO
# ============================================================

def mensaje_accion(
    action_type,
    executed_by,
    target_ref,
    executed_at
):

    fecha_utc = (
        executed_at
        .astimezone(timezone.utc)
        .isoformat(
            timespec="microseconds"
        )
    )

    return (
        f"{action_type}|"
        f"{executed_by}|"
        f"{target_ref}|"
        f"{fecha_utc}"
    ).encode(
        "utf-8"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not PUBLIC_KEYS_FILE.exists():

        raise RuntimeError(
            "No existe el registro "
            "de claves públicas."
        )

    claves = json.loads(
        PUBLIC_KEYS_FILE.read_text(
            encoding="utf-8"
        )
    )

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id,
            action_type,
            executed_by,
            target_ref,
            executed_at,
            signature

        FROM technical_action_log

        ORDER BY executed_at
        """
    )

    acciones = cur.fetchall()

    correctas = 0
    errores = []

    for (
        action_id,
        action_type,
        executed_by,
        target_ref,
        executed_at,
        signature
    ) in acciones:

        executed_by_str = str(
            executed_by
        )

        # ====================================================
        # CLAVE PÚBLICA CONOCIDA
        # ====================================================

        informacion = claves.get(
            executed_by_str
        )

        if informacion is None:

            errores.append(
                f"{action_id}: "
                f"no existe clave pública "
                f"del ejecutor."
            )

            continue

        public_bytes = (
            base64.b64decode(
                informacion[
                    "public_key"
                ]
            )
        )

        public_key = (
            Ed25519PublicKey.from_public_bytes(
                public_bytes
            )
        )

        # ====================================================
        # VERIFICAR FIRMA
        # ====================================================

        mensaje = mensaje_accion(
            action_type,
            executed_by_str,
            target_ref,
            executed_at
        )

        try:

            public_key.verify(
                base64.b64decode(
                    signature
                ),
                mensaje
            )

        except InvalidSignature:

            errores.append(
                f"{action_id}: "
                f"firma criptográfica inválida."
            )

            continue

        # ====================================================
        # VERIFICAR QUE TENÍA MANDATO
        # ====================================================

        cur.execute(
            """
            SELECT COUNT(*)

            FROM technical_roles

            WHERE user_id = %s

              AND granted_at <= %s

              AND granted_until > %s

              AND (
                    revoked_at IS NULL
                    OR revoked_at > %s
                  )
            """,
            (
                executed_by,
                executed_at,
                executed_at,
                executed_at
            )
        )

        if cur.fetchone()[0] == 0:

            errores.append(
                f"{action_id}: "
                f"acción firmada por usuario "
                f"sin mandato vigente."
            )

            continue

        correctas += 1

    cur.close()
    conn.close()

    print()
    print("VERIFICACIÓN LOG V6")
    print(
        "================================"
    )

    print(
        f"Acciones revisadas: "
        f"{len(acciones)}"
    )

    print(
        f"Firmas válidas: "
        f"{correctas}"
    )

    print()

    if errores:

        print(
            f"❌ Errores: "
            f"{len(errores)}"
        )

        for error in errores:

            print(
                f"- {error}"
            )

    else:

        print(
            "✅ Todas las acciones "
            "tienen firma válida y "
            "mandato técnico vigente."
        )

    print(
        "================================"
    )


if __name__ == "__main__":
    main()
