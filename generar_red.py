#!/usr/bin/env python3
"""
Generador de red sintética para la gobernanza por grafo de invitaciones (v1+v2+v3+v4).
Uso: python generar_red.py --total 100 --fundadores 5 --semilla 42
"""

import argparse
import hashlib
import random
import uuid
from datetime import datetime, timedelta

import psycopg2
from faker import Faker

# ============================================================
# CONFIGURACIÓN DE LA BASE DE DATOS (AJUSTAR)
# ============================================================
DB_CONFIG = {
    "dbname": "gobernanza",
    "user": "postgres",
    "password": "1234",
    "host": "localhost",
    "port": 5432,
}

fake = Faker("es_ES")

# Enumeraciones para v2
SOCIOECONOMIC_LEVELS = ['bajo', 'medio_bajo', 'medio', 'medio_alto', 'alto']
BACKGROUND_TYPES = ['laboral', 'educativo', 'judicial', 'referencia_personal', 'otro']


# ============================================================
# FUNCIONES DE SORTEO DETERMINISTA
# ============================================================
def hash_determinista(seed, user_id, context):
    data = f"{seed}|{user_id}|{context}".encode("utf-8")
    return int(hashlib.sha256(data).hexdigest(), 16)


def sortear_hermanos(seed, user_id, hermanos, k):
    if k <= 0 or not hermanos:
        return []
    if k >= len(hermanos):
        return hermanos[:]

    hermanos_ordenados = sorted(hermanos)
    seleccionados = []
    indices_usados = set()
    for i in range(k):
        h = hash_determinista(seed, user_id, f"sibling_{i}")
        idx = h % len(hermanos_ordenados)
        while idx in indices_usados:
            idx = (idx + 1) % len(hermanos_ordenados)
        indices_usados.add(idx)
        seleccionados.append(hermanos_ordenados[idx])
    return seleccionados


# ============================================================
# GENERACIÓN DEL ÁRBOL DE INVITACIONES
# ============================================================
def generar_arbol_aleatorio(total_miembros, num_fundadores, max_hijos=4, max_profundidad=6, seed=None):
    if seed is not None:
        random.seed(seed)

    if num_fundadores > total_miembros:
        num_fundadores = total_miembros

    ids = [str(uuid.uuid4()) for _ in range(total_miembros)]
    usuarios = []
    cola = []

    # Fundadores
    for i in range(num_fundadores):
        uid = ids[i]
        usuarios.append({
            "id": uid,
            "inviter_id": None,
            "profundidad": 0,
            "rama_root": uid,
        })
        cola.append((uid, None, 0, uid))

    # Construir árbol
    idx = num_fundadores
    while cola and idx < total_miembros:
        padre_id, _, prof, raiz = cola.pop(0)
        prob = max(0.0, 0.8 - 0.1 * prof)
        if random.random() > prob:
            continue
        num_hijos = random.randint(0, max_hijos)
        num_hijos = min(num_hijos, total_miembros - idx)
        for _ in range(num_hijos):
            if idx >= total_miembros:
                break
            uid = ids[idx]
            usuarios.append({
                "id": uid,
                "inviter_id": padre_id,
                "profundidad": prof + 1,
                "rama_root": raiz,
            })
            cola.append((uid, padre_id, prof + 1, raiz))
            idx += 1

    # Asignar miembros sobrantes a fundadores aleatorios
    if idx < total_miembros:
        posibles_padres = [u["id"] for u in usuarios if u["profundidad"] == 0]
        for i in range(idx, total_miembros):
            padre = random.choice(posibles_padres)
            for u in usuarios:
                if u["id"] == padre:
                    raiz = u["rama_root"]
                    break
            usuarios.append({
                "id": ids[i],
                "inviter_id": padre,
                "profundidad": 1,
                "rama_root": raiz,
            })

    return usuarios


def calcular_ascendentes(usuarios_dict, user_id):
    ascendentes = []
    actual = user_id
    for _ in range(2):
        if actual not in usuarios_dict:
            break
        inviter = usuarios_dict[actual]["inviter_id"]
        if inviter is None:
            break
        ascendentes.append(inviter)
        actual = inviter
    return ascendentes


def obtener_hermanos(usuarios_dict, user_id):
    inviter = usuarios_dict[user_id]["inviter_id"]
    if inviter is None:
        return []
    hermanos = []
    for uid, data in usuarios_dict.items():
        if uid != user_id and data["inviter_id"] == inviter:
            hermanos.append(uid)
    return hermanos


# ============================================================
# FUNCIONES PARA V2 (PERFIL Y ANTECEDENTES)
# ============================================================
def insertar_perfil_socioeconomico(cur, user_id, fake):
    level = random.choice(SOCIOECONOMIC_LEVELS)
    occupation = fake.job() if random.random() < 0.8 else None
    education = random.choice(['primaria', 'secundaria', 'técnico', 'universitario', 'postgrado', None])
    income = random.choice(['<300k', '300k-600k', '600k-1M', '1M-2M', '>2M', None])
    notes = fake.sentence() if random.random() < 0.3 else None
    cur.execute("""
        INSERT INTO user_socioeconomic_profile
        (user_id, socioeconomic_level, occupation, education_level, monthly_income_range, notes, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (user_id, level, occupation, education, income, notes, datetime.now()))


def insertar_antecedentes(cur, user_id, fake, ids_existentes, max_por_usuario=3):
    num = random.randint(0, max_por_usuario)
    for _ in range(num):
        btype = random.choice(BACKGROUND_TYPES)
        desc = fake.sentence(nb_words=8)
        occurred = fake.date_between(start_date='-5y', end_date='today') if random.random() < 0.7 else None
        verified = random.random() < 0.3
        verified_by = None
        verified_at = None
        if verified and ids_existentes:
            verified_by = random.choice(ids_existentes)
            verified_at = datetime.now()
        cur.execute("""
            INSERT INTO user_backgrounds
            (user_id, background_type, description, occurred_at, verified, verified_by, verified_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, btype, desc, occurred, verified, verified_by, verified_at, datetime.now()))


# ============================================================
# FUNCIÓN PARA V4 (VECINOS INTER-RAMA PERSISTENTES)
# ============================================================
def asignar_vecinos_inter_rama(cur, user_id, rama_root, usuarios_dict, seed):
    """
    Asigna vecinos persistentes de otras ramas usando balanceo round-robin.
    """
    # Obtener todas las raíces de ramas (fundadores)
    raices = list({u["rama_root"] for u in usuarios_dict.values() if u["rama_root"] is not None})
    if not raices:
        return

    otras_ramas = [r for r in raices if r != rama_root]
    if not otras_ramas:
        return

    for otra_rama in otras_ramas:
        # Contar asignaciones activas de cada miembro de esa rama
        cur.execute("""
            SELECT neighbor_id, COUNT(*) AS cnt
            FROM inter_rama_assignments
            WHERE other_rama_root_id = %s AND replaced_at IS NULL
            GROUP BY neighbor_id
        """, (otra_rama,))
        counts = {row[0]: row[1] for row in cur.fetchall()}

        # Obtener miembros activos de esa rama
        cur.execute("SELECT id FROM users WHERE rama_root_id = %s AND status = 'active'", (otra_rama,))
        miembros = [row[0] for row in cur.fetchall()]
        if not miembros:
            continue

        # Elegir el que tenga menor carga (round-robin), desempatar con hash
        min_count = min(counts.get(m, 0) for m in miembros)
        candidatos = [m for m in miembros if counts.get(m, 0) == min_count]

        def hash_orden(m):
            return hash_determinista(seed, m, f"interrama_{otra_rama}")
        elegido = min(candidatos, key=hash_orden)

        # Insertar asignación
        cur.execute("""
            INSERT INTO inter_rama_assignments (user_id, neighbor_id, other_rama_root_id, assigned_at)
            VALUES (%s, %s, %s, now())
        """, (user_id, elegido, otra_rama))

    # Actualizar rama_root_id en users (cache)
    cur.execute("UPDATE users SET rama_root_id = %s WHERE id = %s", (rama_root, user_id))


# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Generar red sintética para gobernanza v1+v2+v3+v4")
    parser.add_argument("--total", type=int, default=100, help="Número total de miembros")
    parser.add_argument("--fundadores", type=int, default=5, help="Número de fundadores (génesis)")
    parser.add_argument("--semilla", type=int, default=42, help="Semilla para reproducibilidad")
    parser.add_argument("--max-hijos", type=int, default=4, help="Máximo de hijos por persona")
    parser.add_argument("--max-profundidad", type=int, default=6, help="Profundidad máxima del árbol")
    parser.add_argument("--borrar", action="store_true", help="Eliminar datos existentes antes de insertar")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    if args.borrar:
        print("Eliminando datos existentes...")
        cur.execute("DELETE FROM delegation_requests;")
        cur.execute("DELETE FROM inter_rama_assignments;")
        cur.execute("DELETE FROM sibling_assignments;")
        cur.execute("DELETE FROM votes;")
        cur.execute("DELETE FROM invitations;")
        cur.execute("DELETE FROM user_backgrounds;")
        cur.execute("DELETE FROM user_socioeconomic_profile;")
        cur.execute("DELETE FROM users;")
        conn.commit()

    print(f"Generando árbol con {args.total} miembros, {args.fundadores} fundadores, semilla {args.semilla}")
    usuarios = generar_arbol_aleatorio(
        total_miembros=args.total,
        num_fundadores=args.fundadores,
        max_hijos=args.max_hijos,
        max_profundidad=args.max_profundidad,
        seed=args.semilla
    )

    usuarios_ordenados = sorted(usuarios, key=lambda x: (x["profundidad"], x["id"]))
    usuarios_dict = {u["id"]: u for u in usuarios}

    print("Insertando usuarios, perfiles v2 y vecinos inter-rama v4...")
    inserted_ids = []  # para usar como verificadores de antecedentes

    for u in usuarios_ordenados:
        # Insertar usuario
        cur.execute(
            """
            INSERT INTO users (id, display_name, inviter_id, principles_accepted_at, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                u["id"],
                fake.name(),
                u["inviter_id"],
                datetime.now() - timedelta(days=random.randint(0, 365)),
                "active",
            ),
        )
        inserted_ids.append(u["id"])

        # Perfil socioeconómico (v2)
        insertar_perfil_socioeconomico(cur, u["id"], fake)

        # Antecedentes (v2)
        insertar_antecedentes(cur, u["id"], fake, inserted_ids, max_por_usuario=3)

        # Vecinos inter-rama persistentes (v4) - solo si no es fundador
        if u["inviter_id"] is not None:
            asignar_vecinos_inter_rama(cur, u["id"], u["rama_root"], usuarios_dict, args.semilla)
        else:
            # Fundador: su rama_root es su propio id
            cur.execute("UPDATE users SET rama_root_id = %s WHERE id = %s", (u["id"], u["id"]))

    conn.commit()
    print(f"{len(usuarios)} usuarios insertados con sus perfiles y vecinos inter-rama.")

    # Calcular y persistir hermanos vecinales (v1)
    print("Calculando y persistiendo hermanos vecinales...")
    semilla_red = args.semilla

    for u in usuarios_ordenados:
        user_id = u["id"]
        ascendentes = calcular_ascendentes(usuarios_dict, user_id)
        k = len(ascendentes)
        hermanos = obtener_hermanos(usuarios_dict, user_id)

        if k == 0 or not hermanos:
            continue

        seleccionados = sortear_hermanos(semilla_red, user_id, hermanos, k)

        for sibling_id in seleccionados:
            cur.execute(
                """
                INSERT INTO sibling_assignments (user_id, sibling_id, assigned_at)
                VALUES (%s, %s, %s)
                """,
                (user_id, sibling_id, datetime.now()),
            )
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM sibling_assignments;")
    count_siblings = cur.fetchone()[0]
    print(f"Total de asignaciones de hermanos: {count_siblings}")

    cur.execute("SELECT COUNT(*) FROM inter_rama_assignments;")
    count_inter = cur.fetchone()[0]
    print(f"Total de asignaciones inter-rama: {count_inter}")

    cur.close()
    conn.close()
    print("¡Red generada con éxito!")


if __name__ == "__main__":
    main()