"""
Traffic Flow Visualization Generator

This module generates PNG plots of traffic flows in a sankey diagramm format from Excel data.
It supports general traffic and peak hour analysis (morning and afternoon).
"""

import io
import re
from typing import List, Tuple, Dict, Optional, Any   #Type hints
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg") # Agg is a non-interactive, off-screen rendering backend, Plots are rendered directly to image file
import matplotlib.pyplot as plt    
from matplotlib.patches import Polygon
from openpyxl import load_workbook
from datetime import datetime, timedelta

#AB HIER CODE AUS "LOCAL" ERSETZEN
# --------------------- CONFIG ---------------------

def cell(ws, addr):
    value = ws[addr].value

    if value is None or value == "":
        return 0.0

    return float(value)

def get_figure_renderer(fig):
    """
    Gibt den aktuellen Matplotlib-Renderer zurück.
    Funktioniert auch bei PNG-, SVG- und PDF-Ausgaben.
    """
    fig.canvas.draw()

    if hasattr(fig.canvas, "get_renderer"):
        return fig.canvas.get_renderer()

    return fig._get_renderer()
    
#PKW_Einheiten faktors
PKW_E_FAKTOREN = {
    "MIT VLSA": {
        "rad": 0.3,
        "einspurig": 0.5,
        "pkw": 1.0,
        "linienbus": 2.0,
        "reisebus": 2.0,
        "lkw": 2.0,
        "lkw_anhaenger": 4.0,
        "sonstige": 4.0,
    },
    "OHNE VLSA": {
        "rad": 0.5,
        "einspurig": 1.0,
        "pkw": 1.0,
        "linienbus": 1.5,
        "reisebus": 1.5,
        "lkw": 1.5,
        "lkw_anhaenger": 2.0,
        "sonstige": 1.5,
    },
}

# 12 directions possible (R1..R12) -> endpoints (i,j)
DIR_TO_FLOW = {
    1:  (1, 24),
    2:  (2, 17),
    3:  (3, 10),
    4:  (6, 7),
    5:  (8, 23),
    6:  (16, 9),
    7:  (13, 12),
    8:  (14, 5),
    9:  (15, 22),
    10: (18, 19),
    11: (20, 11),
    12: (4, 21),
}

# Rectangles: define as unordered so orientation doesn't matter
RECT_FLOWS_U = {tuple(sorted(p)) for p in [(2, 17), (5, 14), (8, 23), (11, 20)]}

# Draw params
C = np.array([0.0, 0.0])    # center
R = 4.0                     # radius for placing points  
d = 1                       # distance from center line to middle point of group
inward = 0.9                # inward control for bezier curves (curvature strength)
inward_straight = 0.35      # schwächere Krümmung für "geradeaus"-Relationen (RECT_FLOWS_U)

FILL = "lightblue"
EDGE = "none"
EDGE_LW = 0.0

# Darstellung sehr kleiner bzw. leerer Relationen
MIN_POSITIVE_FLOW_WIDTH = 0.05    # Mindestbreite bei mehr als 0 Fahrzeugen
ZERO_FLOW_LAYOUT_WIDTH = 0.05    # Platz für eine Relation mit 0 Fahrzeugen
ZERO_FLOW_LINEWIDTH = 1.5   # Breite der gestrichelten Linie
ZERO_FLOW_DASH_PATTERN = (0, (5, 4))
ARROW_LABEL_MIN_WIDTH = 0.25

# Group slots
# Dict mapping (side, type) → list of port IDs
GROUP_SLOTS = {
    ("N", "dep"): [1, 2, 3],
    ("N", "arr"): [6, 5, 4],

    ("E", "dep"): [7, 8, 9],
    ("E", "arr"): [12, 11, 10],

    ("S", "dep"): [13, 14, 15],
    ("S", "arr"): [18, 17, 16],

    ("W", "dep"): [19, 20, 21],
    ("W", "arr"): [24, 23, 22],
}

# Dict side → Matplotlib color name.
SIDE_COLOR = {"N": "tab:blue", "E": "tab:orange", "S": "tab:green", "W": "tab:red"}

def fmt_int_dot(value):
    """
    Formatiert ganze Zahlen mit Punkt als Tausendertrennzeichen.
    Beispiel: 1000 -> 1.000
    """
    return f"{int(round(float(value))):,}".replace(",", ".")


def get_side_normal(side):
    """
    Gibt die feste Außennormale einer Zufahrt zurück.
    """
    return {
        "N": np.array([0.0, +1.0]),
        "E": np.array([+1.0, 0.0]),
        "S": np.array([0.0, -1.0]),
        "W": np.array([-1.0, 0.0]),
    }[side]


def get_side_tangent(side):
    nrm = get_side_normal(side)
    return np.array([-nrm[1], nrm[0]])

def get_text_rotation(side):
    if side in ("N", "S"):
        return 0
    return 270
    
def get_flow_label_rotation(side):
    # Vertikale Beschriftungen einheitlich von rechts lesbar.
    if side in ("N", "S"):
        return 270
    return 0

def add_flow_label_before_start(
    ax,
    A,
    side,
    text,
    color,
    fontsize=12,
    occupied_label_boxes=None,
    collision_step=0.15,
    max_collision_steps=20,
):
    """
    Zeichnet den Relationswert am Beginn des Relationsbandes.

    Verhalten:
    - Die Beschriftung ist längs zur jeweiligen Zufahrt ausgerichtet.
    - Alle Texte beginnen an derselben radialen Position.
    - Bei Kollisionen werden sie ausschließlich quer zum Pfeil
      entlang des Querschnitts verschoben.
    """
    A = np.asarray(A, dtype=float)

    if occupied_label_boxes is None:
        occupied_label_boxes = []

    # Abstand vom Relationsanfang nach außen
    if "|" in str(text):
        base_distance = 0.35
    else:
        base_distance = 0.35

    nrm = get_side_normal(side)
    tan = get_side_tangent(side)
    angle_deg = get_flow_label_rotation(side)

    # Textverankerung:
    # Der Text wächst jeweils vom Relationsanfang nach außen.
    horizontal_alignment = {
        "N": "right",
        "E": "left",
        "S": "left",
        "W": "right",
    }[side]

    # Einheitliche radiale Ausgangslinie
    base_pos = A + base_distance * nrm

    text_artist = None
    final_box = None

    for step_index in range(max_collision_steps + 1):

        # Kollisionsausweichung wie ursprünglich:
        # quer zum Pfeil beziehungsweise entlang des Querschnitts
        transverse_offset = step_index * collision_step
        pos = base_pos + transverse_offset * tan

        if text_artist is not None:
            text_artist.remove()

        text_artist = ax.text(
            pos[0],
            pos[1],
            str(text),
            rotation=angle_deg,
            rotation_mode="anchor",
            ha=horizontal_alignment,
            va="center",
            fontsize=fontsize,
            color=color,
            zorder=50,
            fontweight="bold",
            clip_on=False,
        )

        ax.figure.canvas.draw()
        renderer = get_figure_renderer(ax.figure)

        current_box = text_artist.get_window_extent(
            renderer=renderer
        )

        current_box_with_padding = current_box.expanded(
            1.25,
            1.30,
        )

        collision_found = any(
            current_box_with_padding.overlaps(existing_box)
            for existing_box in occupied_label_boxes
        )

        if not collision_found:
            final_box = current_box_with_padding
            break

    # Falls auch die letzte getestete Position kollidiert,
    # wird diese dennoch registriert.
    if final_box is None and text_artist is not None:
        renderer = get_figure_renderer(ax.figure)

        final_box = text_artist.get_window_extent(
            renderer=renderer
        ).expanded(
            1.25,
            1.30,
        )

    if final_box is not None:
        occupied_label_boxes.append(final_box)

    return text_artist

def add_side_span_line_and_total(ax, P, W, dep_ids, arr_ids, side, total_text,
                                d_NS, d_WE,
                                line_lw=3, line_color="black",
                                text_color="black", text_fontsize=18,
                                offset_line=0.9, offset_text=1.2,
                                zorder=40,
                                street_name: str = "",
                                street_fontsize: Optional[int] = None,
                                street_gap: float = 0.45,
                                total_gap: float = 0.45,
                                ):
    """
    Zeichnet den Querschnittsstrich inkl. Straßenname und Summe.

    Reihenfolge:
    außen: Straßenname
    Mitte: Strich
    innen: Summe
    """

    dep_ids = list(dep_ids) if dep_ids else []
    arr_ids = list(arr_ids) if arr_ids else []

    real_pids = [
        pid
        for pid in (dep_ids + arr_ids)
        if pid in P and pid in W
    ]

    if len(real_pids) == 0:
        return

    nrm = get_side_normal(side)
    tan = get_side_tangent(side)
    rotation = get_text_rotation(side)

    extents = []
    normal_values = []

    for pid in real_pids:
        pt = np.array(P[pid], float)
        s = float(np.dot(pt, tan))
        o = float(np.dot(pt, nrm))
        half = float(W[pid]) / 2.0

        extents.append((s - half, s + half))
        normal_values.append(o)

    min_s = min(e[0] for e in extents)
    max_s = max(e[1] for e in extents)
    mean_o = float(np.mean(normal_values))

    # Strich etwas nach außen verschieben
    line_o = mean_o + offset_line

    p1_line = min_s * tan + line_o * nrm
    p2_line = max_s * tan + line_o * nrm

    ax.plot(
        [p1_line[0], p2_line[0]],
        [p1_line[1], p2_line[1]],
        linewidth=line_lw,
        color=line_color,
        solid_capstyle="round",
        zorder=zorder,
        clip_on=False
    )

    mid_line = 0.5 * (p1_line + p2_line)

    # nrm zeigt immer nach außen.
    # Neue Reihenfolge von innen nach außen:
    # Relationsbänder -> Querschnittsstrich -> Gesamtsumme -> Straßenname
    total_pos = mid_line + total_gap * nrm
    street_pos = mid_line + (total_gap + street_gap) * nrm

    rotation = get_text_rotation(side)

    # Summe außerhalb des Querschnittsstrichs zeichnen
    ax.text(
        total_pos[0],
        total_pos[1],
        str(total_text),
        ha="center",
        va="center",
        fontsize=text_fontsize,
        color=text_color,
        fontweight="bold",
        rotation=rotation,
        rotation_mode="anchor",
        zorder=zorder + 2,
        clip_on=False,
    )

    # Straßenname außen zeichnen
    street_name = str(street_name).strip() if street_name is not None else ""

    if street_fontsize is None:
        street_fontsize = text_fontsize

    if street_name:
        ax.text(
            street_pos[0],
            street_pos[1],
            street_name,
            ha="center",
            va="center",
            fontsize=street_fontsize,
            color=text_color,
            fontweight="normal",
            rotation=rotation,
            rotation_mode="anchor",
            zorder=zorder + 3,
            clip_on=False,
        )

def compute_side_sums(flows_present, kfz_array):
    """
    Compute sums per side for departing and arriving traffic.

    Returns:
      dep_kfz, arr_kfz, total_kfz
      and if bike_array provided: dep_bike, arr_bike, total_bike
    """

    # Map port id -> side for dep and arr ports
    dep_pid_to_side = {}
    arr_pid_to_side = {}
    for side in ("N", "E", "S", "W"):
        for pid in GROUP_SLOTS[(side, "dep")]:
            dep_pid_to_side[pid] = side
        for pid in GROUP_SLOTS[(side, "arr")]:
            arr_pid_to_side[pid] = side

    dep_kfz = {s: 0.0 for s in ("N", "E", "S", "W")}
    arr_kfz = {s: 0.0 for s in ("N", "E", "S", "W")}

    # --- KFZ sums ---
    for (i, j), kfz in zip(flows_present, kfz_array):
        if i in dep_pid_to_side and j in arr_pid_to_side:
            dep_side = dep_pid_to_side[i]
            arr_side = arr_pid_to_side[j]
        elif j in dep_pid_to_side and i in arr_pid_to_side:
            dep_side = dep_pid_to_side[j]
            arr_side = arr_pid_to_side[i]
        else:
            continue

        dep_kfz[dep_side] += float(kfz)
        arr_kfz[arr_side] += float(kfz)

    total_kfz = {s: dep_kfz[s] + arr_kfz[s] for s in ("N", "E", "S", "W")}
    
    return {
        "dep_kfz": dep_kfz,
        "arr_kfz": arr_kfz,
        "total_kfz": total_kfz,
    }

def calculate_width(direction_dic, width_min, width_max, tmin, tmax, gamma=1.0, PKW_Einheiten=False):
    """
    Calculate width array based on KFZ values using a GLOBAL mapping:
      - tmin -> width_min
      - tmax -> width_max
      - in between proportional (non-linear with gamma)

    gamma = 1.0  -> linear
    gamma < 1.0  -> more resolution for small flows (recommended: 0.5)
    gamma > 1.0  -> more resolution for large flows
    """
    if not PKW_Einheiten:
        traffic = np.array([sub_dic["kfz"] for sub_dic in direction_dic.values()], dtype=float)  #Extracts all kfz values from the dictionary (in iteration order)
    else:
        traffic = np.array([sub_dic["PKW_Total"] for sub_dic in direction_dic.values()], dtype=float)  #Extracts all PKW_Einheiten values from the dictionary (in iteration order)

    if traffic.size == 1 or np.isclose(tmax, tmin):     #If only one flow or all flows equal (no scale), give them all mid-width
        return np.round(np.full_like(traffic, (width_min + width_max) / 2.0), 2)

    norm = (traffic - tmin) / (tmax - tmin)     #Normalize to [0,1]
    norm = np.clip(norm, 0.0, 1.0)      #Ensure norm within [0,1]

    widths = width_min + (norm ** gamma) * (width_max - width_min)      #Scale to [width_min, width_max] using gamma correction
    return np.round(widths, 2)      #Returns all widths 

def numeric_block_sum(df, row_start, row_end, col_start, col_end):
    """
    Summiert einen DataFrame-Bereich robust.

    Leere Zellen und nichtnumerische Texte werden als 0 behandelt.
    row_end und col_end sind wie bei iloc exklusiv.
    """
    block = df.iloc[row_start:row_end, col_start:col_end]

    numeric_block = block.apply(
        lambda column: pd.to_numeric(column, errors="coerce")
    ).fillna(0.0)

    return float(numeric_block.to_numpy().sum())

def build_direction_dic(sheets, start_idx, n_rows=4):
    """
    Summiert die Verkehrswerte je Relation für einen frei wählbaren Zeitraum.

    Parameter
    ----------
    sheets:
        Dictionary der eingelesenen Excel-Blätter.

    start_idx:
        Erste auszuwertende DataFrame-Zeile.

    n_rows:
        Anzahl der auszuwertenden Zeitintervalle.
        Standardmäßig 4 Zeilen = 1 Stunde bei 15-Minuten-Intervallen.
    """
    if n_rows < 1:
        raise ValueError("n_rows muss mindestens 1 sein.")

    end_idx = start_idx + n_rows
    direction_dic = {}

    for sheet_name, df in sheets.items():
        if not sheet_name.startswith("R"):
            continue

        # Fahrrad + gesamter motorisierter Verkehr
        total_sum = numeric_block_sum(
            df,
            start_idx,
            end_idx,
            1,
            9,
        )

        # Kfz ohne Fahrräder: Spalten C bis I
        kfz_sum = numeric_block_sum(
            df,
            start_idx,
            end_idx,
            2,
            9,
        )

        # Schwerverkehr: Spalten E bis I
        sv_sum = numeric_block_sum(
            df,
            start_idx,
            end_idx,
            4,
            9,
        )

        # Fahrräder: Spalte B
        rad_sum = numeric_block_sum(
            df,
            start_idx,
            end_idx,
            1,
            2,
        )

        direction_dic[sheet_name] = {
            "total": total_sum,
            "kfz": kfz_sum,
            "rad": rad_sum,
            "Summe_SV": sv_sum,
        }

    return direction_dic

def PKW_Einheiten_traffic_dic(
    sheets,
    start_idx,
    n_rows=4,
    vlsa_mode="MIT VLSA",
):
    """
    Berechnet Pkw-Einheiten für einen beliebigen Zeitraum.
    """

    if vlsa_mode not in PKW_E_FAKTOREN:
        raise ValueError(
            f"Ungültige VLSA-Auswahl: {vlsa_mode}"
        )

    faktoren = PKW_E_FAKTOREN[vlsa_mode]

    if n_rows < 1:
        raise ValueError("n_rows muss mindestens 1 sein.")

    end_idx = start_idx + n_rows
    dic = {}

    for sheet_name, df in sheets.items():
        if not sheet_name.startswith("R"):
            continue

        block = df.iloc[start_idx:end_idx]

        rad = (
            pd.to_numeric(
                block.iloc[:, 1],
                errors="coerce",
            ).fillna(0).sum()
            * faktoren["rad"]
        )

        einsp = (
            pd.to_numeric(
                block.iloc[:, 2],
                errors="coerce",
            ).fillna(0).sum()
            * faktoren["einspurig"]
        )

        pkw = (
            pd.to_numeric(
                block.iloc[:, 3],
                errors="coerce",
            ).fillna(0).sum()
            * faktoren["pkw"]
        )

        linienbus = (
            pd.to_numeric(
                block.iloc[:, 4],
                errors="coerce",
            ).fillna(0).sum()
            * faktoren["linienbus"]
        )

        reisebus = (
            pd.to_numeric(
                block.iloc[:, 5],
                errors="coerce",
            ).fillna(0).sum()
            * faktoren["reisebus"]
        )

        lkw = (
            pd.to_numeric(
                block.iloc[:, 6],
                errors="coerce",
            ).fillna(0).sum()
            * faktoren["lkw"]
        )

        lkw_anh = (
            pd.to_numeric(
                block.iloc[:, 7],
                errors="coerce",
            ).fillna(0).sum()
            * faktoren["lkw_anhaenger"]
        )

        sonstige = (
            pd.to_numeric(
                block.iloc[:, 8],
                errors="coerce",
            ).fillna(0).sum()
            * faktoren["sonstige"]
        )

        dic[sheet_name] = {
            "PKW_Total": round(
                rad
                + einsp
                + pkw
                + linienbus
                + reisebus
                + lkw
                + lkw_anh
                + sonstige
            ),
            "Summe_SV": round(
                linienbus
                + reisebus
                + lkw
                + lkw_anh
                + sonstige
            ),
        }

    return dic



# --------------------- FG / RAD QUERUNGEN ---------------------

def normalize_text(value):
    if value is None or pd.isna(value):
        return ""
    return (
        str(value).strip().upper()
        .replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE")
        .replace("ß", "SS")
    )

def find_fg_sheet(sheets):
    """Findet ein Blatt mit Fußgänger-/Radquerungen."""
    candidates = []
    for sheet_name, df in sheets.items():
        n = normalize_text(sheet_name).replace("_", "").replace(".", "").replace(" ", "")
        if n in {"FG", "FGRAD", "FUSSG", "FUSSGAENGER"}:
            return sheet_name, df
        if "FG" in n or "FUSS" in n:
            candidates.append((sheet_name, df))
    return candidates[0] if candidates else (None, None)

def _find_fg_header_rows(df):
    """Sucht die zwei Kopfzeilen der FG-Tabelle dynamisch."""
    max_scan = min(len(df), 30)
    for r in range(max_scan - 1):
        row1 = [normalize_text(v) for v in df.iloc[r].tolist()]
        row2 = [normalize_text(v) for v in df.iloc[r + 1].tolist()]
        has_mode = any(("FG" in v or "RAD" in v or "FUSS" in v) for v in row1)
        has_time = any(v == "ZEIT" for v in row2)
        if has_mode and has_time:
            return r, r + 1
    return None, None

def detect_fg_columns(df):
    """
    Erkennt FG-/Radspalten in unterschiedlichen Zählblatt-Layouts.
    Unterstützt u.a.:
      - Zeile 1: FG FG FG FG Rad Rad ... / Zeile 2: A B C D A B ...
      - Zeile 1: FG A, leer, FG C, leer ... / Zeile 2: FG, Rad, FG, Rad ...
      - Zeile 1: FG, Rad, Rad ... / Zeile 2: C, RW2, RW3 ...
    """
    h1, h2 = _find_fg_header_rows(df)
    if h1 is None:
        return [], None

    detected = []
    active_group = None
    active_relation = None

    for col in range(1, df.shape[1]):
        top = normalize_text(df.iloc[h1, col])
        sub = normalize_text(df.iloc[h2, col])

        # Ab der ersten Aggregatspalte beginnen Hilfs-/Spitzenstundenspalten.
        # Diese gehören nicht mehr zu den eigentlichen Querungsrelationen.
        combined = f"{top} {sub}"
        if any(x in combined for x in ["15 MIN", "30 MIN", "1 STD", "/ 15", "/ 30", "/ 1"]):
            break

        mode = None
        relation = None

        # Layout "FG A" + Unterzeile "FG/Rad"
        m = re.match(r"^(FG|FUSS(?:GAENGER)?)\s*([A-Z0-9_-]+)$", top)
        if m:
            active_relation = m.group(2)
            relation = active_relation
            if "RAD" in sub or sub.startswith("RW"):
                mode = "RAD"
            elif "FG" in sub or "FUSS" in sub:
                mode = "FG"
            else:
                mode = "FG"
        else:
            if "FG" in top or "FUSS" in top:
                active_group = "FG"
            elif "RAD" in top:
                active_group = "RAD"

            if sub and sub not in {"FG", "RAD"}:
                relation = sub
                mode = active_group
            elif sub in {"FG", "RAD"}:
                mode = sub
                relation = active_relation

        if not relation or mode not in {"FG", "RAD"}:
            continue

        # Nur plausible Relationsbezeichnungen übernehmen
        if relation in {"FG/R", "SUMME", "ZEIT"}:
            continue

        detected.append({
            "column": col,
            "mode": mode,
            "relation": relation,
            "key": f"{mode}:{relation}",
        })

    # Duplikate entfernen
    unique = []
    seen = set()
    for item in detected:
        marker = (item["column"], item["mode"], item["relation"])
        if marker not in seen:
            seen.add(marker)
            unique.append(item)
    return unique, h2 + 1

def find_sum_row_index(df):
    for idx, value in enumerate(df.iloc[:, 0]):
        if isinstance(value, str) and "SUMME" in value.upper():
            return idx
    return len(df)

def build_fg_values(fg_df, fg_columns, start_idx, n_rows):
    end_idx = min(start_idx + n_rows, len(fg_df))
    result = {}
    for item in fg_columns:
        value = pd.to_numeric(
            fg_df.iloc[start_idx:end_idx, item["column"]],
            errors="coerce",
        ).fillna(0.0).sum()
        key = item["key"]
        result[key] = {
            "key": key,
            "mode": item["mode"],
            "relation": item["relation"],
            "value": float(value),
        }
    return result

def add_fg_crossing(
    ax,
    side,
    fg_value=0.0,
    rad_value=0.0,
    color="#333333",
    linewidth=1.8,
    fontsize=11,
    radial_offset=0.34,
    show_fg=True,
    show_rad=True,
):
    """
    Zeichnet eine kurze gestrichelte Querung knapp außerhalb der
    Relationsanfänge/-enden. Die Beschriftung liegt auf der Innenseite
    der Linie, also immer in Richtung Kreuzungsmittelpunkt.
    """
    nrm = get_side_normal(side)
    tan = get_side_tangent(side)

    # Knapp außerhalb der Port-/Pfeilbasis bei Radius R.
    center = nrm * (R + radial_offset)

    # Kürzer als bisher, damit die Querung nur den Straßenquerschnitt markiert.
    half_length = 0.95
    start = center - half_length * tan
    end = center + half_length * tan

    ax.plot(
        [start[0], end[0]],
        [start[1], end[1]],
        color=color,
        linewidth=linewidth,
        linestyle=(0, (4, 3)),
        zorder=70,
        clip_on=False,
    )

    label_parts = []
    if show_fg and fg_value is not None:
        label_parts.append(f"FG {fmt_int_dot(fg_value)}")
    if show_rad and rad_value is not None:
        label_parts.append(f"Rad {fmt_int_dot(rad_value)}")

    if not label_parts:
        return

    label = " - ".join(label_parts)

    # Unterhalb/innenseitig der Querung, immer Richtung Kreuzungsmittelpunkt.
    label_pos = center - 0.22 * nrm
    rotation = 270 if side in ("E", "W") else 0

    ax.text(
        label_pos[0],
        label_pos[1],
        label,
        ha="center",
        va="center",
        rotation=rotation,
        rotation_mode="anchor",
        fontsize=fontsize,
        color=color,
        fontweight="bold",
        zorder=71,
        clip_on=False,
    )


def draw_fg_relations(
    ax,
    fg_relations,
    show_fg=True,
    show_rad=True,
):
    """Fasst FG und Rad je Querung zusammen und zeichnet sie."""
    if not fg_relations or (not show_fg and not show_rad):
        return

    grouped = {}
    for item in fg_relations:
        side = item.get("side")
        if side not in {"N", "E", "S", "W"}:
            continue

        relation = str(item.get("relation", "")).strip()
        group_key = (side, relation)
        grouped.setdefault(group_key, {"FG": None, "RAD": None})
        grouped[group_key][item.get("mode", "FG")] = float(item.get("value", 0.0))

    # Bei mehreren Querungen auf derselben Seite leicht nach außen staffeln.
    side_counts = {s: 0 for s in ("N", "E", "S", "W")}
    for (side, _relation), values in grouped.items():
        idx = side_counts[side]
        side_counts[side] += 1

        fg_value = values.get("FG") if show_fg else None
        rad_value = values.get("RAD") if show_rad else None

        if fg_value is None and rad_value is None:
            continue

        add_fg_crossing(
            ax,
            side,
            fg_value=fg_value,
            rad_value=rad_value,
            radial_offset=0.34 + idx * 0.28,
            show_fg=show_fg,
            show_rad=show_rad,
        )


def _sv_stats(total: float, sv: float) -> Dict[str, float]:
    total = float(total)
    sv = float(sv)
    share = (sv / total * 100.0) if total > 0 else 0.0
    return {"total": total, "sv": sv, "sv_share_pct": round(share, 2)}

# --------------------- GEOMETRY HELPERS ---------------------
def segment_rectangle(A, B, width):
    """Create a rectangular segment between points A and B with given width."""
    A = np.asarray(A, float)
    B = np.asarray(B, float)
    v = B - A
    L = np.hypot(v[0], v[1])
    u = v / L
    n = np.array([-u[1], u[0]])
    off = (width / 2.0) * n
    return np.vstack([A + off, B + off, B - off, A - off])

def inward_ctrl(Z, P, inward_amount):
    """Calculate inward control point for bezier curves."""
    return P + inward_amount * (Z - P)

def bezier_points(P0, P1, P2, P3, n=250):
    """Generate points along a bezier curve."""
    t = np.linspace(0, 1, n)[:, None]
    return ((1-t)**3)*P0 + 3*((1-t)**2)*t*P1 + 3*(1-t)*(t**2)*P2 + (t**3)*P3

def bezier_tangent(P0, P1, P2, P3, n=250):
    """Calculate tangents along a bezier curve."""
    t = np.linspace(0, 1, n)[:, None]
    return (3*((1-t)**2)*(P1-P0) + 6*(1-t)*t*(P2-P1) + 3*(t**2)*(P3-P2))

def bezier_ribbon_polygon(P0, P1, P2, P3, width, n=250, eps=1e-12):
    """Create a ribbon polygon along a bezier curve."""
    pts = bezier_points(P0, P1, P2, P3, n)
    tan = bezier_tangent(P0, P1, P2, P3, n)

    L = np.maximum(np.hypot(tan[:, 0], tan[:, 1]), eps)
    u = tan / L[:, None]
    nrm = np.column_stack([-u[:, 1], u[:, 0]])

    off = (width / 2.0) * nrm
    left = pts + off
    right = pts - off
    return np.vstack([left, right[::-1]])

def add_patch(ax, poly, color=None):
    """Add a polygon patch to the axes."""
    ax.add_patch(
        Polygon(
            poly, closed=True,
            facecolor=color if color is not None else FILL,
            edgecolor=EDGE, linewidth=EDGE_LW
        )
    )

def add_bezier_ribbon(ax, A, B, Z, width, color):
    """Add a bezier ribbon between A and B via Z."""
    P0, P3 = A, B
    P1 = inward_ctrl(Z, A, inward)
    P2 = inward_ctrl(Z, B, inward)
    poly = bezier_ribbon_polygon(P0, P1, P2, P3, width=width)
    add_patch(ax, poly, color)

def add_zero_flow_line(ax, A, B, Z, color, straight=False):
    """
    Zeichnet eine Relation mit 0 Fahrzeugen als gestrichelte Mittellinie.

    Geradeausrelationen werden gerade gezeichnet.
    Abbieger werden entlang ihrer Bezierkurve gezeichnet.
    """
    A = np.asarray(A, float)
    B = np.asarray(B, float)

    if straight:
        pts = np.vstack([A, B])
    else:
        P0, P3 = A, B
        P1 = inward_ctrl(Z, A, inward)
        P2 = inward_ctrl(Z, B, inward)
        pts = bezier_points(P0, P1, P2, P3, n=250)

    ax.plot(
        pts[:, 0],
        pts[:, 1],
        color=color,
        linewidth=ZERO_FLOW_LINEWIDTH,
        linestyle=ZERO_FLOW_DASH_PATTERN,
        alpha=0.75,
        dash_capstyle="round",
        zorder=8,
        clip_on=False,
    )

def place_group_variable(P, fixed_axis, fixed_val, ids, mid_val, dir_to_axis, W):
    """Place points for a group of slots.
    - fixed axis: 0 for x fixed, 1 for y fixed
    - fixed val: value on fixed axis 
        (N: fixed axis = 1, fixed_val = +R, 
         S: fixed axis = 1, fixed_val = -R,
         E: fixed axis = 0, fixed_val = +R,
         W: fixed axis = 0, fixed_val = -R)
    - ids: list of point IDs ([1,2,3], etc.)
    - mid_val: midpoint value on the variable axis (+d or -d)
    - dir_to_axis: direction to the center axis (1 or -1)
    - W: width dictionary
    """
    if not ids: #if group empty, exit 
        return

    widths = [W[i] for i in ids]      #Get widths for all points in the group, order matter, determines left-to-right placement
    span = sum(widths)                #Total span of the group (sum of widths)

    offsets = []
    acc = -span / 2.0                  #Start at negative half-span, running currently accumulated offset
    for w in widths:
        offsets.append(acc + w / 2.0)
        acc += w

    #Point placement
    for pid, off in zip(ids, offsets):
        pt = np.array([0.0, 0.0], float)
        pt[fixed_axis] = fixed_val
        pt[1 - fixed_axis] = mid_val + dir_to_axis * off     #Position on variable axis, works such that the center of the group lays at mid_val from center line
        P[pid] = C + pt

def align_rect_pairs_shift_groups(P: Dict[int, np.ndarray], pairs: List[Tuple[int, int]]) -> None:
    """
    Post-process already-computed port positions P so that the rectangle pairs
    (2,17), (5,14), (8,23), (11,20) are aligned.

    Alignment rule (per pair):
      - Use the midpoint of the pair's *variable* coordinate
      - Apply the required delta to the ENTIRE group (side, dep/arr) of each endpoint,
        so neighboring ports move together and flows still start/end flush.

    Variable axis:
      - N/S groups vary in x  -> axis 0
      - E/W groups vary in y  -> axis 1

    Requires GROUP_SLOTS to be defined (as in your module).
    """
    # --- local helpers (kept inside this single function) ---
    def _pid_to_group_key(pid):
        for side in ("N", "E", "S", "W"):
            if pid in GROUP_SLOTS[(side, "dep")]:
                return (side, "dep")
            if pid in GROUP_SLOTS[(side, "arr")]:
                return (side, "arr")
        return None

    def _var_axis_from_side(side):
        return 0 if side in ("N", "S") else 1

    # --- apply constraints ---
    for a, b in pairs:
        if a not in P or b not in P:
            continue

        ga = _pid_to_group_key(a)
        gb = _pid_to_group_key(b)
        if ga is None or gb is None:
            continue

        side_a, _ = ga
        side_b, _ = gb
        ax_a = _var_axis_from_side(side_a)
        ax_b = _var_axis_from_side(side_b)
        if ax_a != ax_b:
            # safety: don't try to align across different variable axes
            continue
        var_axis = ax_a

        Pa = np.array(P[a], float)
        Pb = np.array(P[b], float)
        mid = 0.5 * (Pa[var_axis] + Pb[var_axis])

        # shift full group containing a
        delta_a = mid - Pa[var_axis]
        for pid in GROUP_SLOTS[ga]:
            if pid in P:
                Ppid = np.array(P[pid], float)
                Ppid[var_axis] += delta_a
                P[pid] = Ppid

        # shift full group containing b
        delta_b = mid - Pb[var_axis]
        for pid in GROUP_SLOTS[gb]:
            if pid in P:
                Ppid = np.array(P[pid], float)
                Ppid[var_axis] += delta_b
                P[pid] = Ppid

    """
    Force each (a,b) pair to share the same 'variable' coordinate by setting
    both to the midpoint of their current variable coordinate.

    Variable axis:
      - If the points are on N/S (y is +/-R), variable axis is x (axis 0)
      - If the points are on E/W (x is +/-R), variable axis is y (axis 1)

    This runs AFTER P has been computed.
    """
    for a, b in pairs:
        if a not in P or b not in P:
            continue

        Pa = np.array(P[a], float)
        Pb = np.array(P[b], float)

        # Decide if this pair is N/S-like or E/W-like based on which coordinate is "fixed"
        # N/S points have y near +/-R (so y has large abs), E/W points have x near +/-R.
        if abs(Pa[1]) >= abs(Pa[0]) and abs(Pb[1]) >= abs(Pb[0]):
            var_axis = 0  # align x
        else:
            var_axis = 1  # align y

        mid = 0.5 * (Pa[var_axis] + Pb[var_axis])

        Pa[var_axis] = mid
        Pb[var_axis] = mid

        P[a] = Pa
        P[b] = Pb

def add_label_background_rect(ax, outer_center, span_width, tan_vec, inward_vec, text,
                                fontsize, color="#666666", zorder=9,
                                depth_pad=1.6, min_depth=0.32, min_width=ARROW_LABEL_MIN_WIDTH, ):
    """
    Zeichnet ein graues Rechteck an der Basis des Pfeils.
    - Breite (entlang tan_vec) = grafische Breite der Relation(en) an der Basis
    - Tiefe (entlang inward_vec) = an die Textlänge angepasst, wächst nach INNEN
      (Richtung Kreuzungsmitte), damit es nicht mit weiter außen liegenden
      Beschriftungen (Einzelwerte, Straßennamen, Summen) kollidiert.
    Gibt den Mittelpunkt des Rechtecks zurück (für die Textplatzierung).
    """
    outer_center = np.asarray(outer_center, float)
    tan_vec = np.asarray(tan_vec, float)
    inward_vec = np.asarray(inward_vec, float)

    depth = max(len(str(text)), 1) * fontsize * 0.013 * depth_pad
    depth = max(depth, min_depth)

    half_w = max(span_width, min_width) / 2.0
    inner_center = outer_center + depth * inward_vec
    rect_center = outer_center + (depth / 2.0) * inward_vec

    corners = np.vstack([
        outer_center - half_w * tan_vec,
        outer_center + half_w * tan_vec,
        inner_center + half_w * tan_vec,
        inner_center - half_w * tan_vec,
    ])

    ax.add_patch(
        Polygon(corners, closed=True, facecolor=color, edgecolor="none", zorder=zorder)
    )
    return rect_center

def add_group_arrow(ax, P, W, group_ids, side, outward=True, color="#666666", zorder=10,
                    label: Optional[str] = None, label_color: str = "white",
                    label_fontsize: int = 12):
    """
    Add an arrow for a group of slots.
    Der Pfeil wird mit dem jeweiligen Arm mitgedreht.
    """
    ids = list(group_ids)
    if not ids:
        return

    nrm = get_side_normal(side)
    tan = get_side_tangent(side)

    s_values = [float(np.dot(P[i], tan)) for i in ids]

    min_idx = int(np.argmin(s_values))
    max_idx = int(np.argmax(s_values))

    pid_min = ids[min_idx]
    pid_max = ids[max_idx]

    P_min = np.array(P[pid_min], float)
    P_max = np.array(P[pid_max], float)

    base_min = P_min - tan * (float(W[pid_min]) / 2.0)
    base_max = P_max + tan * (float(W[pid_max]) / 2.0)

    # Falls eine Beschriftung vorhanden ist, muss die Pfeilbasis
    # mindestens so breit sein wie das graue Beschriftungsrechteck.
    if label is not None:
        label_text = str(label)

        # Mindestbreite des grauen Rechtecks.
        # Entspricht dem min_width-Wert in add_label_background_rect().
        required_base_width = ARROW_LABEL_MIN_WIDTH

        current_base_width = float(
            np.linalg.norm(base_max - base_min)
        )

        if current_base_width < required_base_width:
            additional_width = (
                required_base_width - current_base_width
            ) / 2.0

            base_min = base_min - tan * additional_width
            base_max = base_max + tan * additional_width

    base_center = 0.5 * (base_min + base_max)

    if outward:
        tip = base_center + nrm * 0.5
    else:
        tip = base_center - nrm * 0.5

    tri = np.vstack([tip, base_min, base_max])

    # Einfahrend (outward=False): nur Rechteck; ausfahrend: Dreieck + Rechteck
    if outward:
        ax.add_patch(
            Polygon(
                tri,
                closed=True,
                facecolor=color,
                edgecolor="none",
                zorder=zorder
            )
        )

    if label is not None:
        label_text = str(label)

        # Basis-Mittelpunkt und grafische Breite der Gruppe (= Pfeilbasis)
        base_center = 0.5 * (tri[1] + tri[2])
        span_width = float(np.linalg.norm(base_max - base_min))

        # Beschriftung wächst immer Richtung Kreuzungsmitte (innen),
        # unabhängig davon ob der Pfeil nach außen oder innen zeigt –
        # so kollidiert sie nie mit den weiter außen liegenden
        # Einzelwert-/Straßennamen-/Summen-Beschriftungen.
        inward_vec = -nrm

        fs = label_fontsize

        if side in ("N", "S"):
            label_rotation = 270
        else:
            label_rotation = 0

        # Graues Hintergrundfeld an der Basis zeichnen, exakt so breit
        # wie die Relation(en), und Textmittelpunkt davon übernehmen
        label_pos = add_label_background_rect(
            ax,
            outer_center=base_center,
            span_width=span_width,
            tan_vec=tan,
            inward_vec=inward_vec,
            text=label_text,
            fontsize=fs,
            color=color,
            zorder=zorder + 1,
        )

        ax.text(
            label_pos[0],
            label_pos[1],
            label_text,
            ha="center",
            va="center",
            fontsize=fs,
            color=label_color,
            rotation=label_rotation,
            rotation_mode="anchor",
            zorder=zorder + 2,
            fontweight="bold",
            clip_on=True,
        )

def create_plot(kfz, bike, width, flows_present, verkehrszählungsort, suffix, start_time, end_time, side_colors, d_NS, d_WE, fmt: str = "png", show_bicycle_labels: bool = True, kfz_label_fontsize: int = 12, arrow_label_fontsize: int = 12, side_total_fontsize: int = 18, street_names: Optional[Dict[str, str]] = None, fg_relations: Optional[List[Dict[str, Any]]] = None, show_fg_crossings: bool = True, show_rad_crossings: bool = True, ):
    """Create a PNG plot for given traffic and width data."""
    # Update SIDE_COLOR with user-provided side_colors
    if side_colors:
        SIDE_COLOR.update(side_colors)

    # Verkehrswerte je Relation
    flow_kfz = {
        (i, j): float(v)
        for (i, j), v in zip(flows_present, kfz)
    }

    flow_bike = {
        (i, j): float(v)
        for (i, j), v in zip(flows_present, bike)
    }

    # Ursprünglich berechnete Breiten
    raw_flow_width = {
        (i, j): float(w)
        for (i, j), w in zip(flows_present, width)
    }

    # Sichtbare Breite und Layoutbreite getrennt behandeln:
    # - jede positive Relation bekommt eine Mindestbreite
    # - eine Null-Relation bekommt kein Band, reserviert aber etwas Platz
    flow_width = {}
    layout_flow_width = {}

    for flow in flows_present:
        traffic_value = flow_kfz[flow]
        raw_width = raw_flow_width[flow]

        if traffic_value <= 0:
            # Kein gefülltes Band zeichnen
            flow_width[flow] = 0.0

            # Trotzdem Platz in der Anordnung reservieren
            layout_flow_width[flow] = ZERO_FLOW_LAYOUT_WIDTH
        else:
            visible_width = max(
                raw_width,
                MIN_POSITIVE_FLOW_WIDTH,
            )

            flow_width[flow] = visible_width
            layout_flow_width[flow] = visible_width

    # Portbreiten für die geometrische Anordnung
    W = {}

    for (i, j), w in layout_flow_width.items():
        W[i], W[j] = w, w

    active_points = set(W.keys())
    show_departure_labels = True

    # Active groups, only include points that are active
    GROUP_ACTIVE = {
        key: [pid for pid in values if pid in active_points]
        for key, values in GROUP_SLOTS.items()
    }

    # Colors
    departing_points = set()
    pid_to_side = {}
    point_to_color = {}
    for side in ("N", "E", "S", "W"):
        for p in GROUP_ACTIVE[(side, "dep")]:
            departing_points.add(p)
            pid_to_side[p] = side
            point_to_color[p] = SIDE_COLOR[side]
            # Vollständige Port -> Seite Zuordnung (dep UND arr), für die Elbow-Berechnung

    def flow_color(i, j, default="lightblue"):
        if i in departing_points:
            return point_to_color[i]
        if j in departing_points:
            return point_to_color[j]
        return default

    # Place points
    P = {}
    place_group_variable(P, 1, +R, GROUP_ACTIVE[("N","dep")], -d_NS, +1, W)
    place_group_variable(P, 1, +R, GROUP_ACTIVE[("N","arr")], +d_NS, -1, W)

    place_group_variable(P, 0, +R, GROUP_ACTIVE[("E","dep")], +d_WE, -1, W)
    place_group_variable(P, 0, +R, GROUP_ACTIVE[("E","arr")], -d_WE, +1, W)

    place_group_variable(P, 1, -R, GROUP_ACTIVE[("S","dep")], +d_NS, -1, W)
    place_group_variable(P, 1, -R, GROUP_ACTIVE[("S","arr")], -d_NS, +1, W)

    place_group_variable(P, 0, -R, GROUP_ACTIVE[("W","dep")], -d_WE, +1, W)
    place_group_variable(P, 0, -R, GROUP_ACTIVE[("W","arr")], +d_WE, -1, W)

    # --- ALIGN RECT PAIRS (post-placement) ---
    align_rect_pairs_shift_groups(
        P,
        pairs=[(2, 17), (5, 14), (8, 23), (11, 20)]
    )

    # Plot
    fig, ax = plt.subplots(figsize=(10, 10))

    pad = 1.4
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-R - pad, R + pad)
    ax.set_ylim(-R - pad, R + pad)
    ax.set_axis_off()

    fig.canvas.draw()

    occupied_flow_label_boxes = []
    pending_flow_labels = []

    # Große Relationen zuerst zeichnen.
    # Kleine Relationen und Null-Linien werden danach darüber gezeichnet.
    flows_draw_order = sorted(
        flows_present,
        key=lambda flow: flow_kfz[flow],
        reverse=True,
    )

    for (i, j) in flows_draw_order:
        if i not in P or j not in P:
            continue

        A, B = P[i], P[j]
        w = flow_width[(i, j)]
        col = flow_color(i, j)

        traffic_value = flow_kfz[(i, j)]
        is_straight = tuple(sorted((i, j))) in RECT_FLOWS_U

        if traffic_value <= 0:
            # Relation mit 0 Fahrzeugen:
            # nur gestrichelte Mittellinie zeichnen
            if is_straight:
                add_zero_flow_line(
                    ax,
                    A,
                    B,
                    Z=None,
                    color=col,
                    straight=True,
                )
            else:
                Z = C + np.array([A[0], B[1]])

                add_zero_flow_line(
                    ax,
                    A,
                    B,
                    Z=Z,
                    color=col,
                    straight=False,
                )

        elif is_straight:
            add_patch(
                ax,
                segment_rectangle(A, B, w),
                col,
            )

        else:
            Z = C + np.array([A[0], B[1]])

            add_bezier_ribbon(
                ax,
                A,
                B,
                Z,
                w,
                col,
            )
        # ---------- LABEL BEFORE START ----------
        if show_departure_labels:
            start_pid = None

            if i in departing_points:
                start_pid = i
            elif j in departing_points:
                start_pid = j

            if start_pid is not None:
                Astart = np.asarray(P[start_pid], float)
                side = pid_to_side[start_pid]
                kfz_val = flow_kfz[(i, j)]
                bike_val = flow_bike[(i, j)]

                if show_bicycle_labels:
                    txt = f"{fmt_int_dot(kfz_val)} | {fmt_int_dot(bike_val)}"
                else:
                    txt = f"{fmt_int_dot(kfz_val)}"

                pending_flow_labels.append({
                    "Astart": Astart,
                    "side": side,
                    "text": txt,
                    "color": col,
                })

    # ---------- SORTED FLOW LABELS ----------
    for label_side in ("N", "E", "S", "W"):

        side_labels = [
            item
            for item in pending_flow_labels
            if item["side"] == label_side
        ]

        tan = get_side_tangent(label_side)

        # Entlang der gedrehten Straßenachse sortieren.
        side_labels.sort(
            key=lambda item: float(
                np.dot(np.asarray(item["Astart"], float), tan)
            )
        )

        # Für jede Zufahrt eine eigene Kollisionsliste verwenden.
        side_occupied_boxes = []

        for item in side_labels:
            add_flow_label_before_start(
                ax,
                item["Astart"],
                item["side"],
                item["text"],
                color=item["color"],
                fontsize=kfz_label_fontsize,
                occupied_label_boxes=side_occupied_boxes,
                collision_step=0.15,
                max_collision_steps=20,
            )
        
    # ---------- GROUP ARROWS ----------
    side_sums = compute_side_sums(flows_present, kfz)
    dep_kfz_by_side = side_sums["dep_kfz"]
    arr_kfz_by_side = side_sums["arr_kfz"]
    total_kfz_by_side = side_sums["total_kfz"]

    for side in ("N", "E", "S", "W"):
        ids_dep = GROUP_ACTIVE[(side, "dep")]
        ids_arr = GROUP_ACTIVE[(side, "arr")]

        # Einfahrend: nur Summenrechteck, kein Dreieck
        if len(ids_dep) >= 1:
            dep_label = fmt_int_dot(dep_kfz_by_side.get(side, 0.0))
            add_group_arrow(
                ax, P, W, ids_dep, side, outward=False,
                color="#666666", label=dep_label,
                label_color="white", label_fontsize=arrow_label_fontsize,
            )

        # Ausfahrend: Pfeil + Summenrechteck
        if len(ids_arr) >= 1:
            arr_label = fmt_int_dot(arr_kfz_by_side.get(side, 0.0))
            add_group_arrow(
                ax, P, W, ids_arr, side, outward=True,
                color="#666666", label=arr_label,
                label_color="white", label_fontsize=arrow_label_fontsize,
            )

        if len(ids_dep) >= 1 or len(ids_arr) >= 1:
            total_val = fmt_int_dot(total_kfz_by_side.get(side, 0.0))
            add_side_span_line_and_total(
                ax, P, W, dep_ids=ids_dep, arr_ids=ids_arr, side=side,
                total_text=total_val, d_NS=d_NS, d_WE=d_WE, line_lw=3,
                text_fontsize=side_total_fontsize, offset_line=1.48,
                offset_text=1.5, total_gap=0.30, street_gap=0.42,
                street_name=(street_names or {}).get(side, ""),
            )

    # ---------- FG / RAD QUERUNGEN ----------
    draw_fg_relations(
        ax,
        fg_relations,
        show_fg=show_fg_crossings,
        show_rad=show_rad_crossings,
    )

    buf = io.BytesIO()
    if fmt in ("png", "jpg", "jpeg", "pdf"):
        fig.savefig(buf, format=fmt, transparent=True, bbox_inches="tight", dpi=300)
    else:
        fig.savefig(buf, format=fmt, transparent=True, bbox_inches="tight")

    plt.close(fig)
    safe_name = re.sub(r"[^\w\-]+", "_", str(verkehrszählungsort))
    filename = f"VZ_{safe_name}_{suffix}_{start_time}_{end_time}.{fmt}"
    return buf.getvalue(), filename

# --------------------- MAIN GENERATOR ---------------------
def generate_png_from_excel(
    excel_bytes: bytes,
    side_colors: Optional[Dict[str, str]] = None,
    d_NS: float = 1,
    d_WE: float = 1,
    w_min: float = 0.0,
    w_max: float = 1.4,
    mode: str = "KFZ",
    vlsa_mode: str = "MIT VLSA",
    use_custom_window: bool = False,
    custom_start_time=None,
    custom_end_time=None,
    show_bicycle_labels: bool = True,
    kfz_label_fontsize: int = 12,
    arrow_label_fontsize: int = 12,
    side_total_fontsize: int = 18,
    street_names: Optional[Dict[str, str]] = None,
    fg_mapping: Optional[Dict[str, str]] = None,
    show_fg_crossings: bool = True,
    show_rad_crossings: bool = True,
) -> Tuple[List[Tuple[bytes, str]], List[Tuple[bytes, str]], List[Tuple[bytes, str]], Dict[str, Any]]:

    if vlsa_mode not in PKW_E_FAKTOREN:
        raise ValueError(
            f"Ungültige VLSA-Auswahl: {vlsa_mode}"
        )

    faktoren = PKW_E_FAKTOREN[vlsa_mode]

    verkehrszählungsort = "Unbekannter Ort"

    wb = load_workbook(io.BytesIO(excel_bytes), data_only=True)

    if "Deckbl." in wb.sheetnames:
        ws_deckblatt = wb["Deckbl."]
        if ws_deckblatt["C8"].value is not None:
            verkehrszählungsort = ws_deckblatt["C8"].value
    
    # Load sheets for peak calculation
    sheets = pd.read_excel(io.BytesIO(excel_bytes), sheet_name=None, header=None)

    fg_sheet_name, fg_df = find_fg_sheet(sheets)
    fg_columns, fg_data_start_idx = (detect_fg_columns(fg_df) if fg_df is not None else ([], None))
    fg_sum_idx = find_sum_row_index(fg_df) if fg_df is not None else None
    
    first_R_df = None
    first_R_sheet_name = None

    for sheet_name, df in sheets.items():
        if not sheet_name.startswith("R"):
            continue

        traffic_block = df.iloc[13:, 1:9].apply(
            lambda column: pd.to_numeric(column, errors="coerce")
        ).fillna(0.0)

        if (traffic_block.abs() > 0).any().any():
            first_R_df = df
            first_R_sheet_name = sheet_name
            break

    if first_R_df is None:
        raise ValueError(
            "In keinem R-Blatt wurden Verkehrswerte größer null gefunden."
        )

    summe_idx = None

    for i, val in enumerate(first_R_df.iloc[:, 0]):
        if isinstance(val, str) and "SUMME" in val.upper():
            summe_idx = i
            break

    if summe_idx is None:
        raise ValueError(
            f"SUMME-Zeile im Referenzblatt {first_R_sheet_name} nicht gefunden."
        )

    summe_row_number = summe_idx + 1

    def _parse_interval(cell_value):
        if cell_value is None:
            return None, None

        text = str(cell_value).strip()
        text = text.replace("–", "-").replace("—", "-")
        text = text.replace(" ", "")

        if "-" not in text:
            return None, None

        parts = text.split("-", 1)

        if len(parts) != 2:
            return None, None

        start_text, end_text = parts

        def normalize_time(value):
            try:
                hour_text, minute_text = value.split(":", 1)

                hour = int(hour_text)
                minute = int(minute_text)

                # 24:00 als Tagesende erlauben
                if hour == 24 and minute == 0:
                    return "24:00"

                if not 0 <= hour <= 23:
                    return None

                if not 0 <= minute <= 59:
                    return None

                return f"{hour:02d}:{minute:02d}"

            except (ValueError, TypeError, AttributeError):
                return None

        start_time = normalize_time(start_text)
        end_time = normalize_time(end_text)

        if start_time is None or end_time is None:
            return None, None

        return start_time, end_time

    def _find_row_for_start(hhmm):
        target_time = datetime.strptime(
            hhmm,
            "%H:%M",
        ).strftime("%H:%M")

        for i in range(13, summe_idx):
            interval_start, _ = _parse_interval(
                first_R_df.iloc[i, 0]
            )

            if interval_start == target_time:
                return i

        raise ValueError(
            f"Startzeit {target_time} wurde in Excel nicht gefunden."
        )

    # Read directions
    direction_dic = {}
    for sheet_name in wb.sheetnames:
        if sheet_name.startswith("R"):
            ws = wb[sheet_name]
            total = sum(
                cell(ws, f"{col}{summe_row_number}")
                for col in "BCDEFGHI"
                )

            direction_dic[sheet_name] = {
                "total": total,
                "kfz": total - cell(ws, f"B{summe_row_number}"),
                "rad": cell(ws, f"B{summe_row_number}"),
                "Summe_SV": sum(
                    cell(ws, f"{col}{summe_row_number}")
                    for col in "EFGHI"
                ),
            }
    
    # PKW Einheiten
    PKW_direction_general_dic = {}

    for sheet_name in wb.sheetnames:
        if sheet_name.startswith("R"):
            ws = wb[sheet_name]

            rad = (
                cell(ws, f"B{summe_row_number}")
                * faktoren["rad"]
            )

            einsp = (
                cell(ws, f"C{summe_row_number}")
                * faktoren["einspurig"]
            )

            PKW = (
                cell(ws, f"D{summe_row_number}")
                * faktoren["pkw"]
            )

            Linienbus = (
                cell(ws, f"E{summe_row_number}")
                * faktoren["linienbus"]
            )

            Reisebus = (
                cell(ws, f"F{summe_row_number}")
                * faktoren["reisebus"]
            )

            LKW = (
                cell(ws, f"G{summe_row_number}")
                * faktoren["lkw"]
            )

            LKW_Anh = (
                cell(ws, f"H{summe_row_number}")
                * faktoren["lkw_anhaenger"]
            )

            sons = (
                cell(ws, f"I{summe_row_number}")
                * faktoren["sonstige"]
            )

            PKW_direction_general_dic[sheet_name] = {
                "PKW_Total": round(
                    rad
                    + einsp
                    + PKW
                    + Linienbus
                    + Reisebus
                    + LKW
                    + LKW_Anh
                    + sons
                ),
                "Summe_SV": round(
                    Linienbus
                    + Reisebus
                    + LKW
                    + LKW_Anh
                    + sons
                ),
            }
    
    # Find peaks
    kfz_morning_peak = 0
    kfz_afternoon_peak = 0
    for idx in range(13, summe_idx-3):  # sliding window of 4 rows
        kfz_block_sum = 0
        
        for sheet_name, df in sheets.items():
            if sheet_name.startswith("R"):
                kfz_sheet_block_sum = numeric_block_sum(
                    df,
                    idx,
                    idx + 4,
                    2,
                    9,
                )
                kfz_block_sum += kfz_sheet_block_sum
                
        # read time from first_R_df (stable reference)
        if first_R_df is None:
            raise ValueError("No R sheets found – first_R_df was never assigned")
        time_start = first_R_df.iloc[idx, 0]
        time_end   = first_R_df.iloc[idx+3, 0]

        if idx < summe_idx/2 and kfz_block_sum > kfz_morning_peak:
            kfz_morning_peak = kfz_block_sum
            morning_time_start = time_start
            morning_time_end = time_end
            morning_start_idx = idx

        if idx >= summe_idx/2 and kfz_block_sum > kfz_afternoon_peak:
            kfz_afternoon_peak = kfz_block_sum
            afternoon_time_start = time_start
            afternoon_time_end = time_end
            afternoon_peak_start_idx = idx
    
   # --------------------------------------------------
    # Ganztageszeitraum über ALLE R-Blätter bestimmen
    # --------------------------------------------------
    #
    # Beginn:
    # frühester Zeitpunkt, zu dem auf irgendeiner Relation
    # mindestens ein Fahrzeug bzw. Fahrrad gezählt wurde.
    #
    # Ende:
    # spätester Zeitpunkt, zu dem auf irgendeiner Relation
    # mindestens ein Fahrzeug bzw. Fahrrad gezählt wurde.

    def time_to_minutes(hhmm: str) -> int:
        """
        Wandelt eine Uhrzeit wie '7:15' oder '07:15'
        in Minuten seit Mitternacht um.
        """
        hour, minute = hhmm.strip().split(":")
        return int(hour) * 60 + int(minute)


    day_start_candidates = []
    day_end_candidates = []

    for sheet_name, df in sheets.items():
        if not sheet_name.startswith("R"):
            continue

        # SUMME-Zeile für das jeweilige R-Blatt bestimmen
        sheet_summe_idx = None

        for row_idx, value in enumerate(df.iloc[:, 0]):
            if isinstance(value, str) and "SUMME" in value.upper():
                sheet_summe_idx = row_idx
                break

        if sheet_summe_idx is None:
            continue

        for row_idx in range(13, sheet_summe_idx):

            row_values = pd.to_numeric(
                df.iloc[row_idx, 1:9],
                errors="coerce"
            ).fillna(0.0)

            # Nur Zeitintervalle mit tatsächlichem Aufkommen berücksichtigen
            if not (row_values.abs() > 0).any():
                continue

            interval_start, interval_end = _parse_interval(
                df.iloc[row_idx, 0]
            )

            if interval_start is None or interval_end is None:
                continue

            day_start_candidates.append(interval_start)
            day_end_candidates.append(interval_end)


    if not day_start_candidates or not day_end_candidates:
        raise ValueError(
            "In keinem R-Blatt wurden gültige Zeitintervalle "
            "mit Verkehrswerten gefunden."
        )


    day_start_time = min(
        day_start_candidates,
        key=time_to_minutes,
    )

    day_end_time = max(
        day_end_candidates,
        key=time_to_minutes,
    )

    morning_time_start = str(morning_time_start).split("-")[0]
    morning_time_end   = str(morning_time_end).split("-")[-1]

    afternoon_time_start = str(afternoon_time_start).split("-")[0]
    afternoon_time_end   = str(afternoon_time_end).split("-")[-1]
    
    #KFZ
    kfz_Tag_Summe = sum(value["kfz"] for value in direction_dic.values())
    kfz_Tag_SV = sum(value["Summe_SV"] for value in direction_dic.values())
    
    direction_morning_dic = build_direction_dic(sheets, morning_start_idx)
    direction_afternoon_dic = build_direction_dic(sheets, afternoon_peak_start_idx)
    
    direction_custom_dic = None
    PKW_Einheiten_traffic_custom = None
    custom_time_start = None
    custom_time_end = None
    custom_start_idx = None

    if use_custom_window:
        if not custom_start_time:
            raise ValueError(
                "Für den benutzerdefinierten Zeitraum fehlt die Startzeit."
            )

        # Standardmäßig eine Stunde auswerten
        if not custom_end_time:
            start_dt = datetime.strptime(custom_start_time, "%H:%M")
            custom_end_time = (
                start_dt + timedelta(hours=1)
            ).strftime("%H:%M")

        start_dt = datetime.strptime(custom_start_time, "%H:%M")
        end_dt = datetime.strptime(custom_end_time, "%H:%M")

        if end_dt <= start_dt:
            raise ValueError(
                "Die Endzeit muss nach der Startzeit liegen."
            )

        duration_minutes = int(
            (end_dt - start_dt).total_seconds() / 60
        )

        # Excel enthält 15-Minuten-Intervalle
        if duration_minutes % 15 != 0:
            raise ValueError(
                "Der Auswertezeitraum muss ein Vielfaches "
                "von 15 Minuten sein."
            )

        custom_n_rows = duration_minutes // 15

        custom_time_start = custom_start_time
        custom_time_end = custom_end_time

        custom_start_idx = _find_row_for_start(
            custom_time_start
        )

        custom_end_idx = custom_start_idx + custom_n_rows

        if custom_end_idx > summe_idx:
            raise ValueError(
                f"Der gewählte Zeitraum "
                f"{custom_time_start}–{custom_time_end} "
                "überschreitet die verfügbaren Zähldaten."
            )

        direction_custom_dic = build_direction_dic(
            sheets,
            custom_start_idx,
            n_rows=custom_n_rows,
        )

        PKW_Einheiten_traffic_custom = (
            PKW_Einheiten_traffic_dic(
                sheets,
                custom_start_idx,
                n_rows=custom_n_rows,
                vlsa_mode=vlsa_mode,
            )
        )
    
    kfz_morning_summe = sum(value["kfz"] for value in direction_morning_dic.values())
    kfz_afternoon_summe = sum(value["kfz"] for value in direction_afternoon_dic.values())
    kfz_SV_morning = sum(value["Summe_SV"] for value in direction_morning_dic.values())
    kfz_SV_afternoon = sum(value["Summe_SV"] for value in direction_afternoon_dic.values())     
    
    #PKV Einheiten 
    PKW_Einheiten_Tag_Summe = sum(value["PKW_Total"] for value in PKW_direction_general_dic.values())
    PKW_Einheiten_Tag_SV = sum(value["Summe_SV"] for value in PKW_direction_general_dic.values())

    
    PKW_Einheiten_traffic_morning = PKW_Einheiten_traffic_dic(
    sheets,
    morning_start_idx,
    vlsa_mode=vlsa_mode,
    )
    PKW_Einheiten_traffic_afternoon = PKW_Einheiten_traffic_dic(
    sheets,
    afternoon_peak_start_idx,
    vlsa_mode=vlsa_mode,
    )

    PKW_Einheiten_morning_summe = sum(value["PKW_Total"] for value in PKW_Einheiten_traffic_morning.values())
    PKW_Einheiten_afternoon_summe = sum(value["PKW_Total"] for value in PKW_Einheiten_traffic_afternoon.values())

    PKW_Einheiten_SV_morning = sum(value["Summe_SV"] for value in PKW_Einheiten_traffic_morning.values())
    PKW_Einheiten_SV_afternoon = sum(value["Summe_SV"] for value in PKW_Einheiten_traffic_afternoon.values())

    kfz_sv_full = _sv_stats(kfz_Tag_Summe, kfz_Tag_SV)
    kfz_sv_morning = _sv_stats(kfz_morning_summe, kfz_SV_morning)
    kfz_sv_afternoon = _sv_stats(kfz_afternoon_summe, kfz_SV_afternoon)

    pkw_sv_full = _sv_stats(PKW_Einheiten_Tag_Summe, PKW_Einheiten_Tag_SV)
    pkw_sv_morning = _sv_stats(PKW_Einheiten_morning_summe, PKW_Einheiten_SV_morning)
    pkw_sv_afternoon = _sv_stats(PKW_Einheiten_afternoon_summe, PKW_Einheiten_SV_afternoon)

    # --- Nur Relationen berücksichtigen, die über den gesamten Tag KFZ > 0 haben ---
    #
    # Dadurch gilt:
    # - Tagessumme KFZ = 0:
    #   Relation wird in keinem Diagramm dargestellt.
    #
    # - Tagessumme KFZ > 0, aber Spitzenstunde KFZ = 0:
    #   Relation bleibt enthalten und wird in der Spitzenstunde
    #   als gestrichelte Null-Relation mit dem Label "0" dargestellt.
    present_dirnums = sorted(
        int(name[1:])
        for name, values in direction_dic.items()
        if float(values["kfz"]) > 0
    )

    if not present_dirnums:
        raise ValueError(
            "Keine Relation mit einer KFZ-Tagessumme größer 0 gefunden."
        )

    present_dirs = [f"R{k}" for k in present_dirnums]
    flows_present = [DIR_TO_FLOW[k] for k in present_dirnums]

    # Alle Dictionaries auf dieselben aktiven Relationen reduzieren
    # und in identischer Reihenfolge anordnen.
    direction_dic = {
        k: direction_dic[k]
        for k in present_dirs
    }

    direction_morning_dic = {
        k: direction_morning_dic[k]
        for k in present_dirs
    }

    direction_afternoon_dic = {
        k: direction_afternoon_dic[k]
        for k in present_dirs
    }

    PKW_direction_general_dic = {
        k: PKW_direction_general_dic[k]
        for k in present_dirs
    }

    PKW_Einheiten_traffic_morning = {
        k: PKW_Einheiten_traffic_morning[k]
        for k in present_dirs
    }

    PKW_Einheiten_traffic_afternoon = {
        k: PKW_Einheiten_traffic_afternoon[k]
        for k in present_dirs
    }

    # --------------------------------------------------
    # Globale Skalierung für KFZ
    # --------------------------------------------------
    all_kfz = []

    for traffic_dic in (
        direction_dic,
        direction_morning_dic,
        direction_afternoon_dic,
    ):
        all_kfz.extend(
            float(values["kfz"])
            for values in traffic_dic.values()
        )

    tmin_kfz = float(min(all_kfz))
    tmax_kfz = float(max(all_kfz))


    # --------------------------------------------------
    # Globale Skalierung für PKW-E
    # --------------------------------------------------
    all_pkw = []

    for traffic_dic in (
        PKW_direction_general_dic,
        PKW_Einheiten_traffic_morning,
        PKW_Einheiten_traffic_afternoon,
    ):
        all_pkw.extend(
            float(values["PKW_Total"])
            for values in traffic_dic.values()
        )

    tmin_pkw = float(min(all_pkw))
    tmax_pkw = float(max(all_pkw))


    # --------------------------------------------------
    # Breiten berechnen
    # --------------------------------------------------
    gamma = 0.5

    width_general = calculate_width(
        direction_dic,
        w_min,
        w_max,
        tmin_kfz,
        tmax_kfz,
        gamma=gamma,
        PKW_Einheiten=False,
    )

    width_morning_peak = calculate_width(
        direction_morning_dic,
        w_min,
        w_max,
        tmin_kfz,
        tmax_kfz,
        gamma=gamma,
        PKW_Einheiten=False,
    )

    width_afternoon_peak = calculate_width(
        direction_afternoon_dic,
        w_min,
        w_max,
        tmin_kfz,
        tmax_kfz,
        gamma=gamma,
        PKW_Einheiten=False,
    )

    width_PKW_general = calculate_width(
        PKW_direction_general_dic,
        w_min,
        w_max,
        tmin_pkw,
        tmax_pkw,
        gamma=gamma,
        PKW_Einheiten=True,
    )

    width_PKW_morning = calculate_width(
        PKW_Einheiten_traffic_morning,
        w_min,
        w_max,
        tmin_pkw,
        tmax_pkw,
        gamma=gamma,
        PKW_Einheiten=True,
    )

    width_PKW_afternoon = calculate_width(
        PKW_Einheiten_traffic_afternoon,
        w_min,
        w_max,
        tmin_pkw,
        tmax_pkw,
        gamma=gamma,
        PKW_Einheiten=True,
    )
    
    width_custom = None
    width_PKW_custom = None
    
    kfz_custom = None
    bike_custom = None
    PKW_custom = None

    side_custom = None
    PKW_side_custom = None
        
    kfz_sv_custom = None
    pkw_sv_custom = None

    if (
        direction_custom_dic is not None
        and PKW_Einheiten_traffic_custom is not None
    ):
        # Zuerst auf aktive Relationen reduzieren und sortieren
        direction_custom_dic = {
            k: direction_custom_dic[k]
            for k in present_dirs
        }

        PKW_Einheiten_traffic_custom = {
            k: PKW_Einheiten_traffic_custom[k]
            for k in present_dirs
        }

        # Danach Custom-Werte in die jeweilige globale Skalierung aufnehmen
        custom_kfz_values = [
            float(values["kfz"])
            for values in direction_custom_dic.values()
        ]

        custom_pkw_values = [
            float(values["PKW_Total"])
            for values in PKW_Einheiten_traffic_custom.values()
        ]

        tmin_kfz_custom = min(tmin_kfz, min(custom_kfz_values))
        tmax_kfz_custom = max(tmax_kfz, max(custom_kfz_values))

        tmin_pkw_custom = min(tmin_pkw, min(custom_pkw_values))
        tmax_pkw_custom = max(tmax_pkw, max(custom_pkw_values))

        width_custom = calculate_width(
            direction_custom_dic,
            w_min,
            w_max,
            tmin_kfz_custom,
            tmax_kfz_custom,
            gamma=gamma,
            PKW_Einheiten=False,
        )

        width_PKW_custom = calculate_width(
            PKW_Einheiten_traffic_custom,
            w_min,
            w_max,
            tmin_pkw_custom,
            tmax_pkw_custom,
            gamma=gamma,
            PKW_Einheiten=True,
        )

        kfz_custom = np.array([direction_custom_dic[name]["kfz"] for name in present_dirs], dtype=float)
        bike_custom = np.array([direction_custom_dic[name]["rad"] for name in present_dirs], dtype=float)
        PKW_custom = np.array([PKW_Einheiten_traffic_custom[name]["PKW_Total"] for name in present_dirs], dtype=float)

        side_custom = compute_side_sums(flows_present, kfz_custom)
        PKW_side_custom = compute_side_sums(flows_present, PKW_custom)
        
        kfz_custom_sum = sum(value["kfz"] for value in direction_custom_dic.values())
        kfz_custom_sv  = sum(value["Summe_SV"] for value in direction_custom_dic.values())
        kfz_sv_custom = _sv_stats(kfz_custom_sum, kfz_custom_sv)

        pkw_custom_sum = sum(value["PKW_Total"] for value in PKW_Einheiten_traffic_custom.values())
        pkw_custom_sv  = sum(value["Summe_SV"] for value in PKW_Einheiten_traffic_custom.values())
        pkw_sv_custom = _sv_stats(pkw_custom_sum, pkw_custom_sv)   


    kfz_general = np.array([direction_dic[name]["kfz"] for name in present_dirs], dtype=float)
    kfz_morning = np.array([direction_morning_dic[name]["kfz"] for name in present_dirs], dtype=float)
    kfz_afternoon = np.array([direction_afternoon_dic[name]["kfz"] for name in present_dirs], dtype=float)

    bike_general = np.array([direction_dic[name]["rad"] for name in present_dirs], dtype=float)
    bike_morning = np.array([direction_morning_dic[name]["rad"] for name in present_dirs], dtype=float)
    bike_afternoon = np.array([direction_afternoon_dic[name]["rad"] for name in present_dirs], dtype=float)

    PKW_general = np.array([PKW_direction_general_dic[name]["PKW_Total"] for name in present_dirs], dtype=float)
    PKW_morning = np.array([PKW_Einheiten_traffic_morning[name]["PKW_Total"] for name in present_dirs], dtype=float)
    PKW_afternoon = np.array([PKW_Einheiten_traffic_afternoon[name]["PKW_Total"] for name in present_dirs], dtype=float)
    
    
    #Number of KFZ per side: {"dep_kfz": dep_kfz, "arr_kfz": arr_kfz, "total_kfz": total_kfz}
    side_general = compute_side_sums(flows_present, kfz_general) 
    side_morning = compute_side_sums(flows_present, kfz_morning)
    side_afternoon = compute_side_sums(flows_present, kfz_afternoon)
    
    PKW_side_general = compute_side_sums(flows_present, PKW_general)
    PKW_side_morning = compute_side_sums(flows_present, PKW_morning)
    PKW_side_afternoon = compute_side_sums(flows_present, PKW_afternoon)

    # ---- Per-direction KFZ + Bicycle values for display in Streamlit ----
    per_direction = []
    for name in present_dirs:
        per_direction.append({
            "direction": name,

            "full_day_kfz": float(direction_dic[name]["kfz"]),
            "morning_peak_kfz": float(direction_morning_dic[name]["kfz"]),
            "afternoon_peak_kfz": float(direction_afternoon_dic[name]["kfz"]),

            "full_day_pkw": float(PKW_direction_general_dic[name]["PKW_Total"]),
            "morning_peak_pkw": float(PKW_Einheiten_traffic_morning[name]["PKW_Total"]),
            "afternoon_peak_pkw": float(PKW_Einheiten_traffic_afternoon[name]["PKW_Total"]),

            "full_day_bike": float(direction_dic[name]["rad"]),
            "morning_peak_bike": float(direction_morning_dic[name]["rad"]),
            "afternoon_peak_bike": float(direction_afternoon_dic[name]["rad"]),
        })  
        
        if direction_custom_dic is not None and PKW_Einheiten_traffic_custom is not None:
            per_direction[-1]["custom_kfz"] = float(direction_custom_dic[name]["kfz"])
            per_direction[-1]["custom_pkw"] = float(PKW_Einheiten_traffic_custom[name]["PKW_Total"])
            per_direction[-1]["custom_bike"] = float(direction_custom_dic[name]["rad"]) 
    
    mode = mode.upper().strip()
    use_pkw = mode.startswith("PKW")

    if use_pkw:
        flow_general   = PKW_general
        flow_morning   = PKW_morning
        flow_afternoon = PKW_afternoon

        width_general_sel   = width_PKW_general
        width_morning_sel   = width_PKW_morning
        width_afternoon_sel = width_PKW_afternoon

        unit_label = "PKW_Einheiten"
        suffix_general = "full_day_PKW_Einheiten"
        suffix_morning = "morning_peak_PKW_Einheiten"
        suffix_afternoon = "afternoon_peak_PKW_Einheiten"

        side_general_sel   = PKW_side_general
        side_morning_sel   = PKW_side_morning
        side_afternoon_sel = PKW_side_afternoon
    else:
        flow_general   = kfz_general
        flow_morning   = kfz_morning
        flow_afternoon = kfz_afternoon

        width_general_sel   = width_general
        width_morning_sel   = width_morning_peak
        width_afternoon_sel = width_afternoon_peak

        unit_label = "KFZ"
        suffix_general = "full_day"
        suffix_morning = "morning_peak"
        suffix_afternoon = "afternoon_peak"

        side_general_sel   = side_general
        side_morning_sel   = side_morning
        side_afternoon_sel = side_afternoon
    
    # FG-/Radwerte für dieselben Zeiträume aufbauen
    fg_periods = {"full_day": [], "morning_peak": [], "afternoon_peak": [], "custom": []}
    if fg_df is not None and fg_columns and fg_data_start_idx is not None:
        # Zeitzeilen im FG-Blatt anhand der Uhrzeit suchen
        def _fg_row_for_start(hhmm):
            target = datetime.strptime(str(hhmm).strip(), "%H:%M").strftime("%H:%M")
            upper = fg_sum_idx if fg_sum_idx is not None else len(fg_df)
            for ridx in range(fg_data_start_idx, upper):
                a, _ = _parse_interval(fg_df.iloc[ridx, 0])
                if a == target:
                    return ridx
            return None

        full_start = fg_data_start_idx
        full_end = fg_sum_idx if fg_sum_idx is not None else len(fg_df)
        fg_full = build_fg_values(fg_df, fg_columns, full_start, max(0, full_end-full_start))

        fm = _fg_row_for_start(morning_time_start)
        fa = _fg_row_for_start(afternoon_time_start)
        fg_morn = build_fg_values(fg_df, fg_columns, fm, 4) if fm is not None else {}
        fg_aft = build_fg_values(fg_df, fg_columns, fa, 4) if fa is not None else {}
        fg_custom_vals = {}
        if direction_custom_dic is not None:
            fc = _fg_row_for_start(custom_time_start)
            if fc is not None:
                fg_custom_vals = build_fg_values(fg_df, fg_columns, fc, custom_n_rows)

        def _to_plot_list(values):
            out = []
            for key, item in values.items():
                side = (fg_mapping or {}).get(key, "")
                if side in {"N", "E", "S", "W"}:
                    out.append({**item, "side": side})
            return out

        fg_periods["full_day"] = _to_plot_list(fg_full)
        fg_periods["morning_peak"] = _to_plot_list(fg_morn)
        fg_periods["afternoon_peak"] = _to_plot_list(fg_aft)
        fg_periods["custom"] = _to_plot_list(fg_custom_vals)

        fg_values_by_period = {
            "full_day": fg_full,
            "morning_peak": fg_morn,
            "afternoon_peak": fg_aft,
            "custom": fg_custom_vals,
        }
    else:
        fg_values_by_period = {
            "full_day": {},
            "morning_peak": {},
            "afternoon_peak": {},
            "custom": {},
        }

    # Generate three plots
    pngs = []
    svgs = []
    pdfs = []
    def _add_both(flow, bike, w, suffix, start, end, location_name=verkehrszählungsort, fg_relations=None):
        pngs.append(create_plot(
            flow, bike, w, flows_present, location_name,
            suffix, start, end, side_colors, d_NS, d_WE,
            fmt="png", show_bicycle_labels=show_bicycle_labels, kfz_label_fontsize=kfz_label_fontsize, arrow_label_fontsize=arrow_label_fontsize,  side_total_fontsize=side_total_fontsize, street_names=street_names, fg_relations=fg_relations,
            show_fg_crossings=show_fg_crossings, show_rad_crossings=show_rad_crossings,
        ))
        svgs.append(create_plot(
            flow, bike, w, flows_present, location_name,
            suffix, start, end, side_colors, d_NS, d_WE,
            fmt="svg", show_bicycle_labels=show_bicycle_labels, kfz_label_fontsize=kfz_label_fontsize, arrow_label_fontsize=arrow_label_fontsize,  side_total_fontsize=side_total_fontsize, street_names=street_names, fg_relations=fg_relations,
            show_fg_crossings=show_fg_crossings, show_rad_crossings=show_rad_crossings,
        ))
        pdfs.append(create_plot(
            flow, bike, w, flows_present, location_name,
            suffix, start, end, side_colors, d_NS, d_WE,
            fmt="pdf", show_bicycle_labels=show_bicycle_labels, kfz_label_fontsize=kfz_label_fontsize, arrow_label_fontsize=arrow_label_fontsize, side_total_fontsize=side_total_fontsize, street_names=street_names, fg_relations=fg_relations,
            show_fg_crossings=show_fg_crossings, show_rad_crossings=show_rad_crossings,
        ))

    _add_both(flow_general, bike_general, width_general_sel, suffix_general, day_start_time, day_end_time, fg_relations=fg_periods["full_day"])
    _add_both(flow_morning, bike_morning, width_morning_sel, suffix_morning, morning_time_start, morning_time_end, fg_relations=fg_periods["morning_peak"])
    _add_both(flow_afternoon, bike_afternoon, width_afternoon_sel, suffix_afternoon, afternoon_time_start, afternoon_time_end, fg_relations=fg_periods["afternoon_peak"])

    if direction_custom_dic is not None:
        custom_suffix_time = (
            f"{custom_time_start.replace(':', '')}_"
            f"{custom_time_end.replace(':', '')}"
        )

        if use_pkw:
            flow_custom = PKW_custom
            width_custom_sel = width_PKW_custom
            suffix_custom = (
                f"custom_{custom_suffix_time}_PKW_Einheiten"
            )
            side_custom_sel = PKW_side_custom
        else:
            flow_custom = kfz_custom
            width_custom_sel = width_custom
            suffix_custom = f"custom_{custom_suffix_time}"
            side_custom_sel = side_custom

        _add_both(
            flow_custom,
            bike_custom,
            width_custom_sel,
            suffix_custom,
            custom_time_start,
            custom_time_end,
            fg_relations=fg_periods["custom"],
        )
        
    totals = {
    "full_day_kfz": float(np.sum(kfz_general)),
    "morning_peak_kfz": float(np.sum(kfz_morning)),
    "afternoon_peak_kfz": float(np.sum(kfz_afternoon)),

    "full_day_pkw": float(np.sum(PKW_general)),
    "morning_peak_pkw": float(np.sum(PKW_morning)),
    "afternoon_peak_pkw": float(np.sum(PKW_afternoon)),

    "full_day_bike": float(np.sum(bike_general)),
    "morning_peak_bike": float(np.sum(bike_morning)),
    "afternoon_peak_bike": float(np.sum(bike_afternoon)),
    }

    # Add custom totals only if custom exists
    if direction_custom_dic is not None:
        if kfz_custom is not None and bike_custom is not None and PKW_custom is not None:
            totals["custom_kfz"] = float(np.sum(kfz_custom))
            totals["custom_pkw"] = float(np.sum(PKW_custom))
            totals["custom_bike"] = float(np.sum(bike_custom))
    
    meta = {
        "location": verkehrszählungsort,
        "mode": unit_label, 
        "vlsa_mode": vlsa_mode,
        "pkw_e_faktoren": faktoren.copy(),
        "fg": {
            "sheet": fg_sheet_name,
            "detected_columns": fg_columns,
            "mapping": fg_mapping or {},
            "periods": fg_periods,
            "values_by_period": fg_values_by_period,
        },

        "day": {"start": day_start_time, "end": day_end_time},
        "morning_peak": {"start": morning_time_start, "end": morning_time_end},
        "afternoon_peak": {"start": afternoon_time_start, "end": afternoon_time_end},

        "tmin_kfz": tmin_kfz,
        "tmax_kfz": tmax_kfz,
        "tmin_pkw": tmin_pkw,
        "tmax_pkw": tmax_pkw,
        "gamma": gamma,

        # Keep your per_direction as-is OR extend it (see below)
        "per_direction": per_direction,

        # totals now depend on selected mode
        "totals": totals,
    
        "custom": ({"start": custom_time_start, "end": custom_time_end} if direction_custom_dic is not None else None),

        "by_side": {
            "full_day": side_general_sel,
            "morning_peak": side_morning_sel,
            "afternoon_peak": side_afternoon_sel,
            **({"custom": side_custom_sel} if direction_custom_dic is not None else {}),
        },
        
        "sv": {
        "kfz": {
            "full_day": kfz_sv_full,
            "morning_peak": kfz_sv_morning,
            "afternoon_peak": kfz_sv_afternoon,
             **({"custom": kfz_sv_custom} if kfz_sv_custom is not None else {})
        },
        "pkw": {
            "full_day": pkw_sv_full,
            "morning_peak": pkw_sv_morning,
            "afternoon_peak": pkw_sv_afternoon,
            **({"custom": pkw_sv_custom} if pkw_sv_custom is not None else {}),
        },
    },
    }
    
    return pngs, svgs, pdfs, meta

def generate_plots_from_direction_values(
    direction_values: Dict[str, Dict[str, float]],
    location: str = "Manual Input",
    side_colors: Optional[Dict[str, str]] = None,
    d_NS: float = 1.5,
    d_WE: float = 1.5,
    w_min: float = 0.0,
    w_max: float = 1.4,
    mode: str = "KFZ",
    show_bicycle_labels: bool = True,
    kfz_label_fontsize: int = 12,
    arrow_label_fontsize: int = 12,
    side_total_fontsize: int = 18,
    street_names: Optional[Dict[str, str]] = None,
    fg_relations: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Tuple[bytes, str]], List[Tuple[bytes, str]], List[Tuple[bytes, str]], Dict[str, Any]]:
    
    # keep only R1..R12 that exist
    present_dirnums = sorted(int(k[1:]) for k in direction_values.keys() if k.startswith("R"))
    present_dirs = [f"R{i}" for i in present_dirnums]
    flows_present = [DIR_TO_FLOW[i] for i in present_dirnums]

    # build ordered arrays
    kfz = np.array([direction_values[r]["kfz"] for r in present_dirs], dtype=float)
    bike = np.array([direction_values[r].get("rad", 0.0) for r in present_dirs], dtype=float)

    # width scaling (use kfz or pkw depending on mode)
    tmin, tmax = float(kfz.min()), float(kfz.max())
    gamma = 1.0
    tmp_dic = {r: {"kfz": direction_values[r]["kfz"], "PKW_Total": direction_values[r]["kfz"]} for r in present_dirs}

    use_pkw = mode.upper().startswith("PKW")
    widths = calculate_width(tmp_dic, w_min, w_max, tmin, tmax, gamma=gamma, PKW_Einheiten=use_pkw)

    # you may not have morning/afternoon in manual mode; simplest: produce one "full_day" plot
    pngs = [create_plot(
        kfz, bike, widths, flows_present, location,
        "manual", "manual", "manual", side_colors, d_NS, d_WE,
        fmt="png",
        show_bicycle_labels=show_bicycle_labels,
        kfz_label_fontsize=kfz_label_fontsize,
        arrow_label_fontsize=arrow_label_fontsize,
        side_total_fontsize=side_total_fontsize,
        street_names=street_names,
        fg_relations=fg_relations,
    )]

    svgs = [create_plot(
        kfz, bike, widths, flows_present, location,
        "manual", "manual", "manual", side_colors, d_NS, d_WE,
        fmt="svg",
        show_bicycle_labels=show_bicycle_labels,
        kfz_label_fontsize=kfz_label_fontsize,
        arrow_label_fontsize=arrow_label_fontsize,
        side_total_fontsize=side_total_fontsize,
        street_names=street_names,
        fg_relations=fg_relations,
    )]

    pdfs = [create_plot(
        kfz, bike, widths, flows_present, location,
        "manual", "manual", "manual", side_colors, d_NS, d_WE,
        fmt="pdf",
        show_bicycle_labels=show_bicycle_labels,
        kfz_label_fontsize=kfz_label_fontsize,
        arrow_label_fontsize=arrow_label_fontsize,
        side_total_fontsize=side_total_fontsize,
        street_names=street_names,
        fg_relations=fg_relations,
    )]

    meta = {"location": location, "mode": mode, "per_direction": direction_values}
    return pngs, svgs, pdfs, meta
