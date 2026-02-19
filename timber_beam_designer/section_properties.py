"""
Standard NZ timber section sizes and section property calculations.
Dimensions in mm.
"""

STANDARD_SIZES = [
    (45, 90), (45, 140), (45, 190), (45, 240), (45, 290),
    (65, 90), (65, 140), (65, 190), (65, 240), (65, 290),
    (90, 90), (90, 140), (90, 190), (90, 240), (90, 290),
    (140, 140), (140, 190), (140, 240), (140, 290),
    (190, 190), (190, 240), (190, 290),
]


class TimberSection:
    """Rectangular timber section with calculated properties."""

    def __init__(self, width_mm: float, depth_mm: float):
        if width_mm <= 0 or depth_mm <= 0:
            raise ValueError("Section dimensions must be positive")
        self.b = width_mm
        self.d = depth_mm

    @property
    def area(self) -> float:
        """Cross-sectional area (mm^2)."""
        return self.b * self.d

    @property
    def Zx(self) -> float:
        """Section modulus about major axis (mm^3). Zx = b*d^2/6."""
        return self.b * self.d ** 2 / 6.0

    @property
    def Ix(self) -> float:
        """Second moment of area about major axis (mm^4). Ix = b*d^3/12."""
        return self.b * self.d ** 3 / 12.0

    def shear_area(self) -> float:
        """Effective shear area = 2/3 * b * d (mm^2)."""
        return 2.0 / 3.0 * self.b * self.d

    def bearing_area(self, bearing_length_mm: float) -> float:
        """Bearing area = bearing_length * width (mm^2)."""
        return bearing_length_mm * self.b

    def __repr__(self):
        return f"TimberSection({self.b:.0f}x{self.d:.0f})"

    def label(self) -> str:
        return f"{self.b:.0f}x{self.d:.0f}"
