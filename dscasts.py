"""Decisive Sniping per-cast stats: main hit + 6 follow-ups (DoT ticks excluded)."""
import os, sys
from tlcompare import load, parse_arg

for arg in sys.argv[1:]:
    path = parse_arg(arg)[0]
    hits = [h for h in load(path) if h[1] == "Decisive Sniping" and (h[3] or h[4] or h[2] >= 10000)]
    casts, i = [], 0
    while i < len(hits):
        t = hits[i][0]
        prev_ok = i == 0 or t - hits[i - 1][0] > 0.5
        next_ok = i + 1 >= len(hits) or hits[i + 1][0] - t > 0.5
        if prev_ok and next_ok:
            fol = []
            j = i + 1
            while j < len(hits) and hits[j][0] - t <= 2.0 and len(fol) < 6:
                fol.append(hits[j]); j += 1
            casts.append((hits[i], fol)); i = j
        else:
            i += 1
    full = [c for c in casts if len(c[1]) == 6]
    n = len(full)
    main = sum(c[0][2] for c in full) / n
    fsum = sum(sum(h[2] for h in c[1]) for c in full) / n
    mc = sum(c[0][3] for c in full) / n; mh = sum(c[0][4] for c in full) / n
    fc = sum(h[3] for c in full for h in c[1]) / (6 * n); fh = sum(h[4] for c in full for h in c[1]) / (6 * n)
    dur = (hits[-1][0] - hits[0][0]) / 60
    print(f"{os.path.basename(path)[:22]:22} casts {len(casts):3} ({len(casts)/dur:4.1f}/min, {len(casts)-n} partial) | "
          f"main {main:7.0f} crit {mc:4.0%} hvy {mh:4.0%} | 6 follow {fsum:7.0f} crit {fc:4.0%} hvy {fh:4.0%} | cast {main+fsum:7.0f}")
