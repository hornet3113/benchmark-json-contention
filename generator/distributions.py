"""distributions.py — parámetros del dataset sintético (SPEC A8, docs/F2_GENERADOR.md).

Todo número que mueva las métricas del benchmark vive aquí, con nombre, para
que el reporte (sección 1) pueda citarlo y otro equipo pueda reproducirlo.
Cambiar cualquiera de estos valores cambia el hash del dataset.

Solo datos: nada de lógica de generación (eso está en synthetic_data_generator.py).
Todos los textos son ASCII y sin "\\", tabuladores ni saltos de línea, para que
el COPY de PostgreSQL en F3 no los interprete (docs/F2_GENERADOR.md, trampa 4).
"""

from datetime import datetime, timezone

# Semilla fija y versionada (A8, R-33).
SEED = 42

# --- timestamp (A8) ---------------------------------------------------------
# Uniforme al segundo entre estos dos instantes, ambos incluidos. 2025 y 2026
# tienen 365 días cada uno, así que ≈50 % cae en 2026 o después: es la fracción
# que pasa el filtro "timestamp >= 2026-01-01T00:00:00Z" de Q2.
TS_START = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
TS_END = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
# Formato estricto: UTC, "Z", sin fracciones. Ver trampa 1 en docs/F2_GENERADOR.md.
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# --- items (R-09, F2-f) -----------------------------------------------------
# 1..6 ítems por registro. Media exacta: (1·20+2·24+3·20+4·16+5·12+6·8)/100 = 3.00
ITEM_COUNT_WEIGHTS = {1: 20, 2: 24, 3: 20, 4: 16, 5: 12, 6: 8}

# price uniforme en centavos [100, 9000] → 1.00 .. 90.00 (F2-e).
# P(price > 50) = (9000 − 5000) / (9000 − 100 + 1) = 4000 / 8901 ≈ 44.94 %
PRICE_CENTS_MIN = 100
PRICE_CENTS_MAX = 9000

QTY_MIN = 1
QTY_MAX = 5

# Porcentajes enteros: así el impuesto se calcula en enteros, sin flotantes.
TAX_PCT_WEIGHTS = {0: 10, 8: 30, 16: 60}

# discounts: lista de 0–2 porcentajes (F2-b). Números, no objetos, para no
# pasar de 3 niveles de anidamiento.
DISCOUNT_COUNT_WEIGHTS = {0: 60, 1: 30, 2: 10}
DISCOUNT_PCT_VALUES = (5, 10, 15, 20)

# 20 categorías × 12 países = 240 grupos posibles en Q1 (A8).
CATEGORIES = {
    "electronics": "ELE", "books": "BOO", "home": "HOM", "garden": "GAR",
    "toys": "TOY", "sports": "SPO", "beauty": "BEA", "health": "HEA",
    "grocery": "GRO", "fashion": "FAS", "shoes": "SHO", "automotive": "AUT",
    "office": "OFF", "pets": "PET", "music": "MUS", "movies": "MOV",
    "games": "GAM", "tools": "TOO", "baby": "BAB", "jewelry": "JEW",
}
BRAND_COUNT = 30  # "BRAND01" .. "BRAND30": nombres neutros, sin marcas reales
SKU_NUMBER_MAX = 99999

# --- customer ---------------------------------------------------------------
CUSTOMER_POOL = 100_000  # "C000000" .. "C099999": los clientes se repiten
TIER_WEIGHTS = {"bronze": 50, "silver": 30, "gold": 15, "platinum": 5}
SEGMENT_WEIGHTS = {"consumer": 70, "smb": 20, "enterprise": 10}

# 12 países, uniformes (A8). Cada uno: (lon, lat) aproximados del centro, y
# 2 estados con 2 ciudades cada uno. Las coordenadas se generan con
# ±COORD_JITTER_DEG alrededor del centro; no pretenden ser geografía exacta.
COUNTRIES = {
    "MX": ((-102.5, 23.6), {"Chiapas": ("Tuxtla Gutierrez", "Tapachula"),
                            "Jalisco": ("Guadalajara", "Zapopan")}),
    "US": ((-98.6, 39.8), {"California": ("Los Angeles", "San Diego"),
                           "Texas": ("Houston", "Austin")}),
    "CA": ((-106.3, 56.1), {"Ontario": ("Toronto", "Ottawa"),
                            "Quebec": ("Montreal", "Quebec City")}),
    "BR": ((-51.9, -14.2), {"Sao Paulo": ("Sao Paulo", "Campinas"),
                            "Rio de Janeiro": ("Rio de Janeiro", "Niteroi")}),
    "AR": ((-63.6, -38.4), {"Buenos Aires": ("La Plata", "Mar del Plata"),
                            "Cordoba": ("Cordoba", "Villa Maria")}),
    "CO": ((-74.3, 4.6), {"Antioquia": ("Medellin", "Envigado"),
                          "Cundinamarca": ("Bogota", "Soacha")}),
    "CL": ((-71.5, -35.7), {"Santiago": ("Santiago", "Puente Alto"),
                            "Valparaiso": ("Valparaiso", "Vina del Mar")}),
    "ES": ((-3.7, 40.4), {"Madrid": ("Madrid", "Alcala de Henares"),
                          "Cataluna": ("Barcelona", "Girona")}),
    "DE": ((10.4, 51.2), {"Bayern": ("Munich", "Nuremberg"),
                          "Hessen": ("Frankfurt", "Wiesbaden")}),
    "FR": ((2.2, 46.2), {"Ile-de-France": ("Paris", "Versailles"),
                         "Provence": ("Marseille", "Nice")}),
    "JP": ((138.3, 36.2), {"Tokyo": ("Tokyo", "Hachioji"),
                           "Osaka": ("Osaka", "Sakai")}),
    "IN": ((78.9, 20.6), {"Maharashtra": ("Mumbai", "Pune"),
                          "Karnataka": ("Bengaluru", "Mysuru")}),
}
COORD_JITTER_DEG = 1.0
COORD_DECIMALS = 6

# --- payment ----------------------------------------------------------------
# 70 % completed (A8): define el tamaño del sort de Q2.
STATUS_WEIGHTS = {"completed": 70, "pending": 12, "failed": 10, "refunded": 8}
METHOD_WEIGHTS = {"card": 55, "paypal": 20, "transfer": 15, "cash": 10}
GATEWAY_LATENCY_MS_MIN = 20
GATEWAY_LATENCY_MS_MAX = 800

# --- metadata ---------------------------------------------------------------
CHANNEL_WEIGHTS = {"web": 45, "mobile_app": 35, "marketplace": 15, "call_center": 5}
USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Mobile Safari/537.36",
    "ShopApp/4.2.1 (Android 14; build 4210)",
)
FLAG_VALUES = ("gift", "express", "first_order", "promo", "fraud_review")
FLAG_COUNT_WEIGHTS = {0: 50, 1: 35, 2: 15}
