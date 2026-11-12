#!/usr/bin/env python3
"""Copy an explicit allowlist of research artifacts; never publish native logs/profiles."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--root',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--private-profile',type=Path,required=True,help='Used only to reject accidental credential disclosure')
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
secret=json.loads(a.private_profile.read_text())['api_key'].encode()
manifest={}
def copy(source,target=None):
    src=a.root/source;dst=a.out/(target or source)
    raw=src.read_bytes();assert secret not in raw
    if source=='dispatch.json':
        digest=(hashlib.sha256(raw).hexdigest()+'\n').encode()
        (a.out/'dispatch.original.sha256').write_bytes(digest)
        manifest['dispatch.original.sha256']=hashlib.sha256(digest).hexdigest()
        raw=raw.rstrip()+b'\n'  # Only normalize blank lines at EOF.
    dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(raw)
    manifest[str(dst.relative_to(a.out))]=hashlib.sha256(raw).hexdigest()
for name in ['analysis.json','runtime-inventory.json','engine-build.json','hardware.json',
             'routes.jsonl','dispatch.json','calibration-build-v2/build.json','calibration-build-v2/isa-verification.json',
             'q8-build-v4/build.json','projection-build/build.json',
             'q8-first-v2-dispatch.json','q8-return-v2-dispatch.json']:
    copy(name)
for directory in ['calibration-exclusive','operators','q8-final']:
    data=json.loads((a.root/directory/'summary.json').read_text())
    assert data['completed'] and data['restoration']['health']['loaded']
    copy(directory+'/summary.json')
    for step in data['steps']:
        # The earlier head-packed qualification was not the deployed NativeHead
        # path. Keep its metadata in the summary, use only final raw Q8 results.
        if directory=='operators' and step['name'].startswith('q8-'):continue
        for file in ['stdout','stderr','telemetry.jsonl']:
            copy(directory+'/'+step['name']+'/'+file)
        for file in (a.root/directory/step['name']).glob('profile/*.csv'):
            copy(str(file.relative_to(a.root)))
summary=json.loads((a.root/'routing-run/summary.json').read_text())
assert summary['completed'] and summary['arms'][0]['reference_outputs_match']
curated={k:summary[k] for k in ['completed','protocol','engine_sha256','baseline_engine_sha256','candidate_switches','restoration']}
curated['reference_outputs_match']=True
raw=(json.dumps(curated,indent=2)+'\n').encode();assert secret not in raw
(a.out/'routing-run').mkdir(exist_ok=True);(a.out/'routing-run/summary.json').write_bytes(raw)
manifest['routing-run/summary.json']=hashlib.sha256(raw).hexdigest()
for file in ['results.json','native-accounting.json','command.json']:
    copy('routing-run/00-/profile/'+file,'routing-run/'+file)
(a.out/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'files':len(manifest),'bytes':sum((a.out/k).stat().st_size for k in manifest)}))
