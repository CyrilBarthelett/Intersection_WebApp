<<<<<<< HEAD
"""
Traffic Flow Visualization Generator

This module generates PNG plots of traffic flows in a sankey diagramm format from Excel data.
It supports general traffic and peak hour analysis (morning and afternoon).
"""

import io
import re
from typing import List, Tuple, Dict, Optional
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg") 
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from openpyxl import load_workbook

# --------------------- CONFIG ---------------------
width_min = 0.1
width_max = 0.8

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
R = 4.0
d = 1
inward = 0.9

FILL = "lightblue"
EDGE = "none"
EDGE_LW = 0.0

# Group slots
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

SIDE_COLOR = {"N": "tab:blue", "E": "tab:orange", "S": "tab:green", "W": "tab:red"}

def calculate_width(direction_dic):
    """Calculate width array for traffic visualization based on KFZ values."""
    traffic = np.array([list(sub_dic.values())[1] for sub_dic in direction_dic.values()])  # kfz_traffic
    if traffic.size == 1 or np.isclose(traffic.max(), traffic.min()):
        width = np.round(np.full_like(traffic, (width_min + width_max) / 2.0), 2)
    else:
        width = np.round(width_min + (traffic - traffic.min()) * (width_max - width_min) / (traffic.max() - traffic.min()), 2)
    return width

def build_direction_dic(sheets, peak_idx):
    """Build direction dictionary for a given peak index from sheets."""
    dic = {}
    for sheet_name, df in sheets.items():
        if sheet_name.startswith("R"):
            kfz_sum = df.iloc[peak_idx:peak_idx+4, 2:9].sum().sum()
            total_sum = df.iloc[peak_idx:peak_idx+4, 1:9].sum().sum()
            dic[sheet_name] = {
                "total": total_sum,
                "kfz": kfz_sum,
                "rad": total_sum - kfz_sum
            }
    return dic

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

def place_group_variable(P, fixed_axis, fixed_val, ids, mid_val, dir_to_axis, W):
    """Place points for a group of slots."""
    if not ids:
        return

    widths = [W[i] for i in ids]
    span = sum(widths)

    offsets = []
    acc = -span / 2.0
    for w in widths:
        offsets.append(acc + w / 2.0)
        acc += w

    for pid, off in zip(ids, offsets):
        pt = np.array([0.0, 0.0], float)
        pt[fixed_axis] = fixed_val
        pt[1 - fixed_axis] = mid_val + dir_to_axis * off
        P[pid] = C + pt

def add_group_arrow(ax, P, W, group_ids, side, outward=True, color="k", zorder=10):
    """Add an arrow for a group of slots."""
    ids = list(group_ids)
    pts = np.array([P[i] for i in ids], float)

    if side in ("N", "S"):
        var_axis = 0  # x
        nrm = np.array([0.0, +1.0]) if side == "N" else np.array([0.0, -1.0])
    else:
        var_axis = 1  # y
        nrm = np.array([+1.0, 0.0]) if side == "E" else np.array([-1.0, 0.0])

    var = pts[:, var_axis]
    far_idx = int(np.argmax(np.abs(var)))
    clo_idx = int(np.argmin(np.abs(var)))

    pid_far = ids[far_idx]
    pid_clo = ids[clo_idx]

    P_far = np.array(P[pid_far], float)
    P_clo = np.array(P[pid_clo], float)

    s_far = np.sign(P_far[var_axis]) or 1.0
    d_far = (W[pid_far] / 2.0) * s_far
    d_clo = -(W[pid_clo] / 2.0) * s_far

    base_far = P_far.copy(); base_far[var_axis] += d_far
    base_clo = P_clo.copy(); base_clo[var_axis] += d_clo

    base_center = 0.5 * (base_far + base_clo)
    tip = base_center + (nrm * 0.5 if outward else -nrm * 0.5)

    tri = np.vstack([tip, base_far, base_clo])
    ax.add_patch(Polygon(tri, closed=True, facecolor=color, edgecolor="none", zorder=zorder))

def create_plot(traffic, width, flows_present, present_dirs, verkehrszählungsort, suffix, side_colors):
    """Create a PNG plot for given traffic and width data."""
    # Update SIDE_COLOR with user-provided side_colors
    if side_colors:
        SIDE_COLOR.update(side_colors)

    # Width mapping already done
    flow_width = {(i, j): w for (i, j), w in zip(flows_present, width)}

    # Point widths
    W = {}
    for (i, j), w in flow_width.items():
        W[i] = w
        W[j] = w
    active_points = set(W.keys())

    # Active groups
    GROUP_ACTIVE = {
        key: [pid for pid in values if pid in active_points]
        for key, values in GROUP_SLOTS.items()
    }

    # Colors
    departing_points = set()
    point_to_color = {}
    for side in ("N", "E", "S", "W"):
        for p in GROUP_ACTIVE[(side, "dep")]:
            departing_points.add(p)
            point_to_color[p] = SIDE_COLOR[side]

    def flow_color(i, j, default="lightblue"):
        if i in departing_points:
            return point_to_color[i]
        if j in departing_points:
            return point_to_color[j]
        return default

    # Place points
    P = {}
    place_group_variable(P, 1, +R, GROUP_ACTIVE[("N","dep")], -d, +1, W)
    place_group_variable(P, 1, +R, GROUP_ACTIVE[("N","arr")], +d, -1, W)

    place_group_variable(P, 0, +R, GROUP_ACTIVE[("E","dep")], +d, -1, W)
    place_group_variable(P, 0, +R, GROUP_ACTIVE[("E","arr")], -d, +1, W)

    place_group_variable(P, 1, -R, GROUP_ACTIVE[("S","dep")], +d, -1, W)
    place_group_variable(P, 1, -R, GROUP_ACTIVE[("S","arr")], -d, +1, W)

    place_group_variable(P, 0, -R, GROUP_ACTIVE[("W","dep")], -d, +1, W)
    place_group_variable(P, 0, -R, GROUP_ACTIVE[("W","arr")], +d, -1, W)

    # Plot
    fig, ax = plt.subplots(figsize=(10, 10))

    for (i, j) in flows_present:
        if i not in P or j not in P:
            continue

        A, B = P[i], P[j]
        w = flow_width[(i, j)]
        col = flow_color(i, j)

        if tuple(sorted((i, j))) in RECT_FLOWS_U:
            add_patch(ax, segment_rectangle(A, B, w), col)
        else:
            Z = C + np.array([A[0], B[1]])
            add_bezier_ribbon(ax, A, B, Z, w, col)

    for side in ("N", "E", "S", "W"):
        ids_dep = GROUP_ACTIVE[(side, "dep")]
        if len(ids_dep) >= 2:
            add_group_arrow(ax, P, W, ids_dep, side, outward=False)

        ids_arr = GROUP_ACTIVE[(side, "arr")]
        if len(ids_arr) >= 2:
            add_group_arrow(ax, P, W, ids_arr, side, outward=True)

    ax.set_aspect("equal", adjustable="box")
    pad = 1.4
    ax.set_xlim(-R - pad, R + pad)
    ax.set_ylim(-R - pad, R + pad)
    ax.set_axis_off()

    # Return PNG bytes (no filesystem)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, bbox_inches="tight", dpi=300)
    plt.close(fig)

    safe_name = re.sub(r"[^\w\-]+", "_", str(verkehrszählungsort))
    filename = f"VZ_{safe_name}_{suffix}.png"
    return buf.getvalue(), filename

# --------------------- MAIN GENERATOR ---------------------
def generate_png_from_excel(excel_bytes: bytes, side_colors: Optional[Dict[str, str]] = None) -> List[Tuple[bytes, str]]:  #Takes Excel bytes as input, Returns list of (png_bytes, filename)
    wb = load_workbook(io.BytesIO(excel_bytes), data_only=True)

    ws_deckblatt = wb["Deckbl."]
    verkehrszählungsort = ws_deckblatt["C8"].value

    # Read directions
    direction_dic = {}
    for sheet_name in wb.sheetnames:
        if sheet_name.startswith("R"):
            ws = wb[sheet_name]
            direction_dic[sheet_name] = {
                "total": ws["J82"].value,
                "kfz": ws["J82"].value - ws["B82"].value,
                "rad": ws["B82"].value
            }

    # Load sheets for peak calculation
    sheets = pd.read_excel(io.BytesIO(excel_bytes), sheet_name=None, header=None)

    # Find peaks
    kfz_morning_peak = 0
    kfz_afternoon_peak = 0
    for idx in range(13, 77+1):  # sliding window of 4 rows
        kfz_block_sum = 0
        for sheet_name, df in sheets.items():
            if sheet_name.startswith("R"):
                kfz_sheet_block_sum = df.iloc[idx:idx+4, 2:9].sum().sum()
                kfz_block_sum += kfz_sheet_block_sum
                
                if kfz_block_sum > kfz_morning_peak and idx < 40:
                    kfz_morning_peak = kfz_block_sum
                    morning_start_idx = idx

                if kfz_block_sum > kfz_afternoon_peak and idx >= 40:
                    kfz_afternoon_peak = kfz_block_sum
                    afternoon_peak_start_idx = idx

    # Build peak dics
    direction_morning_dic = build_direction_dic(sheets, morning_start_idx)
    direction_afternoon_dic = build_direction_dic(sheets, afternoon_peak_start_idx)

    # Calculate widths
    width_general = calculate_width(direction_dic)
    width_morning_peak = calculate_width(direction_morning_dic)
    width_afternoon_peak = calculate_width(direction_afternoon_dic)

    present_dirnums = sorted(int(name[1:]) for name in direction_dic.keys())
    if not present_dirnums:
        raise ValueError("No 'R*' sheets found. Nothing to plot.")

    present_dirs = [f"R{k}" for k in present_dirnums]
    flows_present = [DIR_TO_FLOW[k] for k in present_dirnums]

    traffic_general = np.array([direction_dic[name]["kfz"] for name in present_dirs], dtype=float)
    traffic_morning = np.array([direction_morning_dic[name]["kfz"] for name in present_dirs], dtype=float)
    traffic_afternoon = np.array([direction_afternoon_dic[name]["kfz"] for name in present_dirs], dtype=float)

    # Generate three plots
    pngs = []
    pngs.append(create_plot(traffic_general, width_general, flows_present, present_dirs, verkehrszählungsort, "full_day", side_colors))
    pngs.append(create_plot(traffic_morning, width_morning_peak, flows_present, present_dirs, verkehrszählungsort, "morning_peak", side_colors))
    pngs.append(create_plot(traffic_afternoon, width_afternoon_peak, flows_present, present_dirs, verkehrszählungsort, "afternoon_peak", side_colors))

    return pngs
=======
import io
import re
import numpy as np
import matplotlib
matplotlib.use("Agg")  # IMPORTANT: headless backend for servers
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from openpyxl import load_workbook

# --------------------- CONFIG ---------------------
width_min = 0.1
width_max = 0.8

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
R = 4.0
d = 1
inward = 0.9

FILL = "lightblue"
EDGE = "none"
EDGE_LW = 0.0

# Group slots
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

SIDE_COLOR = {"N": "tab:blue", "E": "tab:orange", "S": "tab:green", "W": "tab:red"}

# --------------------- GEOMETRY HELPERS ---------------------
def segment_rectangle(A, B, width):
    A = np.asarray(A, float)
    B = np.asarray(B, float)
    v = B - A
    L = np.hypot(v[0], v[1])
    u = v / L
    n = np.array([-u[1], u[0]])
    off = (width / 2.0) * n
    return np.vstack([A + off, B + off, B - off, A - off])

def inward_ctrl(Z, P, inward_amount):
    return P + inward_amount * (Z - P)

def bezier_points(P0, P1, P2, P3, n=250):
    t = np.linspace(0, 1, n)[:, None]
    return ((1-t)**3)*P0 + 3*((1-t)**2)*t*P1 + 3*(1-t)*(t**2)*P2 + (t**3)*P3

def bezier_tangent(P0, P1, P2, P3, n=250):
    t = np.linspace(0, 1, n)[:, None]
    return (3*((1-t)**2)*(P1-P0) + 6*(1-t)*t*(P2-P1) + 3*(t**2)*(P3-P2))

def bezier_ribbon_polygon(P0, P1, P2, P3, width, n=250, eps=1e-12):
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
    ax.add_patch(
        Polygon(
            poly, closed=True,
            facecolor=color if color is not None else FILL,
            edgecolor=EDGE, linewidth=EDGE_LW
        )
    )

def add_bezier_ribbon(ax, A, B, Z, width, color):
    P0, P3 = A, B
    P1 = inward_ctrl(Z, A, inward)
    P2 = inward_ctrl(Z, B, inward)
    poly = bezier_ribbon_polygon(P0, P1, P2, P3, width=width)
    add_patch(ax, poly, color)

def place_group_variable(P, fixed_axis, fixed_val, ids, mid_val, dir_to_axis, W):
    if not ids:
        return

    widths = [W[i] for i in ids]
    span = sum(widths)

    offsets = []
    acc = -span / 2.0
    for w in widths:
        offsets.append(acc + w / 2.0)
        acc += w

    for pid, off in zip(ids, offsets):
        pt = np.array([0.0, 0.0], float)
        pt[fixed_axis] = fixed_val
        pt[1 - fixed_axis] = mid_val + dir_to_axis * off
        P[pid] = C + pt

def add_group_arrow(ax, P, W, group_ids, side, outward=True, color="k", zorder=10):
    ids = list(group_ids)
    pts = np.array([P[i] for i in ids], float)

    if side in ("N", "S"):
        var_axis = 0  # x
        nrm = np.array([0.0, +1.0]) if side == "N" else np.array([0.0, -1.0])
    else:
        var_axis = 1  # y
        nrm = np.array([+1.0, 0.0]) if side == "E" else np.array([-1.0, 0.0])

    var = pts[:, var_axis]
    far_idx = int(np.argmax(np.abs(var)))
    clo_idx = int(np.argmin(np.abs(var)))

    pid_far = ids[far_idx]
    pid_clo = ids[clo_idx]

    P_far = np.array(P[pid_far], float)
    P_clo = np.array(P[pid_clo], float)

    s_far = np.sign(P_far[var_axis]) or 1.0
    d_far = (W[pid_far] / 2.0) * s_far
    d_clo = -(W[pid_clo] / 2.0) * s_far

    base_far = P_far.copy(); base_far[var_axis] += d_far
    base_clo = P_clo.copy(); base_clo[var_axis] += d_clo

    base_center = 0.5 * (base_far + base_clo)
    tip = base_center + (nrm * 0.5 if outward else -nrm * 0.5)

    tri = np.vstack([tip, base_far, base_clo])
    ax.add_patch(Polygon(tri, closed=True, facecolor=color, edgecolor="none", zorder=zorder))

# --------------------- MAIN GENERATOR ---------------------
def generate_png_from_excel(excel_bytes: bytes) -> tuple[bytes, str]:  #Takes Excel bytes as input, Returns (png_bytes, filename)
    wb = load_workbook(io.BytesIO(excel_bytes), data_only=True)

    ws_deckblatt = wb["Deckbl."]
    verkehrszählungsort = ws_deckblatt["C8"].value

    # Read directions
    direction_dic = {}
    for sheet_name in wb.sheetnames:
        if sheet_name.startswith("R"):
            ws = wb[sheet_name]
            direction_dic[sheet_name] = {
                "total": ws["J82"].value,
                "kfz": ws["J82"].value - ws["B82"].value,
                "rad": ws["B82"].value
            }

    present_dirnums = sorted(int(name[1:]) for name in direction_dic.keys())
    if not present_dirnums:
        raise ValueError("No 'R*' sheets found. Nothing to plot.")

    present_dirs = [f"R{k}" for k in present_dirnums]
    traffic = np.array([direction_dic[name]["kfz"] for name in present_dirs], dtype=float)

    # Width mapping
    if traffic.size == 1 or np.isclose(traffic.max(), traffic.min()):
        width = np.round(np.full_like(traffic, (width_min + width_max) / 2.0), 2)
    else:
        width = np.round(
            width_min + (traffic - traffic.min()) * (width_max - width_min) / (traffic.max() - traffic.min()),
            2
        )

    # Flows
    flows_present = [DIR_TO_FLOW[k] for k in present_dirnums]
    flow_width = {(i, j): w for (i, j), w in zip(flows_present, width)}

    # Point widths
    W = {}
    for (i, j), w in flow_width.items():
        W[i] = w
        W[j] = w
    active_points = set(W.keys())

    # Active groups
    GROUP_ACTIVE = {
        key: [pid for pid in values if pid in active_points]
        for key, values in GROUP_SLOTS.items()
    }

    # Colors
    departing_points = set()
    point_to_color = {}
    for side in ("N", "E", "S", "W"):
        for p in GROUP_ACTIVE[(side, "dep")]:
            departing_points.add(p)
            point_to_color[p] = SIDE_COLOR[side]

    def flow_color(i, j, default="lightblue"):
        if i in departing_points:
            return point_to_color[i]
        if j in departing_points:
            return point_to_color[j]
        return default

    # Place points
    P = {}
    place_group_variable(P, 1, +R, GROUP_ACTIVE[("N","dep")], -d, +1, W)
    place_group_variable(P, 1, +R, GROUP_ACTIVE[("N","arr")], +d, -1, W)

    place_group_variable(P, 0, +R, GROUP_ACTIVE[("E","dep")], +d, -1, W)
    place_group_variable(P, 0, +R, GROUP_ACTIVE[("E","arr")], -d, +1, W)

    place_group_variable(P, 1, -R, GROUP_ACTIVE[("S","dep")], +d, -1, W)
    place_group_variable(P, 1, -R, GROUP_ACTIVE[("S","arr")], -d, +1, W)

    place_group_variable(P, 0, -R, GROUP_ACTIVE[("W","dep")], -d, +1, W)
    place_group_variable(P, 0, -R, GROUP_ACTIVE[("W","arr")], +d, -1, W)

    # Plot
    fig, ax = plt.subplots(figsize=(10, 10))

    for (i, j) in flows_present:
        if i not in P or j not in P:
            continue

        A, B = P[i], P[j]
        w = flow_width[(i, j)]
        col = flow_color(i, j)

        if tuple(sorted((i, j))) in RECT_FLOWS_U:
            add_patch(ax, segment_rectangle(A, B, w), col)
        else:
            Z = C + np.array([A[0], B[1]])
            add_bezier_ribbon(ax, A, B, Z, w, col)

    for side in ("N", "E", "S", "W"):
        ids_dep = GROUP_ACTIVE[(side, "dep")]
        if len(ids_dep) >= 2:
            add_group_arrow(ax, P, W, ids_dep, side, outward=False)

        ids_arr = GROUP_ACTIVE[(side, "arr")]
        if len(ids_arr) >= 2:
            add_group_arrow(ax, P, W, ids_arr, side, outward=True)

    ax.set_aspect("equal", adjustable="box")
    pad = 1.4
    ax.set_xlim(-R - pad, R + pad)
    ax.set_ylim(-R - pad, R + pad)
    ax.set_axis_off()

    # Return PNG bytes (no filesystem)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True, bbox_inches="tight", dpi=300)
    plt.close(fig)

    safe_name = re.sub(r"[^\w\-]+", "_", str(verkehrszählungsort))
    filename = f"VZ_{safe_name}.png"
    return buf.getvalue(), filename
>>>>>>> 5990b1326f8bff3498181549b3e1013a44fcac51
