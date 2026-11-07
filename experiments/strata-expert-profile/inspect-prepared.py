#!/usr/bin/env python3
"""Compare control device instructions and record prepared-kernel resources."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ap = argparse.ArgumentParser(description=__doc__)
for key in ('source', 'sdk', 'control_object', 'out'):
    ap.add_argument('--' + key.replace('_', '-'), type=Path, required=True)
ap.add_argument('--candidate-source', default='moe_f16_prepared', help='Candidate translation-unit basename without .cu')
a = ap.parse_args()
a.out.mkdir(parents=True, exist_ok=False)
llvm = a.sdk / 'lib/llvm/bin'
commands = []

def run(cmd):
    cmd = list(map(str, cmd))
    commands.append(cmd)
    return subprocess.check_output(cmd, text=True)

def inspect(label, obj):
    isa = run([llvm / 'llvm-objdump', '-d', obj])
    metadata = run([llvm / 'llvm-readelf', '--notes', obj])
    (a.out / (label + '.isa')).write_text(isa)
    (a.out / (label + '.metadata')).write_text(metadata)
    resources = {}
    for block in metadata.split('  - .args:')[1:]:
        name = re.search(r'^    \.name:\s+(\S+)', block, re.M)
        if name:
            resources[name[1]] = {key: int(re.search(r'^    \.' + key + r':\s+(\d+)', block, re.M)[1])
                for key in ('group_segment_fixed_size', 'private_segment_fixed_size',
                            'vgpr_count', 'vgpr_spill_count', 'sgpr_count', 'sgpr_spill_count')}
    chunks = re.split(r'^([0-9a-f]+ <[^>]+>:)\s*$', isa, flags=re.M)
    result = {}
    for i in range(1, len(chunks), 2):
        name = chunks[i].split('<', 1)[1].removesuffix('>:')
        instructions = [line.split('//')[0].strip() for line in chunks[i + 1].splitlines()
                        if re.search(r'// [0-9A-Fa-f]+:', line)]
        if name in resources:
            result[name] = {'instruction_count': len(instructions),
                           'sha256': hashlib.sha256('\n'.join(instructions).encode()).hexdigest(),
                           'resources': resources[name]}
    return result

control = inspect('original', a.control_object)
versions = {}
for label, filename in [('rebuilt', 'moe_f16_kq'), ('prepared', a.candidate_source)]:
    host = a.source / f'build-halo-lab/CMakeFiles/strata_mmq.dir/src/prefill/{filename}.cu.o'
    fatbin, device = a.out / (label + '.fatbin'), a.out / (label + '.co')
    run([llvm / 'llvm-objcopy', '--dump-section', f'.hip_fatbin={fatbin}', host])
    run([llvm / 'clang-offload-bundler', '--type=o', '--unbundle', f'--input={fatbin}',
         '--targets=hipv4-amdgcn-amd-amdhsa--gfx1151', f'--output={device}'])
    versions[label] = inspect(label, device)
report = {'original_kernels': {name: {'original': data, 'rebuilt': versions['rebuilt'].get(name),
    'identical': data == versions['rebuilt'].get(name)} for name, data in control.items()},
    'prepared_kernels': versions['prepared'],
    'control_code_object_sha256': hashlib.sha256(a.control_object.read_bytes()).hexdigest()}
(a.out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
(a.out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
print(json.dumps({'original_kernels': len(control), 'identical': sum(x['identical'] for x in report['original_kernels'].values()),
                  'prepared_kernels': len(versions['prepared'])}))
assert len(control) == 10 and all(x['identical'] for x in report['original_kernels'].values())
