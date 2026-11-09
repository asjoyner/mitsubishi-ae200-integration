#!/usr/bin/env python3
"""Does a zone warm while parked in heat above its setpoint?

Joins Prometheus (inlet + written setpoint, long retention) with the HA
recorder (hvac mode, fan) on a common grid, then reports the inlet slope
separately for intervals where the equipment could act and where it could not.

Reads HASS_SERVER / HASS_TOKEN from the environment only; run via
run_with_ha_env.sh so the credentials file is never opened here.
"""
import json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

PROM = "http://localhost:9090"
ZONES = [  # (prom group_name, HA climate entity suffix)
    ("VAULT",           "vault"),
    ("MAIN LEVEL LEFT", "main_level_left"),
    ("UPSTAIRS",        "upstairs"),
    ("DOWNSTAIRS",      "downstairs"),
    ("MASTER BEDROOM",  "master_bedroom"),
]
STEP = 300  # 5 min


def get(url, token=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def prom_range(expr, start, end):
    q = urllib.parse.urlencode({
        "query": expr, "start": start.isoformat(), "end": end.isoformat(), "step": STEP})
    d = get("%s/api/v1/query_range?%s" % (PROM, q))
    out = {}
    for res in d["data"]["result"]:
        for ts, val in res["values"]:
            out[int(float(ts)) // STEP * STEP] = float(val)
    return out


def ha_modes(entity, start, token, server):
    q = urllib.parse.urlencode({
        "filter_entity_id": entity, "minimal_response": "", "no_attributes": ""})
    d = get("%s/api/history/period/%s?%s" % (server, start.isoformat(), q), token)
    if not d:
        return []
    out = []
    for s in d[0]:
        t = s.get("last_changed") or s.get("last_updated")
        out.append((datetime.fromisoformat(t).timestamp(), s["state"]))
    return sorted(out)


def mode_at(series, ts):
    cur = None
    for t, st in series:
        if t <= ts:
            cur = st
        else:
            break
    return cur


def main():
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 12
    server = os.environ["HASS_SERVER"].rstrip("/")
    token = os.environ["HASS_TOKEN"]
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    print("Zone response to the control input — last %g h (to %s)"
          % (hours, end.strftime("%Y-%m-%d %H:%MZ")))
    print("=" * 78)

    verdicts = []
    for group, suffix in ZONES:
        inlet = prom_range(
            'ae200_inlet_temperature_celsius{group_name="%s"} * 9/5 + 32' % group, start, end)
        sp = prom_range(
            'ae200_set_temperature_celsius{group_name="%s"} * 9/5 + 32' % group, start, end)
        modes = ha_modes("climate.mitsubishi_ae_200_geothermal_%s" % suffix, start, token, server)

        # Group into contiguous runs of one regime, then take the slope ACROSS
        # each run. Differencing adjacent samples does not work here: the inlet
        # arrives as whole degrees F, so a single 1 F quantisation step over a
        # 5 min gap reads as 12 F/h and swamps any real trend. Over a run of
        # 20 min or more the quantisation is a bounded error on the endpoints
        # instead of a multiplier on every sample.
        MIN_RUN = 20 * 60
        keys = sorted(k for k in inlet if k in sp)
        runs = []          # (label, t_start, t_end)
        for k in keys:
            m = mode_at(modes, k)
            if m not in ("heat", "cool"):
                label = None
            else:
                demanding = (sp[k] > inlet[k] + 0.3) if m == "heat" else (sp[k] < inlet[k] - 0.3)
                label = "%s, %s" % (m, "driving" if demanding else "parked")
            if runs and runs[-1][0] == label and k - runs[-1][2] <= STEP * 1.5:
                runs[-1][2] = k
            else:
                runs.append([label, k, k])

        buckets = {}       # label -> [(slope F/h, minutes)]
        for label, t0, t1 in runs:
            if label is None or t1 - t0 < MIN_RUN:
                continue
            slope = (inlet[t1] - inlet[t0]) * 3600.0 / (t1 - t0)
            buckets.setdefault(label, []).append((slope, (t1 - t0) / 60.0))

        print("\n%s" % group)
        if not buckets:
            print("  no run of %d min or more in a single regime" % (MIN_RUN // 60))
            continue
        for label in sorted(buckets):
            v = buckets[label]
            total = sum(d for _, d in v)
            mean = sum(sl * d for sl, d in v) / total
            flag = ""
            if label == "heat, parked" and mean > 0.3:
                flag = "   <<< WARMING WHILE PARKED IN HEAT"
                verdicts.append(("warming parked in heat", group, mean, total))
            elif label == "cool, parked" and mean > 0.5:
                flag = "   (drifting up, not holding)"
            print("  %-16s %4d min in %d run(s)   slope %+5.2f F/h   runs: %s%s"
                  % (label, total, len(v), mean,
                     ", ".join("%+.2f/%.0fm" % (sl, d) for sl, d in v), flag))

    print("\n" + "=" * 78)
    if verdicts:
        print("VERDICT: a zone parked in heat is still warming its room. Parking")
        print("is doing harm, not nothing. Candidates: dual-setpoint auto, or a")
        print("narrower mode band.")
        for what, g, m, mins in verdicts:
            print("  %-18s %+.2f F/h over %.0f min" % (g, m, mins))
    else:
        print("VERDICT: no zone parked in heat warmed its room by more than")
        print("0.3 F/h in a run of 20 min or more. Not yet proof that parking is")
        print("inert -- it is one window, and it needs days of runs to be a claim.")
    return 0


sys.exit(main())
