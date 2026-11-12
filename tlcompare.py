"""Compare TL combat logs by LUCK-FREE expected DPS.

Method (post-stratification): within each skill, hits fall in 4 cells (crit x heavy).
Each hit is reweighted by  target_cell_prob / observed_cell_frac, so a log that rolled
more crits than its rate predicts is scaled back down. No multipliers, sub-hit tiers,
or flat bonus damage need modelling: crit/heavy rolls are independent of which sub-hit
it was, so reweighting is unbiased for the damage the SAME hits would deal on average.

Target rates per file:
  - pass the character-sheet chance:  log.txt@crit=45.2,heavy=31   (percent)
  - omitted -> the file's observed rate (still luck-affected; flagged in output)
Per-skill offsets (skills with bonus crit chance) come from the pooled logs:
  skill_rate_in_file = pooled_skill_rate * file_rate / pooled_rate

Usage:
  python tlcompare.py A.txt@crit=45,heavy=30 B.txt@crit=52,heavy=30
  python tlcompare.py --last 2            (newest logs in the TL CombatLogs dir)
  options: --len SECONDS (default: shortest log), --boot N (default 2000)
"""
import argparse, glob, os, random, sys
from collections import defaultdict

LOGDIR = os.path.expandvars(r"%LOCALAPPDATA%\TL\Saved\CombatLogs")


def parse_ts(s):  # 20260916-01:40:58:945
    d, rest = s.split("-")
    h, m, sec, ms = rest.split(":")
    return int(d) * 86400 + int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


def load(path):
    hits = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            p = line.rstrip("\n").split(",")
            if len(p) < 10 or p[1] != "DamageDone" or not p[2]:
                continue
            hits.append((parse_ts(p[0]), p[2], int(p[4]), int(p[5]), int(p[6])))
    hits.sort()
    return hits


def parse_arg(a):
    path, _, opts = a.partition("@")
    if not os.path.exists(path) and os.path.exists(os.path.join(LOGDIR, path)):
        path = os.path.join(LOGDIR, path)
    rates = {}
    for kv in filter(None, opts.split(",")):
        k, v = kv.split("=")
        rates[k.strip()] = float(v) / 100
    return path, rates.get("crit"), rates.get("heavy")


def rate(hits, capable, idx):
    n = sum(1 for h in hits if h[1] in capable)
    return (sum(h[idx] for h in hits if h[1] in capable) / n) if n else 0.0


def expected_damage(hits, crit_cap, heavy_cap, skill_c, skill_h, fc, fh, pool_c, pool_h):
    """Sum of reweighted damage + per-skill breakdown."""
    by_skill = defaultdict(list)
    for h in hits:
        by_skill[h[1]].append(h)
    total, per = 0.0, {}
    for s, hs in by_skill.items():
        pc = min(1.0, skill_c[s] * fc / pool_c) if s in crit_cap and pool_c else None
        ph = min(1.0, skill_h[s] * fh / pool_h) if s in heavy_cap and pool_h else None
        cells = defaultdict(lambda: [0, 0.0])
        for _, _, d, c, hv in hs:
            key = (c if pc is not None else 0, hv if ph is not None else 0)
            cells[key][0] += 1
            cells[key][1] += d
        tgt = {}
        for (c, hv) in cells:
            t = 1.0
            if pc is not None:
                t *= pc if c else 1 - pc
            if ph is not None:
                t *= ph if hv else 1 - ph
            tgt[(c, hv)] = t
        norm = sum(tgt.values()) or 1.0  # renormalise over cells that actually occurred
        n = len(hs)
        e = 0.0
        for k, (cnt, dsum) in cells.items():
            e += (tgt[k] / norm) / (cnt / n) * dsum if tgt[k] > 0 else 0.0
        per[s] = (n, sum(h[2] for h in hs), e)
        total += e
    return total, per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="*")
    ap.add_argument("--last", type=int)
    ap.add_argument("--len", type=float)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--full", action="store_true", help="use each log's full length instead of cutting to the shortest")
    a = ap.parse_args()
    args = a.logs
    if a.last:
        files = sorted(glob.glob(os.path.join(LOGDIR, "*.txt")), key=os.path.getmtime)
        args = [f for f in files if os.path.getsize(f) > 1000][-a.last:]
    if not args:
        sys.exit("no logs given")

    runs = []
    for arg in args:
        path, rc, rh = parse_arg(arg)
        hits = load(path)
        if len(hits) < 10:
            print(f"skip {os.path.basename(path)}: {len(hits)} hits")
            continue
        runs.append({"name": os.path.basename(path), "hits": hits, "rc": rc, "rh": rh})
    if not runs:
        sys.exit("nothing to compare")

    dur = a.len or (1e9 if a.full else min(r["hits"][-1][0] - r["hits"][0][0] for r in runs))
    for r in runs:
        t0 = r["hits"][0][0]
        r["hits"] = [h for h in r["hits"] if h[0] - t0 <= dur]
        r["dur"] = r["hits"][-1][0] - t0

    # Split never-crit DoT ticks off their parent skill: a non-crit, non-heavy hit under half the
    # skill's smallest crit is a tick. Otherwise a log with the DoT removed shifts the skill's
    # crit/heavy rate and the per-skill scaling mistakes that for luck.
    min_crit = {}
    for r in runs:
        for h in r["hits"]:
            if h[3] or h[4]:
                min_crit[h[1]] = min(min_crit.get(h[1], h[2]), h[2])
    for r in runs:
        r["hits"] = [(t, s + " (dot)", d, c, hv)
                     if not c and not hv and s in min_crit and d < min_crit[s] / 2
                     else (t, s, d, c, hv) for t, s, d, c, hv in r["hits"]]

    allhits = [h for r in runs for h in r["hits"]]
    crit_cap = {h[1] for h in allhits if h[3]}
    heavy_cap = {h[1] for h in allhits if h[4]}
    pool_c, pool_h = rate(allhits, crit_cap, 3), rate(allhits, heavy_cap, 4)
    cnt = defaultdict(lambda: [0, 0, 0])
    for h in allhits:
        cnt[h[1]][0] += 1; cnt[h[1]][1] += h[3]; cnt[h[1]][2] += h[4]
    skill_c = {s: v[1] / v[0] for s, v in cnt.items()}
    skill_h = {s: v[2] / v[0] for s, v in cnt.items()}

    def evaluate(r, hits):
        fc = r["rc"] if r["rc"] is not None else rate(hits, crit_cap, 3)
        fh = r["rh"] if r["rh"] is not None else rate(hits, heavy_cap, 4)
        return expected_damage(hits, crit_cap, heavy_cap, skill_c, skill_h, fc, fh, pool_c, pool_h)

    print(f"window {'full' if dur >= 1e9 else f'{dur:.1f}s'}   pooled crit {pool_c:.1%}  heavy {pool_h:.1%}\n")
    rnd = random.Random(1)
    for r in runs:
        hits = r["hits"]
        oc, oh = rate(hits, crit_cap, 3), rate(hits, heavy_cap, 4)
        tot, per = evaluate(r, hits)
        dur = r["dur"]
        r["exp"], r["per"] = tot / dur, per
        r["raw"] = sum(h[2] for h in hits) / dur
        r["oc"], r["oh"] = oc, oh
        # stratified bootstrap: resample hits within each skill (rotation counts fixed)
        groups = defaultdict(list)
        for h in hits:
            groups[h[1]].append(h)
        r["boot"] = []
        for _ in range(a.boot):
            bs = [rnd.choice(g) for g in groups.values() for _ in g]
            r["boot"].append(evaluate(r, bs)[0] / dur)

    def ci(xs):
        xs = sorted(xs)
        return xs[int(0.05 * len(xs))], xs[int(0.95 * len(xs)) - 1]

    print(f"{'log':32} {'len':>6} {'raw DPS':>9} {'exp DPS':>9} {'90% CI':>19}  crit obs/used   heavy obs/used")
    for r in runs:
        lo, hi = ci(r["boot"])
        uc = f"{r['rc']:.1%}" if r["rc"] is not None else "obs*"
        uh = f"{r['rh']:.1%}" if r["rh"] is not None else "obs*"
        print(f"{r['name'][:32]:32} {r['dur']:5.0f}s {r['raw']:9.0f} {r['exp']:9.0f} {lo:9.0f}-{hi:<9.0f}  "
              f"{r['oc']:6.1%}/{uc:7} {r['oh']:6.1%}/{uh}")
    if any(r["rc"] is None or r["rh"] is None for r in runs):
        print("  * obs = no sheet rate given; that rate is still luck. Pass @crit=..,heavy=.. (percent).")

    base = runs[0]
    for r in runs[1:]:
        diffs = [b / a_ - 1 for a_, b in zip(base["boot"], r["boot"])]
        lo, hi = ci(diffs)
        p = sum(d > 0 for d in diffs) / len(diffs)
        print(f"\n{r['name']} vs {base['name']}: {r['exp'] / base['exp'] - 1:+.2%}"
              f"  (90% CI {lo:+.2%} .. {hi:+.2%}, P(better)={p:.2f})")

    skills = sorted({s for r in runs for s in r["per"]},
                    key=lambda s: -max(r["per"].get(s, (0, 0, 0))[2] for r in runs))
    print("\nper skill: hits/min | expected DPS (share)")
    print(f"{'skill':22}" + "".join(f" | {r['name'][-17:]:>27}" for r in runs))
    for s in skills[:12]:
        row = f"{s[:22]:22}"
        for r in runs:
            n, _, e = r["per"].get(s, (0, 0, 0.0))
            dur = r["dur"]
            row += f" | {n * 60 / dur:6.1f} {e / dur:9.0f} ({e / dur / r['exp']:5.1%})"
        print(row)


if __name__ == "__main__":
    main()
