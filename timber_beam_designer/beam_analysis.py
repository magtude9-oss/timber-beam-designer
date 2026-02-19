"""
Simply supported beam analysis for UDL loading.
All units: forces in kN, moments in kNm, lengths in m or mm as noted.
"""

from dataclasses import dataclass


@dataclass
class BeamActions:
    """Internal actions for a simply supported beam under UDL."""
    span_m: float
    w_uls: float        # ULS UDL (kN/m)
    w_sls_short: float  # SLS short-term UDL (kN/m)
    w_sls_long: float   # SLS long-term UDL (kN/m)
    M_star: float       # ULS max bending moment (kNm)
    V_star: float       # ULS max shear force (kN)
    R_max: float        # ULS max reaction (kN)


def analyse_simply_supported(span_m: float, w_uls: float,
                              w_sls_short: float, w_sls_long: float) -> BeamActions:
    """
    Analyse a simply supported beam under UDL.
    M = wL^2/8, V = wL/2, R = wL/2
    """
    L = span_m
    M_star = w_uls * L ** 2 / 8.0
    V_star = w_uls * L / 2.0
    R_max = V_star
    return BeamActions(
        span_m=L,
        w_uls=w_uls,
        w_sls_short=w_sls_short,
        w_sls_long=w_sls_long,
        M_star=M_star,
        V_star=V_star,
        R_max=R_max,
    )


def calc_deflection(w_kn_per_m: float, span_m: float,
                     E_mpa: float, Ix_mm4: float) -> float:
    """
    Mid-span deflection for simply supported beam under UDL.
    delta = 5*w*L^4 / (384*E*I)
    w in N/mm, L in mm, E in MPa, I in mm^4 -> delta in mm.
    Note: 1 kN/m = 1 N/mm (convenient unit equivalence).
    """
    w_n_per_mm = w_kn_per_m  # kN/m = N/mm
    L_mm = span_m * 1000.0
    return 5.0 * w_n_per_mm * L_mm ** 4 / (384.0 * E_mpa * Ix_mm4)
