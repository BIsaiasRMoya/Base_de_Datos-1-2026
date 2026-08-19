#!/usr/bin/env python3
"""
Pobla las tablas de la versión 2 (perfil socioeconómico y antecedentes)
para todos los usuarios existentes en la base de datos.
Uso: python poblar_v2.py
"""

import random
import psycopg2
from faker import Faker
from datetime import datetime

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


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()

    # Obtener todos los usuarios activos
    cur.execute("SELECT id FROM users WHERE status = 'active'")
    user_ids = [row[0] for row in cur.fetchall()]
    print(f"Usuarios encontrados: {len(user_ids)}")

    if not user_ids:
        print("No hay usuarios. Ejecuta primero generar_red.py")
        return

    for uid in user_ids:
        # ---- Perfil socioeconómico (solo si no existe) ----
        cur.execute("SELECT 1 FROM user_socioeconomic_profile WHERE user_id = %s", (uid,))
        if not cur.fetchone():
            level = random.choice(SOCIOECONOMIC_LEVELS)
            occupation = fake.job() if random.random() < 0.8 else None
            education = random.choice(['primaria', 'secundaria', 'técnico', 'universitario', 'postgrado', None])
            income = random.choice(['<300k', '300k-600k', '600k-1M', '1M-2M', '>2M', None])
            notes = fake.sentence() if random.random() < 0.3 else None
            cur.execute("""
                INSERT INTO user_socioeconomic_profile
                (user_id, socioeconomic_level, occupation, education_level, monthly_income_range, notes, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (uid, level, occupation, education, income, notes, datetime.now()))

        # ---- Antecedentes (entre 0 y 3 por usuario) ----
        num = random.randint(0, 3)
        for _ in range(num):
            btype = random.choice(BACKGROUND_TYPES)
            desc = fake.sentence(nb_words=8)
            occurred = fake.date_between(start_date='-5y', end_date='today') if random.random() < 0.7 else None
            verified = random.random() < 0.3
            verified_by = random.choice(user_ids) if verified and user_ids else None
            verified_at = datetime.now() if verified else None
            cur.execute("""
                INSERT INTO user_backgrounds
                (user_id, background_type, description, occurred_at, verified, verified_by, verified_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (uid, btype, desc, occurred, verified, verified_by, verified_at, datetime.now()))

    conn.commit()
    print("Perfiles y antecedentes insertados correctamente.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()