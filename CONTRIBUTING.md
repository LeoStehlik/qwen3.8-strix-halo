# Contributing

`main` is the canonical branch for deployment scripts, documentation and experiment
evidence. Merge completed work into `main` and retire its topic branch. Keep
experimental code and measured results clearly labelled in `experiments/` and
`evidence/`; merging research does not promote it into the serving deployment.

Benchmark contributions are welcome when they are reproducible. Include:

- Hardware, installed memory and power policy
- OS, kernel and GPU driver
- llama.cpp commit and backend
- Exact model filenames, sizes and SHA-256 hashes
- Context, slots, KV types, batch, ubatch and thread counts
- Complete speculative-decoding settings
- Prompt or public dataset, sampler, seed and output-token limit
- Warm-up procedure and number of repetitions
- Prompt tok/s, decode tok/s, drafted/accepted counts and memory use

Separate measured facts from interpretation. Do not replace an existing result
with a number measured under different settings; add another clearly labelled
row instead.

Before submitting code:

```bash
bash -n run-router.sh run-server.sh scripts/*.sh
python3 -m py_compile *.py
./scripts/verify-install.sh
```

`./scripts/capture-environment.sh` prints a useful baseline for a benchmark
report without including the hostname, user name or network addresses.

Do not commit model weights, downloaded runtime binaries, API tokens, personal
images or generated benchmark output containing private prompts.
