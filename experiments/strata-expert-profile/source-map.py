#!/usr/bin/env python3
"""Map ATT to source only after a line-info build preserves kernel instructions."""
import argparse
import collections
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

ap = argparse.ArgumentParser(description=__doc__)
for name in ('source', 'sdk', 'traces', 'out'):
    ap.add_argument('--' + name, type=Path, required=True)
a = ap.parse_args()
for name in ('source', 'sdk', 'traces', 'out'):
    setattr(a, name, getattr(a, name).resolve())
a.out.mkdir(parents=True, exist_ok=False)
llvm = a.sdk / 'lib/llvm/bin'
env = {'ROCM_PATH': str(a.sdk), 'HIP_PATH': str(a.sdk), 'HIP_PLATFORM': 'amd',
       'LD_LIBRARY_PATH': f'{a.sdk}/lib:{a.sdk}/lib/rocm_sysdeps/lib:{a.sdk}/lib/llvm/lib'}
commands = subprocess.check_output(['ninja', '-C', str(a.source / 'build-halo-lab'), '-t', 'commands'], text=True).splitlines()
cmd = shlex.split(next(line for line in commands if '-c ' + str(a.source / 'src/prefill/moe_f16_kq.cu') in line))
if cmd[0] == 'ccache':
    cmd = cmd[1:]
for flag, count in [('-MD', 1), ('-MT', 2), ('-MF', 2)]:
    i = cmd.index(flag)
    del cmd[i:i + count]
cmd[cmd.index('-o') + 1] = str(a.out / 'moe_f16_kq.debug.o')
cmd.insert(1, '-gline-tables-only')
record = {'argv': cmd, 'env': env, 'source_commit': subprocess.check_output(
    ['git', '-C', str(a.source), 'rev-parse', 'HEAD'], text=True).strip()}
with (a.out / 'stdout').open('w') as out, (a.out / 'stderr').open('w') as err:
    result = subprocess.run(cmd, cwd=a.source / 'build-halo-lab', env={**os.environ, **env}, stdout=out, stderr=err)
record['exit_code'] = result.returncode
(a.out / 'build.json').write_text(json.dumps(record, indent=2) + '\n')
assert result.returncode == 0
commands = [[llvm / 'llvm-objcopy', '--dump-section', f'.hip_fatbin={a.out}/device.fatbin', a.out / 'moe_f16_kq.debug.o'],
            [llvm / 'clang-offload-bundler', '--type=o', '--unbundle', f'--input={a.out}/device.fatbin',
             '--targets=hipv4-amdgcn-amd-amdhsa--gfx1151', f'--output={a.out}/debug.co']]
for cmd in commands:
    subprocess.run(list(map(str, cmd)), check=True)
control = a.traces / 'gate-i5/expert_gfx1151_code_object_id_4.out'
control_hash = hashlib.sha256(control.read_bytes()).hexdigest()
for d in a.traces.glob('*-i*'):
    assert hashlib.sha256((d / 'expert_gfx1151_code_object_id_4.out').read_bytes()).hexdigest() == control_hash
functions = {}
for label, path in [('control', control), ('debug', a.out / 'debug.co')]:
    isa = subprocess.check_output([str(llvm / 'llvm-objdump'), '-d', str(path)], text=True)
    (a.out / (label + '.isa')).write_text(isa)
    chunks = re.split(r'^([0-9a-f]+ <[^>]+>:)\s*$', isa, flags=re.M)
    for name, fragment in [('gate', 'gate_up_kernelILi12ELi128ELb0'), ('down', 'down_kernelILi128')]:
        matches = [i for i in range(1, len(chunks), 2) if fragment in chunks[i]]
        assert len(matches) == 1
        i = matches[0]
        instructions = []
        for line in chunks[i + 1].splitlines():
            match = re.search(r'// ([0-9A-Fa-f]+): (.+)$', line)
            if match:
                instructions.append({'address': int(match[1], 16), 'asm': line.split('//')[0].strip(), 'words': match[2].strip()})
        functions.setdefault(name, {})[label] = {'header': chunks[i], 'instructions': instructions,
            'sha256': hashlib.sha256('\n'.join(x['asm'] for x in instructions).encode()).hexdigest()}
for versions in functions.values():
    assert versions['control']['sha256'] == versions['debug']['sha256'], 'Line-info build changed instructions'
addresses = sorted({x['address'] for v in functions.values() for x in v['debug']['instructions']})
symbolize = [str(llvm / 'llvm-symbolizer'), '--obj=' + str(a.out / 'debug.co'), '--output-style=JSON', '--no-inlines']
result = subprocess.run(symbolize, input=''.join(hex(x) + '\n' for x in addresses), text=True, stdout=subprocess.PIPE, check=True)
(a.out / 'symbols.jsonl').write_text(result.stdout)
(a.out / 'functions.json').write_text(json.dumps(functions, indent=2) + '\n')
(a.out / 'commands.json').write_text(json.dumps({'extract': [[str(x) for x in c] for c in commands], 'symbolize': symbolize}, indent=2) + '\n')
symbols = {int(x['Address'], 16): x['Symbol'] for x in map(json.loads, result.stdout.splitlines())}
report = {'kernels': {k: {'instruction_sha256': v['control']['sha256'], 'instruction_count': len(v['control']['instructions']),
                          'line_info_instructions_unchanged': True} for k, v in functions.items()},
          'control_code_object_sha256': control_hash, 'traces': {},
          'limits': ['Compiler line attribution may assign waits to an adjacent source operation.',
                     'Header line attribution alone cannot distinguish every inlined call site.',
                     'Summed instruction latency is not wall-time share.']}
for d in sorted(a.traces.glob('*-i*')):
    v = functions['gate' if d.name.startswith('gate') else 'down']
    mapping = {c['address']: symbols[n['address']] for c, n in zip(v['control']['instructions'], v['debug']['instructions'])}
    groups = collections.Counter()
    mapped, unknown = [], 0
    for r in csv.DictReader(next(d.glob('stats_*.csv')).open()):
        latency = int(r['Latency'])
        if latency == 0:
            continue
        entry = mapping.get(int(r['Vaddr']), [])
        if not entry:
            unknown += latency
            continue
        s = entry[0]
        file, line = Path(s.get('FileName', '')).name, s.get('Line', 0)
        groups[f'{file}:{line}'] += latency
        mapped.append({**r, 'file': file, 'line': line, 'column': s.get('Column', 0)})
    (a.out / (d.name + '.mapped.json')).write_text(json.dumps(mapped, indent=2) + '\n')
    report['traces'][d.name] = {'lines': groups, 'unknown_latency': unknown, 'total_latency': sum(groups.values()) + unknown}
(a.out / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'kernels': report['kernels'], 'unknown_latency': {k: v['unknown_latency'] for k, v in report['traces'].items()}}))
