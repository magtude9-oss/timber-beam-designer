"""
Timber beam design checks per NZS AS 1720.1:2022.
Returns utilisation ratios and pass/fail for each check.

Capacity equations per Section 3:
  Bending:  Md  = phi * k1 * k4 * k6 * k9 * k12 * f'b * Z      [Eq. 3.2(2)]
  Shear:    Vd  = phi * k1 * k4 * k6 * f's * As                  [Eq. 3.2(14)]
  Bearing:  Nd,p = phi * k1 * k4 * k6 * k7 * f'p * Ap            [Eq. 3.2(16)]

Uses per-grade phi and k2 values from the grade dict.
"""

from dataclasses import dataclass
from .material_data import K4_DRY, K6_DEFAULT
from .beam_analysis import (
    calc_deflection, calc_total_deflection,
    calc_total_deflection_overhang_between,
    calc_total_deflection_overhang_tip,
    SIMPLY_SUPPORTED, OVERHANGING,
)


@dataclass
class CheckResult:
    """Result of a single design check."""
    name: str
    demand: float
    capacity: float
    utilisation: float  # demand/capacity as percentage
    passed: bool
    unit: str = ""
    details: str = ""


def check_bending(M_star_knm: float, section, grade: dict,
                  k1: float, k6: float = 1.0,
                  k9: float = 1.0, k12: float = 1.0) -> CheckResult:
    """
    Bending check per Clause 3.2.1.1, Eq. 3.2(2):
      Md = phi * k1 * k4 * k6 * k9 * k12 * f'b * Z >= M*
    M_star in kNm, capacities computed in kNm.
    """
    phi = grade["phi"]
    fb = grade["fb"]
    Zx = section.Zx  # mm^3
    # Capacity in Nmm then convert to kNm
    phi_Mx = phi * k1 * K4_DRY * k6 * k9 * k12 * fb * Zx  # Nmm
    phi_Mx_knm = phi_Mx / 1e6  # kNm
    M_star = M_star_knm
    util = (M_star / phi_Mx_knm * 100) if phi_Mx_knm > 0 else 999.0
    details = (
        f"phi={phi}, k1={k1}, k4={K4_DRY}, k6={k6}, "
        f"k9={k9}, k12={k12}, f'b={fb} MPa, "
        f"Zx={Zx/1e3:.1f}x10^3 mm^3"
    )
    return CheckResult(
        name="Bending",
        demand=M_star,
        capacity=phi_Mx_knm,
        utilisation=util,
        passed=util <= 100.0,
        unit="kNm",
        details=details,
    )


def check_shear(V_star_kn: float, section, grade: dict,
                k1: float, k6: float = 1.0) -> CheckResult:
    """
    Shear check per Clause 3.2.5, Eq. 3.2(14):
      Vd = phi * k1 * k4 * k6 * f's * As >= V*
    V_star in kN.
    """
    phi = grade["phi"]
    fs = grade["fs"]
    if fs is None:
        return CheckResult(
            name="Shear",
            demand=V_star_kn,
            capacity=0.0,
            utilisation=999.0,
            passed=False,
            unit="kN",
            details="Shear data not available for this grade -- MANUAL CHECK REQUIRED",
        )
    As = section.shear_area()  # mm^2
    phi_Vs = phi * k1 * K4_DRY * k6 * fs * As / 1e3  # kN
    util = (V_star_kn / phi_Vs * 100) if phi_Vs > 0 else 999.0
    details = (
        f"phi={phi}, k1={k1}, k4={K4_DRY}, k6={k6}, "
        f"f's={fs} MPa, As=2/3*{section.b}*{section.d}={As:.0f} mm^2"
    )
    return CheckResult(
        name="Shear",
        demand=V_star_kn,
        capacity=phi_Vs,
        utilisation=util,
        passed=util <= 100.0,
        unit="kN",
        details=details,
    )


def check_bearing(R_max_kn: float, section, grade: dict,
                  k1: float, bearing_length_mm: float,
                  k6: float = 1.0, k7: float = 1.0) -> CheckResult:
    """
    Bearing check per Clause 3.2.6.1, Eq. 3.2(16):
      Nd,p = phi * k1 * k4 * k6 * k7 * f'p * Ap >= N*p
    R_max in kN, bearing_length in mm.
    k7 = bearing length factor (Table 2.6). k7=1.0 for end bearings.
    """
    phi = grade["phi"]
    fp = grade["fp"]
    if fp is None:
        return CheckResult(
            name="Bearing",
            demand=R_max_kn,
            capacity=0.0,
            utilisation=999.0,
            passed=False,
            unit="kN",
            details="Bearing data not available for this grade -- MANUAL CHECK REQUIRED",
        )
    Ap = section.bearing_area(bearing_length_mm)  # mm^2
    phi_Np = phi * k1 * K4_DRY * k6 * k7 * fp * Ap / 1e3  # kN
    util = (R_max_kn / phi_Np * 100) if phi_Np > 0 else 999.0
    details = (
        f"phi={phi}, k1={k1}, k4={K4_DRY}, k6={k6}, k7={k7}, "
        f"f'p={fp} MPa, Ap={bearing_length_mm}*{section.b}={Ap:.0f} mm^2"
    )
    return CheckResult(
        name="Bearing",
        demand=R_max_kn,
        capacity=phi_Np,
        utilisation=util,
        passed=util <= 100.0,
        unit="kN",
        details=details,
    )


def check_deflection(span_m: float, section, grade: dict,
                     w_sls_short: float, w_sls_long: float,
                     deflection_limit: int = 300,
                     point_loads: list = None,
                     beam_type: str = SIMPLY_SUPPORTED,
                     w_G: float = 0.0, w_psi_lQ: float = 0.0) -> tuple:
    """
    Deflection checks for simply supported beams.
    Returns a tuple of two CheckResult objects: (short_term, long_term).

    Long-term deflection per NZS AS 1720.1 Cl 2.4.5.2:
      delta_LT = k2 * delta(G) + delta(psi_l * Q)
    k2 (creep factor) applies ONLY to the permanent (dead) load deflection.
    """
    E = grade["E"]
    k2 = grade["k2"]
    Ix = section.Ix

    _calc_total = calc_total_deflection

    # Short-term: elastic deflection under G + 0.7Q + point loads (no creep)
    delta_short = _calc_total(w_sls_short, span_m, E, Ix,
                               point_loads=point_loads)

    # Long-term per Cl 2.4.5.2: k2 * delta(G) + delta(psi_l * Q)
    # w_G = dead load UDL, w_psi_lQ = 0.4Q (long-term live)
    if w_G > 0 or w_psi_lQ > 0:
        # Correct method: separate G and Q components
        delta_G = _calc_total(w_G, span_m, E, Ix, point_loads=None)
        delta_psiQ = _calc_total(w_psi_lQ, span_m, E, Ix, point_loads=point_loads)
        delta_long = k2 * delta_G + delta_psiQ
    else:
        # Fallback if G/Q breakdown not available (backward compat)
        delta_long_elastic = _calc_total(w_sls_long, span_m, E, Ix,
                                          point_loads=point_loads)
        delta_long = k2 * delta_long_elastic

    allowable = span_m * 1000.0 / deflection_limit

    pl_note = ""
    if point_loads:
        pl_note = f" + {len(point_loads)} point load(s)"

    # Short-term result
    util_st = (delta_short / allowable * 100) if allowable > 0 else 999.0
    details_st = (
        f"E={E:.0f} MPa, Ix={Ix/1e6:.1f}x10^6 mm^4, "
        f"w_sls_short={w_sls_short:.3f} kN/m (G+0.7Q){pl_note}, "
        f"delta={delta_short:.1f} mm, "
        f"allow=L/{deflection_limit}={allowable:.1f} mm"
    )
    result_st = CheckResult(
        name="Deflection (short-term)",
        demand=delta_short,
        capacity=allowable,
        utilisation=util_st,
        passed=util_st <= 100.0,
        unit="mm",
        details=details_st,
    )

    # Long-term result
    util_lt = (delta_long / allowable * 100) if allowable > 0 else 999.0
    details_lt = (
        f"E={E:.0f} MPa, Ix={Ix/1e6:.1f}x10^6 mm^4, "
        f"k2={k2}, "
        f"delta_LT = k2*delta(G) + delta(0.4Q){pl_note}, "
        f"delta_long={delta_long:.1f} mm, "
        f"allow=L/{deflection_limit}={allowable:.1f} mm"
    )
    result_lt = CheckResult(
        name="Deflection (long-term)",
        demand=delta_long,
        capacity=allowable,
        utilisation=util_lt,
        passed=util_lt <= 100.0,
        unit="mm",
        details=details_lt,
    )

    return (result_st, result_lt)


# ═══════════════════════════════════════════════════════════════════
# OVERHANGING BEAM — specialised checks
# ═══════════════════════════════════════════════════════════════════


def check_deflection_overhanging(beam_actions, section, grade: dict,
                                  deflection_limit: int = 300,
                                  deflection_limit_tip: int = 150) -> tuple:
    """
    Deflection checks for overhanging beam.
    Returns 4 CheckResult objects:
      (back_span_short, back_span_long, tip_short, tip_long)

    Long-term deflection per NZS AS 1720.1 Cl 2.4.5.2:
      delta_LT = k2 * delta(G) + delta(psi_l * Q)
    k2 (creep factor) applies ONLY to the permanent (dead) load deflection.

    Back span: allowable = ell * 1000 / deflection_limit
    Overhang tip: allowable = a * 1000 / deflection_limit_tip
    """
    E = grade["E"]
    k2 = grade["k2"]
    Ix = section.Ix
    ell = beam_actions.back_span_m
    a = beam_actions.cant_span_m

    pl_back = beam_actions.point_loads_back or None
    pl_cant = beam_actions.point_loads_cant or None

    # G/Q breakdown for correct long-term calc
    w_G_back = beam_actions.w_G_back
    w_psi_lQ_back = beam_actions.w_psi_lQ_back
    w_G_cant = beam_actions.w_G_cant
    w_psi_lQ_cant = beam_actions.w_psi_lQ_cant

    # ── Back span deflection ──
    allowable_back = ell * 1000.0 / deflection_limit

    # Short-term (G+0.7Q)
    d_back_short = calc_total_deflection_overhang_between(
        beam_actions.w_sls_short, beam_actions.w_sls_short_cant,
        ell, a, E, Ix, pl_back, pl_cant
    )
    util_bs = (d_back_short / allowable_back * 100) if allowable_back > 0 else 999.0
    result_back_short = CheckResult(
        name="Defl. back span (ST)",
        demand=d_back_short,
        capacity=allowable_back,
        utilisation=util_bs,
        passed=util_bs <= 100.0,
        unit="mm",
        details=f"Between supports, short-term. allow=ell/{deflection_limit}={allowable_back:.1f}mm"
    )

    # Long-term: k2 * delta(G) + delta(0.4Q)
    if w_G_back > 0 or w_psi_lQ_back > 0 or w_G_cant > 0 or w_psi_lQ_cant > 0:
        # Correct method: separate G and psi_l*Q components
        d_back_G = calc_total_deflection_overhang_between(
            w_G_back, w_G_cant, ell, a, E, Ix, None, None
        )
        d_back_psiQ = calc_total_deflection_overhang_between(
            w_psi_lQ_back, w_psi_lQ_cant, ell, a, E, Ix, pl_back, pl_cant
        )
        d_back_long = k2 * d_back_G + d_back_psiQ
    else:
        # Fallback if G/Q breakdown not available
        d_back_long_elastic = calc_total_deflection_overhang_between(
            beam_actions.w_sls_long, beam_actions.w_sls_long_cant,
            ell, a, E, Ix, pl_back, pl_cant
        )
        d_back_long = k2 * d_back_long_elastic

    util_bl = (d_back_long / allowable_back * 100) if allowable_back > 0 else 999.0
    result_back_long = CheckResult(
        name="Defl. back span (LT)",
        demand=d_back_long,
        capacity=allowable_back,
        utilisation=util_bl,
        passed=util_bl <= 100.0,
        unit="mm",
        details=f"Between supports, LT: k2*d(G)+d(0.4Q), k2={k2}. allow=ell/{deflection_limit}={allowable_back:.1f}mm"
    )

    # ── Overhang tip deflection ──
    allowable_tip = a * 1000.0 / deflection_limit_tip

    # Short-term
    d_tip_short = calc_total_deflection_overhang_tip(
        beam_actions.w_sls_short_cant, a, ell, E, Ix, pl_cant
    )
    util_ts = (d_tip_short / allowable_tip * 100) if allowable_tip > 0 else 999.0
    result_tip_short = CheckResult(
        name="Defl. overhang (ST)",
        demand=d_tip_short,
        capacity=allowable_tip,
        utilisation=util_ts,
        passed=util_ts <= 100.0,
        unit="mm",
        details=f"At free end, short-term. allow=a/{deflection_limit_tip}={allowable_tip:.1f}mm"
    )

    # Long-term at tip: k2 * delta_tip(G) + delta_tip(0.4Q)
    if w_G_cant > 0 or w_psi_lQ_cant > 0:
        d_tip_G = calc_total_deflection_overhang_tip(
            w_G_cant, a, ell, E, Ix, None
        )
        d_tip_psiQ = calc_total_deflection_overhang_tip(
            w_psi_lQ_cant, a, ell, E, Ix, pl_cant
        )
        d_tip_long = k2 * d_tip_G + d_tip_psiQ
    else:
        d_tip_long_elastic = calc_total_deflection_overhang_tip(
            beam_actions.w_sls_long_cant, a, ell, E, Ix, pl_cant
        )
        d_tip_long = k2 * d_tip_long_elastic

    util_tl = (d_tip_long / allowable_tip * 100) if allowable_tip > 0 else 999.0
    result_tip_long = CheckResult(
        name="Defl. overhang (LT)",
        demand=d_tip_long,
        capacity=allowable_tip,
        utilisation=util_tl,
        passed=util_tl <= 100.0,
        unit="mm",
        details=f"At free end, LT: k2*d(G)+d(0.4Q), k2={k2}. allow=a/{deflection_limit_tip}={allowable_tip:.1f}mm"
    )

    return (result_back_short, result_back_long, result_tip_short, result_tip_long)


def check_bearing_overhanging(beam_actions, section, grade: dict,
                               k1: float, bearing_length_mm: float,
                               k6: float = 1.0, k7: float = 1.0) -> tuple:
    """
    Bearing check for both supports of an overhanging beam.
    Returns (result_R1, result_R2).
    If R1 is in uplift (negative), bearing at R1 is not critical.
    """
    R1 = beam_actions.R_left
    R2 = beam_actions.R_right

    # R2 bearing check (always applicable)
    result_R2 = check_bearing(abs(R2), section, grade, k1, bearing_length_mm,
                               k6=k6, k7=k7)
    result_R2.name = "Bearing (R2)"

    # R1 bearing check
    if R1 < 0:
        # R1 is in uplift — no bearing check needed, but warn about hold-down
        phi = grade["phi"]
        fp = grade.get("fp")
        Ap = section.bearing_area(bearing_length_mm)
        cap = 0.0
        if fp:
            cap = phi * k1 * K4_DRY * k6 * k7 * fp * Ap / 1e3
        result_R1 = CheckResult(
            name="Bearing (R1)",
            demand=0.0,
            capacity=cap,
            utilisation=0.0,
            passed=True,
            unit="kN",
            details=f"R1 is in UPLIFT ({R1:.2f} kN) -- hold-down connection required"
        )
    else:
        result_R1 = check_bearing(abs(R1), section, grade, k1, bearing_length_mm,
                                   k6=k6, k7=k7)
        result_R1.name = "Bearing (R1)"

    return (result_R1, result_R2)


def run_all_checks(beam_actions, section, grade: dict,
                   k1: float, bearing_length_mm: float = 50.0,
                   k6: float = 1.0, k7: float = 1.0,
                   k9: float = 1.0, k12: float = 1.0,
                   deflection_limit: int = 300,
                   deflection_limit_tip: int = 150) -> list:
    """Run all design checks and return results.
    SS: 5 checks. Overhanging: 9 checks."""
    beam_type = getattr(beam_actions, 'beam_type', SIMPLY_SUPPORTED)

    if beam_type == OVERHANGING:
        # Bending: check both sagging and hogging
        result_sag = check_bending(beam_actions.M_sagging, section, grade, k1,
                                    k6=k6, k9=k9, k12=k12)
        result_sag.name = "Bending (sagging)"

        result_hog = check_bending(beam_actions.M_hogging, section, grade, k1,
                                    k6=k6, k9=k9, k12=k12)
        result_hog.name = "Bending (hogging)"

        # Shear
        result_shear = check_shear(beam_actions.V_star, section, grade, k1, k6=k6)

        # Bearing: both supports
        result_R1, result_R2 = check_bearing_overhanging(
            beam_actions, section, grade, k1, bearing_length_mm, k6=k6, k7=k7
        )

        # Deflection: 4 checks
        d_bs, d_bl, d_ts, d_tl = check_deflection_overhanging(
            beam_actions, section, grade, deflection_limit, deflection_limit_tip
        )

        return [result_sag, result_hog, result_shear, result_R1, result_R2,
                d_bs, d_bl, d_ts, d_tl]

    else:
        # Simply Supported — 5 checks
        point_loads = getattr(beam_actions, 'point_loads', None) or None
        defl_st, defl_lt = check_deflection(
            beam_actions.span_m, section, grade,
            beam_actions.w_sls_short, beam_actions.w_sls_long,
            deflection_limit,
            point_loads=point_loads,
            beam_type=beam_type,
            w_G=getattr(beam_actions, 'w_G_back', 0.0),
            w_psi_lQ=getattr(beam_actions, 'w_psi_lQ_back', 0.0),
        )
        return [
            check_bending(beam_actions.M_star, section, grade, k1,
                          k6=k6, k9=k9, k12=k12),
            check_shear(beam_actions.V_star, section, grade, k1, k6=k6),
            check_bearing(beam_actions.R_max, section, grade, k1,
                          bearing_length_mm, k6=k6, k7=k7),
            defl_st,
            defl_lt,
        ]
