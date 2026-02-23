"""
Timber material properties per NZS AS 1720.1:2022 (incorporating AS 1720.1:2010 + NZ Appendix ZZ).
Strength values in MPa, modulus of elasticity stored as MPa internally.

Grade table includes phi and k2 per grade (varies between sawn timber and engineered products).
Grades with no wet-use data do not have a wet variant.

Modification factors per AS 1720.1:2022 Section 2 & 3:
  k1  - Duration of load factor (Table 2.3)
  k4  - Moisture condition factor (Clause 2.4.2)
  k6  - Temperature factor (Clause 2.4.3) -- 1.0 for NZ
  k7  - Length and position of bearing factor (Table 2.6)
  k9  - Strength sharing factor (Clause 2.4.5)
  k12 - Stability factor (Clause 3.2.4)

Note: The old NZS 3603 factors k5 (temperature) and k8 (depth) do NOT exist
in AS 1720.1:2022.  k5 is replaced by k6; k8 has no direct equivalent.
"""

# ── Timber Grade Data ──────────────────────────────────────────────
# Each grade stores: fb (MPa), E (MPa), phi, k2, fs (MPa), fp (MPa)
# E values in the user table are in GPa -- we store as MPa (* 1000).
# fs and fp: use None where data is not applicable (e.g. Macrocarpa).
# rho_b: material constant for k12 stability calc (Table ZZ3.1 for NZ sawn,
#         or manufacturer data for engineered products).

TIMBER_GRADES = {
    # ── Sawn Timber (NZ verified, Table ZZ2.1) ─────────────────────
    # phi = 0.8 per ZZ2.3(a); density = design density per Table ZZ2.1
    # f's = 3.8 MPa for radiata pine (Note 1)
    # f'p = 6.9 MPa for radiata pine/Douglas fir (Note 2)
    "SG8": {
        "fb": 14.0, "fs": 3.8, "fp": 6.9,
        "E": 8000.0, "phi": 0.8, "k2": 2.0,
        "density": 450.0, "has_wet": True,
        "rho_b": 0.76,
    },
    "SG8 Wet in Use": {
        "fb": 11.7, "fs": 2.4, "fp": 5.3,
        "E": 6500.0, "phi": 0.8, "k2": 2.0,
        "density": 550.0, "has_wet": False,  # this IS the wet variant
        "rho_b": 0.76,
    },

    # ── Prolam Glulam (phi=0.8 per ZZ2.3(a)) ──────────────────────
    # rho_b calculated from Eq. E2(1): rho_b = 14.71*(E/f'b)^-0.480 * r^-0.061
    # at r = 0.25 (per Table ZZ3.1 note), using GL-grade E and f'b values.
    "Prolam PL8": {
        "fb": 19.0, "fs": 3.7, "fp": 8.9,
        "E": 8000.0, "phi": 0.8, "k2": 1.5,
        "density": 500.0, "has_wet": True,
        "rho_b": 0.88,
    },
    "Prolam PL8 Wet": {
        "fb": 15.2, "fs": 2.5, "fp": 5.3,
        "E": 6400.0, "phi": 0.8, "k2": 1.5,
        "density": 600.0, "has_wet": False,
        "rho_b": 0.88,
    },
    "Prolam PL10": {
        "fb": 22.0, "fs": 3.7, "fp": 8.9,
        "E": 10000.0, "phi": 0.8, "k2": 1.5,
        "density": 530.0, "has_wet": True,
        "rho_b": 0.85,
    },
    "Prolam PL10 Wet": {
        "fb": 17.6, "fs": 2.5, "fp": 5.3,
        "E": 8000.0, "phi": 0.8, "k2": 1.5,
        "density": 630.0, "has_wet": False,
        "rho_b": 0.85,
    },
    "Prolam PL12": {
        "fb": 25.0, "fs": 3.7, "fp": 8.9,
        "E": 11500.0, "phi": 0.8, "k2": 1.5,
        "density": 560.0, "has_wet": True,
        "rho_b": 0.84,
    },
    "Prolam PL12 Wet": {
        "fb": 20.0, "fs": 2.5, "fp": 5.3,
        "E": 9200.0, "phi": 0.8, "k2": 1.5,
        "density": 660.0, "has_wet": False,
        "rho_b": 0.84,
    },
    "Prolam PL17": {
        "fb": 42.0, "fs": 3.7, "fp": 8.9,
        "E": 16700.0, "phi": 0.8, "k2": 1.5,
        "density": 620.0, "has_wet": True,
        "rho_b": 0.91,
    },
    "Prolam PL17 Wet": {
        "fb": 33.6, "fs": 2.5, "fp": 5.3,
        "E": 13400.0, "phi": 0.8, "k2": 1.5,
        "density": 720.0, "has_wet": False,
        "rho_b": 0.91,
    },

    # ── Engineered Wood Products (no wet variants) ─────────────────
    # phi = 0.9 per ZZ2.3(b) for LVL
    # rho_b calculated from Eq. 8(1)/E2(1): rho_b = 14.71*(E/f'b)^-0.480 * r^-0.061
    # at r = 0.25 (capped per Section 8.4.7). Uses manufacturer E and f'b values.
    "hySPAN": {
        "fb": 48.0, "fs": 4.6, "fp": 12.0,
        "E": 13200.0, "phi": 0.9, "k2": 2.0,
        "density": 600.0, "has_wet": False,
        "rho_b": 1.08,
    },
    "LVL": {
        "fb": 42.0, "fs": 4.6, "fp": 12.0,
        "E": 13200.0, "phi": 0.9, "k2": 2.0,
        "density": 600.0, "has_wet": False,
        "rho_b": 1.01,
    },
    "hyONE": {
        "fb": 48.0, "fs": 4.6, "fp": 12.0,
        "E": 16000.0, "phi": 0.9, "k2": 2.0,
        "density": 600.0, "has_wet": False,
        "rho_b": 0.99,
    },
    "hyCHORD": {
        "fb": 48.0, "fs": 4.6, "fp": 11.11,
        "E": 11000.0, "phi": 0.9, "k2": 2.0,
        "density": 600.0, "has_wet": False,
        "rho_b": 1.18,
    },
    "Nelson Pine": {
        "fb": 42.0, "fs": 5.0, "fp": 12.0,
        "E": 10700.0, "phi": 0.9, "k2": 2.0,
        "density": 600.0, "has_wet": False,
        "rho_b": 1.12,
    },
    "Macrocarpa": {
        "fb": 87.8, "fs": None, "fp": None,
        "E": 5790.0, "phi": 0.8, "k2": 2.0,
        "density": 480.0, "has_wet": False,
        "rho_b": 0.76,
    },
    "hy90": {
        "fb": 34.0, "fs": 4.6, "fp": 12.0,
        "E": 9500.0, "phi": 0.9, "k2": 2.0,
        "density": 600.0, "has_wet": False,
        "rho_b": 1.07,
    },
}


# ── k1: Duration of Load Factor (Table 2.3) ───────────────────────
# Values for timber member strength (not joints).
# Per user request: short_term=1.0, medium_term=0.8, long_term=0.6
K1_FACTORS = {
    "short_term": 1.0,
    "medium_term": 0.8,
    "long_term": 0.6,
}

# ── k4: Moisture Condition (Clause 2.4.2) ─────────────────────────
K4_DRY = 1.0       # seasoned timber, MC <= 15%
K4_WET = 0.7       # minimum k4 for wet conditions

# ── k6: Temperature Factor (Clause 2.4.3) ─────────────────────────
K6_DEFAULT = 1.0    # 1.0 for NZ (no tropical reduction)

# ── k7: Bearing Length Factor (Table 2.6) ──────────────────────────
# Applicable only when bearing is >= 75 mm from end of member.
# For end bearings, k7 = 1.0.
K7_TABLE = {
    12: 1.75,
    25: 1.40,
    50: 1.20,
    75: 1.15,
    125: 1.10,
    150: 1.00,
}


def get_k7(bearing_length_mm: float, is_at_end: bool = True) -> float:
    """
    Bearing length factor k7 per Table 2.6.
    k7 > 1.0 only when bearing is >= 75 mm from the end of the member.
    For end bearings (typical for simply supported beams), k7 = 1.0.
    """
    if is_at_end:
        return 1.0
    # Interpolate from Table 2.6
    lengths = sorted(K7_TABLE.keys())
    if bearing_length_mm <= lengths[0]:
        return K7_TABLE[lengths[0]]
    if bearing_length_mm >= lengths[-1]:
        return K7_TABLE[lengths[-1]]
    for i in range(len(lengths) - 1):
        if lengths[i] <= bearing_length_mm <= lengths[i + 1]:
            x0, x1 = lengths[i], lengths[i + 1]
            y0, y1 = K7_TABLE[x0], K7_TABLE[x1]
            return y0 + (y1 - y0) * (bearing_length_mm - x0) / (x1 - x0)
    return 1.0


# ── k12: Stability Factor (Clause 3.2.4) ──────────────────────────

def get_k12(rho_b: float, S1: float) -> float:
    """
    Stability factor k12 per Clause 3.2.4.
    rho_b = material constant (Table ZZ3.1 for NZ sawn timber).
    S1    = slenderness coefficient (depends on restraint conditions).

    For fully restrained beams (continuous compression edge restraint),
    S1 = 0.0 and k12 = 1.0.

    (a) rho_b * S1 <= 10:  k12 = 1.0
    (b) 10 < rho_b * S1 <= 20:  k12 = 1.5 - 0.05 * rho_b * S1
    (c) rho_b * S1 > 20:  k12 = 200 / (rho_b * S1)^2
    """
    product = rho_b * S1
    if product <= 10.0:
        return 1.0
    elif product <= 20.0:
        return 1.5 - 0.05 * product
    else:
        return 200.0 / (product ** 2)


def get_S1_compression_edge(d: float, b: float, Lay: float) -> float:
    """
    Slenderness coefficient S1 for beam with discrete lateral restraints
    at the compression edge, per Eq. 3.2(4).
    S1 = 1.25 * (d/b) * (Lay/d)^0.5
    d = depth (mm), b = breadth (mm), Lay = restraint spacing (mm).
    """
    if b <= 0 or d <= 0 or Lay <= 0:
        return 0.0
    return 1.25 * (d / b) * (Lay / d) ** 0.5


def is_lvl_grade(grade_name: str) -> bool:
    """Check if a grade is an LVL product (k9 must be 1.0 per Section 8.4.6)."""
    lvl_names = {"hySPAN", "LVL", "hyONE", "hyCHORD", "Nelson Pine", "hy90"}
    return grade_name in lvl_names


def is_glulam_grade(grade_name: str) -> bool:
    """Check if a grade is glulam (Prolam)."""
    return grade_name.startswith("Prolam")


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
