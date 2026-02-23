"""
Load calculations per AS/NZS 1170.0.
Structured loading panel with multiple load types.
Each load type has its own tributary width(s).
Converts area loads (kPa) to line loads (kN/m).
Includes beam self-weight as additional dead load.
"""

from dataclasses import dataclass, field

# Gravitational acceleration (m/s^2)
GRAVITY = 9.81


# Fixed live loads per load type (kPa) — read-only in the UI.
# "trib_mode": "single" for Roof/Walls, "dual" for floors (Mid Floor/Ground Floor)
# Dual = left + right tributary widths (applicable to floor loads only).
LOAD_TYPES = {
    "Roof": {"live_kpa": 0.25, "trib_mode": "single"},
    "Mid Floor": {"live_kpa": 1.5, "trib_mode": "dual"},
    "Ground Floor": {"live_kpa": 1.5, "trib_mode": "dual"},
    "First Floor Wall": {"live_kpa": 0.0, "trib_mode": "single"},
    "Ground Floor Wall": {"live_kpa": 0.0, "trib_mode": "single"},
}


@dataclass
class LoadEntry:
    """A single load type entry with dead load, live load, and tributary width(s)."""
    load_type: str
    dead_kpa: float
    live_kpa: float  # fixed per type
    trib_width_m: float = 0.6  # total tributary width (single or left+right sum)

    @property
    def total_kpa(self) -> float:
        """Total pressure load for this type (kPa)."""
        return self.dead_kpa + self.live_kpa

    @property
    def udl_kn_per_m(self) -> float:
        """UDL contribution from this load type (kN/m)."""
        return self.total_kpa * self.trib_width_m

    @property
    def G_line(self) -> float:
        """Dead line load from this type (kN/m)."""
        return self.dead_kpa * self.trib_width_m

    @property
    def Q_line(self) -> float:
        """Live line load from this type (kN/m)."""
        return self.live_kpa * self.trib_width_m


@dataclass
class StructuredLoads:
    """Collection of active load entries — no global tributary width."""
    entries: list[LoadEntry] = field(default_factory=list)

    @property
    def total_G(self) -> float:
        """Total dead line load (kN/m) — sum of all entries."""
        return sum(e.G_line for e in self.entries)

    @property
    def total_Q(self) -> float:
        """Total live line load (kN/m) — sum of all entries."""
        return sum(e.Q_line for e in self.entries)

    @property
    def total_udl(self) -> float:
        """Total UDL (kN/m)."""
        return self.total_G + self.total_Q


@dataclass
class LineLoads:
    """Line loads in kN/m."""
    G: float  # dead load (kN/m)
    Q: float  # live load (kN/m)

    @property
    def w_uls(self) -> float:
        """ULS design load = max(1.35G, 1.2G + 1.5Q) in kN/m."""
        return max(1.35 * self.G, 1.2 * self.G + 1.5 * self.Q)

    @property
    def w_sls_short(self) -> float:
        """SLS short-term load = G + 0.7Q in kN/m."""
        return self.G + 0.7 * self.Q

    @property
    def w_sls_long(self) -> float:
        """SLS long-term load = G + 0.4Q in kN/m."""
        return self.G + 0.4 * self.Q

    @property
    def uls_combo_label(self) -> str:
        """Return which ULS combination governs."""
        if 1.35 * self.G >= 1.2 * self.G + 1.5 * self.Q:
            return "1.35G"
        return "1.2G + 1.5Q"


@dataclass
class PointLoad:
    """A single concentrated point load on the beam.
    User provides pre-factored ULS and SLS values directly (not split into G/Q).
    """
    P_uls: float   # ULS point load (kN)
    P_sls: float   # SLS point load (kN)
    a_m: float     # distance from left support (m)

    def calc_b(self, span_m: float) -> float:
        """Distance from right support = L - a."""
        return span_m - self.a_m

    def validate(self, span_m: float) -> bool:
        """Check that point load position is within the span."""
        return 0.0 < self.a_m < span_m


@dataclass
class PointLoadOverhang(PointLoad):
    """Point load on the cantilever overhang of an overhanging beam.
    a_m = distance from R2 support (interior support), NOT from R1.
    """

    def calc_b(self, cant_span_m: float) -> float:
        """Distance from free end = cantilever span - a."""
        return cant_span_m - self.a_m

    def validate(self, cant_span_m: float) -> bool:
        """Check that point load position is within the overhang."""
        return 0.0 < self.a_m <= cant_span_m


def calc_self_weight(b_mm: float, d_mm: float, density_kg_m3: float) -> float:
    """
    Beam self-weight as a line load (kN/m).
    SW = density * b * d * g
    b, d in mm -> convert to m.  density in kg/m^3.  g = 9.81 m/s^2.
    Result in kN/m.
    """
    b_m = b_mm / 1000.0
    d_m = d_mm / 1000.0
    return density_kg_m3 * b_m * d_m * GRAVITY / 1000.0  # N/m -> kN/m


def compute_line_loads(structured: StructuredLoads,
                       self_weight_kn_m: float = 0.0) -> LineLoads:
    """Sum individual load type contributions into total line loads,
    plus beam self-weight added to G (dead load)."""
    return LineLoads(
        G=structured.total_G + self_weight_kn_m,
        Q=structured.total_Q,
    )
