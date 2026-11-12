# tl-combat-bench

Luck-free DPS comparison for THRONE AND LIBERTY combat logs.

Gear tests on a training dummy are noisy: two 90-second runs with the same gear can differ by
7% in raw DPS from crit and heavy-attack luck alone. That is bigger than most gear upgrades.
`tlcompare.py` removes the luck so you can see what the gear actually changed.

## Usage

Enable combat logging in game. Record one log per gear setup, then:

```bash
python tlcompare.py A.txt@crit=45,heavy=30 B.txt@crit=52,heavy=30
python tlcompare.py --last 2        # newest two logs in %LOCALAPPDATA%\TL\Saved\CombatLogs
```

`@crit=..,heavy=..` are the percentages from your character sheet for that setup.

Options: `--len SECONDS` (default: shortest log), `--boot N` bootstrap resamples (default 2000).
Python 3.8+, standard library only.

## Method

Post-stratification. Within each skill, every hit falls in one of four cells:
crit x heavy. Each hit is reweighted by `target_cell_probability / observed_cell_fraction`,
so a log that rolled more crits than its rate predicts is scaled back down.

- No damage multipliers or sub-hit tiers have to be modelled. Rolls are independent of which
  sub-hit landed, so the reweighting is unbiased.
- Target rates come from the character sheet per file. Skills with bonus crit chance get a
  per-skill offset from the pooled logs: `skill_rate = pooled_skill_rate * file_rate / pooled_rate`.
- Damage-over-time ticks that can never crit are split into `<skill> (dot)` so they do not
  distort their parent skill.
- All logs are cut to the shortest one, so they cover equal windows.
- Output includes a bootstrap confidence interval per comparison.

Validation: two halves of one log differed by 7% in raw DPS and 0.9% in expected DPS.

## Known limits

- The bootstrap resamples within each skill, so intervals are wide (about +-12-17% on 90 s
  halves). Longer logs tighten them.
- Procs whose *count* depends on crits are not corrected.
- If you omit `@crit/heavy`, the observed rate is used and luck is not removed. The output
  flags this.

`dscasts.py` is a small helper that prints per-cast stats for one skill (Decisive Sniping).

Unofficial fan tool. Not affiliated with or endorsed by NCSOFT or Amazon Games. THRONE AND LIBERTY is a trademark of its respective owners.
