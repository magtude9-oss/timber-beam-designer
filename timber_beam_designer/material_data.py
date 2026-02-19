"""
Timber material properties per NZS AS 1720.1:2022.
Strength values in MPa, modulus of elasticity in GPa (stored as MPa internally).

Grade table includes phi and k2 per grade (varies between sawn timber and engineered products).
Grades with no wet-use data do not have a wet variant.
"""

# Each grade stores: fb (MPa), E (MPa), phi, k2, fs (MPa), fp (MPa)
# E values in the user table are in GPa — we store as MPa (* 1000).
# fs and fp: use None where data is not applicable (e.g. Macrocarpa).

TIMBER_GRADES = {
    # ── Sawn Timber ──────────────────────────────────────────────
    # density in kg/m^3 for self-weight calculation
    "SG8": {
        "fb": 14.0, "fs": 3.8, "fp": 8.9,
        "E": 8000.0, "phi": 0.8, "k2": 2.0,
        "density": 500.0, "has_wet": True,
    },
    "SG8 Wet in Use": {
        "fb": 11.7, "fs": 2.4, "fp": 5.3,
        "E": 6500.0, "phi": 0.8, "k2": 2.0,
        "density": 600.0, "has_wet": False,  # this IS the wet variant
    },

    # ── Prolam Glulam ───────────────────────────────────────────
    "Prolam PL8": {
        "fb": 19.0, "fs": 3.7, "fp": 8.9,
        "E": 8000.0, "phi": 0.8, "k2": 1.5,
        "density": 500.0, "has_wet": True,
    },
    "Prolam PL8 Wet": {
        "fb": 15.2, "fs": 2.5, "fp": 5.3,
        "E": 6400.0, "phi": 0.8, "k2": 1.5,
        "density": 600.0, "has_wet": False,
    },
    "Prolam PL10": {
        "fb": 22.0, "fs": 3.7, "fp": 8.9,
        "E": 10000.0, "phi": 0.8, "k2": 1.5,
        "density": 530.0, "has_wet": True,
    },
    "Prolam PL10 Wet": {
        "fb": 17.6, "fs": 2.5, "fp": 5.3,
        "E": 8000.0, "phi": 0.8, "k2": 1.5,
        "density": 630.0, "has_wet": False,
    },
    "Prolam PL12": {
        "fb": 25.0, "fs": 3.7, "fp": 8.9,
        "E": 11500.0, "phi": 0.8, "k2": 1.5,
        "density": 560.0, "has_wet": True,
    },
    "Prolam PL12 Wet": {
        "fb": 20.0, "fs": 2.5, "fp": 5.3,
        "E": 9200.0, "phi": 0.8, "k2": 1.5,
        "density": 660.0, "has_wet": False,
    },
    "Prolam PL17": {
        "fb": 42.0, "fs": 3.7, "fp": 8.9,
        "E": 16700.0, "phi": 0.8, "k2": 1.5,
        "density": 620.0, "has_wet": True,
    },
    "Prolam PL17 Wet": {
        "fb": 33.6, "fs": 2.5, "fp": 5.3,
        "E": 13400.0, "phi": 0.8, "k2": 1.5,
        "density": 720.0, "has_wet": False,
    },

    # ── Engineered Wood Products (no wet variants) ──────────────
    "hySPAN": {
        "fb": 48.0, "fs": 4.6, "fp": 12.0,
        "E": 13200.0, "phi": 0.9, "k2": 2.0,
        "density": 600.0, "has_wet": False,
    },
    "LVL": {
        "fb": 42.0, "fs": 4.6, "fp": 12.0,
        "E": 13200.0, "phi": 0.9, "k2": 2.0,
        "density": 600.0, "has_wet": False,
    },
    "hyONE": {
        "fb": 48.0, "fs": 4.6, "fp": 12.0,
        "E": 16000.0, "phi": 0.9, "k2": 2.0,
        "density": 600.0, "has_wet": False,
    },
    "hyCHORD": {
        "fb": 48.0, "fs": 4.6, "fp": 11.11,
        "E": 11000.0, "phi": 0.9, "k2": 2.0,
        "density": 600.0, "has_wet": False,
    },
    "Nelson Pine": {
        "fb": 42.0, "fs": 5.0, "fp": 12.0,
        "E": 10700.0, "phi": 0.9, "k2": 2.0,
        "density": 600.0, "has_wet": False,
    },
    "Macrocarpa": {
        "fb": 87.8, "fs": None, "fp": None,
        "E": 5790.0, "phi": 0.8, "k2": 2.0,
        "density": 480.0, "has_wet": False,
    },
    "hy90": {
        "fb": 34.0, "fs": 4.6, "fp": 12.0,
        "E": 9500.0, "phi": 0.9, "k2": 2.0,
        "density": 600.0, "has_wet": False,
    },
}


K1_FACTORS = {
    "long_term": 0.57,
    "medium_term": 0.77,
    "short_term": 0.94,
}

K4_DRY = 1.0
K4_GREEN = 0.7
K5_DEFAULT = 1.0


def get_k8(depth_mm: float) -> float:
    """Depth factor k8 = (300/d)^0.167, capped at 1.5."""
    if depth_mm <= 0:
        raise ValueError("Depth must be positive")
    return min((300.0 / depth_mm) ** 0.167, 1.5)


def get_grade(grade_name: str) -> dict:
    """Return material properties for a given grade name."""
    if grade_name not in TIMBER_GRADES:
        raise ValueError(
            f"Unknown grade '{grade_name}'. "
            f"Available: {', '.join(TIMBER_GRADES.keys())}"
        )
    return TIMBER_GRADES[grade_name]


def get_dropdown_grades() -> list[str]:
    """Return list of grade names suitable for the dropdown.
    Excludes wet variants that are shown only when the dry parent has_wet=True
    and the user selects wet use. Instead, we show all grades as-is since
    wet variants are already separate entries."""
    return list(TIMBER_GRADES.keys())
