#!/usr/bin/env python3
"""
Simula actividad de invitaciones y votos en la red v1 + v2 + v3.
Los votos se ven influidos por el perfil socioeconómico y antecedentes
del candidato (simulado y persistido en la BD) y del votante (de la BD).
Uso: python simular_actividad.py --num-invitaciones 50 --prob-si 0.6
"""

import argparse
import random
import uuid
from datetime import datetime, timedelta

import psycopg2
from faker import Faker

# Configuración de conexión (ajústala)
DB_CONFIG = {
    "dbname": "gobernanza",
    "user": "postgres",
    "password": "1234",
    "host": "localhost",
    "port": 5432,
}

fake = Faker("es_ES")

# Enumeraciones de v2
SOCIOECONOMIC_LEVELS = ['bajo', 'medio_bajo', 'medio', 'medio_alto', 'alto']
BACKGROUND_TYPES = ['laboral', 'educativo', 'judicial', 'referencia_personal', 'otro']

# Cache de perfiles de votantes
_voter_profile_cache = {}


def obtener_vecindario_local(cur, user_id):
    """
    Calcula el vecindario local de un usuario según v1:
    - Ascendentes hasta 2 niveles (madrina y abuela)
    - Hijos (invitados por él)
    - Hermanos vecinales sorteados (de sibling_assignments)
    Retorna un conjunto de IDs.
    """
    vecinos = set()

    # 1. Ascendentes
    actual = user_id
    for _ in range(2):
        cur.execute("SELECT inviter_id FROM users WHERE id = %s", (actual,))
        row = cur.fetchone()
        if row is None or row[0] is None:
            break
        vecinos.add(row[0])
        actual = row[0]

    # 2. Hijos
    cur.execute("SELECT id FROM users WHERE inviter_id = %s", (user_id,))
    for row in cur.fetchall():
        vecinos.add(row[0])

    # 3. Hermanos vecinales activos
    cur.execute(
        """
        SELECT sibling_id
        FROM sibling_assignments
        WHERE user_id = %s AND replaced_at IS NULL
        """,
        (user_id,),
    )
    for row in cur.fetchall():
        vecinos.add(row[0])

    vecinos.discard(user_id)
    return vecinos


def calcular_cuorum(tamano):
    """Cuórum = ceil(tamano/2)"""
    return (tamano + 1) // 2


def obtener_perfil_votante(cur, voter_id):
    """Retorna el nivel socioeconómico del votante, o None si no existe."""
    if voter_id in _voter_profile_cache:
        return _voter_profile_cache[voter_id]

    cur.execute(
        "SELECT socioeconomic_level FROM user_socioeconomic_profile WHERE user_id = %s",
        (voter_id,)
    )
    row = cur.fetchone()
    level = row[0] if row else None
    _voter_profile_cache[voter_id] = level
    return level


def generar_perfil_candidato():
    """
    Genera un perfil sintético para un candidato (no registrado aún).
    Retorna dict con 'level' y 'backgrounds' (lista de strings).
    """
    level = random.choice(SOCIOECONOMIC_LEVELS)
    backgrounds = []
    
    # ~30% de probabilidad de tener antecedentes judiciales
    if random.random() < 0.3:
        backgrounds.append('judicial')
    
    # Añade 0 o 1 antecedente adicional (no judicial)
    others = [t for t in BACKGROUND_TYPES if t != 'judicial']
    if random.random() < 0.5:
        backgrounds.append(random.choice(others))
    
    random.shuffle(backgrounds)
    return {
        'level': level,
        'backgrounds': backgrounds,
        'has_judicial': 'judicial' in backgrounds,
        'is_high': level in ['medio_alto', 'alto'],
        'is_low': level == 'bajo'
    }


def calcular_probabilidades_voto(base_si, base_no, base_abst, candidato, votante_level):
    """
    Ajusta las probabilidades base según el perfil del candidato y del votante.
    Retorna (p_si, p_no, p_abst) normalizadas a 1.
    """
    p_si = base_si
    p_no = base_no
    p_abst = base_abst

    # Ajustes por perfil del candidato
    if candidato['has_judicial']:
        p_si -= 0.15
        p_no += 0.15
    if candidato['is_high']:
        p_si += 0.10
        p_no -= 0.05
    elif candidato['is_low']:
        p_si -= 0.05
        p_no += 0.05

    # Ajuste por homofilia (votante y candidato mismo nivel)
    if votante_level and votante_level == candidato['level']:
        p_si += 0.05
        p_no -= 0.05

    # Normalizar
    p_si = max(0.0, p_si)
    p_no = max(0.0, p_no)
    p_abst = max(0.0, p_abst)
    total = p_si + p_no + p_abst
    if total == 0:
        return (1/3, 1/3, 1/3)
    return (p_si / total, p_no / total, p_abst / total)


def generar_invitacion_y_votos(
    cur,
    proposer_id,
    vecinos,
    base_probs,
    fecha_base=None,
):
    """Genera una invitación, persiste el perfil del candidato y registra votos."""
    if not vecinos:
        return None

    # Fechas
    if fecha_base is None:
        fecha_base = datetime.now() - timedelta(days=random.randint(0, 180))
    opened_at = fecha_base
    closes_at = opened_at + timedelta(days=7)

    # Generar perfil sintético del candidato (se persistirá en invitations)
    candidato = generar_perfil_candidato()

    # Insertar invitación incluyendo las nuevas columnas de v3
    invitation_id = str(uuid.uuid4())
    candidate_email = fake.email()
    cur.execute(
        """
        INSERT INTO invitations 
        (id, proposer_id, candidate_email, opened_at, closes_at, status,
         candidate_socioeconomic_level, candidate_backgrounds)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            invitation_id,
            proposer_id,
            candidate_email,
            opened_at,
            closes_at,
            "open",
            candidato['level'],
            candidato['backgrounds']  # psycopg2 convierte lista a array PostgreSQL
        ),
    )

    # Simular votos de los vecinos
    votos_si = 0
    for voter_id in vecinos:
        votante_level = obtener_perfil_votante(cur, voter_id)

        p_si, p_no, p_abst = calcular_probabilidades_voto(
            base_probs['si'],
            base_probs['no'],
            base_probs['abst'],
            candidato,
            votante_level
        )

        r = random.random()
        if r < p_si:
            choice = "yes"
            votos_si += 1
            reason = None
        elif r < p_si + p_no:
            choice = "no"
            reason = fake.sentence(nb_words=10)
        else:
            choice = "abstain"
            reason = None

        cast_at = opened_at + timedelta(seconds=random.randint(0, 7 * 24 * 3600))
        cur.execute(
            """
            INSERT INTO votes (invitation_id, voter_id, choice, reason, cast_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (invitation_id, voter_id, choice, reason, cast_at),
        )

    # Determinar estado final según cuórum
    cuorum = calcular_cuorum(len(vecinos))
    status = "closed_approved" if votos_si >= cuorum else "closed_rejected"

    cur.execute(
        "UPDATE invitations SET status = %s WHERE id = %s",
        (status, invitation_id),
    )

    return invitation_id


def main():
    parser = argparse.ArgumentParser(description="Simular actividad en la red v1+v2+v3")
    parser.add_argument(
        "--num-invitaciones",
        type=int,
        default=50,
        help="Número de invitaciones a generar",
    )
    parser.add_argument(
        "--prob-si",
        type=float,
        default=0.6,
        help="Probabilidad base de voto SÍ (0-1)",
    )
    parser.add_argument(
        "--prob-no",
        type=float,
        default=0.2,
        help="Probabilidad base de voto NO (0-1)",
    )
    parser.add_argument(
        "--prob-abstencion",
        type=float,
        default=0.2,
        help="Probabilidad base de abstención (0-1)",
    )
    parser.add_argument(
        "--fecha-inicio",
        type=str,
        default=None,
        help="Fecha mínima para las invitaciones (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--fecha-fin",
        type=str,
        default=None,
        help="Fecha máxima para las invitaciones (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--borrar",
        action="store_true",
        help="Eliminar invitations y votes existentes antes de generar",
    )
    args = parser.parse_args()

    # Validar probabilidades
    if abs(args.prob_si + args.prob_no + args.prob_abstencion - 1.0) > 0.001:
        print("Error: Las probabilidades base deben sumar 1.0")
        return

    base_probs = {
        'si': args.prob_si,
        'no': args.prob_no,
        'abst': args.prob_abstencion
    }

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    if args.borrar:
        print("Eliminando invitations y votes existentes...")
        cur.execute("DELETE FROM votes;")
        cur.execute("DELETE FROM invitations;")
        conn.commit()

    # Obtener usuarios activos
    cur.execute("SELECT id FROM users WHERE status = 'active'")
    usuarios = [row[0] for row in cur.fetchall()]
    if not usuarios:
        print("No hay usuarios en la base de datos. Ejecuta primero generar_red.py")
        return

    # Verificar existencia de v2
    cur.execute("SELECT 1 FROM user_socioeconomic_profile LIMIT 1")
    tiene_v2 = cur.fetchone() is not None
    if tiene_v2:
        print("✅ Datos de v2 (perfiles socioeconómicos) encontrados. Los votos se verán influenciados.")
    else:
        print("⚠️  No se encontraron perfiles v2. Los votos usarán solo las probabilidades base.")

    # Rango de fechas
    fecha_inicio = None
    fecha_fin = None
    if args.fecha_inicio:
        fecha_inicio = datetime.strptime(args.fecha_inicio, "%Y-%m-%d")
    if args.fecha_fin:
        fecha_fin = datetime.strptime(args.fecha_fin, "%Y-%m-%d")
    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        print("Error: fecha_inicio debe ser anterior a fecha_fin")
        return

    # Bucle de generación
    invitaciones_generadas = 0
    intentos = 0
    max_intentos = args.num_invitaciones * 3

    while invitaciones_generadas < args.num_invitaciones and intentos < max_intentos:
        intentos += 1
        proposer = random.choice(usuarios)
        vecinos = obtener_vecindario_local(cur, proposer)
        if not vecinos:
            continue

        if fecha_inicio and fecha_fin:
            fecha_base = fake.date_time_between(start_date=fecha_inicio, end_date=fecha_fin)
        elif fecha_inicio:
            fecha_base = fake.date_time_between(start_date=fecha_inicio, end_date="+180d")
        elif fecha_fin:
            fecha_base = fake.date_time_between(start_date="-180d", end_date=fecha_fin)
        else:
            fecha_base = fake.date_time_between(start_date="-180d", end_date="now")

        invitacion_id = generar_invitacion_y_votos(
            cur,
            proposer,
            vecinos,
            base_probs,
            fecha_base=fecha_base,
        )
        if invitacion_id:
            invitaciones_generadas += 1
            if invitaciones_generadas % 10 == 0:
                print(f"Generadas {invitaciones_generadas} invitaciones...")

    conn.commit()
    print(f"Se generaron {invitaciones_generadas} invitaciones con sus votos y perfiles persistidos.")

    # Resumen
    cur.execute("SELECT status, COUNT(*) FROM invitations GROUP BY status;")
    print("Resumen de estados:")
    for status, count in cur.fetchall():
        print(f"  {status}: {count}")

    cur.execute("SELECT COUNT(*) FROM votes;")
    total_votos = cur.fetchone()[0]
    print(f"Total de votos emitidos: {total_votos}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()