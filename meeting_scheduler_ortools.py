# meeting_scheduler_ortools.py
# Prototype meeting scheduler using OR-Tools CP-SAT
# - Discretizes a single-day horizon into 30-minute slots (UTC)
# - Models participants with local working windows (using UTC offset)
# - Models meetings (teams) with required participants and duration
# - Ensures no participant is double-booked
# - Minimizes a simple "discomfort" cost (penalizes meetings outside local 9-17)

from ortools.sat.python import cp_model
import pandas as pd
import math
from datetime import datetime, timedelta, time

# Helper: convert hour:minute to slot index given epoch_start and slot_length_minutes
def time_to_slot_index(dt_time, epoch_date, slot_length_min):
    minutes = dt_time.hour * 60 + dt_time.minute
    return minutes // slot_length_min

# Configuration
SLOT_MIN = 30  # minutes per discrete slot
SLOTS_PER_DAY = 24 * 60 // SLOT_MIN  # e.g., 48 for 30-min slots
EPOCH_DATE = datetime(2025, 9, 17)  # anchor date (UTC); only used for display
HORIZON_SLOTS = SLOTS_PER_DAY  # one day horizon (extendable)

# Example participants (name, utc_offset_hours, preferred_start_local, preferred_end_local)
participants = [
    ("Alice", -2, time(9,0), time(17,0)),
    ("Bob", 1, time(9,0), time(17,0)),
    ("Cara", 2, time(10,0), time(18,0)),
    ("Dan", -2, time(8,30), time(16,30)),
    ("Eve", 0, time(9,0), time(17,0)),
]

# Example meetings (meeting_id, team_name, duration_minutes, required_participant_names)
meetings = [
    ("Mktg.Sync", "Marketing", 60, ["Alice","Bob","Eve"]),
    ("Eng.AllHands", "Engineering", 30, ["Bob","Cara","Dan"]),
    ("Prod.Planning", "Product", 60, ["Alice","Cara","Eve"]),
]

# Precompute participant availability as boolean arrays of length HORIZON_SLOTS
def local_window_to_utc_slots(utc_offset_hours, start_local, end_local):
    offset_minutes = int(round(utc_offset_hours * 60))
    start_minutes_local = start_local.hour * 60 + start_local.minute
    end_minutes_local = end_local.hour * 60 + end_local.minute
    start_utc_minutes = start_minutes_local - offset_minutes
    end_utc_minutes = end_minutes_local - offset_minutes
    start_slot = math.floor(start_utc_minutes / SLOT_MIN)
    end_slot = math.ceil(end_utc_minutes / SLOT_MIN)
    avail = [False]*HORIZON_SLOTS
    for s in range(HORIZON_SLOTS):
        if s >= start_slot and s < end_slot:
            avail[s] = True
    return avail

participant_avail = {}
for name, utc_off, start_local, end_local in participants:
    participant_avail[name] = local_window_to_utc_slots(utc_off, start_local, end_local)

participant_utc_offsets = {name: utc for name,utc,_,_ in participants}

def slot_to_local_hour(slot_index, utc_offset_hours):
    minutes_utc = slot_index * SLOT_MIN + SLOT_MIN//2
    minutes_local = minutes_utc + int(round(utc_offset_hours*60))
    minutes_local = minutes_local % (24*60)
    hour = minutes_local // 60
    minute = minutes_local % 60
    return hour + minute/60.0

# Candidate start slots per meeting
meeting_candidates = {}
meeting_duration_slots = {}
for mid, team, dur_min, required in meetings:
    dur_slots = math.ceil(dur_min / SLOT_MIN)
    meeting_duration_slots[mid] = dur_slots
    candidates = []
    for s in range(HORIZON_SLOTS - dur_slots + 1):
        ok = True
        for p in required:
            for t in range(s, s+dur_slots):
                if not participant_avail[p][t]:
                    ok=False
                    break
            if not ok:
                break
        if ok:
            candidates.append(s)
    meeting_candidates[mid] = candidates

# CP-SAT model
model = cp_model.CpModel()
start_vars = {}
for mid, team, dur_min, required in meetings:
    for s in meeting_candidates[mid]:
        start_vars[(mid,s)] = model.NewBoolVar(f"start_{mid}_{s}")

# Each meeting scheduled exactly once
for mid, team, dur_min, required in meetings:
    vars_for_mid = [start_vars[(mid,s)] for s in meeting_candidates[mid]]
    if not vars_for_mid:
        # No feasible slot for this meeting — model will be infeasible
        model.AddBoolOr([])  # intentionally infeasible
    else:
        model.Add(sum(vars_for_mid) == 1)

# No double-booking
for p_name, utc_off, _, _ in participants:
    for t in range(HORIZON_SLOTS):
        occupying = []
        for mid, team, dur_min, required in meetings:
            if p_name not in required:
                continue
            dur = meeting_duration_slots[mid]
            for s in meeting_candidates[mid]:
                if s <= t < s+dur:
                    occupying.append(start_vars[(mid,s)])
        if occupying:
            model.Add(sum(occupying) <= 1)

# Discomfort cost: penalty outside local 9-17
def slot_discomfort_for_participant(slot, participant_name):
    utc_off = participant_utc_offsets[participant_name]
    local_hour = slot_to_local_hour(slot, utc_off)
    if 9 <= local_hour < 17:
        return 0
    if local_hour < 9:
        dist = 9 - local_hour
    else:
        dist = local_hour - 17
    return int(math.ceil(dist * 10))

start_cost = {}
for mid, team, dur_min, required in meetings:
    dur = meeting_duration_slots[mid]
    for s in meeting_candidates[mid]:
        cost = 0
        for t in range(s, s+dur):
            for p in required:
                cost += slot_discomfort_for_participant(t, p)
        start_cost[(mid,s)] = cost

objective_terms = []
for key, var in start_vars.items():
    cost = start_cost.get(key, 0)
    if cost != 0:
        objective_terms.append(var * cost)
model.Minimize(sum(objective_terms))

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 30
solver.parameters.num_search_workers = 8
status = solver.Solve(model)

rows = []
if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
    for mid, team, dur_min, required in meetings:
        chosen = None
        for s in meeting_candidates[mid]:
            v = start_vars[(mid,s)]
            if solver.Value(v) == 1:
                chosen = s
                break
        start_utc = None
        end_utc = None
        if chosen is not None:
            start_utc = EPOCH_DATE + timedelta(minutes=chosen*SLOT_MIN)
            end_utc = start_utc + timedelta(minutes=meeting_duration_slots[mid]*SLOT_MIN)
        local_times = []
        for p in required:
            if chosen is not None:
                off = participant_utc_offsets[p]
                start_local = start_utc + timedelta(hours=off)
                end_local = end_utc + timedelta(hours=off)
                local_times.append(f"{p}: {start_local.time().strftime('%H:%M')}–{end_local.time().strftime('%H:%M')} (UTC{off:+})")
            else:
                local_times.append(f"{p}: n/a")
        rows.append({
            "Meeting": mid,
            "Team": team,
            "StartUTC": start_utc.time().strftime("%H:%M") if start_utc else None,
            "EndUTC": end_utc.time().strftime("%H:%M") if end_utc else None,
            "LocalTimes": " | ".join(local_times),
            "Attendees": ",".join(required),
            "Penalty": sum(start_cost[(mid,chosen)] for _ in [0]) if chosen is not None else None
        })
else:
    print("No feasible solution found. Solver status:", status)

df = pd.DataFrame(rows)
print(df.to_string(index=False))
