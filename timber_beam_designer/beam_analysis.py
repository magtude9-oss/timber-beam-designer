"""
Beam analysis for simply supported and overhanging beams.
UDL + optional point loads with superposition.
All units: forces in kN, moments in kNm, lengths in m or mm as noted.

Overhanging beam geometry:
  R1 ---- ell (back span) ---- R2 ---- a (overhang) ---- free end
  |<------------ total span = ell + a ---------------------->|
"""

import math
from dataclasses import dataclass, field

# Beam type constants
SIMPLY_SUPPORTED = "simply_supported"
OVERHANGING = "overhanging"


@dataclass
class BeamActions:
    """Internal actions for a beam under UDL + optional point loads."""
    span_m: float           # SS: full span. Overhanging: total span (ell + a)
    w_uls: float            # ULS UDL for back span (kN/m)
    w_sls_short: float      # SLS short-term UDL for back span (kN/m)
    w_sls_long: float       # SLS long-term UDL for back span (kN/m)
    M_star: float           # Total ULS max bending moment (kNm)
    V_star: float           # Total ULS max shear force (kN)
    R_max: float            # Total ULS max reaction (kN)
    # Beam type
    beam_type: str = SIMPLY_SUPPORTED
    # Point load tracking (for reporting breakdowns)
    point_loads: list = field(default_factory=list)
    M_udl: float = 0.0
    M_point: float = 0.0
    V_udl: float = 0.0
    R_left: float = 0.0    # R1 (left support)
    R_right: float = 0.0   # R2 (right/interior support)

    # ── SLS G / Q breakdown (for correct long-term deflection) ──
    w_G_back: float = 0.0            # Dead load UDL on back span (kN/m)
    w_psi_lQ_back: float = 0.0       # Long-term live load = 0.4Q on back span (kN/m)
    w_G_cant: float = 0.0            # Dead load UDL on overhang (kN/m)
    w_psi_lQ_cant: float = 0.0       # Long-term live load = 0.4Q on overhang (kN/m)

    # ── Overhanging beam specific fields ──
    back_span_m: float = 0.0         # ell (distance between supports)
    cant_span_m: float = 0.0         # a (overhang length beyond R2)
    w_uls_cant: float = 0.0          # ULS UDL on overhang (kN/m)
    w_sls_short_cant: float = 0.0    # SLS short-term UDL on overhang (kN/m)
    w_sls_long_cant: float = 0.0     # SLS long-term UDL on overhang (kN/m)
    M_sagging: float = 0.0           # Max sagging moment between supports (kNm)
    M_hogging: float = 0.0           # Hogging moment at R2 (positive magnitude, kNm)
    M_sagging_udl: float = 0.0       # Sagging from UDL only
    M_hogging_udl: float = 0.0       # Hogging from UDL only
    M_sagging_point: float = 0.0     # Sagging from point loads on back span
    M_hogging_point: float = 0.0     # Hogging from point loads on overhang
    V_at_R2: float = 0.0             # Shear at R2
    point_loads_back: list = field(default_factory=list)   # Point loads on back span
    point_loads_cant: list = field(default_factory=list)    # Point loads on overhang


# ═══════════════════════════════════════════════════════════════════
# SIMPLY SUPPORTED — point load helpers
# ═══════════════════════════════════════════════════════════════════


def point_load_moment(P: float, a: float, L: float) -> float:
    """Max moment from a point load P at distance 'a' from left support.
    M = P*a*(L-a)/L at the load point."""
    return P * a * (L - a) / L


def point_load_reactions(P: float, a: float, L: float) -> tuple:
    """Reactions for point load P at distance 'a' from left support.
    Ra = P*(L-a)/L, Rb = P*a/L"""
    Ra = P * (L - a) / L
    Rb = P * a / L
    return Ra, Rb


def calc_deflection_point_load(P_kn: float, a_m: float, span_m: float,
                                E_mpa: float, Ix_mm4: float) -> float:
    """
    Midspan deflection for a point load P at distance 'a' from left support
    on a simply supported beam.
    Uses: delta_mid = P*b*(3L^2 - 4b^2) / (48*E*I)
    where b = min(a, L-a) (symmetry).
    P in kN -> N, a and L in m -> mm. Returns deflection in mm.
    """
    P_n = P_kn * 1000.0
    L_mm = span_m * 1000.0
    a_mm = a_m * 1000.0
    b_mm = min(a_mm, L_mm - a_mm)

    if L_mm <= 0 or E_mpa <= 0 or Ix_mm4 <= 0:
        return 0.0

    return P_n * b_mm * (3.0 * L_mm ** 2 - 4.0 * b_mm ** 2) / (48.0 * E_mpa * Ix_mm4)


# ═══════════════════════════════════════════════════════════════════
# SIMPLY SUPPORTED — main analysis
# ═══════════════════════════════════════════════════════════════════


def analyse_simply_supported(span_m: float, w_uls: float,
                              w_sls_short: float, w_sls_long: float,
                              point_loads: list = None,
                              w_G: float = 0.0, w_psi_lQ: float = 0.0) -> BeamActions:
    """
    Analyse a simply supported beam under UDL + optional point loads.
    Uses superposition: total actions = UDL actions + sum of point load actions.
    """
    L = span_m

    # UDL contributions
    M_udl = w_uls * L ** 2 / 8.0
    V_udl = w_uls * L / 2.0
    R_udl = V_udl

    # Point load contributions (superposition)
    M_point = 0.0
    R_left_point = 0.0
    R_right_point = 0.0

    if point_loads:
        for pl in point_loads:
            M_point += point_load_moment(pl.P_uls, pl.a_m, L)
            Ra, Rb = point_load_reactions(pl.P_uls, pl.a_m, L)
            R_left_point += Ra
            R_right_point += Rb

    # Combined actions
    M_star = M_udl + M_point
    R_left = R_udl + R_left_point
    R_right = R_udl + R_right_point
    V_star = max(R_left, R_right)
    R_max = max(R_left, R_right)

    return BeamActions(
        span_m=L,
        w_uls=w_uls,
        w_sls_short=w_sls_short,
        w_sls_long=w_sls_long,
        M_star=M_star,
        V_star=V_star,
        R_max=R_max,
        beam_type=SIMPLY_SUPPORTED,
        point_loads=point_loads or [],
        M_udl=M_udl,
        M_point=M_point,
        V_udl=V_udl,
        R_left=R_left,
        R_right=R_right,
        w_G_back=w_G,
        w_psi_lQ_back=w_psi_lQ,
    )


# ═══════════════════════════════════════════════════════════════════
# OVERHANGING BEAM — point load helpers
# ═══════════════════════════════════════════════════════════════════


def point_load_reactions_backspan(P: float, a_from_R1: float, ell: float) -> tuple:
    """Reactions for point load P at distance a_from_R1 from R1 on back span.
    Standard SS formula: R1 = P*(ell-a)/ell, R2 = P*a/ell"""
    b = ell - a_from_R1
    R1 = P * b / ell
    R2 = P * a_from_R1 / ell
    return R1, R2


def point_load_moment_backspan(P: float, a_from_R1: float, ell: float) -> float:
    """Max sagging moment from point load on back span.
    M = P*a*b/ell where b = ell - a."""
    b = ell - a_from_R1
    return P * a_from_R1 * b / ell


def point_load_reactions_overhang(P: float, x1: float, ell: float) -> tuple:
    """Reactions for point load P at distance x1 from R2 on the overhang.
    R1 = -P*x1/ell (negative = downward/uplift at R1)
    R2 = P*(ell + x1)/ell"""
    R1 = -P * x1 / ell
    R2 = P * (ell + x1) / ell
    return R1, R2


def point_load_hogging_at_R2(P: float, x1: float) -> float:
    """Hogging moment at R2 from point load at distance x1 from R2 on overhang.
    M_hog = P * x1"""
    return P * x1


# ═══════════════════════════════════════════════════════════════════
# OVERHANGING BEAM — main analysis
# ═══════════════════════════════════════════════════════════════════


def analyse_overhanging(
    total_span_m: float,
    cant_span_m: float,
    w_uls_back: float,
    w_sls_short_back: float,
    w_sls_long_back: float,
    w_uls_cant: float,
    w_sls_short_cant: float,
    w_sls_long_cant: float,
    point_loads_back: list = None,
    point_loads_cant: list = None,
    w_G_back: float = 0.0,
    w_psi_lQ_back: float = 0.0,
    w_G_cant: float = 0.0,
    w_psi_lQ_cant: float = 0.0,
) -> BeamActions:
    """
    Analyse a beam overhanging one support.

    Geometry:
      R1 ---- ell ---- R2 ---- a ---- free end
      |<------ total_span = ell + a -------->|

    Loading (superposition of 4 cases):
      Case A: UDL w_back on back span (between R1 and R2)
      Case B: UDL w_cant on overhang (between R2 and free end)
      Case C: Point loads on overhang (position from R2)
      Case D: Point loads on back span (position from R1)
    """
    a = cant_span_m
    ell = total_span_m - a  # back span

    if ell <= 0:
        raise ValueError(f"Back span must be positive. total={total_span_m}, cant={a}")

    # ── Case A: UDL on back span only ──
    # Like a SS beam on span ell
    R1_udl_back = w_uls_back * ell / 2.0
    R2_udl_back = w_uls_back * ell / 2.0
    M_sag_udl_back = w_uls_back * ell ** 2 / 8.0

    # ── Case B: UDL on overhang only ──
    # Reference: Image 2 formulas
    R1_udl_cant = -w_uls_cant * a ** 2 / (2.0 * ell)       # negative = uplift at R1
    R2_udl_cant = w_uls_cant * a * (2.0 * ell + a) / (2.0 * ell)
    M_hog_udl_cant = w_uls_cant * a ** 2 / 2.0

    # ── Combined UDL reactions ──
    R1_total_udl = R1_udl_back + R1_udl_cant
    R2_total_udl = R2_udl_back + R2_udl_cant

    # ── Combined UDL sagging moment between supports ──
    # M(x) = R1_total * x - w_back * x^2 / 2  for x in [0, ell]
    # dM/dx = R1_total - w_back * x = 0  =>  x_max = R1_total / w_back
    if w_uls_back > 0:
        x_max_sag = R1_total_udl / w_uls_back
        if 0 < x_max_sag < ell:
            M_sag_combined_udl = R1_total_udl * x_max_sag - w_uls_back * x_max_sag ** 2 / 2.0
            M_sag_combined_udl = max(M_sag_combined_udl, 0.0)
        else:
            # No turning point in span — check endpoints
            M_sag_combined_udl = max(0.0, R1_total_udl * ell - w_uls_back * ell ** 2 / 2.0, 0.0)
    elif R1_total_udl > 0:
        # No back span UDL but positive R1 — linear M(x) = R1*x, max at x=ell
        M_sag_combined_udl = max(R1_total_udl * ell, 0.0)
    else:
        M_sag_combined_udl = 0.0

    # ── Point load contributions (superposition) ──
    M_sag_point = 0.0
    M_hog_point = 0.0
    R1_point = 0.0
    R2_point = 0.0

    if point_loads_back:
        for pl in point_loads_back:
            # pl.a_m is distance from R1, within [0, ell]
            M_sag_point += point_load_moment_backspan(pl.P_uls, pl.a_m, ell)
            r1, r2 = point_load_reactions_backspan(pl.P_uls, pl.a_m, ell)
            R1_point += r1
            R2_point += r2

    if point_loads_cant:
        for pl in point_loads_cant:
            # pl.a_m is distance from R2, within (0, a]
            M_hog_point += point_load_hogging_at_R2(pl.P_uls, pl.a_m)
            r1, r2 = point_load_reactions_overhang(pl.P_uls, pl.a_m, ell)
            R1_point += r1
            R2_point += r2

    # ── Totals ──
    R1_total = R1_total_udl + R1_point
    R2_total = R2_total_udl + R2_point

    # For sagging with point loads: sum UDL sagging + point load sagging (conservative)
    M_sagging_total = M_sag_combined_udl + M_sag_point
    M_hogging_total = M_hog_udl_cant + M_hog_point

    M_star = max(M_sagging_total, M_hogging_total)
    V_star = max(abs(R1_total), abs(R2_total))
    R_max = max(abs(R1_total), abs(R2_total))

    # UDL-only moment for breakdown
    M_udl = max(M_sag_combined_udl, M_hog_udl_cant)

    return BeamActions(
        span_m=total_span_m,
        w_uls=w_uls_back,
        w_sls_short=w_sls_short_back,
        w_sls_long=w_sls_long_back,
        M_star=M_star,
        V_star=V_star,
        R_max=R_max,
        beam_type=OVERHANGING,
        point_loads=list(point_loads_back or []) + list(point_loads_cant or []),
        M_udl=M_udl,
        M_point=M_sag_point + M_hog_point,
        V_udl=max(abs(R1_total_udl), abs(R2_total_udl)),
        R_left=R1_total,
        R_right=R2_total,
        # G/Q breakdown for long-term deflection
        w_G_back=w_G_back,
        w_psi_lQ_back=w_psi_lQ_back,
        w_G_cant=w_G_cant,
        w_psi_lQ_cant=w_psi_lQ_cant,
        # Overhanging-specific
        back_span_m=ell,
        cant_span_m=a,
        w_uls_cant=w_uls_cant,
        w_sls_short_cant=w_sls_short_cant,
        w_sls_long_cant=w_sls_long_cant,
        M_sagging=M_sagging_total,
        M_hogging=M_hogging_total,
        M_sagging_udl=M_sag_combined_udl,
        M_hogging_udl=M_hog_udl_cant,
        M_sagging_point=M_sag_point,
        M_hogging_point=M_hog_point,
        V_at_R2=abs(R2_total),
        point_loads_back=point_loads_back or [],
        point_loads_cant=point_loads_cant or [],
    )


# ═══════════════════════════════════════════════════════════════════
# DEFLECTION FUNCTIONS — Simply Supported
# ═══════════════════════════════════════════════════════════════════


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


def calc_total_deflection(w_kn_per_m: float, span_m: float,
                           E_mpa: float, Ix_mm4: float,
                           point_loads: list = None) -> float:
    """
    Total midspan deflection for simply supported beam.
    UDL deflection + sum of point load deflections (superposition).
    """
    delta_udl = calc_deflection(w_kn_per_m, span_m, E_mpa, Ix_mm4)
    delta_point = 0.0
    if point_loads:
        for pl in point_loads:
            delta_point += calc_deflection_point_load(
                pl.P_sls, pl.a_m, span_m, E_mpa, Ix_mm4
            )
    return delta_udl + delta_point


# ═══════════════════════════════════════════════════════════════════
# DEFLECTION FUNCTIONS — Overhanging Beam
# ═══════════════════════════════════════════════════════════════════


def calc_deflection_overhang_backspan_udl(w_kn_per_m: float, ell_m: float,
                                           E_mpa: float, Ix_mm4: float) -> float:
    """Midspan deflection between supports for UDL on back span only.
    Standard SS formula: delta = 5*w*ell^4 / (384*E*I)"""
    w = w_kn_per_m  # kN/m = N/mm
    L = ell_m * 1000.0
    if L <= 0 or E_mpa <= 0 or Ix_mm4 <= 0:
        return 0.0
    return 5.0 * w * L ** 4 / (384.0 * E_mpa * Ix_mm4)


def calc_deflection_overhang_cantudl_between(w_kn_per_m: float, a_m: float,
                                              ell_m: float, E_mpa: float,
                                              Ix_mm4: float) -> float:
    """Max deflection between supports due to UDL on overhang only.
    From reference: delta_max at x = ell/sqrt(3) = w*a^2*ell^2 / (18*sqrt(3)*E*I)
    This is an UPWARD deflection between supports (returned as positive value).
    """
    w = w_kn_per_m
    a = a_m * 1000.0
    L = ell_m * 1000.0
    if L <= 0 or E_mpa <= 0 or Ix_mm4 <= 0 or a <= 0:
        return 0.0
    return w * a ** 2 * L ** 2 / (18.0 * math.sqrt(3) * E_mpa * Ix_mm4)


def calc_deflection_overhang_cantudl_tip(w_kn_per_m: float, a_m: float,
                                          ell_m: float, E_mpa: float,
                                          Ix_mm4: float) -> float:
    """Free-end deflection due to UDL on overhang only.
    From reference: delta = w*a^3*(4*ell + 3*a) / (24*E*I)"""
    w = w_kn_per_m
    a = a_m * 1000.0
    L = ell_m * 1000.0
    if L <= 0 or E_mpa <= 0 or Ix_mm4 <= 0 or a <= 0:
        return 0.0
    return w * a ** 3 * (4.0 * L + 3.0 * a) / (24.0 * E_mpa * Ix_mm4)


def calc_deflection_overhang_pl_cant_between(P_kn: float, x1_m: float,
                                              ell_m: float, E_mpa: float,
                                              Ix_mm4: float) -> float:
    """Max deflection between supports from point load on overhang.
    From reference: delta_max at x=ell/sqrt(3) = P*x1*ell^2 / (9*sqrt(3)*E*I)
    This is an UPWARD deflection (returned as positive value)."""
    P = P_kn * 1000.0
    x1 = x1_m * 1000.0
    L = ell_m * 1000.0
    if L <= 0 or E_mpa <= 0 or Ix_mm4 <= 0 or x1 <= 0:
        return 0.0
    return P * x1 * L ** 2 / (9.0 * math.sqrt(3) * E_mpa * Ix_mm4)


def calc_deflection_overhang_pl_cant_tip(P_kn: float, x1_m: float,
                                          ell_m: float, E_mpa: float,
                                          Ix_mm4: float) -> float:
    """Free-end deflection from point load at x1 from R2 on overhang.
    For load at tip (x1=a): delta = P*a^2*(ell+a)/(3*E*I)
    General: delta = P*x1^2*(3*ell + x1)/(6*E*I) ... but the exact free-end
    formula is Pa^2(L+a)/(3EI) when load is at tip. For load not at tip,
    use the general overhang deflection at the free end:
    delta_tip = P*x1^2*(3*(ell+a-x1) ... conservative: P*x1^2*(ell+x1)/(3EI)
    """
    P = P_kn * 1000.0
    x1 = x1_m * 1000.0
    L = ell_m * 1000.0
    if L <= 0 or E_mpa <= 0 or Ix_mm4 <= 0 or x1 <= 0:
        return 0.0
    return P * x1 ** 2 * (L + x1) / (3.0 * E_mpa * Ix_mm4)


def calc_deflection_overhang_pl_back_between(P_kn: float, a_from_R1_m: float,
                                              ell_m: float, E_mpa: float,
                                              Ix_mm4: float) -> float:
    """Midspan deflection from point load on back span.
    Reuses the standard SS formula on span ell."""
    return calc_deflection_point_load(P_kn, a_from_R1_m, ell_m, E_mpa, Ix_mm4)


def calc_total_deflection_overhang_between(
    w_back: float, w_cant: float,
    ell_m: float, a_m: float,
    E_mpa: float, Ix_mm4: float,
    point_loads_back: list = None,
    point_loads_cant: list = None,
) -> float:
    """Total deflection between supports (at midspan of back span) by superposition.
    Back-span UDL causes downward deflection.
    Overhang UDL causes upward deflection between supports (partially cancels).
    Net = max(down - up, 0)."""
    d = 0.0
    # UDL on back span (downward)
    d += calc_deflection_overhang_backspan_udl(w_back, ell_m, E_mpa, Ix_mm4)
    # UDL on overhang (upward between supports)
    d -= calc_deflection_overhang_cantudl_between(w_cant, a_m, ell_m, E_mpa, Ix_mm4)

    # Point loads on back span (downward)
    if point_loads_back:
        for pl in point_loads_back:
            d += calc_deflection_overhang_pl_back_between(
                pl.P_sls, pl.a_m, ell_m, E_mpa, Ix_mm4
            )
    # Point loads on overhang (upward between supports)
    if point_loads_cant:
        for pl in point_loads_cant:
            d -= calc_deflection_overhang_pl_cant_between(
                pl.P_sls, pl.a_m, ell_m, E_mpa, Ix_mm4
            )

    return max(d, 0.0)  # deflection cannot be negative for this check


def calc_total_deflection_overhang_tip(
    w_cant: float, a_m: float, ell_m: float,
    E_mpa: float, Ix_mm4: float,
    point_loads_cant: list = None,
) -> float:
    """Total deflection at free end of overhang by superposition.
    Only overhang loads contribute to tip deflection (back-span loads
    cause upward tip movement which is conservative to ignore)."""
    d = 0.0
    # UDL on overhang
    d += calc_deflection_overhang_cantudl_tip(w_cant, a_m, ell_m, E_mpa, Ix_mm4)
    # Point loads on overhang
    if point_loads_cant:
        for pl in point_loads_cant:
            d += calc_deflection_overhang_pl_cant_tip(
                pl.P_sls, pl.a_m, ell_m, E_mpa, Ix_mm4
            )
    return d
