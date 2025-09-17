# Scheduling-assistant
Tool for optimizing meeting scheduling


# How to run

```
pip install ortools pandas
python meeting_scheduler_ortools.py
```


# How it works

## Meeting Scheduler with OR-Tools

This project is a prototype meeting scheduler using Google OR-Tools CP-SAT solver. It schedules meetings for a single day, considering participant availability and minimizing discomfort for meetings outside preferred hours.

## Algorithm Overview

1. **Time Discretization**
   - The day is split into 30-minute slots (48 slots for 24 hours).

2. **Participant Availability**
   - Each participant has a local working window (e.g., 9:00–17:00 local time).
   - Their availability is mapped to UTC slots using their UTC offset.

3. **Meeting Candidates**
   - For each meeting, the algorithm finds all possible start slots where all required participants are available for the full meeting duration.

4. **Variables**
   - For each meeting and candidate slot, a Boolean variable is created to indicate if the meeting starts at that slot.

5. **Constraints**
   - Each meeting must be scheduled exactly once (at one candidate slot).
   - No participant can be double-booked (cannot attend two meetings at the same time).

6. **Objective**
   - The algorithm minimizes a "discomfort" cost, which penalizes meetings scheduled outside each participant’s preferred local hours (9:00–17:00).

7. **Solving**
   - The CP-SAT solver tries to find a feasible schedule that satisfies all constraints and minimizes discomfort.

8. **Output**
   - If a solution is found, it prints the meeting times in UTC and local time for each participant. If not, it reports infeasibility.