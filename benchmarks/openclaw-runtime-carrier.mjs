// Read-only projection probe for the installed OpenClaw 2026.10.9 bundles.
// This imports pure message helpers; it creates no agent/session and calls no tool.
// Run: node --input-type=module - /path/to/openclaw < this-file.mjs
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';

const root = process.argv[2];
if (!root) throw new Error('Pass the installed OpenClaw package root');
const dist = path.join(root, 'dist');
const files = fs.readdirSync(dist);
const select = prefix => {
  const candidates = files.filter(x => x.startsWith(prefix) && x.endsWith('.mjs'));
  if (candidates.length !== 1) throw new Error(`Ambiguous bundle: ${prefix}`);
  return path.join(dist, candidates[0]);
};
const builderFile = select('runtime-context-prompt-');
const projectorFile = select('internal-runtime-context-');
const { a: buildCarrier } = await import(pathToFileURL(builderFile));
const { d: relocate } = await import(pathToFileURL(projectorFile));
if (typeof buildCarrier !== 'function' || typeof relocate !== 'function') {
  throw new Error('Bundle exports changed; inspect this version before adapting the probe');
}
const carrier = buildCarrier('Public synthetic runtime context.');
const history = [carrier, { role: 'user', content: 'Public task', timestamp: 0 }];
const label = m => m === carrier ? 'runtime_context' : m.role;
const runs = [];
for (let turn = 0; turn < 3; turn++) {
  history.push({ role: 'assistant', content: [{ type: 'toolCall', id: `lookup${turn}`,
    name: 'lookup', arguments: { turn } }], timestamp: 0 });
  history.push({ role: 'toolResult', toolCallId: `lookup${turn}`, toolName: 'lookup',
    content: [{ type: 'text', text: 'Public result' }], timestamp: 0 });
  runs.push({ turn, before: history.map(label), after: relocate(history).map(label) });
}
console.log(JSON.stringify({
  version: JSON.parse(fs.readFileSync(path.join(root, 'package.json'))).version,
  source: [builderFile, projectorFile].map(file => ({ name: path.basename(file),
    sha256: crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex') })),
  synthetic: true,
  scope: 'Pure message projection only; no agent, session, provider request or tool execution',
  runs,
}, null, 2));
