# Factory GPU clock-policy screen: keep automatic clocks

Five cold 64K requests did not establish a useful new clock-policy baseline.
`high` measured **1.48% above its bracketing controls** in one arm, with uneven
memory-stall activity. `profile_peak` was **8.58% slower** than its controls.
Both remain unselected. The original **`auto`** policy was restored and the
existing endpoint was loaded/idle at **19:21:03 UTC**.

This was a hardware-policy screen, not an overclock: no clock table, voltage
override, power limit or firmware was modified. Linux documents `high`
as selecting the highest power state, and the profiling modes as disabling
clock/power gating; these descriptions do not guarantee an observed frequency
on this APU. See the [kernel interface documentation](https://docs.kernel.org/7.2/gpu/amdgpu/thermal.html#power-dpm-force-performance-level).

## Controlled configuration

The already loaded packaged engine remained running throughout: HIP-Halo
0.1.57, UD-Q4_K_XL, 262,144 context, INT8 KV, all 24,576 experts resident,
16,384 prefill capacity, short-read 64, stream minimum 128 and MTP depth 4.
The independent message-boundary checkpoint live trial remained enabled.
No source experiment or tracing was enabled. Neither Strata nor the Mac
OpenClaw gateway was restarted.

The [driver](../benchmarks/strata-clock-policy.py) ran the existing public
prefill fixture using greedy sampling, presence penalty zero and 128 output
tokens **for these benchmark requests only**. A different leading nonce per
arm prevented prefix reuse on the same engine. All five measured responses
reported **zero reused tokens** and complete streams. Prompt length varied
by three tokens; reported rates use actual counts. Different prompts mean
output hashes are recorded evidence, not an exact-output comparison.
No OpenClaw task or tool was executed.

Order was `auto / high / auto / profile_peak / auto`. Each arm included the
standard small warm-up, then one measured request. The server remained
available but occupied during inference. Request-count checks found no
concurrent client requests. This is a bounded screen, not a repeated trial
of either candidate or a representative generation benchmark.

## Results

| Mode, in order | New tokens | Prefill seconds | Prefill tok/s | Median observed GPU MHz | Median temperature °C |
|---|---:|---:|---:|---:|---:|
| auto | 65,549 | 46.888 | 1,398.0 | 2,617 | 65 |
| high | 65,546 | 46.264 | 1,416.8 | 2,541 | 75 |
| auto | 65,549 | 47.013 | 1,394.3 | 2,569 | 78 |
| profile_peak | 65,547 | 51.398 | 1,275.3 | 2,207 | 77 |
| auto | 65,546 | 46.960 | 1,395.8 | 2,552 | 82 |

Sensor summaries use half-second samples where the API reported `reading`
and prompt size exceeded 60,000. Median reported power was about 120 W in
every arm. These observations do not establish the firmware's limiting
mechanism; do not label the run definitively thermally or power throttled.
The peak mode did not sustain the advertised 2,900 MHz ceiling. Its lower
observed clocks accompanied lower throughput, and returning to automatic
policy restored performance despite a higher median temperature.

The high-mode comparison is a small positive result to retain as evidence,
not a reason to change the default. The first control accumulated 378 ms of
main-process KFD eviction time during sampled reading; the high arm and next
control had zero sampled reading-counter increases. Whole-arm deltas were
378 / 32 / 567 ms, including warm-up and generation. Peak's sampled reading
delta was 482 ms and its return control's 142 ms. VM migration/compaction and
page-reclaim counters also moved. These counters are not independent wall
durations: do not subtract them to manufacture corrected throughput or sum
the inference and vision processes as stall time.

The short 128-token outputs varied in content and draft acceptance. Their
35–42 tok/s generation readings do not prove either a generation improvement
or regression. No representative long-generation experiment was done here.

## Reproduction and evidence

Use an idle AMD endpoint with the documented serving configuration and a
private Strata profile containing its existing API key. The script uses
noninteractive sudo only to write the selected mode to
`power_dpm_force_performance_level`. It restores the original mode in a
`finally` block on completion or ordinary exceptions. Check the sysfs value
manually after a forced process kill or host failure.

```sh
curl -L --fail \
  https://raw.githubusercontent.com/LeoStehlik/qwen3.6-35b-a3b-strix-halo/fc06ab712eb6a89e49d5c935ae47dba190c1a0a5/benchmarks/fixtures/prompt.txt \
  -o /tmp/strata-public-reference.txt
python3 benchmarks/strata-clock-policy.py \
  --profile /path/to/private-strata-profile.json \
  --fixture /tmp/strata-public-reference.txt \
  --out /tmp/strata-clock-aba --url http://100.96.8.54:8083
python3 benchmarks/strata-clock-policy.py \
  --profile /path/to/private-strata-profile.json \
  --fixture /tmp/strata-public-reference.txt \
  --out /tmp/strata-clock-peak --url http://100.96.8.54:8083 \
  --modes profile_peak auto
```

Output directories must be new. Use the actual endpoint and GPU device for
the host being tested. The [evidence](../evidence/strata-performance-2026-11-07/clock-policy/)
contains the redacted profile, unchanged runtime override, engine/fixture
hashes, supported-mode probe, full public API results, sensor/VM/KFD samples,
analysis and restoration health. Private credentials and live conversation
logs are excluded. All five requests were cold; this does not raise the
baseline or meet the 1,700–2,000 prefill / 50–70 generation targets.
