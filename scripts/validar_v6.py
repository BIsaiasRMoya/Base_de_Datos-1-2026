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


BASE_DIR = Path(__file__).resolve().parents[1]

PUBLIC_KEYS_FILE = (
    BASE_DIR
    / "config"
    / "technical_public_keys.json"
)


# ============================================================
# MENSAJE CANÓNICO DE FIRMA
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

    texto = (
        f"{action_type}|"
        f"{executed_by}|"
        f"{target_ref}|"
        f"{fecha_utc}"
    )

    return texto.encode(
        "utf-8"
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

    mandatos_revisados = 0
    shards_revisados = 0
    acciones_revisadas = 0
    firmas_validas = 0

    # ========================================================
    # 1. VALIDAR MANDATOS TÉCNICOS
    # ========================================================

    cur.execute(
        """
        SELECT
            user_id,
            granted_at,
            granted_until,
            revoked_at,
            revoked_by

        FROM technical_roles

        ORDER BY granted_at
        """
    )

    mandatos = cur.fetchall()

    for (
        user_id,
        granted_at,
        granted_until,
        revoked_at,
        revoked_by
    ) in mandatos:

        mandatos_revisados += 1

        # El mandato debe terminar después de comenzar.
        if granted_until <= granted_at:

            errores.append(
                f"Mandato de {user_id}: "
                f"granted_until no es posterior "
                f"a granted_at."
            )

        # Si existe revocación,
        # debe existir persona que revocó.
        if (
            revoked_at is not None
            and revoked_by is None
        ):

            errores.append(
                f"Mandato de {user_id}: "
                f"revocado sin revoked_by."
            )

        if (
            revoked_at is None
            and revoked_by is not None
        ):

            errores.append(
                f"Mandato de {user_id}: "
                f"tiene revoked_by pero "
                f"no revoked_at."
            )

        if (
            revoked_at is not None
            and revoked_at < granted_at
        ):

            errores.append(
                f"Mandato de {user_id}: "
                f"revocado antes de comenzar."
            )

    # ========================================================
    # 2. VALIDAR SHARDS
    # ========================================================

    cur.execute(
        """
        SELECT
            shard_id,
            custodian_id,
            threshold_k,
            total_n,
            created_at

        FROM key_shards

        ORDER BY created_at, shard_id
        """
    )

    shards = cur.fetchall()

    shards_revisados = len(
        shards
    )

    for (
        shard_id,
        custodian_id,
        threshold_k,
        total_n,
        created_at
    ) in shards:

        if threshold_k < 2:

            errores.append(
                f"Shard {shard_id}: "
                f"threshold menor que 2."
            )

        if total_n < threshold_k:

            errores.append(
                f"Shard {shard_id}: "
                f"total_n menor que threshold."
            )

    # ========================================================
    # 3. VALIDAR DISTRIBUCIÓN DE CUSTODIOS
    # ========================================================

    cur.execute(
        """
        SELECT
            created_at,
            threshold_k,
            total_n,
            COUNT(*) AS cantidad,
            COUNT(
                DISTINCT custodian_id
            ) AS custodios

        FROM key_shards

        GROUP BY
            created_at,
            threshold_k,
            total_n
        """
    )

    grupos_shards = cur.fetchall()

    for (
        created_at,
        threshold_k,
        total_n,
        cantidad,
        custodios
    ) in grupos_shards:

        if cantidad != total_n:

            errores.append(
                f"Grupo Shamir {created_at}: "
                f"esperaba {total_n} shards "
                f"pero existen {cantidad}."
            )

        if custodios != total_n:

            errores.append(
                f"Grupo Shamir {created_at}: "
                f"los {total_n} fragmentos "
                f"no están en custodios distintos."
            )

    # ========================================================
    # 4. COMPROBAR QUE POSTGRESQL NO GUARDE EL SECRETO
    # ========================================================

    cur.execute(
        """
        SELECT column_name

        FROM information_schema.columns

        WHERE table_name = 'key_shards'
        """
    )

    columnas_shards = {
        fila[0].lower()
        for fila in cur.fetchall()
    }

    columnas_prohibidas = {
        "secret",
        "secret_fragment",
        "fragment",
        "fragment_value",
        "share",
        "share_value",
        "private_key",
    }

    encontradas = (
        columnas_shards
        & columnas_prohibidas
    )

    if encontradas:

        errores.append(
            "key_shards contiene columnas "
            f"que podrían almacenar secretos: "
            f"{sorted(encontradas)}"
        )

    # ========================================================
    # 5. CARGAR CLAVES PÚBLICAS
    # ========================================================

    if not PUBLIC_KEYS_FILE.exists():

        errores.append(
            "No existe "
            "config/technical_public_keys.json"
        )

        claves = {}

    else:

        try:

            claves = json.loads(
                PUBLIC_KEYS_FILE.read_text(
                    encoding="utf-8"
                )
            )

        except Exception as error:

            errores.append(
                "No se pudo leer el archivo "
                f"de claves públicas: {error}"
            )

            claves = {}

    # ========================================================
    # 6. VALIDAR LOG TÉCNICO
    # ========================================================

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

    for (
        action_id,
        action_type,
        executed_by,
        target_ref,
        executed_at,
        signature
    ) in acciones:

        acciones_revisadas += 1

        executed_by_str = str(
            executed_by
        )

        # ----------------------------------------------------
        # Debe existir clave pública
        # ----------------------------------------------------

        datos_clave = claves.get(
            executed_by_str
        )

        if datos_clave is None:

            errores.append(
                f"Acción {action_id}: "
                f"ejecutor sin clave pública."
            )

            continue

        if (
            datos_clave.get(
                "algorithm"
            )
            != "Ed25519"
        ):

            errores.append(
                f"Acción {action_id}: "
                f"algoritmo de firma "
                f"no reconocido."
            )

            continue

        # ----------------------------------------------------
        # Reconstruir clave pública
        # ----------------------------------------------------

        try:

            public_bytes = (
                base64.b64decode(
                    datos_clave[
                        "public_key"
                    ]
                )
            )

            public_key = (
                Ed25519PublicKey
                .from_public_bytes(
                    public_bytes
                )
            )

        except Exception:

            errores.append(
                f"Acción {action_id}: "
                f"clave pública inválida."
            )

            continue

        # ----------------------------------------------------
        # Verificar firma
        # ----------------------------------------------------

        mensaje = mensaje_accion(
            action_type,
            executed_by_str,
            target_ref,
            executed_at
        )

        try:

            firma_bytes = (
                base64.b64decode(
                    signature
                )
            )

            public_key.verify(
                firma_bytes,
                mensaje
            )

            firmas_validas += 1

        except (
            InvalidSignature,
            ValueError,
            TypeError
        ):

            errores.append(
                f"Acción {action_id}: "
                f"firma inválida."
            )

            continue

        # ----------------------------------------------------
        # Debía tener mandato válido
        # AL MOMENTO de ejecutar la acción.
        # ----------------------------------------------------

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

        tiene_mandato = (
            cur.fetchone()[0]
        )

        if tiene_mandato == 0:

            errores.append(
                f"Acción {action_id}: "
                f"ejecutada sin mandato "
                f"técnico vigente."
            )

    # ========================================================
    # 7. EVITAR SOLAPAMIENTO DE MANDATOS
    # DEL MISMO USUARIO
    # ========================================================

    cur.execute(
        """
        SELECT
            a.user_id,
            a.granted_at,
            b.granted_at

        FROM technical_roles a

        JOIN technical_roles b
            ON b.user_id = a.user_id

           AND b.granted_at > a.granted_at

           AND b.granted_at
               <
               COALESCE(
                   a.revoked_at,
                   a.granted_until
               )
        """
    )

    for (
        user_id,
        mandato_1,
        mandato_2
    ) in cur.fetchall():

        errores.append(
            f"Usuario {user_id}: "
            f"mandatos técnicos solapados."
        )

    # ========================================================
    # MÉTRICAS
    # ========================================================

    cur.execute(
        """
        SELECT COUNT(*)

        FROM technical_roles

        WHERE revoked_at IS NOT NULL
        """
    )

    revocados = (
        cur.fetchone()[0]
    )

    cur.close()
    conn.close()

    # ========================================================
    # RESULTADO
    # ========================================================

    print()
    print("VALIDACIÓN V6")
    print(
        "================================"
    )

    print(
        f"Mandatos revisados: "
        f"{mandatos_revisados}"
    )

    print(
        f"Mandatos revocados: "
        f"{revocados}"
    )

    print(
        f"Shards revisados: "
        f"{shards_revisados}"
    )

    print(
        f"Acciones revisadas: "
        f"{acciones_revisadas}"
    )

    print(
        f"Firmas válidas: "
        f"{firmas_validas}"
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
            "de v6 se cumplen."
        )

    print(
        "================================"
    )


if __name__ == "__main__":
    main()
