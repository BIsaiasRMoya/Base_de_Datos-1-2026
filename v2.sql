-- ============================================================
-- v2 — Perfil extendido de usuarios: nivel socioeconómico y antecedentes
-- Migración ADITIVA sobre v1: no borra ni renombra nada existente.
-- Agrega dos tablas nuevas relacionadas 1:1 y 1:N con users.
-- ============================================================

-- Enumeración para nivel socioeconómico (escala ordinal simple)
CREATE TYPE socioeconomic_level AS ENUM (
    'bajo',
    'medio_bajo',
    'medio',
    'medio_alto',
    'alto'
);

-- Enumeración para el tipo de antecedente registrado
CREATE TYPE background_type AS ENUM (
    'laboral',
    'educativo',
    'judicial',
    'referencia_personal',
    'otro'
);

-- ------------------------------------------------------------
-- Tabla de perfil socioeconómico (relación 1:1 con users)
-- ------------------------------------------------------------
CREATE TABLE user_socioeconomic_profile (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    socioeconomic_level socioeconomic_level NOT NULL,
    occupation TEXT,
    education_level TEXT,
    monthly_income_range TEXT,
    notes TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE user_socioeconomic_profile IS 'Perfil socioeconómico extendido de cada usuario. Relación 1:1 con users, introducida en v2.';
COMMENT ON COLUMN user_socioeconomic_profile.socioeconomic_level IS 'Nivel socioeconómico autodeclarado o estimado.';
COMMENT ON COLUMN user_socioeconomic_profile.monthly_income_range IS 'Rango de ingreso mensual, texto libre para no forzar precisión (ej. "500.000 - 800.000 CLP").';

-- ------------------------------------------------------------
-- Tabla de antecedentes (relación 1:N con users)
-- Un usuario puede tener varios antecedentes de distinto tipo.
-- ------------------------------------------------------------
CREATE TABLE user_backgrounds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    background_type background_type NOT NULL,
    description TEXT NOT NULL,
    occurred_at DATE,
    verified BOOLEAN NOT NULL DEFAULT false,
    verified_by UUID REFERENCES users(id) ON DELETE SET NULL,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE user_backgrounds IS 'Antecedentes registrados por usuario (laborales, educativos, judiciales, referencias, etc). Relación 1:N con users, introducida en v2.';
COMMENT ON COLUMN user_backgrounds.verified IS 'Indica si el antecedente fue verificado por otro miembro de la red.';
COMMENT ON COLUMN user_backgrounds.verified_by IS 'Usuario que verificó este antecedente (NULL si no ha sido verificado).';

-- ------------------------------------------------------------
-- Índices para consultas típicas
-- ------------------------------------------------------------
CREATE INDEX idx_user_socioeconomic_profile_level ON user_socioeconomic_profile(socioeconomic_level);
CREATE INDEX idx_user_backgrounds_user_id ON user_backgrounds(user_id);
CREATE INDEX idx_user_backgrounds_type ON user_backgrounds(background_type);
CREATE INDEX idx_user_backgrounds_verified ON user_backgrounds(verified);
