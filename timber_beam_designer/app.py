"""
Timber Beam Designer - Streamlit Web GUI.
Timber beam design to NZS AS 1720.1:2022.
Supports UDL + optional point loads (superposition) and multi-beam design.
Beam types: Simply Supported, Beam Overhanging One Support.

Run with: streamlit run run.py
"""

import streamlit as st
import tempfile
import os
from datetime import date

from .material_data import (
    TIMBER_GRADES, K1_FACTORS, get_grade,
    K4_DRY, K6_DEFAULT, get_dropdown_grades,
    get_k7, get_k12, get_S1_compression_edge,
    is_lvl_grade, is_glulam_grade,
)
from .section_properties import TimberSection
from .loads import (
    LOAD_TYPES, LoadEntry, StructuredLoads, PointLoad, PointLoadOverhang,
    compute_line_loads, calc_self_weight,
)
from .beam_analysis import analyse_simply_supported, analyse_overhanging, SIMPLY_SUPPORTED, OVERHANGING
from .design_checks import run_all_checks
from .report_generator import generate_report, generate_multi_beam_report


def check_password():
    """Simple password gate. Returns True if the user has entered the correct password."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.title("Timber Beam Designer")
    st.caption("NZS AS 1720.1:2022 -- Timber Beam Design")
    st.divider()

    # Get password from secrets.toml or fallback
    try:
        correct_password = st.secrets["password"]
    except (KeyError, FileNotFoundError):
        correct_password = "magnitude2024"

    password = st.text_input("Enter access password:", type="password")
    if st.button("Login", type="primary"):
        if password == correct_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")
    return False


def default_beam_state() -> dict:
    """Return a default beam design state dictionary."""
    return {
        "name": "Beam 1",
        # Results (populated after calculation)
        "results": None,
        "beam_actions": None,
        "line_loads": None,
        "section": None,
        "grade": None,
        "grade_name": None,
        "all_passed": None,
        "max_util": None,
        "active_entries": None,
        "point_load_list": None,
        "sw_kn_m": None,
        "k_factors": None,
        "inputs_dict": None,
        "load_entries_for_pdf": None,
    }


def _render_load_panel(active_idx: int, prefix: str, panel_label: str,
                        panel_caption: str, grade, beam_b, beam_d):
    """Render a loading panel (shared by back span and overhang panels).
    Returns (active_entries, structured, sw_kn_m)."""
    st.subheader(panel_label)
    st.caption(panel_caption)

    active_entries = []

    for lt_name, lt_data in LOAD_TYPES.items():
        checked = st.checkbox(
            lt_name,
            value=(lt_name == "Roof"),
            key=f"b{active_idx}_{prefix}_chk_{lt_name}",
        )
        if checked:
            live_val = lt_data["live_kpa"]
            trib_mode = lt_data["trib_mode"]

            col_dead, col_live = st.columns(2)
            with col_dead:
                dead_val = st.number_input(
                    f"G - {lt_name} (kPa)",
                    min_value=0.0, value=0.5, step=0.1,
                    key=f"b{active_idx}_{prefix}_dead_{lt_name}",
                )
            with col_live:
                if live_val > 0:
                    st.text_input(
                        f"Q - {lt_name} (kPa)",
                        value=f"{live_val:.2f}",
                        disabled=True,
                        key=f"b{active_idx}_{prefix}_live_{lt_name}",
                    )
                else:
                    st.text_input(
                        f"Q - {lt_name} (kPa)",
                        value="0 (no live)",
                        disabled=True,
                        key=f"b{active_idx}_{prefix}_live_{lt_name}",
                    )

            if trib_mode == "single":
                trib_total = st.number_input(
                    f"Tributary Width - {lt_name} (m)",
                    min_value=0.0, value=0.6, step=0.1,
                    key=f"b{active_idx}_{prefix}_trib_{lt_name}",
                )
            else:
                tcol_l, tcol_r = st.columns(2)
                with tcol_l:
                    trib_left = st.number_input(
                        f"Trib. Left - {lt_name} (m)",
                        min_value=0.0, value=0.0, step=0.1,
                        key=f"b{active_idx}_{prefix}_trib_left_{lt_name}",
                    )
                with tcol_r:
                    trib_right = st.number_input(
                        f"Trib. Right - {lt_name} (m)",
                        min_value=0.0, value=0.0, step=0.1,
                        key=f"b{active_idx}_{prefix}_trib_right_{lt_name}",
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

    return active_entries


def main():
    st.set_page_config(
        page_title="Timber Beam Designer",
        page_icon="\U0001FAB5",
        layout="wide",
    )

    # ── Password gate ──
    if not check_password():
        return

    st.title("Timber Beam Designer")
    st.caption("NZS AS 1720.1:2022 -- Timber Beam Design")

    # ── Multi-beam state initialization ──
    if "beams" not in st.session_state:
        st.session_state.beams = [default_beam_state()]
        st.session_state.active_beam_idx = 0

    beams = st.session_state.beams
    active_idx = st.session_state.active_beam_idx

    # ── Sidebar ────────────────────────────────────────────────────
    with st.sidebar:
        # ── Beam List ──
        st.header("Beam List")
        col_add, col_remove = st.columns(2)
        with col_add:
            if st.button("\u2795 Add Beam", use_container_width=True):
                new_beam = default_beam_state()
                new_beam["name"] = f"Beam {len(beams) + 1}"
                beams.append(new_beam)
                st.session_state.active_beam_idx = len(beams) - 1
                st.rerun()
        with col_remove:
            if len(beams) > 1:
                if st.button("\u2796 Remove", use_container_width=True):
                    beams.pop(active_idx)
                    st.session_state.active_beam_idx = min(active_idx, len(beams) - 1)
                    st.rerun()

        # Beam selector buttons
        for i, b in enumerate(beams):
            status = ""
            if b.get("all_passed") is True:
                status = " [OK]"
            elif b.get("all_passed") is False:
                status = " [FAIL]"
            btn_type = "primary" if i == active_idx else "secondary"
            if st.button(
                f"{b['name']}{status}",
                key=f"beam_btn_{i}",
                type=btn_type,
                use_container_width=True,
            ):
                st.session_state.active_beam_idx = i
                st.rerun()

        st.divider()

        current_beam = beams[active_idx]

        # ── Restore widget states when switching back to this beam ──
        # Streamlit deletes session_state keys for widgets that are not rendered.
        # When the user switches beams, the old beam's widget keys are deleted.
        # We restore them from the beam's saved_inputs dict so values are preserved.
        for _k, _v in current_beam.get("saved_inputs", {}).items():
            if _k not in st.session_state:
                st.session_state[_k] = _v

        # Editable beam name
        current_beam["name"] = st.text_input(
            "Beam Name",
            value=current_beam["name"],
            key=f"b{active_idx}_beam_name",
        )

        st.header("Design Inputs")

        # ── Project Information ──
        with st.expander("Project Information", expanded=True):
            project_name = st.text_input("Project Name", value="", key=f"b{active_idx}_proj_name")
            project_number = st.text_input("Project Number", value="", key=f"b{active_idx}_proj_num")
            project_address = st.text_input("Project Address", value="", key=f"b{active_idx}_proj_addr")
            beam_id = st.text_input("Beam ID", value="", key=f"b{active_idx}_beam_id")
            designer = st.text_input("Designer Name", value="", key=f"b{active_idx}_designer")
            design_date = st.date_input("Date", value=date.today(), key=f"b{active_idx}_date")

        st.divider()

        # ── Timber grade ──
        grade_name = st.selectbox(
            "Timber Grade",
            options=get_dropdown_grades(),
            index=0,
            key=f"b{active_idx}_grade",
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
            st.write(f"**rho_b** = {grade.get('rho_b', 'N/A')}")

        st.divider()

        # ── Beam Section ──
        st.subheader("Beam Section")
        col_b, col_d = st.columns(2)
        with col_b:
            beam_b = st.number_input("Breadth b (mm)", min_value=10.0, value=90.0, step=5.0,
                                      key=f"b{active_idx}_b")
        with col_d:
            beam_d = st.number_input("Depth d (mm)", min_value=10.0, value=240.0, step=5.0,
                                      key=f"b{active_idx}_d")
        section = TimberSection(beam_b, beam_d)

        st.divider()

        # ── Span ──
        span_m = st.number_input("Total Span (m)", min_value=0.1, value=4.0, step=0.1,
                                  key=f"b{active_idx}_span")

        # ── Beam Type ──
        beam_type_options = ["Simply Supported", "Beam Overhanging One Support"]
        beam_type_display = st.selectbox(
            "Support Condition",
            options=beam_type_options,
            index=0,
            key=f"b{active_idx}_beam_type",
            help="Simply Supported: two pin supports at each end. "
                 "Overhanging: two pin supports with cantilever overhang beyond one support.",
        )
        beam_type = SIMPLY_SUPPORTED if beam_type_display == "Simply Supported" else OVERHANGING
        is_overhanging = beam_type == OVERHANGING

        # ── Overhanging beam geometry ──
        cant_span_m = 0.0
        back_span_m = span_m
        if is_overhanging:
            cant_span_m = st.number_input(
                "Cantilever Overhang, a (m)",
                min_value=0.1,
                max_value=max(span_m - 0.1, 0.2),
                value=min(1.0, span_m - 0.1),
                step=0.1,
                key=f"b{active_idx}_cant_span",
            )
            back_span_m = span_m - cant_span_m
            st.caption(f"Back span (ell) = {span_m:.2f} - {cant_span_m:.2f} = **{back_span_m:.2f} m**")

            if back_span_m <= 0:
                st.error("Back span must be positive. Reduce cantilever overhang.")
                return

            st.info(
                f"R1 at left, R2 at {back_span_m:.2f} m from R1, "
                f"free end {cant_span_m:.2f} m beyond R2."
            )

            if cant_span_m > back_span_m / 2:
                st.warning(
                    f"Overhang ({cant_span_m:.2f} m) > back span/2 ({back_span_m/2:.2f} m). "
                    f"R1 may be in uplift -- check hold-down connections."
                )

        st.divider()

        # ── Self-weight (automatic) ──
        density = grade.get("density", 500.0)
        sw_kn_m = calc_self_weight(beam_b, beam_d, density)
        st.caption(f"Beam self-weight: {sw_kn_m:.3f} kN/m "
                   f"({beam_b:.0f}x{beam_d:.0f} mm, "
                   f"{density:.0f} kg/m\u00B3)")

        # ── Loading ──
        if is_overhanging:
            # ── Same / Different loading toggle ──
            load_option = st.radio(
                "Back span and overhang loading",
                options=["Same loading on both", "Different loading"],
                index=0,
                key=f"b{active_idx}_load_same_diff",
                help="'Same' replicates the back span UDL loading to the overhang. "
                     "Point loads are always specified separately.",
                horizontal=True,
            )
            same_loading = load_option == "Same loading on both"

            # ── Back Span Loading (always shown) ──
            panel_label = "Loading" if same_loading else "Loading -- Back Span"
            panel_caption = (
                "Loads applied to the full beam (back span and overhang)."
                if same_loading else
                "Loads applied between supports R1 and R2."
            )
            active_entries_back = _render_load_panel(
                active_idx, "back", panel_label, panel_caption,
                grade, beam_b, beam_d,
            )
            structured_back = StructuredLoads(entries=active_entries_back)
            line_loads_back = compute_line_loads(structured_back, self_weight_kn_m=sw_kn_m)

            if active_entries_back:
                total_G_back = structured_back.total_G + sw_kn_m
                if same_loading:
                    st.info(
                        f"**Both spans:** G={total_G_back:.3f}, Q={structured_back.total_Q:.3f}, "
                        f"w*={line_loads_back.w_uls:.3f} kN/m ({line_loads_back.uls_combo_label})"
                    )
                else:
                    st.info(
                        f"**Back span:** G={total_G_back:.3f}, Q={structured_back.total_Q:.3f}, "
                        f"w*={line_loads_back.w_uls:.3f} kN/m ({line_loads_back.uls_combo_label})"
                    )

            if same_loading:
                # Replicate back span loading to overhang
                active_entries_cant = list(active_entries_back)
                structured_cant = StructuredLoads(entries=active_entries_cant)
                line_loads_cant = compute_line_loads(structured_cant, self_weight_kn_m=sw_kn_m)
            else:
                st.divider()

                # ── Cantilever Overhang Loading (only when different) ──
                active_entries_cant = _render_load_panel(
                    active_idx, "cant", "Loading -- Cantilever Overhang",
                    "Loads applied on the overhang beyond R2.",
                    grade, beam_b, beam_d,
                )
                structured_cant = StructuredLoads(entries=active_entries_cant)
                line_loads_cant = compute_line_loads(structured_cant, self_weight_kn_m=sw_kn_m)

                if active_entries_cant:
                    total_G_cant = structured_cant.total_G + sw_kn_m
                    st.info(
                        f"**Overhang:** G={total_G_cant:.3f}, Q={structured_cant.total_Q:.3f}, "
                        f"w*={line_loads_cant.w_uls:.3f} kN/m ({line_loads_cant.uls_combo_label})"
                    )

            # Combined active entries for validation
            active_entries = active_entries_back + active_entries_cant
        else:
            # ── Simply Supported — single loading panel ──
            st.subheader("Loading")
            st.caption("Select applicable load types. Dead loads are user input; "
                        "live loads are fixed per AS/NZS 1170.0. "
                        "Each load type has its own tributary width.")

            active_entries = []

            for lt_name, lt_data in LOAD_TYPES.items():
                checked = st.checkbox(lt_name, value=(lt_name == "Roof"),
                                       key=f"b{active_idx}_chk_{lt_name}")
                if checked:
                    live_val = lt_data["live_kpa"]
                    trib_mode = lt_data["trib_mode"]

                    col_dead, col_live = st.columns(2)
                    with col_dead:
                        dead_val = st.number_input(
                            f"G - {lt_name} (kPa)",
                            min_value=0.0, value=0.5, step=0.1,
                            key=f"b{active_idx}_dead_{lt_name}",
                        )
                    with col_live:
                        if live_val > 0:
                            st.text_input(
                                f"Q - {lt_name} (kPa)",
                                value=f"{live_val:.2f}",
                                disabled=True,
                                key=f"b{active_idx}_live_{lt_name}",
                            )
                        else:
                            st.text_input(
                                f"Q - {lt_name} (kPa)",
                                value="0 (no live)",
                                disabled=True,
                                key=f"b{active_idx}_live_{lt_name}",
                            )

                    if trib_mode == "single":
                        trib_total = st.number_input(
                            f"Tributary Width - {lt_name} (m)",
                            min_value=0.0, value=0.6, step=0.1,
                            key=f"b{active_idx}_trib_{lt_name}",
                        )
                    else:
                        tcol_l, tcol_r = st.columns(2)
                        with tcol_l:
                            trib_left = st.number_input(
                                f"Trib. Left - {lt_name} (m)",
                                min_value=0.0, value=0.0, step=0.1,
                                key=f"b{active_idx}_trib_left_{lt_name}",
                            )
                        with tcol_r:
                            trib_right = st.number_input(
                                f"Trib. Right - {lt_name} (m)",
                                min_value=0.0, value=0.0, step=0.1,
                                key=f"b{active_idx}_trib_right_{lt_name}",
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

            structured = StructuredLoads(entries=active_entries)

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

        st.divider()

        # ── Point Loads ──
        if is_overhanging:
            # ── Point Load on Back Span (0 or 1) ──
            st.subheader("Point Loads -- Back Span")
            st.caption("0 or 1 point load between R1 and R2. Position from R1.")
            num_pl_back = st.selectbox(
                "Number of point loads (back span)",
                options=[0, 1],
                index=0,
                key=f"b{active_idx}_num_pl_back",
            )

            point_load_list_back = []
            for i in range(num_pl_back):
                st.markdown(f"**Point Load (back span)**")
                col_puls, col_psls = st.columns(2)
                with col_puls:
                    p_uls = st.number_input(
                        "P_ULS (kN)",
                        min_value=0.0, value=5.0, step=0.5,
                        key=f"b{active_idx}_back_p_uls_{i}",
                    )
                with col_psls:
                    p_sls = st.number_input(
                        "P_SLS (kN)",
                        min_value=0.0, value=3.5, step=0.5,
                        key=f"b{active_idx}_back_p_sls_{i}",
                    )
                col_a, col_b_disp = st.columns(2)
                with col_a:
                    a_val = st.number_input(
                        "Distance from R1 (m)",
                        min_value=0.01,
                        max_value=max(back_span_m - 0.01, 0.02),
                        value=min(back_span_m / 2.0, back_span_m - 0.01),
                        step=0.1,
                        key=f"b{active_idx}_back_p_a_{i}",
                    )
                with col_b_disp:
                    b_val = back_span_m - a_val
                    st.session_state[f"b{active_idx}_back_p_b_display_{i}"] = f"{b_val:.2f}"
                    st.text_input(
                        "Distance from R2 (m)",
                        value=f"{b_val:.2f}",
                        disabled=True,
                        key=f"b{active_idx}_back_p_b_display_{i}",
                    )

                pl = PointLoad(P_uls=p_uls, P_sls=p_sls, a_m=a_val)
                if pl.validate(back_span_m):
                    point_load_list_back.append(pl)
                else:
                    st.warning(f"Point load: position must be between 0 and {back_span_m:.2f} m")

            st.divider()

            # ── Point Load on Overhang (0 or 1) ──
            st.subheader("Point Loads -- Overhang")
            st.caption("0 or 1 point load on the overhang. Position from R2.")
            num_pl_cant = st.selectbox(
                "Number of point loads (overhang)",
                options=[0, 1],
                index=0,
                key=f"b{active_idx}_num_pl_cant",
            )

            point_load_list_cant = []
            for i in range(num_pl_cant):
                st.markdown(f"**Point Load (overhang)**")
                col_puls, col_psls = st.columns(2)
                with col_puls:
                    p_uls = st.number_input(
                        "P_ULS (kN)",
                        min_value=0.0, value=5.0, step=0.5,
                        key=f"b{active_idx}_cant_p_uls_{i}",
                    )
                with col_psls:
                    p_sls = st.number_input(
                        "P_SLS (kN)",
                        min_value=0.0, value=3.5, step=0.5,
                        key=f"b{active_idx}_cant_p_sls_{i}",
                    )
                col_a, col_b_disp = st.columns(2)
                with col_a:
                    a_val = st.number_input(
                        "Distance from R2 (m)",
                        min_value=0.01,
                        max_value=cant_span_m,
                        value=cant_span_m,  # default at free end
                        step=0.1,
                        key=f"b{active_idx}_cant_p_a_{i}",
                    )
                with col_b_disp:
                    b_val = cant_span_m - a_val
                    st.session_state[f"b{active_idx}_cant_p_b_display_{i}"] = f"{b_val:.2f}"
                    st.text_input(
                        "From free end (m)",
                        value=f"{b_val:.2f}",
                        disabled=True,
                        key=f"b{active_idx}_cant_p_b_display_{i}",
                    )

                pl = PointLoadOverhang(P_uls=p_uls, P_sls=p_sls, a_m=a_val)
                if pl.validate(cant_span_m):
                    point_load_list_cant.append(pl)
                else:
                    st.warning(f"Point load: position must be between 0 and {cant_span_m:.2f} m")

            # Combine for compatibility
            point_load_list = point_load_list_back + point_load_list_cant
        else:
            # ── SS Point Loads (up to 2) ──
            st.subheader("Point Loads (optional)")
            st.caption("Up to 2 point loads. Provide ULS and SLS values directly.")

            num_point_loads = st.selectbox(
                "Number of point loads",
                options=[0, 1, 2],
                index=0,
                key=f"b{active_idx}_num_pl",
            )

            point_load_list = []
            for i in range(num_point_loads):
                st.markdown(f"**Point Load {i + 1}**")
                col_puls, col_psls = st.columns(2)
                with col_puls:
                    p_uls = st.number_input(
                        f"P{i + 1} ULS (kN)",
                        min_value=0.0, value=5.0, step=0.5,
                        key=f"b{active_idx}_p_uls_{i}",
                    )
                with col_psls:
                    p_sls = st.number_input(
                        f"P{i + 1} SLS (kN)",
                        min_value=0.0, value=3.5, step=0.5,
                        key=f"b{active_idx}_p_sls_{i}",
                    )
                col_a, col_b_disp = st.columns(2)
                with col_a:
                    a_val = st.number_input(
                        f"P{i + 1} from left support (m)",
                        min_value=0.01,
                        max_value=max(span_m - 0.01, 0.02),
                        value=min(span_m / 2.0, span_m - 0.01),
                        step=0.1,
                        key=f"b{active_idx}_p_a_{i}",
                    )
                with col_b_disp:
                    b_val = span_m - a_val
                    st.session_state[f"b{active_idx}_p_b_display_{i}"] = f"{b_val:.2f}"
                    st.text_input(
                        f"P{i + 1} from right support (m)",
                        value=f"{b_val:.2f}",
                        disabled=True,
                        key=f"b{active_idx}_p_b_display_{i}",
                    )

                pl = PointLoad(P_uls=p_uls, P_sls=p_sls, a_m=a_val)
                if pl.validate(span_m):
                    point_load_list.append(pl)
                else:
                    st.warning(f"Point load {i + 1}: position must be between 0 and {span_m:.2f} m")

            point_load_list_back = []
            point_load_list_cant = []

        st.divider()

        # ── Load duration ──
        load_duration = st.selectbox(
            "Load Duration",
            options=list(K1_FACTORS.keys()),
            index=1,  # default medium_term
            key=f"b{active_idx}_dur",
        )
        k1 = K1_FACTORS[load_duration]
        st.write(f"**k1 = {k1}** ({load_duration})")

        st.divider()

        # ── Advanced parameters ──
        with st.expander("Advanced Parameters"):
            k6 = st.number_input(
                "Temperature factor k6",
                min_value=0.0, max_value=1.0, value=K6_DEFAULT, step=0.1,
                help="Temperature/humidity factor per Clause 2.4.3. "
                     "k6 = 1.0 for NZ. k6 = 0.9 for tropical Australia.",
                key=f"b{active_idx}_k6",
            )
            _k9_is_locked = is_lvl_grade(grade_name) or is_glulam_grade(grade_name)
            if _k9_is_locked:
                k9 = 1.0
                st.number_input(
                    "Strength sharing factor k9",
                    min_value=1.0, max_value=1.0, value=1.0, step=0.01,
                    disabled=True,
                    help="k9 = 1.0 for LVL (Section 8.4.6) and glulam (Section 7.4.3).",
                    key=f"b{active_idx}_k9_locked",
                )
                st.caption("k9 locked to 1.0 for LVL/glulam per Sections 7.4.3 & 8.4.6.")
            else:
                k9 = st.number_input(
                    "Strength sharing factor k9",
                    min_value=1.0, max_value=1.33, value=1.0, step=0.01,
                    help="Parallel system strength sharing factor per Clause 2.4.5.",
                    key=f"b{active_idx}_k9",
                )
            k12 = st.number_input(
                "Stability factor k12",
                min_value=0.0, max_value=1.0, value=1.0, step=0.01,
                help="Lateral stability factor per Clause 3.2.4.",
                key=f"b{active_idx}_k12",
            )
            k7 = st.number_input(
                "Bearing length factor k7",
                min_value=1.0, max_value=1.75, value=1.0, step=0.05,
                help="Bearing length factor per Table 2.6.",
                key=f"b{active_idx}_k7",
            )
            bearing_length = st.number_input(
                "Bearing length (mm)",
                min_value=10.0, value=50.0, step=5.0,
                key=f"b{active_idx}_bearing",
            )
            defl_limit = st.number_input(
                "Deflection limit -- span (L/...)",
                min_value=100, value=300, step=50,
                help="Allowable deflection for span between supports = span / this value.",
                key=f"b{active_idx}_defl_limit",
            )
            if is_overhanging:
                defl_limit_tip = st.number_input(
                    "Deflection limit -- overhang tip (L/...)",
                    min_value=100, value=150, step=50,
                    help="Allowable deflection at cantilever free end = a / this value. "
                         "NZS 3604 typical: L/150 for cantilever tips.",
                    key=f"b{active_idx}_defl_limit_tip",
                )
            else:
                defl_limit_tip = defl_limit

            # k12 auto-calculation helper
            rho_b = grade.get("rho_b", 0.76)
            with st.expander("k12 Auto-Calculator"):
                st.caption(
                    "Calculate k12 from restraint conditions per Clause 3.2.4."
                )
                restraint_spacing = st.number_input(
                    "Lay - Restraint spacing (mm)",
                    min_value=0.0, value=0.0, step=100.0,
                    help="Distance between discrete lateral restraints. 0 = continuous.",
                    key=f"b{active_idx}_restraint",
                )
                if restraint_spacing > 0:
                    S1 = get_S1_compression_edge(beam_d, beam_b, restraint_spacing)
                    k12_calc = get_k12(rho_b, S1)
                    st.write(f"S1 = **{S1:.2f}**")
                    st.write(f"rho_b * S1 = {rho_b} * {S1:.2f} = **{rho_b * S1:.2f}**")
                    st.write(f"**k12 = {k12_calc:.3f}**")
                    st.caption("Copy this value to the k12 input above if desired.")
                else:
                    st.write("S1 = 0.0 (continuous restraint)")
                    st.write("**k12 = 1.000**")

    # ── Guard: no loads selected ─────────────────────────────────────
    if not active_entries:
        st.warning("Please select at least one load type in the sidebar.")
        return

    # ── Calculations ─────────────────────────────────────────────────
    if is_overhanging:
        _pl_back = point_load_list_back if point_load_list_back else None
        _pl_cant = point_load_list_cant if point_load_list_cant else None
        beam = analyse_overhanging(
            total_span_m=span_m,
            cant_span_m=cant_span_m,
            w_uls_back=line_loads_back.w_uls,
            w_sls_short_back=line_loads_back.w_sls_short,
            w_sls_long_back=line_loads_back.w_sls_long,
            w_uls_cant=line_loads_cant.w_uls,
            w_sls_short_cant=line_loads_cant.w_sls_short,
            w_sls_long_cant=line_loads_cant.w_sls_long,
            point_loads_back=_pl_back,
            point_loads_cant=_pl_cant,
            w_G_back=line_loads_back.G,
            w_psi_lQ_back=0.4 * line_loads_back.Q,
            w_G_cant=line_loads_cant.G,
            w_psi_lQ_cant=0.4 * line_loads_cant.Q,
        )
        line_loads = line_loads_back  # primary line loads for PDF
    else:
        structured = StructuredLoads(entries=active_entries)
        line_loads = compute_line_loads(structured, self_weight_kn_m=sw_kn_m)
        _pl = point_load_list if point_load_list else None
        beam = analyse_simply_supported(
            span_m, line_loads.w_uls,
            line_loads.w_sls_short, line_loads.w_sls_long,
            point_loads=_pl,
            w_G=line_loads.G,
            w_psi_lQ=0.4 * line_loads.Q,
        )

    results = run_all_checks(
        beam, section, grade, k1,
        bearing_length_mm=bearing_length,
        k6=k6, k7=k7, k9=k9, k12=k12,
        deflection_limit=defl_limit,
        deflection_limit_tip=defl_limit_tip,
    )

    all_passed = all(r.passed for r in results)
    max_util = max(r.utilisation for r in results)

    # Store results in beam state for multi-beam tracking
    phi = grade["phi"]
    k2 = grade["k2"]
    k_factors = {
        "phi": phi, "k1": k1, "k2": k2, "k4": K4_DRY,
        "k6": k6, "k7": k7, "k9": k9, "k12": k12,
    }

    # Build load entries for PDF
    if is_overhanging:
        load_entries_for_pdf_back = [
            {
                "type": e.load_type, "dead": e.dead_kpa, "live": e.live_kpa,
                "trib": e.trib_width_m, "G_line": e.G_line, "Q_line": e.Q_line,
                "udl": e.udl_kn_per_m,
            }
            for e in active_entries_back
        ]
        load_entries_for_pdf_cant = [
            {
                "type": e.load_type, "dead": e.dead_kpa, "live": e.live_kpa,
                "trib": e.trib_width_m, "G_line": e.G_line, "Q_line": e.Q_line,
                "udl": e.udl_kn_per_m,
            }
            for e in active_entries_cant
        ]
        load_entries_for_pdf = load_entries_for_pdf_back  # primary for PDF
    else:
        load_entries_for_pdf = [
            {
                "type": e.load_type, "dead": e.dead_kpa, "live": e.live_kpa,
                "trib": e.trib_width_m, "G_line": e.G_line, "Q_line": e.Q_line,
                "udl": e.udl_kn_per_m,
            }
            for e in active_entries
        ]
        load_entries_for_pdf_back = load_entries_for_pdf
        load_entries_for_pdf_cant = []

    # Build point loads for PDF
    point_loads_back_for_pdf = []
    if point_load_list_back:
        for i, pl in enumerate(point_load_list_back):
            point_loads_back_for_pdf.append({
                "label": f"P_back{i+1}",
                "P_uls": pl.P_uls,
                "P_sls": pl.P_sls,
                "a_m": pl.a_m,
                "b_m": back_span_m - pl.a_m if is_overhanging else pl.calc_b(span_m),
            })

    point_loads_cant_for_pdf = []
    if point_load_list_cant:
        for i, pl in enumerate(point_load_list_cant):
            point_loads_cant_for_pdf.append({
                "label": f"P_cant{i+1}",
                "P_uls": pl.P_uls,
                "P_sls": pl.P_sls,
                "a_m": pl.a_m,
                "b_m": pl.calc_b(cant_span_m),
            })

    # SS point loads for PDF (backward compat)
    point_loads_for_pdf = []
    if not is_overhanging and point_load_list:
        for i, pl in enumerate(point_load_list):
            point_loads_for_pdf.append({
                "label": f"P{i + 1}",
                "P_uls": pl.P_uls,
                "P_sls": pl.P_sls,
                "a_m": pl.a_m,
                "b_m": pl.calc_b(span_m),
            })

    inputs_dict = {
        "project_name": project_name,
        "project_number": project_number,
        "project_address": project_address,
        "beam_id": beam_id,
        "designer": designer,
        "date": design_date.isoformat(),
        "span_m": span_m,
        "beam_type": beam_type,
        "back_span_m": back_span_m,
        "cant_span_m": cant_span_m,
        "load_duration": load_duration,
        "bearing_length_mm": bearing_length,
        "deflection_limit": defl_limit,
        "deflection_limit_tip": defl_limit_tip,
        "self_weight_kn_m": sw_kn_m,
        "density_kg_m3": density,
        "point_loads": point_loads_for_pdf,
        "point_loads_back": point_loads_back_for_pdf,
        "point_loads_cant": point_loads_cant_for_pdf,
        "load_entries_cant": load_entries_for_pdf_cant,
    }

    # Store line loads for overhanging beam PDF
    if is_overhanging:
        inputs_dict["w_uls_cant"] = line_loads_cant.w_uls
        inputs_dict["w_sls_short_cant"] = line_loads_cant.w_sls_short
        inputs_dict["w_sls_long_cant"] = line_loads_cant.w_sls_long
        inputs_dict["uls_combo_label_cant"] = line_loads_cant.uls_combo_label
        inputs_dict["G_cant"] = line_loads_cant.G
        inputs_dict["Q_cant"] = line_loads_cant.Q

    current_beam.update({
        "results": results,
        "beam_actions": beam,
        "line_loads": line_loads,
        "section": section,
        "grade": grade,
        "grade_name": grade_name,
        "all_passed": all_passed,
        "max_util": max_util,
        "active_entries": active_entries,
        "point_load_list": point_load_list,
        "sw_kn_m": sw_kn_m,
        "k_factors": k_factors,
        "inputs_dict": inputs_dict,
        "load_entries_for_pdf": load_entries_for_pdf,
        "span_m": span_m,
        "beam_b": beam_b,
        "beam_d": beam_d,
    })
    if is_overhanging:
        current_beam["line_loads_cant"] = line_loads_cant

    # ── Persist widget states so they survive beam switches ──
    # Save all session_state keys belonging to this beam into its dict.
    # This ensures values are available for restoration when the user returns.
    _pfx = f"b{active_idx}_"
    current_beam["saved_inputs"] = {
        k: v for k, v in st.session_state.items()
        if isinstance(k, str) and k.startswith(_pfx)
    }

    # ── Main Area: Results ───────────────────────────────────────────
    if all_passed:
        st.success(f"DESIGN ADEQUATE -- Max utilisation: {max_util:.0f}%")
    else:
        failing = [r.name for r in results if not r.passed]
        st.error(f"DESIGN INADEQUATE -- Failing: {', '.join(failing)}")

    # R1 uplift warning for overhanging beams
    if is_overhanging and beam.R_left < 0:
        st.warning(
            f"R1 is in UPLIFT ({beam.R_left:.2f} kN). "
            f"Hold-down connection required at R1 support."
        )

    # Summary columns
    if is_overhanging:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Section", section.label() + " mm")
            st.metric("Grade", grade_name)
        with col2:
            st.metric("M* (sagging)", f"{beam.M_sagging:.2f} kNm")
            st.metric("M* (hogging)", f"{beam.M_hogging:.2f} kNm")
        with col3:
            st.metric("V*", f"{beam.V_star:.2f} kN")
            st.metric("R1", f"{beam.R_left:.2f} kN")
        with col4:
            st.metric("R2", f"{beam.R_right:.2f} kN")
            st.metric("Back / Overhang", f"{back_span_m:.2f} / {cant_span_m:.2f} m")
    else:
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

    # ── Superposition breakdown ──
    import pandas as pd

    if is_overhanging:
        st.subheader("Overhanging Beam Actions Breakdown")
        sp_col1, sp_col2 = st.columns(2)
        with sp_col1:
            st.markdown("**Sagging (between supports):**")
            st.write(f"M_sag (UDL) = {beam.M_sagging_udl:.2f} kNm")
            st.write(f"M_sag (point loads) = {beam.M_sagging_point:.2f} kNm")
            st.write(f"**M_sag (total) = {beam.M_sagging:.2f} kNm**")
        with sp_col2:
            st.markdown("**Hogging (at R2):**")
            st.write(f"M_hog (UDL) = {beam.M_hogging_udl:.2f} kNm")
            st.write(f"M_hog (point loads) = {beam.M_hogging_point:.2f} kNm")
            st.write(f"**M_hog (total) = {beam.M_hogging:.2f} kNm**")

        st.markdown("**Reactions:**")
        r_col1, r_col2, r_col3 = st.columns(3)
        with r_col1:
            r1_label = f"R1 = {beam.R_left:.2f} kN"
            if beam.R_left < 0:
                r1_label += " (UPLIFT)"
            st.write(r1_label)
        with r_col2:
            st.write(f"R2 = {beam.R_right:.2f} kN")
        with r_col3:
            st.write(f"**V* = {beam.V_star:.2f} kN**")
        st.divider()

    elif point_load_list:
        st.subheader("Point Load Summary")
        pl_table = []
        for i, pl in enumerate(point_load_list):
            pl_table.append({
                "Load": f"P{i + 1}",
                "P_ULS (kN)": f"{pl.P_uls:.2f}",
                "P_SLS (kN)": f"{pl.P_sls:.2f}",
                "a from left (m)": f"{pl.a_m:.2f}",
                "b from right (m)": f"{pl.calc_b(span_m):.2f}",
            })
        df_pl = pd.DataFrame(pl_table)
        st.dataframe(df_pl, hide_index=True)

        st.markdown("**Superposition breakdown:**")
        sp_col1, sp_col2 = st.columns(2)
        with sp_col1:
            st.write(f"M*(UDL) = {beam.M_udl:.2f} kNm")
            st.write(f"M*(point loads) = {beam.M_point:.2f} kNm")
            st.write(f"**M*(total) = {beam.M_star:.2f} kNm**")
        with sp_col2:
            st.write(f"R_left = {beam.R_left:.2f} kN")
            st.write(f"R_right = {beam.R_right:.2f} kN")
            st.write(f"**V*(max) = {beam.V_star:.2f} kN**")
        st.divider()

    # Load summary
    st.subheader("Load Summary")

    if is_overhanging:
        # Back span loads
        if active_entries_back:
            st.markdown("**Back Span Loads:**")
            load_table = []
            for e in active_entries_back:
                load_table.append({
                    "Load Type": e.load_type,
                    "G (kPa)": f"{e.dead_kpa:.2f}",
                    "Q (kPa)": f"{e.live_kpa:.2f}",
                    "Trib (m)": f"{e.trib_width_m:.2f}",
                    "G (kN/m)": f"{e.G_line:.3f}",
                    "Q (kN/m)": f"{e.Q_line:.3f}",
                    "UDL (kN/m)": f"{e.udl_kn_per_m:.3f}",
                })
            load_table.append({
                "Load Type": "Beam Self-Wt",
                "G (kPa)": "-", "Q (kPa)": "-", "Trib (m)": "-",
                "G (kN/m)": f"{sw_kn_m:.3f}", "Q (kN/m)": "0.000",
                "UDL (kN/m)": f"{sw_kn_m:.3f}",
            })
            df_back = pd.DataFrame(load_table)
            st.dataframe(df_back, width="stretch", hide_index=True)

            st.markdown(
                f"w* (back) = {line_loads_back.w_uls:.3f} kN/m ({line_loads_back.uls_combo_label}), "
                f"w_SLS_short = {line_loads_back.w_sls_short:.3f}, "
                f"w_SLS_long = {line_loads_back.w_sls_long:.3f}"
            )

        # Overhang loads
        if active_entries_cant:
            st.markdown("**Overhang Loads:**")
            load_table_cant = []
            for e in active_entries_cant:
                load_table_cant.append({
                    "Load Type": e.load_type,
                    "G (kPa)": f"{e.dead_kpa:.2f}",
                    "Q (kPa)": f"{e.live_kpa:.2f}",
                    "Trib (m)": f"{e.trib_width_m:.2f}",
                    "G (kN/m)": f"{e.G_line:.3f}",
                    "Q (kN/m)": f"{e.Q_line:.3f}",
                    "UDL (kN/m)": f"{e.udl_kn_per_m:.3f}",
                })
            load_table_cant.append({
                "Load Type": "Beam Self-Wt",
                "G (kPa)": "-", "Q (kPa)": "-", "Trib (m)": "-",
                "G (kN/m)": f"{sw_kn_m:.3f}", "Q (kN/m)": "0.000",
                "UDL (kN/m)": f"{sw_kn_m:.3f}",
            })
            df_cant = pd.DataFrame(load_table_cant)
            st.dataframe(df_cant, width="stretch", hide_index=True)

            st.markdown(
                f"w* (overhang) = {line_loads_cant.w_uls:.3f} kN/m ({line_loads_cant.uls_combo_label}), "
                f"w_SLS_short = {line_loads_cant.w_sls_short:.3f}, "
                f"w_SLS_long = {line_loads_cant.w_sls_long:.3f}"
            )
    else:
        # SS load summary (unchanged)
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
            load_table.append({
                "Load Type": "Beam Self-Weight",
                "Dead G (kPa)": "-", "Live Q (kPa)": "-", "Trib. Width (m)": "-",
                "G (kN/m)": f"{sw_kn_m:.3f}", "Q (kN/m)": "0.000",
                "UDL (kN/m)": f"{sw_kn_m:.3f}",
            })
            load_table.append({
                "Load Type": "TOTAL",
                "Dead G (kPa)": "", "Live Q (kPa)": "", "Trib. Width (m)": "",
                "G (kN/m)": f"{line_loads.G:.3f}",
                "Q (kN/m)": f"{structured.total_Q:.3f}",
                "UDL (kN/m)": f"{line_loads.G + structured.total_Q:.3f}",
            })
            df_loads = pd.DataFrame(load_table)
            st.dataframe(df_loads, width="stretch", hide_index=True)

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
    with st.expander("Modification Factors (AS 1720.1:2022)"):
        kf_col1, kf_col2 = st.columns(2)
        with kf_col1:
            st.write(f"**phi** = {phi}")
            st.write(f"**k1** = {k1} ({load_duration})")
            st.write(f"**k2** = {k2} (creep)")
            st.write(f"**k4** = {K4_DRY} (moisture)")
        with kf_col2:
            st.write(f"**k6** = {k6} (temperature)")
            st.write(f"**k7** = {k7} (bearing length)")
            st.write(f"**k9** = {k9} (strength sharing)")
            st.write(f"**k12** = {k12} (stability)")

    # ── PDF Report Download ──────────────────────────────────────────
    st.divider()
    st.subheader("PDF Reports")

    report_col1, report_col2 = st.columns(2)

    with report_col1:
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

            beam_label = current_beam["name"].replace(" ", "_")
            st.download_button(
                label=f"Download {current_beam['name']} PDF",
                data=pdf_bytes,
                file_name=f"{beam_label}_design_report.pdf",
                mime="application/pdf",
                key=f"b{active_idx}_pdf_single",
            )
        except Exception as e:
            st.error(f"Error generating report: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    with report_col2:
        if len(beams) > 1:
            all_calculated = all(b.get("results") is not None for b in beams)
            if all_calculated:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp_path_multi = tmp.name

                try:
                    generate_multi_beam_report(tmp_path_multi, beams)
                    with open(tmp_path_multi, "rb") as f:
                        multi_pdf_bytes = f.read()

                    st.download_button(
                        label="Download Multi-Beam Report",
                        data=multi_pdf_bytes,
                        file_name="multi_beam_design_report.pdf",
                        mime="application/pdf",
                        key="pdf_multi",
                    )
                except Exception as e:
                    st.error(f"Error generating multi-beam report: {e}")
                finally:
                    if os.path.exists(tmp_path_multi):
                        os.unlink(tmp_path_multi)
            else:
                uncalculated = [b["name"] for b in beams if b.get("results") is None]
                st.warning(f"Calculate all beams first for combined report. "
                           f"Missing: {', '.join(uncalculated)}")


if __name__ == "__main__":
    main()
