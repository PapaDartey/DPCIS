import json, pathlib, collections, re, subprocess
root=pathlib.Path.cwd(); ev=root/'output/pdf/recrop-verification'; out=root/'frontend/dist-report-sourcemap-temp'
counts=collections.defaultdict(set); maps=[]
for f in sorted(out.rglob('*.map')):
 d=json.loads(f.read_text(encoding='utf-8')); sources=d.get('sources',[]); maps.append({'map':str(f.relative_to(out)), 'sources':sources})
 for s in sources:
  s=s.replace('\\','/')
  if 'node_modules/' not in s: continue
  tail=s.rsplit('node_modules/',1)[1]; parts=tail.split('/'); pkg='/'.join(parts[:2]) if tail.startswith('@') else parts[0]
  counts[pkg].add(str((f.parent/s).resolve()))
assert maps, 'No sourcemaps'
data={'method':'Unique resolved source paths per package; package after last node_modules/; deduplicated across maps.', 'map_count':len(maps),'packages':{p:len(v) for p,v in sorted(counts.items())},'maps':maps}
(ev/'sourcemap-packages-2026-11-16.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps({'map_count':len(maps),'packages':data['packages']},indent=2))
