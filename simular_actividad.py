#!/usr/bin/env python3
"""
Simula actividad de invitaciones y votos en la red v1.
Genera invitations y votes para la base de datos.
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


def obtener_vecindario_local(cur, user_id):
    """
    Calcula el vecindario local de un usuario según v1:
    - Ascendentes hasta 2 niveles (madrina y abuela)
    - Hijos (invitados por él)
    - Hermanos vecinales sorteados (de sibling_assignments)
    Retorna un conjunto de IDs.
    """
    vecinos = set()

    # 1. Ascendentes: madrina y abuela
    actual = user_id
    for _ in range(2):
        cur.execute("SELECT inviter_id FROM users WHERE id = %s", (actual,))
        row = cur.fetchone()
        if row is None or row[0] is None:
            break
        vecinos.add(row[0])
        actual = row[0]

    # 2. Hijos: usuarios cuyo inviter_id es este usuario
    cur.execute("SELECT id FROM users WHERE inviter_id = %s", (user_id,))
    for row in cur.fetchall():
        vecinos.add(row[0])

    # 3. Hermanos vecinales (asignaciones activas)
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

    # Excluir al propio usuario (por si acaso)
    vecinos.discard(user_id)

    return vecinos


def calcular_cuorum(tamano):
    """Cuórum = ceil(tamano/2)"""
    return (tamano + 1) // 2


def generar_invitacion_y_votos(
    cur,
    proposer_id,
    vecinos,
    prob_si=0.6,
    prob_no=0.2,
    prob_abstencion=0.2,
    fecha_base=None,
):
    """Genera una invitación y los votos asociados."""

    # Validar que hay vecinos
    if not vecinos:
        return None

    # Fechas
    if fecha_base is None:
        fecha_base = datetime.now() - timedelta(days=random.randint(0, 180))
    opened_at = fecha_base
    closes_at = opened_at + timedelta(days=7)  # plazo de 7 días

    # Insertar invitación (estado inicial 'open')
    invitation_id = str(uuid.uuid4())
    candidate_email = fake.email()
    cur.execute(
        """
        INSERT INTO invitations (id, proposer_id, candidate_email, opened_at, closes_at, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (invitation_id, proposer_id, candidate_email, opened_at, closes_at, "open"),
    )

    # Simular votos de los vecinos
    votos_si = 0
    for voter_id in vecinos:
        # Decidir voto
        r = random.random()
        if r < prob_si:
            choice = "yes"
            votos_si += 1
            reason = None
        elif r < prob_si + prob_no:
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
    if votos_si >= cuorum:
        status = "closed_approved"
    else:
        status = "closed_rejected"

    # Actualizar estado de la invitación
    cur.execute(
        "UPDATE invitations SET status = %s WHERE id = %s",
        (status, invitation_id),
    )

    return invitation_id


def main():
    parser = argparse.ArgumentParser(description="Simular actividad en la red v1")
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
        help="Probabilidad de voto SÍ (0-1)",
    )
    parser.add_argument(
        "--prob-no",
        type=float,
        default=0.2,
        help="Probabilidad de voto NO (0-1)",
    )
    parser.add_argument(
        "--prob-abstencion",
        type=float,
        default=0.2,
        help="Probabilidad de abstención (0-1)",
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
        print("Error: Las probabilidades deben sumar 1.0")
        return

    # Conectar
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    if args.borrar:
        print("Eliminando invitations y votes existentes...")
        cur.execute("DELETE FROM votes;")
        cur.execute("DELETE FROM invitations;")
        conn.commit()

    # Obtener todos los usuarios activos
    cur.execute("SELECT id FROM users WHERE status = 'active'")
    usuarios = [row[0] for row in cur.fetchall()]
    if not usuarios:
        print("No hay usuarios en la base de datos.")
        return

    # Preparar rango de fechas
    fecha_inicio = None
    fecha_fin = None
    if args.fecha_inicio:
        fecha_inicio = datetime.strptime(args.fecha_inicio, "%Y-%m-%d")
    if args.fecha_fin:
        fecha_fin = datetime.strptime(args.fecha_fin, "%Y-%m-%d")
    if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
        print("Error: fecha_inicio debe ser anterior a fecha_fin")
        return

    # Generar invitaciones
    invitaciones_generadas = 0
    intentos = 0
    max_intentos = args.num_invitaciones * 3

    while invitaciones_generadas < args.num_invitaciones and intentos < max_intentos:
        intentos += 1

        # Elegir proponente al azar
        proposer = random.choice(usuarios)

        # Calcular vecindario
        vecinos = obtener_vecindario_local(cur, proposer)
        if not vecinos:
            continue  # este usuario no puede invitar

        # Fecha aleatoria dentro del rango
        if fecha_inicio and fecha_fin:
            fecha_base = fake.date_time_between(start_date=fecha_inicio, end_date=fecha_fin)
        elif fecha_inicio:
            fecha_base = fake.date_time_between(start_date=fecha_inicio, end_date="+180d")
        elif fecha_fin:
            fecha_base = fake.date_time_between(start_date="-180d", end_date=fecha_fin)
        else:
            fecha_base = fake.date_time_between(start_date="-180d", end_date="now")

        # Generar invitación y votos
        invitacion_id = generar_invitacion_y_votos(
            cur,
            proposer,
            vecinos,
            prob_si=args.prob_si,
            prob_no=args.prob_no,
            prob_abstencion=args.prob_abstencion,
            fecha_base=fecha_base,
        )
        if invitacion_id:
            invitaciones_generadas += 1
            if invitaciones_generadas % 10 == 0:
                print(f"Generadas {invitaciones_generadas} invitaciones...")

    conn.commit()
    print(f"Se generaron {invitaciones_generadas} invitaciones con sus votos.")

    # Resumen estadístico
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