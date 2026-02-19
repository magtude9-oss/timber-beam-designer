"""
Timber Beam Designer - Streamlit Web GUI.
Simply supported timber beam design to NZS AS 1720.1:2022.

Run with: streamlit run run.py
"""

import streamlit as st
import tempfile
import os
from datetime import date

from .material_data import (
    TIMBER_GRADES, K1_FACTORS, get_grade, get_k8,
    K4_DRY, K5_DEFAULT, get_dropdown_grades,
)
from .section_properties import TimberSection
from .loads import LOAD_TYPES, LoadEntry, StructuredLoads, compute_line_loads, calc_self_weight
from .beam_analysis import analyse_simply_supported
from .design_checks import run_all_checks
from .report_generator import generate_report


def main():
    st.set_page_config(
        page_title="Timber Beam Designer",
        page_icon="\U0001FAB5",
        layout="wide",
    )

    st.title("Timber Beam Designer")
    st.caption("NZS AS 1720.1:2022 -- Simply Supported Beam")

    # ── Sidebar: All Inputs ──────────────────────────────────────────
    with st.sidebar:
        st.header("Design Inputs")

        # ══════════════════════════════════════════════════════════════
        # CHANGE 3: Expanded Project Information
        # ══════════════════════════════════════════════════════════════
        with st.expander("Project Information", expanded=True):
            project_name = st.text_input("Project Name", value="")
            project_number = st.text_input("Project Number", value="")
            project_address = st.text_input("Project Address", value="")
            beam_id = st.text_input("Beam ID", value="")
            designer = st.text_input("Designer Name", value="")
            design_date = st.date_input("Date", value=date.today())

        st.divider()

        # ── Timber grade ──
        grade_name = st.selectbox(
            "Timber Grade",
            options=get_dropdown_grades(),
            index=0,  # default SG8
        )
        grade = get_grade(grade_name)

        # Show grade properties
        with st.expander("Grade Properties", expanded=False):
            st.write(f"**f'b** = {grade['fb']} MPa")
            st.write(f"**f's** = {grade['fs']} MPa" if grade['fs'] else "**f's** = N/A")
            st.write(f"**f'p** = {grade['fp']} MPa" if grade['fp'] else "**f'p** = N/A")
            st.write(f"**E** = {grade['E']:.0f} MPa")
            st.write(f"**Density** = {grade.get('density', 500):.0f} kg/m\u00B3")
            st.write(f"**phi** = {grade['phi']}")
            st.write(f"**k2** = {grade['k2']}")

        st.divider()

        # ══════════════════════════════════════════════════════════════
        # CHANGE 2: Plain numeric b/d inputs only
        # ══════════════════════════════════════════════════════════════
        st.subheader("Beam Section")
        col_b, col_d = st.columns(2)
        with col_b:
            beam_b = st.number_input("Breadth b (mm)", min_value=10.0, value=90.0, step=5.0)
        with col_d:
            beam_d = st.number_input("Depth d (mm)", min_value=10.0, value=240.0, step=5.0)
        section = TimberSection(beam_b, beam_d)

        st.divider()

        # ── Span ──
        span_m = st.number_input("Span (m)", min_value=0.1, value=4.0, step=0.1)

        st.divider()

        # ══════════════════════════════════════════════════════════════
        # CHANGE 1: Individual tributary widths per load type
        # ══════════════════════════════════════════════════════════════
        st.subheader("Loading")
        st.caption("Select applicable load types. Dead loads are user input; "
                    "live loads are fixed per AS/NZS 1170.0. "
                    "Each load type has its own tributary width.")

        active_entries = []

        for lt_name, lt_data in LOAD_TYPES.items():
            checked = st.checkbox(lt_name, value=(lt_name == "Roof"))
            if checked:
                live_val = lt_data["live_kpa"]
                trib_mode = lt_data["trib_mode"]

                # Dead and live load row
                col_dead, col_live = st.columns(2)
                with col_dead:
                    dead_val = st.number_input(
                        f"G - {lt_name} (kPa)",
                        min_value=0.0, value=0.5, step=0.1,
                        key=f"dead_{lt_name}",
                    )
                with col_live:
                    if live_val > 0:
                        st.text_input(
                            f"Q - {lt_name} (kPa)",
                            value=f"{live_val:.2f}",
                            disabled=True,
                            key=f"live_{lt_name}",
                        )
                    else:
                        st.text_input(
                            f"Q - {lt_name} (kPa)",
                            value="0 (no live)",
                            disabled=True,
                            key=f"live_{lt_name}",
                        )

                # Tributary width row
                if trib_mode == "single":
                    trib_total = st.number_input(
                        f"Tributary Width - {lt_name} (m)",
                        min_value=0.0, value=0.6, step=0.1,
                        key=f"trib_{lt_name}",
                    )
                else:
                    # Dual: left + right
                    tcol_l, tcol_r = st.columns(2)
                    with tcol_l:
                        trib_left = st.number_input(
                            f"Trib. Left - {lt_name} (m)",
                            min_value=0.0, value=0.0, step=0.1,
                            key=f"trib_left_{lt_name}",
                        )
                    with tcol_r:
                        trib_right = st.number_input(
                            f"Trib. Right - {lt_name} (m)",
                            min_value=0.0, value=0.0, step=0.1,
                            key=f"trib_right_{lt_name}",
                        )
                    trib_total = trib_left + trib_right

                active_entries.append(LoadEntry(
                    load_type=lt_name,
                    dead_kpa=dead_val,
                    live_kpa=live_val,
                    trib_width_m=trib_total,
                ))

                st.caption(f"  -> {lt_name} trib. width = {trib_total:.2f} m, "
                           f"UDL = {(dead_val + live_val) * trib_total:.3f} kN/m")

        st.divider()

        # Build structured loads
        structured = StructuredLoads(entries=active_entries)

        # Beam self-weight (automatic)
        density = grade.get("density", 500.0)
        sw_kn_m = calc_self_weight(beam_b, beam_d, density)
        st.caption(f"Beam self-weight: {sw_kn_m:.3f} kN/m "
                   f"({beam_b:.0f}x{beam_d:.0f} mm, "
                   f"{density:.0f} kg/m\u00B3)")

        # Show totals
        if active_entries:
            total_G_with_sw = structured.total_G + sw_kn_m
            st.info(
                f"**G (applied):** {structured.total_G:.3f} kN/m  |  "
                f"**G (self-wt):** {sw_kn_m:.3f} kN/m  |  "
                f"**G (total):** {total_G_with_sw:.3f} kN/m\n\n"
                f"**Total Q:** {structured.total_Q:.3f} kN/m  |  "
                f"**Total UDL:** {total_G_with_sw + structured.total_Q:.3f} kN/m"
            )
        else:
            st.warning("No load types selected.")

        # ── Load duration ──
        load_duration = st.selectbox(
            "Load Duration",
            options=list(K1_FACTORS.keys()),
            index=1,  # default medium_term
        )
        k1 = K1_FACTORS[load_duration]
        st.write(f"**k1 = {k1}** ({load_duration})")

        st.divider()

        # ── Advanced parameters ──
        with st.expander("Advanced Parameters"):
            k12 = st.number_input(
                "Stability factor k12",
                min_value=0.0, max_value=1.0, value=1.0, step=0.01,
                help="Lateral stability factor. Use 1.0 for fully restrained beams. "
                     "Reduce for unrestrained beams per Clause 3.2.4.",
            )
            k3 = st.number_input(
                "Bearing length factor k3",
                min_value=1.0, value=1.0, step=0.1,
                help="Bearing length modification factor per Table 3.5.",
            )
            bearing_length = st.number_input(
                "Bearing length (mm)",
                min_value=10.0, value=50.0, step=5.0,
            )
            defl_limit = st.number_input(
                "Deflection limit (L/...)",
                min_value=100, value=300, step=50,
                help="Allowable deflection = span / this value. "
                     "Typical: L/300 for floors, L/250 for roofs.",
            )

    # ── Guard: no loads selected ─────────────────────────────────────
    if not active_entries:
        st.warning("Please select at least one load type in the sidebar.")
        return

    # ── Calculations ─────────────────────────────────────────────────
    line_loads = compute_line_loads(structured, self_weight_kn_m=sw_kn_m)

    beam = analyse_simply_supported(
        span_m, line_loads.w_uls,
        line_loads.w_sls_short, line_loads.w_sls_long,
    )

    results = run_all_checks(
        beam, section, grade, k1,
        bearing_length_mm=bearing_length,
        k12=k12, k3=k3,
        deflection_limit=defl_limit,
    )

    all_passed = all(r.passed for r in results)
    max_util = max(r.utilisation for r in results)

    # ── Main Area: Results ───────────────────────────────────────────
    if all_passed:
        st.success(f"DESIGN ADEQUATE -- Max utilisation: {max_util:.0f}%")
    else:
        failing = [r.name for r in results if not r.passed]
        st.error(f"DESIGN INADEQUATE -- Failing: {', '.join(failing)}")

    # Summary columns
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Section", section.label() + " mm")
        st.metric("Grade", grade_name)
    with col2:
        st.metric("M*", f"{beam.M_star:.2f} kNm")
        st.metric("V*", f"{beam.V_star:.2f} kN")
    with col3:
        st.metric("R_max", f"{beam.R_max:.2f} kN")
        st.metric("w* (ULS)", f"{line_loads.w_uls:.3f} kN/m")

    st.divider()

    # Load summary
    st.subheader("Load Summary")

    import pandas as pd
    if active_entries:
        load_table = []
        for e in active_entries:
            load_table.append({
                "Load Type": e.load_type,
                "Dead G (kPa)": f"{e.dead_kpa:.2f}",
                "Live Q (kPa)": f"{e.live_kpa:.2f}",
                "Trib. Width (m)": f"{e.trib_width_m:.2f}",
                "G (kN/m)": f"{e.G_line:.3f}",
                "Q (kN/m)": f"{e.Q_line:.3f}",
                "UDL (kN/m)": f"{e.udl_kn_per_m:.3f}",
            })
        # Beam self-weight row
        load_table.append({
            "Load Type": "Beam Self-Weight",
            "Dead G (kPa)": "-",
            "Live Q (kPa)": "-",
            "Trib. Width (m)": "-",
            "G (kN/m)": f"{sw_kn_m:.3f}",
            "Q (kN/m)": "0.000",
            "UDL (kN/m)": f"{sw_kn_m:.3f}",
        })
        load_table.append({
            "Load Type": "TOTAL",
            "Dead G (kPa)": "",
            "Live Q (kPa)": "",
            "Trib. Width (m)": "",
            "G (kN/m)": f"{line_loads.G:.3f}",
            "Q (kN/m)": f"{structured.total_Q:.3f}",
            "UDL (kN/m)": f"{line_loads.G + structured.total_Q:.3f}",
        })
        df_loads = pd.DataFrame(load_table)
        st.dataframe(df_loads, width="stretch", hide_index=True)

    # Intermediate unfactored totals (for user verification)
    st.markdown("**Unfactored line load totals (before load combinations):**")
    uf_col1, uf_col2 = st.columns(2)
    with uf_col1:
        st.write(f"**G (total dead line):** {line_loads.G:.3f} kN/m")
        st.write(f"**Q (total live line):** {line_loads.Q:.3f} kN/m")
    with uf_col2:
        st.write(f"1.35G = {1.35 * line_loads.G:.3f} kN/m")
        st.write(f"1.2G + 1.5Q = {1.2 * line_loads.G + 1.5 * line_loads.Q:.3f} kN/m")

    st.markdown("**Factored design loads:**")
    load_col1, load_col2 = st.columns(2)
    with load_col1:
        st.write(f"**w* (ULS):** {line_loads.w_uls:.3f} kN/m  ({line_loads.uls_combo_label})")
        st.write(f"**k1** = {k1} ({load_duration})")
    with load_col2:
        st.write(f"**w_SLS_short:** {line_loads.w_sls_short:.3f} kN/m (G + 0.7Q)")
        st.write(f"**w_SLS_long:** {line_loads.w_sls_long:.3f} kN/m (G + 0.4Q)")

    st.divider()

    # Design check results table
    st.subheader("Design Checks")

    table_data = []
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        table_data.append({
            "Check": r.name,
            "Demand": f"{r.demand:.2f} {r.unit}",
            "Capacity": f"{r.capacity:.2f} {r.unit}",
            "Utilisation": f"{r.utilisation:.0f}%",
            "Status": status,
        })

    def color_status(val):
        if val == "FAIL":
            return "color: red; font-weight: bold"
        return "color: green"

    df = pd.DataFrame(table_data)
    styled = df.style.map(color_status, subset=["Status"])
    st.dataframe(styled, width="stretch", hide_index=True)

    # Check details
    with st.expander("Check Details"):
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            st.write(f"**{r.name} [{status}]:** {r.details}")

    st.divider()

    # K-factors summary
    phi = grade["phi"]
    k2 = grade["k2"]
    k8 = get_k8(section.d)

    with st.expander("Modification Factors"):
        kf_col1, kf_col2 = st.columns(2)
        with kf_col1:
            st.write(f"**phi** = {phi}")
            st.write(f"**k1** = {k1} ({load_duration})")
            st.write(f"**k2** = {k2}")
            st.write(f"**k3** = {k3}")
        with kf_col2:
            st.write(f"**k4** = {K4_DRY}")
            st.write(f"**k5** = {K5_DEFAULT}")
            st.write(f"**k8** = {k8:.3f}")
            st.write(f"**k12** = {k12}")

    # ══════════════════════════════════════════════════════════════════
    # PDF Report Download
    # ══════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("PDF Report")

    k_factors = {
        "phi": phi,
        "k1": k1,
        "k2": k2,
        "k4": K4_DRY,
        "k5": K5_DEFAULT,
        "k8": f"{k8:.3f}",
        "k12": k12,
        "k3": k3,
    }

    load_entries_for_pdf = [
        {
            "type": e.load_type,
            "dead": e.dead_kpa,
            "live": e.live_kpa,
            "trib": e.trib_width_m,
            "G_line": e.G_line,
            "Q_line": e.Q_line,
            "udl": e.udl_kn_per_m,
        }
        for e in active_entries
    ]

    inputs_dict = {
        "project_name": project_name,
        "project_number": project_number,
        "project_address": project_address,
        "beam_id": beam_id,
        "designer": designer,
        "date": design_date.isoformat(),
        "span_m": span_m,
        "load_duration": load_duration,
        "bearing_length_mm": bearing_length,
        "deflection_limit": defl_limit,
        "self_weight_kn_m": sw_kn_m,
        "density_kg_m3": density,
    }

    # Generate PDF upfront so download_button works on first click
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp_path = tmp.name

    try:
        generate_report(
            tmp_path, inputs_dict, beam, section,
            grade_name, grade, results, k_factors,
            load_entries=load_entries_for_pdf,
            line_loads=line_loads,
        )
        with open(tmp_path, "rb") as f:
            pdf_bytes = f.read()

        st.download_button(
            label="Download PDF Report",
            data=pdf_bytes,
            file_name="beam_design_report.pdf",
            mime="application/pdf",
        )
    except Exception as e:
        st.error(f"Error generating report: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


if __name__ == "__main__":
    main()
