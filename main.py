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


# --------------------- CONFIG ---------------------
# Minimum/maximum thickness for flow bands 
width_min = 0.1
width_max = 0.7

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
d = 1.5                       # distance from center line to middle point of group
inward = 0.9                # inward control for bezier curves (curvature strength)

FILL = "lightblue"
EDGE = "none"
EDGE_LW = 0.0

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

def add_flow_label_before_start(ax, A, side, text, color, fontsize=6):
    """Adds a the traffic near the start of the corresponding flow, before the flow begins"""
    A = np.asarray(A, float)        #Ensures A is a numpy float array.

    back = 0.15                     #How far outside the port the label sits

    #Locate start position and orientation based on side
    if side == "E":
        u_pos = np.array([1.0, 0.0])    
        angle_deg = 0
        ha, va = "left", "center"
    elif side == "W":
        u_pos = np.array([-1.0, 0.0])    
        angle_deg = 0
        ha, va = "right", "center"
    elif side == "N":
        u_pos = np.array([0.0, 1.0])     
        angle_deg = -90                  
        ha, va = "right", "center"
    else:  # "S"
        u_pos = np.array([0.0, -1.0])    
        angle_deg = -90
        ha, va = "left", "center"

    #Final label position
    pos = A + back * u_pos

    ax.text(
        pos[0], pos[1], text,
        rotation=angle_deg,
        rotation_mode="anchor",
        ha=ha, va=va,
        fontsize=fontsize,
        color=color,
        zorder=50,
        clip_on=False
    )

def compute_side_sums(flows_present, kfz_array, bike_array=None):
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

    dep_bike = {s: 0.0 for s in ("N", "E", "S", "W")} if bike_array is not None else None
    arr_bike = {s: 0.0 for s in ("N", "E", "S", "W")} if bike_array is not None else None

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

    # --- Bike sums (optional) ---
    if bike_array is not None:
        for (i, j), bike in zip(flows_present, bike_array):
            if i in dep_pid_to_side and j in arr_pid_to_side:
                dep_side = dep_pid_to_side[i]
                arr_side = arr_pid_to_side[j]
            elif j in dep_pid_to_side and i in arr_pid_to_side:
                dep_side = dep_pid_to_side[j]
                arr_side = arr_pid_to_side[i]
            else:
                continue

            dep_bike[dep_side] += float(bike)
            arr_bike[arr_side] += float(bike)

        total_bike = {s: dep_bike[s] + arr_bike[s] for s in ("N", "E", "S", "W")}

        return {
            "dep_kfz": dep_kfz,
            "arr_kfz": arr_kfz,
            "total_kfz": total_kfz,
            "dep_bike": dep_bike,
            "arr_bike": arr_bike,
            "total_bike": total_bike,
        }

    return {
        "dep_kfz": dep_kfz,
        "arr_kfz": arr_kfz,
        "total_kfz": total_kfz,
    }

def calculate_width(direction_dic, tmin, tmax, gamma=1.0):
    """
    Calculate width array based on KFZ values using a GLOBAL mapping:
      - tmin -> width_min
      - tmax -> width_max
      - in between proportional (non-linear with gamma)

    gamma = 1.0  -> linear
    gamma < 1.0  -> more resolution for small flows (recommended: 0.5)
    gamma > 1.0  -> more resolution for large flows
    """
    traffic = np.array([sub_dic["kfz"] for sub_dic in direction_dic.values()], dtype=float)  #Extracts all kfz values from the dictionary (in iteration order)

    if traffic.size == 1 or np.isclose(tmax, tmin):     #If only one flow or all flows equal (no scale), give them all mid-width
        return np.round(np.full_like(traffic, (width_min + width_max) / 2.0), 2)

    norm = (traffic - tmin) / (tmax - tmin)     #Normalize to [0,1]
    norm = np.clip(norm, 0.0, 1.0)      #Ensure norm within [0,1]

    widths = width_min + (norm ** gamma) * (width_max - width_min)      #Scale to [width_min, width_max] using gamma correction
    return np.round(widths, 2)      #Returns all widths 

def build_direction_dic(sheets, peak_idx):
    """Build direction dictionary for a given peak index from sheets starting with R."""
    dic = {}
    for sheet_name, df in sheets.items():       #Iterate over all sheets
        if sheet_name.startswith("R"):          #Only process sheets starting with "R"
            kfz_sum = df.iloc[peak_idx:peak_idx+4, 2:9].sum().sum()     #Sum kfz values in the specified range (4 rows starting at peak_idx, columns 2 to 8)
            total_sum = df.iloc[peak_idx:peak_idx+4, 1:9].sum().sum()   #Sum total values (kfz + rad) in the specified range (4 rows starting at peak_idx, columns 1 to 8)
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

def add_group_arrow(ax, P, W, group_ids, side, outward=True, color="k", zorder=10):
    """Add an arrow for a group of slots.
    Find the “outermost” and “innermost” ports in that group.
    Create a base line between two boundary points.
    Create a tip point offset outward/inward depending on outward.
    """
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

def create_plot(kfz, bike, width, flows_present, verkehrszählungsort, suffix, start_time, end_time, side_colors, d_NS, d_WE):
    """Create a PNG plot for given traffic and width data.
    kfz: numpy array of KFZ flow magnitudes aligned with flows_present
    bike: numpy array of bicycle flow magnitudes aligned with flows_present
    width: numpy array of ribbon widths aligned with flows_present
    flows_present: list of (i,j) present
    present_dirs: list of sheet names ["R1","R2",...] (mostly informational)
    verkehrszählungsort: location name from Excel
    suffix: string for filename (full_day, morning_peak, ...)
    side_colors: optional dict overriding SIDE_COLOR
    """
    # Update SIDE_COLOR with user-provided side_colors
    if side_colors:
        SIDE_COLOR.update(side_colors)

    # Width mapping already done
    flow_width = {(i, j): w for (i, j), w in zip(flows_present, width)}
    
    #Example: flows_present = [(1,24),(2,17),(3,10),(6,7)]
    #         width         = [0.65,    0.30,   0.15,  0.55]
    #         flow_width = {(1,24): 0.65, (2,17): 0.30, (3,10): 0.15, (6,7) : 0.55}

    # Assigns a width to each port ID
    W = {}
    for (i, j), w in flow_width.items():
        W[i], W[j] = w, w
    active_points = set(W.keys())

    # Map each flow (i,j) -> traffic value (same ordering as flows_present), only for the text of the traffic
    flow_kfz  = {(i, j): float(v) for (i, j), v in zip(flows_present, kfz)}
    flow_bike = {(i, j): float(v) for (i, j), v in zip(flows_present, bike)}
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
            departing_points.add(p)                 #Add departing point to set
            pid_to_side[p] = side                   #Map port ID to side
            point_to_color[p] = SIDE_COLOR[side]    #Map port ID to color

    def flow_color(i, j, default="lightblue"):      #Determine flow color based on departing points
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

    # Plot
    fig, ax = plt.subplots(figsize=(10, 10))  #fig is the whole image canvas, ax is the coordinate system where shapes are drawn

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
            
        # ---------- LABEL BEFORE START ----------
        if show_departure_labels:
            start_pid = None

            # only label flows that start at a departing point
            if i in departing_points:
                start_pid = i
            elif j in departing_points:
                start_pid = j

            if start_pid is not None:
                Astart = np.asarray(P[start_pid], float)
                side = pid_to_side[start_pid]
                kfz = flow_kfz[(i, j)]
                bike = flow_bike[(i, j)]
                txt = f"{int(round(kfz))} | {int(round(bike))}"
                add_flow_label_before_start(ax, Astart, side, txt, color=col, fontsize=6)

    # ---------- GROUP ARROWS ----------
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
    buf = io.BytesIO()                  #raw bytes like a file (so you can read Excel and write PNGs without saving to disk)
    fig.savefig(buf, format="png", transparent=True, bbox_inches="tight", dpi=300)
    plt.close(fig)

    safe_name = re.sub(r"[^\w\-]+", "_", str(verkehrszählungsort))
    filename = f"VZ_{safe_name}_{suffix}_{start_time}_{end_time}.png"
    return buf.getvalue(), filename

# --------------------- MAIN GENERATOR ---------------------
def generate_png_from_excel(excel_bytes: bytes, side_colors: Optional[Dict[str, str]] = None, d_NS: float = 1.5, d_WE: float = 1.5) -> Tuple[List[Tuple[bytes, str]], Dict[str, Any]]:
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

    first_R_df = None
    
    # Find peaks
    kfz_morning_peak = 0
    kfz_afternoon_peak = 0
    for idx in range(13, 77+1):  # sliding window of 4 rows
        kfz_block_sum = 0
        
        for sheet_name, df in sheets.items():
            if sheet_name.startswith("R"):
                if first_R_df is None:
                    first_R_df = df
                kfz_sheet_block_sum = df.iloc[idx:idx+4, 2:9].sum().sum()
                kfz_block_sum += kfz_sheet_block_sum
                
        # read time from first_R_df (stable reference)
        if first_R_df is None:
            raise ValueError("No R sheets found – first_R_df was never assigned")
        time_start = first_R_df.iloc[idx, 0]
        time_end   = first_R_df.iloc[idx+3, 0]

        if idx < 40 and kfz_block_sum > kfz_morning_peak:
            kfz_morning_peak = kfz_block_sum
            morning_time_start = time_start
            morning_time_end = time_end
            morning_start_idx = idx

        if idx >= 40 and kfz_block_sum > kfz_afternoon_peak:
            kfz_afternoon_peak = kfz_block_sum
            afternoon_time_start = time_start
            afternoon_time_end = time_end
            afternoon_peak_start_idx = idx


    col = 1
    start = 13   # Excel row 14
    end = 80     # Excel row 81 (inclusive)

    first_idx = None
    last_idx = None
    started = False
    if first_R_df is None:
        raise ValueError("No R sheets found – first_R_df was never assigned")

    for row_idx in range(start, end + 1):
        current_value = first_R_df.iloc[row_idx, col]

        if pd.notna(current_value) and not started:
            first_idx = row_idx
            last_idx = row_idx
            started = True
        elif pd.notna(current_value) and started:
            last_idx = row_idx
        elif pd.isna(current_value) and started:
            break
        
    if first_idx is None or last_idx is None:
        raise ValueError("No non-NaN data found in the specified range (rows 14–81)")
    day_start_time = str(first_R_df.iloc[first_idx, 0]).split("-")[0]
    day_end_time   = str(first_R_df.iloc[last_idx, 0]).split("-")[-1]
    morning_time_start = str(morning_time_start).split("-")[0]
    morning_time_end   = str(morning_time_end).split("-")[-1]

    afternoon_time_start = str(afternoon_time_start).split("-")[0]
    afternoon_time_end   = str(afternoon_time_end).split("-")[-1]
    # day_start = str(day_start_time).split('-')[0]
    # day_end_time = str(day_end_time).split('-')[1]

    # morning_peak_start = str(morning_time_start).split('-')[0]
    # morning_peak_end = str(morning_time_end).split('-')[1]
    # afternoon_peak_start = str(afternoon_time_start).split('-')[0]
    # afternoon_peak_end = str(afternoon_time_end).split('-')[1]
    
    # Build peak dics
    direction_morning_dic = build_direction_dic(sheets, morning_start_idx)
    direction_afternoon_dic = build_direction_dic(sheets, afternoon_peak_start_idx)

    # --- Ensure consistent ordering (important!) ---
    present_dirnums = sorted(int(name[1:]) for name in direction_dic.keys()) #Convert "R1" → 1, etc, and sorts
    if not present_dirnums:
        raise ValueError("No 'R*' sheets found. Nothing to plot.")

    present_dirs = [f"R{k}" for k in present_dirnums]       #ordered list of sheet names
    flows_present = [DIR_TO_FLOW[k] for k in present_dirnums]       #ordered list of edges (i,j) matching those directions

    # Reorder dictionaries so their .values() match present_dirs order
    direction_dic = {k: direction_dic[k] for k in present_dirs}
    direction_morning_dic = {k: direction_morning_dic[k] for k in present_dirs}
    direction_afternoon_dic = {k: direction_afternoon_dic[k] for k in present_dirs}

    # --- Global min/max across ALL three datasets ---
    all_kfz = []
    for dir in (direction_dic, direction_morning_dic, direction_afternoon_dic):
        all_kfz.extend(v["kfz"] for v in dir.values())

    tmin = float(min(all_kfz))
    tmax = float(max(all_kfz))

    # --- Calculate widths on shared scale ---
    gamma = 0.5  # <--- more resolution; set to 1.0 for strict linear

    width_general = calculate_width(direction_dic, tmin, tmax, gamma=gamma)
    width_morning_peak = calculate_width(direction_morning_dic, tmin, tmax, gamma=gamma)
    width_afternoon_peak = calculate_width(direction_afternoon_dic, tmin, tmax, gamma=gamma)

    present_dirnums = sorted(int(name[1:]) for name in direction_dic.keys())
    if not present_dirnums:
        raise ValueError("No 'R*' sheets found. Nothing to plot.")

    kfz_general = np.array([direction_dic[name]["kfz"] for name in present_dirs], dtype=float)
    kfz_morning = np.array([direction_morning_dic[name]["kfz"] for name in present_dirs], dtype=float)
    kfz_afternoon = np.array([direction_afternoon_dic[name]["kfz"] for name in present_dirs], dtype=float)

    bike_general = np.array([direction_dic[name]["rad"] for name in present_dirs], dtype=float)
    bike_morning = np.array([direction_morning_dic[name]["rad"] for name in present_dirs], dtype=float)
    bike_afternoon = np.array([direction_afternoon_dic[name]["rad"] for name in present_dirs], dtype=float)

    side_general = compute_side_sums(flows_present, kfz_general, bike_general)
    side_morning = compute_side_sums(flows_present, kfz_morning, bike_morning)
    side_afternoon = compute_side_sums(flows_present, kfz_afternoon, bike_afternoon)

        # ---- Per-direction KFZ + Bicycle values for display in Streamlit ----
    per_direction = []
    for name in present_dirs:
        per_direction.append({
            "direction": name,  # e.g. "R1"
            "full_day_kfz": float(direction_dic[name]["kfz"]),
            "full_day_bike": float(direction_dic[name]["rad"]),
            "morning_peak_kfz": float(direction_morning_dic[name]["kfz"]),
            "morning_peak_bike": float(direction_morning_dic[name]["rad"]),
            "afternoon_peak_kfz": float(direction_afternoon_dic[name]["kfz"]),
            "afternoon_peak_bike": float(direction_afternoon_dic[name]["rad"]),
        })
    
    # Generate three plots
    pngs = []
    pngs.append(create_plot(kfz_general, bike_general, width_general, flows_present, verkehrszählungsort, "full_day", day_start_time, day_end_time, side_colors, d_NS, d_WE))
    pngs.append(create_plot(kfz_morning, bike_morning, width_morning_peak, flows_present, verkehrszählungsort, "morning_peak", morning_time_start, morning_time_end, side_colors, d_NS, d_WE))
    pngs.append(create_plot(kfz_afternoon, bike_afternoon, width_afternoon_peak, flows_present, verkehrszählungsort, "afternoon_peak", afternoon_time_start, afternoon_time_end, side_colors, d_NS, d_WE))


    meta = {
        "location": verkehrszählungsort,
        "day": {"start": day_start_time, "end": day_end_time},
        "morning_peak": {"start": morning_time_start, "end": morning_time_end},
        "afternoon_peak": {"start": afternoon_time_start, "end": afternoon_time_end},
        "tmin": tmin,
        "tmax": tmax,
        "gamma": gamma,

        "per_direction": per_direction,
        "totals": {
            "full_day_kfz": float(np.sum(kfz_general)),
            "morning_peak_kfz": float(np.sum(kfz_morning)),
            "afternoon_peak_kfz": float(np.sum(kfz_afternoon)),

            "full_day_bike": float(sum(direction_dic[n]["rad"] for n in present_dirs)),
            "morning_peak_bike": float(sum(direction_morning_dic[n]["rad"] for n in present_dirs)),
            "afternoon_peak_bike": float(sum(direction_afternoon_dic[n]["rad"] for n in present_dirs)),
        },
        
        "by_side": {
        "full_day": side_general,
        "morning_peak": side_morning,
        "afternoon_peak": side_afternoon,
        }
    }
    
    return pngs, meta