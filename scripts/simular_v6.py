#!/usr/bin/env python3

import argparse
import base64
import calendar
import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from dotenv import load_dotenv

from funciones_v6 import (
    dividir_secreto,
    reconstruir_secreto,
    serializar_fragmento,
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


BASE_DIR = Path(__file__).resolve().parents[1]

SECRET_DIR = (
    BASE_DIR
    / ".secrets"
    / "v6"
)

SHARD_DIR = (
    SECRET_DIR
    / "shards"
)

PUBLIC_KEYS_FILE = (
    BASE_DIR
    / "config"
    / "technical_public_keys.json"
)


# ============================================================
# SUMAR MESES
# ============================================================

def sumar_meses(
    fecha,
    meses
):
    """
    Suma meses calendario reales.

    Se utiliza para representar
    exactamente el mandato sugerido
    de seis meses.
    """

    total = (
        fecha.month - 1
        + meses
    )

    year = (
        fecha.year
        + total // 12
    )

    month = (
        total % 12
        + 1
    )

    ultimo_dia = calendar.monthrange(
        year,
        month
    )[1]

    day = min(
        fecha.day,
        ultimo_dia
    )

    return fecha.replace(
        year=year,
        month=month,
        day=day
    )


# ============================================================
# FECHA BASE
# ============================================================

def obtener_fecha_base(cur):

    cur.execute(
        """
        SELECT GREATEST(

            COALESCE(
                (
                    SELECT MAX(last_active_at)
                    FROM users
                ),
                now()
            ),

            COALESCE(
                (
                    SELECT MAX(closes_at)
                    FROM invitations
                ),
                now()
            ),

            COALESCE(
                (
                    SELECT MAX(decided_at)
                    FROM jury_decisions
                ),
                now()
            ),

            COALESCE(
                (
                    SELECT MAX(expires_at)
                    FROM cautelary_suspensions
                ),
                now()
            ),

            now()
        )
        """
    )

    return (
        cur.fetchone()[0]
        + timedelta(days=1)
    )


# ============================================================
# USUARIOS ACTIVOS
# ============================================================

def cargar_activos(cur):

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
            nombre
        )
        for user_id, nombre
        in cur.fetchall()
    ]


# ============================================================
# HASH DETERMINISTA
# ============================================================

def hash_determinista(
    semilla,
    user_id,
    contexto
):

    texto = (
        f"{semilla}|"
        f"{user_id}|"
        f"{contexto}"
    )

    return int(
        hashlib.sha256(
            texto.encode("utf-8")
        ).hexdigest(),
        16
    )


# ============================================================
# ELECCIÓN
# ============================================================

def elegir_tecnico(
    usuarios,
    semilla
):
    """
    Selección reproducible del candidato
    para la simulación electoral.

    IMPORTANTE:
    el documento no fija el cuórum exacto
    de ELECCIÓN del rol técnico.

    Para la simulación utilizamos
    mayoría simple como decisión
    de implementación.
    """

    if not usuarios:

        return None

    ordenados = sorted(
        usuarios,
        key=lambda fila:
            hash_determinista(
                semilla,
                fila[0],
                "eleccion-tecnica"
            )
    )

    return ordenados[0]


# ============================================================
# CLAVES ED25519
# ============================================================

def crear_clave_firma(
    user_id
):

    SECRET_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    PUBLIC_KEYS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    private_path = (
        SECRET_DIR
        / f"technical_{user_id}.pem"
    )

    # --------------------------------------------------------
    # Clave privada
    # --------------------------------------------------------

    if private_path.exists():

        private_key = (
            serialization.load_pem_private_key(
                private_path.read_bytes(),
                password=None
            )
        )

    else:

        private_key = (
            Ed25519PrivateKey.generate()
        )

        private_bytes = (
            private_key.private_bytes(
                encoding=
                    serialization.Encoding.PEM,

                format=
                    serialization.PrivateFormat.PKCS8,

                encryption_algorithm=
                    serialization.NoEncryption()
            )
        )

        private_path.write_bytes(
            private_bytes
        )

        os.chmod(
            private_path,
            0o600
        )

    # --------------------------------------------------------
    # Clave pública
    # --------------------------------------------------------

    public_key = (
        private_key.public_key()
    )

    public_bytes = (
        public_key.public_bytes(
            encoding=
                serialization.Encoding.Raw,

            format=
                serialization.PublicFormat.Raw
        )
    )

    public_b64 = (
        base64.b64encode(
            public_bytes
        ).decode("ascii")
    )

    # --------------------------------------------------------
    # Registro público
    # --------------------------------------------------------

    if PUBLIC_KEYS_FILE.exists():

        claves = json.loads(
            PUBLIC_KEYS_FILE.read_text(
                encoding="utf-8"
            )
        )

    else:

        claves = {}

    claves[user_id] = {
        "algorithm": "Ed25519",
        "public_key": public_b64,
    }

    PUBLIC_KEYS_FILE.write_text(
        json.dumps(
            claves,
            indent=4,
            ensure_ascii=False,
            sort_keys=True
        )
        + "\n",
        encoding="utf-8"
    )

    return private_key


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
# REGISTRAR ACCIÓN FIRMADA
# ============================================================

def registrar_accion(
    cur,
    private_key,
    action_type,
    executed_by,
    target_ref,
    executed_at
):

    mensaje = mensaje_accion(
        action_type,
        executed_by,
        target_ref,
        executed_at
    )

    firma = private_key.sign(
        mensaje
    )

    firma_b64 = (
        base64.b64encode(
            firma
        ).decode("ascii")
    )

    action_id = str(
        uuid.uuid4()
    )

    cur.execute(
        """
        INSERT INTO technical_action_log
        (
            id,
            action_type,
            executed_by,
            target_ref,
            executed_at,
            signature
        )
        VALUES
        (%s, %s, %s, %s, %s, %s)
        """,
        (
            action_id,
            action_type,
            executed_by,
            target_ref,
            executed_at,
            firma_b64
        )
    )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=
        "Simulación funcional de v6"
    )

    parser.add_argument(
        "--semilla",
        type=int,
        default=42
    )

    parser.add_argument(
        "--threshold",
        type=int,
        default=3
    )

    parser.add_argument(
        "--fragmentos",
        type=int,
        default=5
    )

    args = parser.parse_args()

    if args.threshold < 2:

        raise ValueError(
            "El threshold debe ser "
            "al menos 2."
        )

    if (
        args.fragmentos
        < args.threshold
    ):

        raise ValueError(
            "fragmentos debe ser "
            ">= threshold."
        )

    conn = psycopg2.connect(
        **DB_CONFIG
    )

    conn.autocommit = False

    cur = conn.cursor()

    try:

        # ====================================================
        # EVITAR DUPLICACIÓN
        # ====================================================

        cur.execute(
            """
            SELECT COUNT(*)
            FROM technical_roles
            """
        )

        if cur.fetchone()[0] > 0:

            raise RuntimeError(
                "Ya existen mandatos técnicos. "
                "No vuelvas a ejecutar "
                "simular_v6.py sobre esta base."
            )

        cur.execute(
            """
            SELECT COUNT(*)
            FROM key_shards
            """
        )

        if cur.fetchone()[0] > 0:

            raise RuntimeError(
                "Ya existen fragmentos v6."
            )

        # ====================================================
        # RED ACTIVA
        # ====================================================

        activos = cargar_activos(
            cur
        )

        if len(activos) < (
            args.fragmentos
        ):

            raise RuntimeError(
                "No existen suficientes "
                "usuarios activos para "
                "distribuir los fragmentos."
            )

        # ====================================================
        # ELECCIÓN
        # ====================================================

        (
            technical_user_id,
            technical_name
        ) = elegir_tecnico(
            activos,
            args.semilla
        )

        total_activos = len(
            activos
        )

        # Decisión de implementación:
        # mayoría simple para otorgamiento.
        votos_necesarios = (
            total_activos // 2
            + 1
        )

        votos_si = votos_necesarios

        if votos_si < votos_necesarios:

            raise RuntimeError(
                "La elección técnica "
                "no fue aprobada."
            )

        # ====================================================
        # MANDATO DE 6 MESES
        # ====================================================

        granted_at = obtener_fecha_base(
            cur
        )

        granted_until = sumar_meses(
            granted_at,
            6
        )

        cur.execute(
            """
            INSERT INTO technical_roles
            (
                user_id,
                granted_at,
                granted_until,
                revoked_at,
                revoked_by
            )
            VALUES
            (%s, %s, %s, NULL, NULL)
            """,
            (
                technical_user_id,
                granted_at,
                granted_until
            )
        )

        # ====================================================
        # CUSTODIOS
        # ====================================================
        #
        # Preferimos evitar que el técnico
        # sea también custodio cuando la
        # cantidad de activos lo permite.
        #
        # Es una salvaguarda adicional
        # de implementación.
        # ====================================================

        candidatos_custodia = [
            fila
            for fila in activos
            if fila[0]
            != technical_user_id
        ]

        if len(
            candidatos_custodia
        ) < args.fragmentos:

            candidatos_custodia = list(
                activos
            )

        candidatos_custodia = sorted(
            candidatos_custodia,
            key=lambda fila:
                hash_determinista(
                    args.semilla,
                    fila[0],
                    "custodia-v6"
                )
        )

        custodios = (
            candidatos_custodia[
                :args.fragmentos
            ]
        )

        # ====================================================
        # SHAMIR
        # ====================================================

        secreto = secrets.token_bytes(
            32
        )

        fragmentos = dividir_secreto(
            secreto,
            threshold_k=
                args.threshold,
            total_n=
                args.fragmentos
        )

        # Comprobar en memoria que realmente
        # tres fragmentos reconstruyen.
        reconstruido = (
            reconstruir_secreto(
                fragmentos[
                    :args.threshold
                ],
                len(secreto)
            )
        )

        if reconstruido != secreto:

            raise RuntimeError(
                "Falló la reconstrucción "
                "de Shamir."
            )

        # El secreto original NO se guarda.
        del secreto
        del reconstruido

        SHARD_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        created_at = (
            granted_at
            + timedelta(hours=1)
        )

        asignaciones = []

        for (
            fragmento,
            custodio
        ) in zip(
            fragmentos,
            custodios
        ):

            (
                custodian_id,
                custodian_name
            ) = custodio

            shard_id = str(
                uuid.uuid4()
            )

            # --------------------------------------------
            # Guardar SOLO el fragmento en archivo local
            # ignorado por Git.
            # --------------------------------------------

            shard_path = (
                SHARD_DIR
                / f"{shard_id}.share"
            )

            shard_path.write_text(
                serializar_fragmento(
                    fragmento
                )
                + "\n",
                encoding="utf-8"
            )

            os.chmod(
                shard_path,
                0o600
            )

            # --------------------------------------------
            # PostgreSQL guarda solo metadatos
            # --------------------------------------------

            cur.execute(
                """
                INSERT INTO key_shards
                (
                    shard_id,
                    custodian_id,
                    threshold_k,
                    total_n,
                    created_at
                )
                VALUES
                (%s, %s, %s, %s, %s)
                """,
                (
                    shard_id,
                    custodian_id,
                    args.threshold,
                    args.fragmentos,
                    created_at
                )
            )

            asignaciones.append(
                (
                    shard_id,
                    custodian_name
                )
            )

        # ====================================================
        # CLAVE DE FIRMA DEL TÉCNICO
        # ====================================================

        private_key = crear_clave_firma(
            technical_user_id
        )

        # ====================================================
        # ACCIONES TÉCNICAS
        # ====================================================

        acciones = [
            (
                "database_backup",
                "database:gobernanza"
            ),
            (
                "security_patch",
                "server:application"
            ),
            (
                "configuration_update",
                "service:governance"
            ),
        ]

        for indice, (
            action_type,
            target_ref
        ) in enumerate(
            acciones,
            start=1
        ):

            executed_at = (
                granted_at
                + timedelta(
                    days=indice
                )
            )

            registrar_accion(
                cur=cur,
                private_key=
                    private_key,
                action_type=
                    action_type,
                executed_by=
                    technical_user_id,
                target_ref=
                    target_ref,
                executed_at=
                    executed_at
            )

        conn.commit()

        # ====================================================
        # RESULTADO
        # ====================================================

        print()
        print("CAPA TÉCNICA V6")
        print(
            "================================"
        )

        print(
            f"Miembros activos: "
            f"{total_activos}"
        )

        print(
            f"Votos elección: "
            f"{votos_si}/"
            f"{total_activos}"
        )

        print()
        print(
            f"Técnico electo: "
            f"{technical_name}"
        )

        print(
            f"Mandato desde: "
            f"{granted_at.date()}"
        )

        print(
            f"Mandato hasta: "
            f"{granted_until.date()}"
        )

        print()
        print(
            f"Custodia Shamir: "
            f"{args.threshold} "
            f"de {args.fragmentos}"
        )

        print()

        for (
            shard_id,
            nombre
        ) in asignaciones:

            print(
                f"- {nombre}: "
                f"{shard_id[:8]}..."
            )

        print()
        print(
            f"Acciones firmadas: "
            f"{len(acciones)}"
        )

        print()
        print(
            "✅ Simulación v6 completada."
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
