/** Documentation consistency checks only. No application/security assurance. */
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ADR_SECTIONS = ['Context', 'Decision', 'Alternatives', 'Consequences', 'Validation', 'Revisit'];

// POSIX resolution makes repository-relative Markdown links portable to Windows and CI.
export function validateLinks(files) {
  const errors = [];
  for (const [name, content] of files) {
    if (!name.endsWith('.md')) continue;
    const links = content.matchAll(/\[[^\]\n]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)/g);
    for (const match of links) {
      const target = match[1];
      if (/^(?:https?:|mailto:|#)/i.test(target)) continue;
      let destination;
      try {
        destination = decodeURIComponent(target.split('#')[0]);
      } catch {
        errors.push(`${name}: malformed link ${target}`);
        continue;
      }
      const resolved = path.posix.normalize(path.posix.join(path.posix.dirname(name), destination)).replace(/\/$/, '');
      if (path.posix.isAbsolute(destination) || resolved.startsWith('../') || !files.has(resolved)) {
        errors.push(`${name}: missing/outside local link ${target}`);
      }
    }
  }
  return errors;
}

export function validateBacklog(tasks) {
  const errors = [];
  const byId = new Map();
  for (const task of tasks) {
    if (!/^B\d{2}$/.test(task.id) || byId.has(task.id)) errors.push(`Invalid/duplicate task ${task.id}`);
    byId.set(task.id, task);
    if (!Number.isInteger(task.phase) || task.phase < 1 || task.phase > 12) errors.push(`${task.id}: invalid phase`);
    if (!task.title || !task.scope || !['S', 'M', 'L'].includes(task.size)) errors.push(`${task.id}: missing planning fields`);
    if (typeof task.acceptance !== 'string' || task.acceptance.trim().length < 30) errors.push(`${task.id}: missing meaningful acceptance`);
    if (!Array.isArray(task.depends_on)) errors.push(`${task.id}: dependencies must be an array`);
  }
  for (const task of tasks) {
    for (const dependency of task.depends_on ?? []) {
      if (!byId.has(dependency)) errors.push(`${task.id}: unknown dependency ${dependency}`);
      else if (byId.get(dependency).phase > task.phase) errors.push(`${task.id}: depends on later phase ${dependency}`);
    }
  }
  // Gray nodes are active ancestors; revisiting gray detects a directed cycle.
  const colors = new Map();
  function visit(id) {
    if (colors.get(id) === 1) { errors.push(`Dependency cycle at ${id}`); return; }
    if (colors.get(id) === 2 || !byId.has(id)) return;
    colors.set(id, 1);
    for (const dependency of byId.get(id).depends_on ?? []) visit(dependency);
    colors.set(id, 2);
  }
  for (const id of byId.keys()) visit(id);
  return errors;
}

export function validateAdr(content, name = 'ADR') {
  const errors = [];
  if (!/^Status: Proposed\s*$/m.test(content)) errors.push(`${name}: initial review status must remain Proposed`);
  for (const section of ADR_SECTIONS) {
    if (!new RegExp(`^## ${section}\\s*$`, 'm').test(content)) errors.push(`${name}: missing ${section}`);
  }
  return errors;
}

export function capacityRows(inputs) {
  return inputs.organizations.map((organizations) => {
    const chunks = organizations * inputs.documents_per_organization * inputs.chunks_per_document;
    const average = organizations * inputs.queries_per_organization_per_day / inputs.seconds_per_day;
    const peak = average * inputs.peak_multiplier;
    return [organizations, chunks,
      organizations * inputs.document_gb_per_organization,
      organizations * inputs.structured_gb_per_organization,
      Number((chunks * inputs.embedding_dimensions * inputs.bytes_per_dimension / inputs.decimal_bytes_per_gb).toFixed(2)),
      Number(average.toFixed(3)), Number(peak.toFixed(2)), Math.ceil(peak * inputs.occupancy_seconds)];
  });
}

export function validateCapacity(inputs, content) {
  const errors = [];
  if (inputs.status !== 'planning-assumptions-not-benchmarks') errors.push('Capacity assumptions must not be labeled benchmarks');
  const positiveFields = ['documents_per_organization', 'chunks_per_document', 'document_gb_per_organization',
    'structured_gb_per_organization', 'queries_per_organization_per_day', 'peak_multiplier', 'occupancy_seconds',
    'embedding_dimensions', 'bytes_per_dimension', 'tokens_per_chunk', 'seconds_per_day', 'decimal_bytes_per_gb'];
  for (const field of positiveFields) {
    if (!Number.isFinite(inputs[field]) || inputs[field] <= 0) errors.push(`Invalid positive capacity input ${field}`);
  }
  if (JSON.stringify(inputs.organizations) !== JSON.stringify([10, 100, 1000, 10000])) errors.push('Missing requested organization tiers');
  if (errors.length) return errors;
  const section = content.match(/<!-- capacity-table:start -->([\s\S]*?)<!-- capacity-table:end -->/)?.[1];
  if (!section) return ['Missing capacity table markers'];
  const actual = section.split('\n').filter((line) => /^\| \d/.test(line))
    .map((line) => line.split('|').slice(1, -1).map((cell) => Number(cell.trim())));
  const expected = capacityRows(inputs);
  if (JSON.stringify(actual) !== JSON.stringify(expected)) errors.push('Capacity table arithmetic differs from assumption inputs');
  return errors;
}

export function validateManifest(manifest, files, tasks) {
  const errors = [];
  if (manifest.phase !== 1 || manifest.status !== 'proposed') errors.push('Phase 1 review state must remain proposed');
  for (const name of [...(manifest.required_files ?? []), ...(manifest.adr_files ?? [])]) {
    if (!files.has(name)) errors.push(`Missing required artifact ${name}`);
  }
  const expectedIds = Array.from({ length: 14 }, (_, index) => `D${String(index + 1).padStart(2, '0')}`);
  const actualIds = (manifest.deliverables ?? []).map((item) => item.id).sort();
  if (JSON.stringify(actualIds) !== JSON.stringify(expectedIds)) errors.push('All fourteen deliverables must be uniquely mapped');
  for (const deliverable of manifest.deliverables ?? []) {
    if (!deliverable.name || !deliverable.files?.length) errors.push(`${deliverable.id}: missing evidence mapping`);
    for (const file of deliverable.files ?? []) if (!files.has(file)) errors.push(`${deliverable.id}: missing evidence ${file}`);
  }
  const declaredRequirements = [...(files.get('docs/prd.md') ?? '').matchAll(/^\| ((?:FR|NFR)-\d+) \|/gm)].map((match) => match[1]).sort();
  const mapped = (manifest.requirements ?? []).map((item) => item.id).sort();
  if (!declaredRequirements.length || JSON.stringify(mapped) !== JSON.stringify(declaredRequirements)) errors.push('PRD requirements must each map exactly once');
  const taskIds = new Set(tasks.map((task) => task.id));
  for (const requirement of manifest.requirements ?? []) {
    if (!requirement.tasks?.length) errors.push(`${requirement.id}: no implementation task`);
    for (const id of requirement.tasks ?? []) if (!taskIds.has(id)) errors.push(`${requirement.id}: unknown task ${id}`);
  }
  const adrFiles = manifest.adr_files ?? [];
  if (adrFiles.length !== 11 || new Set(adrFiles).size !== 11) errors.push('Expected eleven unique initial ADRs');
  for (const file of adrFiles) errors.push(...validateAdr(files.get(file) ?? '', file));
  return errors;
}

export function validateMarkdown(files) {
  const errors = [];
  let diagrams = 0;
  for (const [name, content] of files) {
    if (!name.endsWith('.md')) continue;
    if (!/^# \S/m.test(content)) errors.push(`${name}: missing document title`);
    let open = false;
    for (const line of content.split('\n')) {
      if (/^```/.test(line)) open = !open;
    }
    if (open) errors.push(`${name}: unclosed code fence`);
    for (const diagram of content.matchAll(/^```mermaid\s*\n([\s\S]*?)^```/gm)) {
      diagrams += 1;
      if (!/^(?:flowchart\s+(?:LR|TB|TD)|sequenceDiagram|stateDiagram-v2|erDiagram)\s*$/m.test(diagram[1].split('\n')[0])) {
        errors.push(`${name}: unrecognized Mermaid source declaration`);
      }
    }
  }
  return { errors, diagrams };
}

async function collectFiles(root) {
  const files = new Map();
  async function visit(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      if (['.git', 'node_modules', 'work', '.venv', '.next', '.secrets', '.uv-cache', '.mypy_cache', '.ruff_cache', '.pytest_cache'].includes(entry.name)) continue;
      const absolute = path.join(directory, entry.name);
      const relative = path.relative(root, absolute).split(path.sep).join('/');
      if (entry.isDirectory()) {
        files.set(relative, ''); // Directory links are valid local documentation targets.
        await visit(absolute);
      } else if (entry.isFile()) {
        // Index source/config paths too; only documentation inputs need their contents read.
        const content = /\.(?:md|json|mjs)$/.test(entry.name) ? await readFile(absolute, 'utf8') : '';
        files.set(relative, content);
      }
    }
  }
  await visit(root);
  return files;
}

export async function validateDocumentation(root = ROOT) {
  const files = await collectFiles(root);
  const manifest = JSON.parse(files.get('docs/testing/phase1-manifest.json'));
  const tasks = JSON.parse(files.get('docs/backlog.json'));
  const inputs = JSON.parse(files.get('docs/architecture/capacity-assumptions.json'));
  const markdown = validateMarkdown(files);
  const errors = [...validateLinks(files), ...validateBacklog(tasks), ...validateManifest(manifest, files, tasks),
    ...validateCapacity(inputs, files.get('docs/architecture/capacity-and-slos.md') ?? ''), ...markdown.errors];
  return { errors, files: files.size, markdownFiles: [...files.keys()].filter((name) => name.endsWith('.md')).length,
    deliverables: manifest.deliverables.length, requirements: manifest.requirements.length,
    adrs: manifest.adr_files.length, tasks: tasks.length, mermaidSources: markdown.diagrams };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const report = await validateDocumentation();
    if (report.errors.length) {
      for (const error of report.errors) console.error(`FAIL: ${error}`);
      process.exitCode = 1;
    } else {
      console.log('PASS: Phase 1 documentation consistency');
      console.log(JSON.stringify(report, null, 2));
      console.log('Not application tests, security assurance, benchmarks, or Mermaid visual rendering.');
    }
  } catch (error) {
    console.error(`FAIL: Cannot validate documentation: ${error.message}`);
    process.exitCode = 1;
  }
}
