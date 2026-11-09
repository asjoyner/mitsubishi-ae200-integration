#!/usr/bin/python3 -I
"""response_curve: does a zone move its room while parked in the wrong mode?

The climate loop holds heat<->cool for 60 min after a change and needs a zone
2 F past target to flip, so a zone can sit in `heat` while the loop writes it a
cooling setpoint. The comments used to claim such a zone just coasts. It does
not necessarily: on R2 heat recovery the coil carries warm refrigerant while
other zones reject heat, so a parked zone with a hard fan is a heater. Aaron
caught the Vault doing exactly that on 2026-11-09 (heat / setpoint 69 /
return air 72 / fan High). This measures whether it is still happening.

Method: join the Prometheus inlet and written-setpoint series to the recorder's
hvac mode, classify each sample as driving (setpoint on the demanding side of
the room) or parked, then take the inlet slope ACROSS contiguous runs.

Do NOT difference adjacent samples. The AE-200 inlet arrives as whole degrees
F, so one quantisation step over a 5 min gap reads as 12 F/h and swamps any
real trend; the first version of this script "concluded" parking was inert off
+/-100 F/h of noise. Over a run of 20 min or more the quantisation is a bounded
error on the two endpoints instead of a multiplier on every sample.

Reads HASS_SERVER / HASS_TOKEN from the environment only, never the credentials
file. Run it via bin/hvac-response-curve, which sources those the way ~/bin/ha
does.

  response_curve.py [hours] [--prom <path>]
"""
import json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

PROM_URL = "http://localhost:9090"
STEP = 300          # 5 min grid
MIN_RUN = 20 * 60   # shortest run worth a slope
WARM_FLAG = 0.3     # F/h past which a parked zone is "doing harm"

ZONES = [
    ("VAULT",           "vault"),
    ("MAIN LEVEL LEFT", "main_level_left"),
    ("UPSTAIRS",        "upstairs"),
    ("DOWNSTAIRS",      "downstairs"),
    ("MASTER BEDROOM",  "master_bedroom"),
]


def _get(url, token=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def prom_range(expr, start, end):
    q = urllib.parse.urlencode({"query": expr, "start": start.isoformat(),
                                "end": end.isoformat(), "step": STEP})
    d = _get("%s/api/v1/query_range?%s" % (PROM_URL, q))
    out = {}
    for res in d["data"]["result"]:
        for ts, val in res["values"]:
            out[int(float(ts)) // STEP * STEP] = float(val)
    return out


def ha_modes(entity, start, server, token):
    q = urllib.parse.urlencode({"filter_entity_id": entity,
                                "minimal_response": "", "no_attributes": ""})
    d = _get("%s/api/history/period/%s?%s" % (server, start.isoformat(), q), token)
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
        if t > ts:
            break
        cur = st
    return cur


def analyse(group, suffix, start, end, server, token):
    inlet = prom_range(
        'ae200_inlet_temperature_celsius{group_name="%s"} * 9/5 + 32' % group, start, end)
    setp = prom_range(
        'ae200_set_temperature_celsius{group_name="%s"} * 9/5 + 32' % group, start, end)
    modes = ha_modes("climate.mitsubishi_ae_200_geothermal_%s" % suffix,
                     start, server, token)

    runs = []
    for k in sorted(k for k in inlet if k in setp):
        m = mode_at(modes, k)
        if m not in ("heat", "cool"):
            label = None
        else:
            demanding = (setp[k] > inlet[k] + 0.3) if m == "heat" \
                else (setp[k] < inlet[k] - 0.3)
            label = "%s, %s" % (m, "driving" if demanding else "parked")
        if runs and runs[-1][0] == label and k - runs[-1][2] <= STEP * 1.5:
            runs[-1][2] = k
        else:
            runs.append([label, k, k])

    buckets = {}
    for label, t0, t1 in runs:
        if label is None or t1 - t0 < MIN_RUN:
            continue
        slope = (inlet[t1] - inlet[t0]) * 3600.0 / (t1 - t0)
        buckets.setdefault(label, []).append((slope, (t1 - t0) / 60.0))

    out = {}
    for label, v in buckets.items():
        total = sum(d for _, d in v)
        out[label] = {"slope": sum(s * d for s, d in v) / total,
                      "minutes": total, "runs": len(v)}
    return out


def write_prom(path, results, hours):
    lines = [
        "# HELP hvac_zone_slope_fahrenheit_per_hour Inlet slope while the zone was in this regime.",
        "# TYPE hvac_zone_slope_fahrenheit_per_hour gauge",
        "# HELP hvac_zone_regime_minutes Minutes spent in this regime in the window.",
        "# TYPE hvac_zone_regime_minutes gauge",
        "# HELP hvac_zone_parked_warming Parked in heat and still warming the room (1/0).",
        "# TYPE hvac_zone_parked_warming gauge",
        "# HELP hvac_response_curve_window_hours Analysis window.",
        "# TYPE hvac_response_curve_window_hours gauge",
        "# HELP hvac_response_curve_last_run_timestamp_seconds When this last ran; staleness means cron broke.",
        "# TYPE hvac_response_curve_last_run_timestamp_seconds gauge",
        "hvac_response_curve_window_hours %g" % hours,
        "hvac_response_curve_last_run_timestamp_seconds %d" % time.time(),
    ]
    for group, buckets in results.items():
        warming = 0
        for label, b in buckets.items():
            mode, regime = [x.strip() for x in label.split(",")]
            lines.append('hvac_zone_slope_fahrenheit_per_hour{zone="%s",mode="%s",regime="%s"} %.3f'
                         % (group, mode, regime, b["slope"]))
            lines.append('hvac_zone_regime_minutes{zone="%s",mode="%s",regime="%s"} %.0f'
                         % (group, mode, regime, b["minutes"]))
            if mode == "heat" and regime == "parked" and b["slope"] > WARM_FLAG:
                warming = 1
        lines.append('hvac_zone_parked_warming{zone="%s"} %d' % (group, warming))

    # node_exporter reads only *.prom, so write a temp name and rename in.
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, path)


def main(argv):
    hours, prom_path = 24.0, None
    args = argv[1:]
    while args:
        a = args.pop(0)
        if a == "--prom":
            prom_path = args.pop(0)
        else:
            hours = float(a)

    server = os.environ["HASS_SERVER"].rstrip("/")
    token = os.environ["HASS_TOKEN"]
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    print("Zone response to the control input - last %g h (to %s)"
          % (hours, end.strftime("%Y-%m-%d %H:%MZ")))
    print("=" * 78)

    results, flagged = {}, []
    for group, suffix in ZONES:
        buckets = analyse(group, suffix, start, end, server, token)
        results[group] = buckets
        print("\n%s" % group)
        if not buckets:
            print("  no run of %d min or more in a single regime" % (MIN_RUN // 60))
            continue
        for label in sorted(buckets):
            b = buckets[label]
            flag = ""
            if label == "heat, parked" and b["slope"] > WARM_FLAG:
                flag = "   <<< WARMING WHILE PARKED IN HEAT"
                flagged.append((group, b["slope"], b["minutes"]))
            elif label == "cool, parked" and b["slope"] > 0.5:
                flag = "   (drifting up, not holding)"
            print("  %-16s %4.0f min in %d run(s)   slope %+5.2f F/h%s"
                  % (label, b["minutes"], b["runs"], b["slope"], flag))

    print("\n" + "=" * 78)
    if flagged:
        print("VERDICT: a zone parked in heat is still warming its room, so parking")
        print("is doing harm rather than nothing. Candidates: dual-setpoint auto, or")
        print("a narrower mode band.")
        for g, s, m in flagged:
            print("  %-18s %+.2f F/h over %.0f min parked" % (g, s, m))
    else:
        print("VERDICT: no zone parked in heat warmed its room by more than %.1f F/h" % WARM_FLAG)
        print("in a run of %d min or more. One window is not proof -- this needs days" % (MIN_RUN // 60))
        print("of runs before parking can be called inert.")

    if prom_path:
        write_prom(prom_path, results, hours)
        print("\nmetrics -> %s" % prom_path)
    return 0


sys.exit(main(sys.argv))
