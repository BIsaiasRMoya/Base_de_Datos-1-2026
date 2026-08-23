#!/usr/bin/env python3
"""
Simula actividad de invitaciones y votos en la red v1+v2+v3+v4.
Los votos se ven influidos por el perfil socioeconómico y antecedentes
del candidato (simulado y persistido en la BD) y del votante.
El vecindario incluye el vecindario local + vecinos inter-rama persistentes (v4).
Además, registra automáticamente las métricas en experiment_log.

Uso: python simular_actividad.py --num-invitaciones 50 --prob-si 0.6 --notas "prueba con v4"
"""

import argparse
import json
import random
import uuid
from datetime import datetime, timedelta

import psycopg2
from faker import Faker

# ============================================================
# CONFIGURACIÓN
# ============================================================
DB_CONFIG = {
    "dbname": "gobernanza",
    "user": "postgres",
    "password": "1234",
    "host": "localhost",
    "port": 5432,
}

fake = Faker("es_ES")

SOCIOECONOMIC_LEVELS = ['bajo', 'medio_bajo', 'medio', 'medio_alto', 'alto']
BACKGROUND_TYPES = ['laboral', 'educativo', 'judicial', 'referencia_personal', 'otro']

_voter_profile_cache = {}


# ============================================================
# FUNCIONES DE VECINDARIO
# ============================================================
def obtener_vecindario_local(cur, user_id):
    """
    Vecindario local: ascendentes (hasta 2), hijos, hermanos sorteados activos.
    """
    vecinos = set()

    # Ascendentes
    actual = user_id
    for _ in range(2):
        cur.execute("SELECT inviter_id FROM users WHERE id = %s", (actual,))
        row = cur.fetchone()
        if row is None or row[0] is None:
            break
        vecinos.add(row[0])
        actual = row[0]

    # Hijos
    cur.execute("SELECT id FROM users WHERE inviter_id = %s", (user_id,))
    for row in cur.fetchall():
        vecinos.add(row[0])

    # Hermanos vecinales (sibling_assignments activas)
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


def obtener_vecindario_expandido(cur, user_id):
    """
    Vecindario expandido = local + vecinos inter-rama persistentes (v4).
    """
    vecinos = obtener_vecindario_local(cur, user_id)
    cur.execute(
        """
        SELECT neighbor_id
        FROM inter_rama_assignments
        WHERE user_id = %s AND replaced_at IS NULL
        """,
        (user_id,),
    )
    for row in cur.fetchall():
        vecinos.add(row[0])
    return vecinos


def calcular_cuorum(tamano):
    return (tamano + 1) // 2


# ============================================================
# PERFILES Y PROBABILIDADES
# ============================================================
def obtener_perfil_votante(cur, voter_id):
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
    level = random.choice(SOCIOECONOMIC_LEVELS)
    backgrounds = []
    if random.random() < 0.3:
        backgrounds.append('judicial')
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
    p_si = base_si
    p_no = base_no
    p_abst = base_abst

    if candidato['has_judicial']:
        p_si -= 0.15
        p_no += 0.15
    if candidato['is_high']:
        p_si += 0.10
        p_no -= 0.05
    elif candidato['is_low']:
        p_si -= 0.05
        p_no += 0.05

    if votante_level and votante_level == candidato['level']:
        p_si += 0.05
        p_no -= 0.05

    p_si = max(0.0, p_si)
    p_no = max(0.0, p_no)
    p_abst = max(0.0, p_abst)
    total = p_si + p_no + p_abst
    if total == 0:
        return (1/3, 1/3, 1/3)
    return (p_si / total, p_no / total, p_abst / total)


# ============================================================
# GENERAR INVITACIÓN
# ============================================================
def generar_invitacion_y_votos(
    cur,
    proposer_id,
    vecinos,
    base_probs,
    fecha_base=None,
):
    if not vecinos:
        return None

    if fecha_base is None:
        fecha_base = datetime.now() - timedelta(days=random.randint(0, 180))
    opened_at = fecha_base
    closes_at = opened_at + timedelta(days=7)

    candidato = generar_perfil_candidato()

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
            candidato['backgrounds']
        ),
    )

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

    cuorum = calcular_cuorum(len(vecinos))
    status = "closed_approved" if votos_si >= cuorum else "closed_rejected"
    cur.execute(
        "UPDATE invitations SET status = %s WHERE id = %s",
        (status, invitation_id),
    )

    return invitation_id


# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Simular actividad en la red v1+v2+v3+v4")
    parser.add_argument("--num-invitaciones", type=int, default=50, help="Número de invitaciones a generar")
    parser.add_argument("--prob-si", type=float, default=0.6, help="Probabilidad base de voto SÍ (0-1)")
    parser.add_argument("--prob-no", type=float, default=0.2, help="Probabilidad base de voto NO (0-1)")
    parser.add_argument("--prob-abstencion", type=float, default=0.2, help="Probabilidad base de abstención (0-1)")
    parser.add_argument("--fecha-inicio", type=str, default=None, help="Fecha mínima (YYYY-MM-DD)")
    parser.add_argument("--fecha-fin", type=str, default=None, help="Fecha máxima (YYYY-MM-DD)")
    parser.add_argument("--borrar", action="store_true", help="Eliminar invitations y votes existentes")
    parser.add_argument("--notas", type=str, default=None, help="Notas cualitativas para el registro")
    parser.add_argument("--version", type=str, default="v4", help="Versión del modelo de gobernanza")
    args = parser.parse_args()

    if abs(args.prob_si + args.prob_no + args.prob_abstencion - 1.0) > 0.001:
        print("Error: Las probabilidades base deben sumar 1.0")
        return

    base_probs = {'si': args.prob_si, 'no': args.prob_no, 'abst': args.prob_abstencion}

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    if args.borrar:
        print("Eliminando invitations y votes existentes...")
        cur.execute("DELETE FROM votes;")
        cur.execute("DELETE FROM invitations;")
        conn.commit()

    # Usuarios activos
    cur.execute("SELECT id FROM users WHERE status = 'active'")
    usuarios = [row[0] for row in cur.fetchall()]
    if not usuarios:
        print("No hay usuarios. Ejecuta primero generar_red.py")
        return

    # Verificar existencia de v2 y v4
    cur.execute("SELECT 1 FROM user_socioeconomic_profile LIMIT 1")
    tiene_v2 = cur.fetchone() is not None
    cur.execute("SELECT 1 FROM inter_rama_assignments LIMIT 1")
    tiene_v4 = cur.fetchone() is not None

    if tiene_v2:
        print("✅ Datos de v2 (perfiles) encontrados.")
    else:
        print("⚠️  Sin perfiles v2, solo probabilidades base.")
    if tiene_v4:
        print("✅ Datos de v4 (vecinos inter-rama) encontrados. Se usará vecindario expandido.")
    else:
        print("⚠️  Sin vecinos inter-rama, se usará vecindario local.")

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
    total_neighborhood_size = 0
    vecindarios_usados = []

    while invitaciones_generadas < args.num_invitaciones and intentos < max_intentos:
        intentos += 1
        proposer = random.choice(usuarios)

        # Usar vecindario expandido si existe v4, si no, local
        if tiene_v4:
            vecinos = obtener_vecindario_expandido(cur, proposer)
        else:
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
            total_neighborhood_size += len(vecinos)
            vecindarios_usados.append(len(vecinos))
            if invitaciones_generadas % 10 == 0:
                print(f"Generadas {invitaciones_generadas} invitaciones...")

    conn.commit()

    # Métricas
    avg_neighborhood = round(total_neighborhood_size / invitaciones_generadas, 2) if invitaciones_generadas else 0
    approved_count = 0
    rejected_count = 0
    cur.execute("SELECT status, COUNT(*) FROM invitations GROUP BY status")
    for status, count in cur.fetchall():
        if status == 'closed_approved':
            approved_count = count
        elif status == 'closed_rejected':
            rejected_count = count

    total_votos = 0
    cur.execute("SELECT COUNT(*) FROM votes")
    total_votos = cur.fetchone()[0]

    approval_rate = round(approved_count / invitaciones_generadas, 2) if invitaciones_generadas else 0
    avg_votes_per_invitation = round(total_votos / invitaciones_generadas, 2) if invitaciones_generadas else 0

    print(f"Se generaron {invitaciones_generadas} invitaciones.")
    print(f"  Aprobadas: {approved_count}, Rechazadas: {rejected_count}")
    print(f"Total de votos: {total_votos}")
    print(f"Tamaño promedio de vecindario: {avg_neighborhood}")

    # Registrar en experiment_log
    try:
        cur.execute("""
            INSERT INTO experiment_log
            (version, script_name, parameters, total_invitations, approved, rejected,
             total_votes, avg_votes_per_invitation, approval_rate, avg_neighborhood_size, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            args.version,
            'simular_actividad.py',
            json.dumps({
                'num_invitaciones': args.num_invitaciones,
                'prob_si': args.prob_si,
                'prob_no': args.prob_no,
                'prob_abstencion': args.prob_abstencion,
                'fecha_inicio': args.fecha_inicio,
                'fecha_fin': args.fecha_fin,
                'borrar': args.borrar,
                'usa_inter_rama': tiene_v4,
            }),
            invitaciones_generadas,
            approved_count,
            rejected_count,
            total_votos,
            avg_votes_per_invitation,
            approval_rate,
            avg_neighborhood,
            args.notas
        ))
        conn.commit()
        print("✅ Métricas registradas en experiment_log.")
    except Exception as e:
        print(f"⚠️  Error al registrar en experiment_log: {e}")
        conn.rollback()

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()