# Spare RAM and prepared expert weights

The rejected prepared-activation experiment used only 280 MiB. Preparing
**weights** is a different proposal with a much larger footprint. The same
model has 48 layers × 512 experts. Each expert's two 640×2,560 gate/up
matrices and 2,560×640 down matrix require **9.375 MiB in FP16**. Keeping a
prepared copy of every expert would add **225 GiB**, before metadata or
workspace. That does not fit this 128 GB machine alongside the serving model.

A selective cache is conceivable. The analysis below retains the original
quantized weights for the existing decode path and budgets an extra FP16
copy only for selected experts. It does not allocate GPU memory or build a
prepared-weight kernel.

## Coverage from the existing routing capture

Use only the first full 16K chunk of the public 64K prompt to rank experts,
independently per layer. Select the same number in every layer, then count
their routed rows in the next three chunks. This avoids choosing winners from
the same chunks being evaluated. It still uses one repeated-source prompt;
it does not establish reuse across unrelated OpenClaw requests.

| Extra capacity budget | Cached experts per layer | Held-out routed rows covered | Same-chunk oracle coverage |
|---|---:|---:|---:|
| 4 GiB | 9 | 15.1% | 18.6% |
| 8 GiB | 18 | 23.2% | 28.3% |
| 12 GiB | 27 | 29.4% | 35.7% |
| 16 GiB | 36 | 34.5% | 41.8% |

The oracle reranks on each evaluated chunk and is an optimistic comparison,
not the measured held-out selection. Unused capacity after allocating equal
slots per layer is not reassigned. The 8 GiB case actually allocates about
7.91 GiB in this arithmetic. Allocation alignment, metadata, conversion
workspace and retained prompt state would need additional space.

**Routed-row coverage is not time saved.** A prepared-weight kernel would
read more weight bytes, could change occupancy and scheduling, and would
need to amortize preparation/eviction costs. Exact conversion would also
need to preserve the current kernel's rounding. No speedup, quality result
or safe live allocation budget follows from this calculation. In particular,
the 16 GiB row is not a recommendation to consume the machine's remaining
memory at full context.

This narrows any future experiment to a selective or temporary per-layer
cache. A small operator test must establish a useful benefit before building
cache management or changing the serving engine. The prepared-activation
loss does not decide the result for weights, but spare capacity alone is
insufficient evidence for a performance claim.

## Reproduce

```sh
python3 experiments/strata-expert-profile/hot-weight-capacity.py \
  --routing evidence/strata-performance-2026-11-07/expert-profile/real64k/routing-summary.json \
  --out /tmp/hot-weight-capacity.json
```

[Results and selected expert IDs](../evidence/strata-performance-2026-11-07/expert-hot-weight-capacity.json).
