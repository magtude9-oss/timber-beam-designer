"""
Timber beam design checks per NZS AS 1720.1:2022.
Returns utilisation ratios and pass/fail for each check.

Now uses per-grade phi and k2 values from the grade dict.
"""

from dataclasses import dataclass
from .material_data import get_k8, K4_DRY, K5_DEFAULT
from .beam_analysis import calc_deflection


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
                  k1: float, k12: float = 1.0) -> CheckResult:
    """
    Bending check: phi * k1 * k4 * k5 * k8 * k12 * fb * Zx >= M*
    M_star in kNm, capacities computed in kNm.
    """
    phi = grade["phi"]
    k8 = get_k8(section.d)
    fb = grade["fb"]
    Zx = section.Zx  # mm^3
    # Capacity in Nmm then convert to kNm
    phi_Mx = phi * k1 * K4_DRY * K5_DEFAULT * k8 * k12 * fb * Zx  # Nmm
    phi_Mx_knm = phi_Mx / 1e6  # kNm
    M_star = M_star_knm
    util = (M_star / phi_Mx_knm * 100) if phi_Mx_knm > 0 else 999.0
    details = (
        f"phi={phi}, k1={k1}, k4={K4_DRY}, k5={K5_DEFAULT}, "
        f"k8={k8:.3f}, k12={k12}, f'b={fb} MPa, "
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
                k1: float) -> CheckResult:
    """
    Shear check: phi * k1 * k4 * k5 * fs * (2/3 * b * d) >= V*
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
            details="Shear data not available for this grade — MANUAL CHECK REQUIRED",
        )
    As = section.shear_area()  # mm^2
    phi_Vs = phi * k1 * K4_DRY * K5_DEFAULT * fs * As / 1e3  # kN
    util = (V_star_kn / phi_Vs * 100) if phi_Vs > 0 else 999.0
    details = (
        f"phi={phi}, k1={k1}, k4={K4_DRY}, k5={K5_DEFAULT}, "
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
                  k3: float = 1.0) -> CheckResult:
    """
    Bearing check: phi * k1 * k3 * fp * (lb * b) >= R_max
    R_max in kN, bearing_length in mm.
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
            details="Bearing data not available for this grade — MANUAL CHECK REQUIRED",
        )
    Ab = section.bearing_area(bearing_length_mm)  # mm^2
    phi_Np = phi * k1 * k3 * K4_DRY * K5_DEFAULT * fp * Ab / 1e3  # kN
    util = (R_max_kn / phi_Np * 100) if phi_Np > 0 else 999.0
    details = (
        f"phi={phi}, k1={k1}, k3={k3}, k4={K4_DRY}, k5={K5_DEFAULT}, "
        f"f'p={fp} MPa, Ab={bearing_length_mm}*{section.b}={Ab:.0f} mm^2"
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
                     deflection_limit: int = 300) -> tuple:
    """
    Deflection checks per AS/NZS 1170.0 Table C1 and NZS AS 1720.1:2022.

    Two independent checks (both must pass):
      1) Short-term: delta = 5wL^4/(384EI) where w = G + 0.7Q, limit = L/defl_limit
      2) Long-term:  delta = k2 * 5wL^4/(384EI) where w = G + 0.4Q, limit = L/defl_limit

    k2 is the creep/duration-of-load factor for stiffness (per-grade):
      - 2.0 for sawn timber / LVL / engineered
      - 1.5 for glulam (Prolam)

    Returns a tuple of two CheckResult objects: (short_term, long_term).
    """
    E = grade["E"]
    k2 = grade["k2"]
    Ix = section.Ix

    # Short-term: elastic deflection under G + 0.7Q (no creep, k2=1.0)
    delta_short = calc_deflection(w_sls_short, span_m, E, Ix)

    # Long-term: elastic deflection under G + 0.4Q multiplied by k2 (creep)
    delta_long_elastic = calc_deflection(w_sls_long, span_m, E, Ix)
    delta_long = k2 * delta_long_elastic

    allowable = span_m * 1000.0 / deflection_limit

    # Short-term result
    util_st = (delta_short / allowable * 100) if allowable > 0 else 999.0
    details_st = (
        f"E={E:.0f} MPa, Ix={Ix/1e6:.1f}x10^6 mm^4, "
        f"w_sls_short={w_sls_short:.3f} kN/m (G+0.7Q), "
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
        f"w_sls_long={w_sls_long:.3f} kN/m (G+0.4Q), "
        f"delta_elastic={delta_long_elastic:.1f} mm, "
        f"delta_long=k2*delta={delta_long:.1f} mm, "
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


def run_all_checks(beam_actions, section, grade: dict,
                   k1: float, bearing_length_mm: float = 50.0,
                   k12: float = 1.0, k3: float = 1.0,
                   deflection_limit: int = 300) -> list[CheckResult]:
    """Run all design checks and return results (5 checks: bending, shear, bearing, defl ST, defl LT)."""
    defl_st, defl_lt = check_deflection(
        beam_actions.span_m, section, grade,
        beam_actions.w_sls_short, beam_actions.w_sls_long,
        deflection_limit,
    )
    return [
        check_bending(beam_actions.M_star, section, grade, k1, k12),
        check_shear(beam_actions.V_star, section, grade, k1),
        check_bearing(beam_actions.R_max, section, grade, k1,
                      bearing_length_mm, k3),
        defl_st,
        defl_lt,
    ]
