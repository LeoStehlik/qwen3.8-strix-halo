# Flash-Next deployment record and recovery handoff

**Historical checkpoint: 2026-11-06 before reboot, originally awaiting go.**
The complete record was pushed and verified in commit `3a4cba4`. The user then
authorized the Linux-host reboot at 18:31 UTC. Acquisition was stopped gracefully
and the remaining shard workers exited after SIGINT. Recovery remains unverified.
The snapshot/table below retain the earlier checkpoint state, not live status.
Do not restart the Mac mini or its OpenClaw gateway.

**Later update:** the authorized reboot completed and GPU/27B endpoint recovery
was verified. Acquisition needed a wrapper correction before resuming. See the
[post-reboot result](STRATA-RECOVERY-RESULT-2026-11-06.md); the evidence below
remains the original pre-reboot record.

This is the operational record for the Linux Strix Halo host. The
[deployment guide](STRATA-FLASH-NEXT.md) contains installation commands, the
planned serving settings and benchmark protocol. The
[machine-readable snapshot](../evidence/strata-2026-11-06/pre-reboot-snapshot.json)
and [archived host files](../evidence/strata-2026-11-06/host-records/README.md)
make the local changes and failure inspectable after this session ends.

## State at the documentation checkpoint

| Item | Observed state |
|---|---|
| Strata Terminal/control | Installed, packaged version 0.1.57 from release v0.2.11 |
| HIP-Halo engine | Signed build `0bdcef4682c5+rocm`, gfx1151, all 282 package files verified |
| Engine test performed | Binary `--version`; GPU auto-detection passed before the driver fault |
| Flash-Next inference | Never started; tools, vision, state and throughput untested |
| Target download | About 43.98 GB durably recorded at 18:21 UTC, out of 111.33 GB |
| Completed target files | Shards 1 and 4; installer SHA-256 marks match expected hashes |
| Partial target files | Shards 2 and 3; resumable 32 MiB pieces; whole-file hashing pending |
| Auxiliary model files | MTP about 5.2 GB and image projector about 0.9 GB still pending |
| GPU | `amdgpu` stuck in `going`; `/dev/dri` and `/dev/kfd` absent; kernel taint 128 |
| Dense 27B endpoint | Offline; unit currently failed, with no main process; enabled for boot |
| Qwen3.6 | Inactive and disabled; weights and frozen code/evidence retained |
| Acquisition supervisor | Enabled user unit, running in its download-wait stage; linger enabled |
| Reboot | Not performed, not scheduled; waiting for explicit user go |

Progress is a timestamped snapshot, not a live counter. Sparse `.part` file lengths
can overstate downloaded bytes. The snapshot counts only fsynced pieces listed
in `.part.chunks` plus completed files; in-flight pieces are excluded. A `.done`
SHA-256 mark records the installer's verification, not a second hash pass by this
documentation task. Preserve `.part`, `.part.chunks`, `.part.src` and completed
files together. Incomplete pieces may be downloaded again after interruption.

## Decisions and previous evidence

Qwen3.6's prefill work reached 1,045–1,049 tok/s in its frozen tests, but its live
OpenClaw failures made it unsuitable for this deployment. The
[operational setback](https://github.com/LeoStehlik/qwen3.6-35b-a3b-strix-halo/blob/main/docs/OPERATIONAL-SETBACK.md)
separates observed failures from unproven causes. The frozen tag
`prefill-stage2-2026-11-04` resolves to commit
`e0bb26c66c9637b8d8f6042947414610a280bffe`; the current documentation head is
`fc06ab712eb6a89e49d5c935ae47dba190c1a0a5`. No Qwen3.6 weights, builds or dirty
source trees were deleted in this Strata deployment work.

The restored dense 27B backend had a historical cold-64K result of 367.33 tok/s;
the later 371.40 tok/s instrumented run was not a speedup claim. Its
[profile and findings](PREFILL-RETURN-2026-11-05.md) remain available. Further
dense-kernel work is deferred while trying Flash-Next on a packaged engine.

The user has already found Flash-Next useful with OpenClaw through Ollama Cloud.
That is a reason to try it locally, not proof of this quant/server's behavior.
The chosen local quant is Unsloth UD-Q4_K_XL, with 256K context, INT8 KV, one slot,
MTP depth 4 and a 16K prefill chunk. Route-tail skipping is explicitly disabled.
No production output-token cap or removal of tools is part of this plan.

The published 1,211 tok/s prefill / 42.64 tok/s decode at 128K belongs to the
maintainers' older Strata 0.1.40 Halo measurements. It has not been reproduced
here. The current launcher also carries a Q4 first-request-hang warning based on
0.1.54/0.1.55; current-build startup reliability remains a required test.

## What ran, in order

Times below are approximate; the kernel excerpt and state snapshot retain their
own timestamps. This list describes actions already taken, not commands to repeat.

1. Inspected the installed dense backend, local hardware, upstream release,
   model pins, Halo documentation, and installation/launch code. Preserved the
   dirty deployment and frozen Qwen3.6 sources.
2. Added a `less:rw` ACL to `/dev/kfd` for the existing login, which predated its
   supplementary-group membership. The `render` and `video` groups already
   contain `less`; the existing render-node ACL was not replaced. The original
   KFD ACL is archived. Device-node ACLs are transient; verify access after boot.
3. Installed Terminal/control from the pinned v0.2.11 release feed. The Linux
   control archive is 99,944,994 bytes, SHA-256
   `2ac78cffee4a638b4f32d3020d5a85da8bd1d32a2b12705d8c4fb706b6094d08`.
   The installer checked the archive checksum and signed feed.
4. Started `strata install -- ... --no-start` for UD-Q4_K_XL. Because the engine
   download was still separate, this first pass warned that no image encoder
   was installed. It was interrupted during target acquisition before writing
   the final model configuration. The final installer rerun must retain vision.
5. Started the signed engine update using `--backend hip-halo`. It installed
   the Halo variant, including ROCm libraries, CPU/GPU vision readers and the
   `gfx1151-hipblaslt-100401.txt` table. No compiler, ROCm toolchain, driver
   package or new engine fork was built. Model preparation has not finished.
6. Used Strata's unmodified resumable, checksum-verifying downloader to fetch
   target shards 2, 3 and 4 concurrently, with 32 connections per shard. The
   [helper](../evidence/strata-2026-11-06/host-records/fetch-shard.py.txt) imports
   the pinned installer's download function; it does not change model bytes or
   relax hashes. A brief pause of those workers let the engine download finish;
   the workers were resumed. Shards 2 and 3 are still running at this checkpoint.
7. Verified every engine package file and automatic backend selection. For this
   CLI, update selection accepts `hip-halo`, while `components engine` expects
   backend `hip`; the verified manifest carries variant `halo`. An initial
   verification call with `hip-halo` reported a selection mismatch; rerunning
   with `hip` and then auto-detection passed. This was not an engine load test.
8. Published the install/launch scripts, tool smoke check, long-prefill probe,
   expected target hashes and engine evidence on branch
   `deploy/strata-flash-next-20261106` (subsequently merged into `main` and retired).
   Shell/Python syntax and launch-plan checks
   passed; no model-based test has run.
9. Found the existing GPU limit was 61,905,670,144 bytes of GTT, with TTM limits
   15,113,689 pages and an 8 GiB BIOS carve-out. The published benchmark used
   112 GiB GTT. The kernel reads these limits into GTT/KFD state at initialization;
   a writable sysfs parameter does not resize all already-initialized state.
10. At about 16:50 UTC, attempted a headless GPU reload after checking that the
    dense 27B slot was idle and it was the only reported GPU client. Stopped its unit,
    wrote the larger TTM configuration, then ran `sudo modprobe -r amdgpu`.
    That removal faulted in the kernel. **This assistant-initiated maintenance
    caused the local inference outage.** It was not caused by a Flash-Next load.
11. The maintenance helper's error path removed the new configuration, tried
    to load `amdgpu` again, and restarted the old unit in `finally`. The removal
    process had died with SIGKILL; the subsequent load returned exit 1. The
    restarted model reported no usable GPU and used CPU fallback. HTTP health
    returned `ok`, but that did not establish restored GPU service. The fallback
    was stopped explicitly. The original failure helper is archived as evidence
    only; **do not run it again**.
12. Captured the kernel fault and confirmed module state `going`, taint 128 and
    missing GPU nodes. Prepared recovery: rewrote the TTM boot configuration,
    rebuilt the running kernel's initramfs, verified the configuration is inside
    it, and checked enabled network/Tailscale/SSH services and user linger.
13. Replaced the transient preparation supervisor with an enabled persistent
    user unit. It waits for owned downloader PIDs with matching start times,
    then reruns the pinned installer with `--no-start` and checks the launch plan.
    Its only terminal success state is `prepared-awaiting-validation`. It never
    promotes Flash-Next or sends an OpenClaw request. Failed preparation retries
    after 60 seconds; it may fail while the GPU is unavailable and retry after
    recovery. Recovery behavior is configured, not yet boot-tested.

## Files, services and settings to preserve

| Purpose | Location / value |
|---|---|
| Deployment worktree | `/home/less/worktrees/qwen38-strata-20261106` |
| Git branch at this historical checkpoint | `deploy/strata-flash-next-20261106` (now merged into `main` and retired) |
| Strata command | `/home/less/.local/bin/strata` |
| Terminal bundle | `/home/less/.local/share/strata/terminal/0.1.57` |
| Engine bundle | `/home/less/.local/share/strata/components/engine/0.1.57-linux-x86_64-hip-halo` |
| Model data root | `/home/less/models/strata-flash-next` |
| Target shard directory | `models/unsloth-UD-Q4_K_XL` under that data root |
| Final installer config root | `/home/less/.local/share/strata/flash-next` (`STRATA_INSTALL_DIR`) |
| Acquisition / maintenance records | `/home/less/.cache/strata-evaluation-20261106` |
| Supervisor | `finish-preparation.py` in the records directory |
| Supervisor status | `preparation-status.json` in the records directory |
| Final preparation log | `finish-preparation.log`, created when the installer rerun starts |
| Download workers / logs | `fetch-shard.py`; `download-shard-{2,3,4}.log` |
| Persistent unit | `~/.config/systemd/user/strata-flash-next-acquire.service` |
| Superseded transient unit | `strata-flash-next-prepare.service`, stopped |
| Boot memory setting | `/etc/modprobe.d/70-strata-halo-ttm.conf` |
| Rebuilt initramfs | `/boot/initrd.img-7.0.0-42-generic` |
| Intended isolated Strata API | `http://127.0.0.1:8083/v1`, not started |
| Existing private API | `http://100.96.8.54:8080/v1`, currently offline |
| Existing API model | `qwen3.8-27b-q4-fast` |
| Existing unit | `qwen38-dflash2.service`, enabled for boot |
| Existing deployment | `/home/less/qwen38-dflash2` |
| Existing environment file | `~/.config/qwen38-dflash2.env`, retained locally |

The boot file contains:

```conf
options ttm pages_limit=29360128 page_pool_size=29360128
```

At 4 KiB/page that is 120,259,084,288 bytes (112 GiB). It is a limit, not a
reservation or proof that the final model fits. The initramfs was rebuilt using
`sudo update-initramfs -u -k 7.0.0-42-generic`; its recorded SHA-256 is
`538b098c14b648119accd5c11564767d93d8aa9edbe191ef859a47755e9d6b1a`.
No GRUB command line, IOMMU setting, BIOS option, kernel package or GPU driver
package was changed. No reboot command has been issued.

The old runtime is `runtime-candidate/vulkan`, source commit
`a82001bd382ea54481603be113ced229a21db8d2`, with bundled Mesa 26.2.4. Its settings
remain context 245,760, Q8 target KV, batch/ubatch 2048/2048, one slot and DFlash2
width 4. The old October snapshot is retained with auto-restore disabled. Preserve
the existing uncommitted `models.ini`, `run-router.sh`, and `runtime-candidate/`;
do not reset or overwrite them to make this branch match the deployment.

## Recovery sequence after the user gives go

These steps are for the continuing agent. Documentation completion is not reboot
approval, and elapsed time is not approval.

1. Confirm the current acquisition phase and write its latest progress locally.
   Preserve all download pieces and metadata. Stop the acquisition supervisor
   gracefully for the reboot without disabling it. If interrupting the separate
   downloader workers, verify their current command lines and start times before
   signalling them; copied PIDs from this record must not be trusted blindly.
2. Reboot only the Linux Strix Halo host, after the explicit go. Expect this
   workspace session to disconnect. Do not send any restart/stop command to the
   Mac, change its OpenClaw routing, or generate channel messages.
3. After reconnecting, verify a changed boot ID, loaded GPU driver, device nodes,
   current user access, actual memory limits, and fresh kernel logs:

   ```bash
   cat /proc/sys/kernel/random/boot_id
   cat /sys/module/amdgpu/initstate
   ls -l /dev/kfd /dev/dri
   id
   cat /sys/module/ttm/parameters/pages_limit
   cat /sys/module/ttm/parameters/page_pool_size
   cat /sys/class/drm/card*/device/mem_info_gtt_total
   sudo dmesg --ctime | rg 'amdgpu|GTT|BUG:|Oops:'
   ```

   Expect `live`, accessible GPU nodes and 112 GiB GTT; confirm rather than
   assuming. The recorded pre-reboot boot ID is in the snapshot. Do not try another
   hot reload if limits or device initialization are wrong.
4. Verify the old 27B service on the GPU before calling the previous endpoint
   restored. Its unit has `Restart=on-failure`, five-second restart delay, and
   remains enabled. Check offloaded layers / Vulkan device selection and send a
   short direct API completion. `/health` alone is insufficient. No OpenClaw
   agent turn is needed. If GPU recovery fails, retain the logs and report the
   actual state instead of presenting CPU fallback as successful recovery.
5. Inspect `strata-flash-next-acquire.service` and `preparation-status.json`.
   The enabled unit and user linger are configured to resume preparation. If it
   fails, inspect its journal and `finish-preparation.log`; do not start a second
   downloader that writes the same shard at the same time. Confirm the two
   already-completed shards are reused and final hashes match the pinned manifest.
6. Once preparation is complete, inspect the generated config and pack. Confirm
   the target revision, MTP companion, image encoder, INT8 KV, 256K context,
   correct bundled HIP engine/tuning table, and shared-memory budget. The initial
   image-encoder warning must not silently become the final configuration.
7. Free the GPU of the dense server before loading Flash-Next. Run the isolated
   loopback listener, test actual generation across fresh starts, exact tools and
   continuation, streaming tool calls, vision, prefix reuse and disk state
   restoration. No persistent Strata serving unit has been created yet.
8. Run the documented cold 64K/128K probes twice, plus a >150K capacity check.
   Record the actual settings, memory, uncached work and client latency. Then
   provide a verified private endpoint for the user's real OpenClaw tests. Only
   promote persistent defaults after validation; keep the dense model for rollback.

If the new boot memory limits themselves cause trouble, the rollback is to move
the new `.conf` out of modprobe's `.conf` set, rebuild the initramfs for the kernel
being used, and perform another coordinated reboot. Original TTM values were
15,113,689 pages each. Do not patch kernel memory or force removal of the stuck
module. Kernel source/ISP behavior has not been fixed or independently diagnosed
beyond the observed stack trace.

## Evidence and next optimization work

No local Flash-Next throughput, quality, vision or state-restoration claim is
supported yet. The existing scripts' syntax checks and launch-plan validation
are setup checks. The smoke test's 2,048-token cap and performance probe's
128-token cap apply only to their requests, not the model's serving allowance.

After obtaining a packaged baseline, test the documented prefill switches
independently, especially fused K-quant experts, GEMM, attention and
hyperconnection work. Profile the combined winner before kernel changes.
Preserve meaningful tool behavior and reason about any numerical changes; fast
decode or warm-cache reuse alone does not meet the cold-prefill objective.

Public evidence contains package/configuration metadata, synthetic benchmark
code and the relevant driver failure. Full kernel logs, private deployment
configuration, credentials and user conversations remain local. No upstream
issue/PR or maintainer message was sent as part of this record.
