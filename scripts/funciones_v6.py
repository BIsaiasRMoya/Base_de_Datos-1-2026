import math
import secrets
from datetime import datetime


# ============================================================
# CAMPO FINITO
# ============================================================
#
# Primo de Mersenne suficientemente grande
# para representar secretos de hasta 64 bytes
# aproximadamente.
#
# Para nuestra simulación utilizaremos
# secretos de 32 bytes.
# ============================================================

PRIMO = (2 ** 521) - 1


# ============================================================
# INVERSO MODULAR
# ============================================================

def inverso_modular(
    numero,
    primo=PRIMO
):
    """
    Calcula el inverso multiplicativo
    dentro del campo finito.
    """

    return pow(
        numero % primo,
        -1,
        primo
    )


# ============================================================
# EVALUAR POLINOMIO
# ============================================================

def evaluar_polinomio(
    coeficientes,
    x,
    primo=PRIMO
):
    """
    Evalúa un polinomio módulo primo.
    """

    resultado = 0

    potencia = 1

    for coeficiente in coeficientes:

        resultado = (
            resultado
            + coeficiente * potencia
        ) % primo

        potencia = (
            potencia * x
        ) % primo

    return resultado


# ============================================================
# DIVIDIR SECRETO
# ============================================================

def dividir_secreto(
    secreto,
    threshold_k=3,
    total_n=5
):
    """
    Divide un secreto utilizando
    Shamir's Secret Sharing.

    secreto:
        bytes

    threshold_k:
        cantidad mínima necesaria
        para reconstruir.

    total_n:
        cantidad total de fragmentos.

    Devuelve:

        [
            (x1, y1),
            (x2, y2),
            ...
        ]

    IMPORTANTE:
    utiliza aleatoriedad criptográfica.
    """

    if not isinstance(
        secreto,
        bytes
    ):

        raise TypeError(
            "El secreto debe ser bytes."
        )

    if threshold_k < 2:

        raise ValueError(
            "threshold_k debe ser "
            "al menos 2."
        )

    if total_n < threshold_k:

        raise ValueError(
            "total_n debe ser mayor "
            "o igual que threshold_k."
        )

    secreto_numero = int.from_bytes(
        secreto,
        byteorder="big"
    )

    if secreto_numero >= PRIMO:

        raise ValueError(
            "El secreto es demasiado grande "
            "para el campo utilizado."
        )

    # El término independiente
    # del polinomio es el secreto.
    coeficientes = [
        secreto_numero
    ]

    # Coeficientes aleatorios.
    for _ in range(
        threshold_k - 1
    ):

        coeficientes.append(
            secrets.randbelow(
                PRIMO
            )
        )

    fragmentos = []

    for x in range(
        1,
        total_n + 1
    ):

        y = evaluar_polinomio(
            coeficientes,
            x
        )

        fragmentos.append(
            (
                x,
                y
            )
        )

    return fragmentos


# ============================================================
# RECONSTRUIR SECRETO
# ============================================================

def reconstruir_secreto(
    fragmentos,
    longitud_bytes
):
    """
    Reconstruye el secreto mediante
    interpolación de Lagrange en x = 0.
    """

    if len(fragmentos) < 2:

        raise ValueError(
            "Se requieren al menos "
            "dos fragmentos."
        )

    xs = [
        fragmento[0]
        for fragmento in fragmentos
    ]

    if len(xs) != len(set(xs)):

        raise ValueError(
            "Los fragmentos no pueden "
            "tener valores x duplicados."
        )

    secreto_numero = 0

    for i, (
        x_i,
        y_i
    ) in enumerate(fragmentos):

        numerador = 1
        denominador = 1

        for j, (
            x_j,
            _
        ) in enumerate(fragmentos):

            if i == j:
                continue

            numerador = (
                numerador
                * (-x_j)
            ) % PRIMO

            denominador = (
                denominador
                * (x_i - x_j)
            ) % PRIMO

        lagrange = (
            numerador
            * inverso_modular(
                denominador
            )
        ) % PRIMO

        secreto_numero = (
            secreto_numero
            + y_i * lagrange
        ) % PRIMO

    return secreto_numero.to_bytes(
        longitud_bytes,
        byteorder="big"
    )


# ============================================================
# SERIALIZAR FRAGMENTO
# ============================================================

def serializar_fragmento(
    fragmento
):
    """
    Convierte un fragmento en texto.

    Formato:

    x:y_en_hexadecimal
    """

    x, y = fragmento

    return (
        f"{x}:"
        f"{y:x}"
    )


# ============================================================
# DESERIALIZAR
# ============================================================

def deserializar_fragmento(
    texto
):

    partes = texto.strip().split(
        ":",
        1
    )

    if len(partes) != 2:

        raise ValueError(
            "Fragmento inválido."
        )

    x = int(
        partes[0]
    )

    y = int(
        partes[1],
        16
    )

    return (
        x,
        y
    )


# ============================================================
# CUÓRUM DE REVOCACIÓN
# ============================================================

def calcular_cuorum_revocacion(
    total_activos
):
    """
    Revocación técnica:
    2/3 de la red activa.
    """

    if total_activos < 0:

        raise ValueError(
            "total_activos no puede "
            "ser negativo."
        )

    if total_activos == 0:

        return 0

    return math.ceil(
        (2 * total_activos) / 3
    )


# ============================================================
# MANDATO VIGENTE
# ============================================================

def mandato_vigente(
    granted_at,
    granted_until,
    revoked_at=None,
    referencia=None
):
    """
    Indica si un mandato técnico
    está vigente.
    """

    if referencia is None:

        referencia = datetime.now(
            tz=granted_at.tzinfo
        )

    if revoked_at is not None:

        if revoked_at <= referencia:
            return False

    return (
        granted_at
        <= referencia
        < granted_until
    )
