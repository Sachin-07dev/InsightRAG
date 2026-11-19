import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { validateLinks, validateBacklog, validateAdr, validateCapacity, validateManifest,
  validateMarkdown, validateDocumentation } from './validate-phase1.mjs';

const task = (id, dependencies = [], phase = 2) => ({ id, phase, title: 'Fixture task', scope: 'MVP', size: 'S',
  depends_on: dependencies, acceptance: 'A reviewer can verify this independently specified acceptance criterion.' });

test('local links resolve relative to their document and missing targets fail', () => {
  const files = new Map([['README.md', '# Guide\n[Design](docs/design.md)'],
    ['docs/design.md', '# Design\n[Root](../README.md)\n[Source](https://example.com/source)']]);
  assert.deepEqual(validateLinks(files), []);
  files.set('docs/design.md', '# Design\n[Missing](absent.md)');
  assert.match(validateLinks(files).join('\n'), /missing\/outside local link/);
});

test('outside-root and malformed encoded links fail instead of being ignored', () => {
  assert.equal(validateLinks(new Map([['README.md', '[Outside](../private.md)\n[Bad](%ZZ.md)']])).length, 2);
});

test('documentation may link to indexed source files and folders inside the repository', () => {
  const files = new Map([['docs/guide.md', '# Guide\n[Source](../apps/main.py)\n[Folder](../apps/)'],
    ['apps/main.py', ''], ['apps', '']]);
  assert.deepEqual(validateLinks(files), []);
  files.delete('apps/main.py');
  assert.match(validateLinks(files).join('\n'), /missing\/outside local link/);
});

test('acyclic backlog passes; unknown dependency and cycle fail', () => {
  assert.deepEqual(validateBacklog([task('B01'), task('B02', ['B01'])]), []);
  assert.match(validateBacklog([task('B01', ['B99'])]).join('\n'), /unknown dependency/);
  assert.match(validateBacklog([task('B01', ['B02']), task('B02', ['B01'])]).join('\n'), /cycle/);
});

test('backlog catches duplicate IDs, missing acceptance and future-phase dependency', () => {
  assert.match(validateBacklog([task('B01'), task('B01')]).join('\n'), /duplicate/);
  assert.match(validateBacklog([{ ...task('B01'), acceptance: '' }]).join('\n'), /acceptance/);
  assert.match(validateBacklog([task('B01', ['B02'], 2), task('B02', [], 3)]).join('\n'), /later phase/);
});

test('ADRs cannot silently become accepted or lose consequences', () => {
  const text = 'Status: Proposed\n' + ['Context', 'Decision', 'Alternatives', 'Consequences', 'Validation', 'Revisit']
    .map((heading) => `## ${heading}\nMeaningful review content.\n`).join('\n');
  assert.deepEqual(validateAdr(text), []);
  assert.match(validateAdr(text.replace('Proposed', 'Accepted')).join('\n'), /Proposed/);
  assert.match(validateAdr(text.replace('## Consequences', '## Removed')).join('\n'), /Consequences/);
});

test('capacity table detects arithmetic drift, missing tier and false benchmark status', async () => {
  const inputs = JSON.parse(await readFile(new URL('../docs/architecture/capacity-assumptions.json', import.meta.url), 'utf8'));
  const content = await readFile(new URL('../docs/architecture/capacity-and-slos.md', import.meta.url), 'utf8');
  assert.deepEqual(validateCapacity(inputs, content), []);
  assert.match(validateCapacity(inputs, content.replace('| 1228.80 |', '| 9999.00 |')).join('\n'), /arithmetic/);
  assert.match(validateCapacity({ ...inputs, organizations: [10, 100] }, content).join('\n'), /tiers/);
  assert.match(validateCapacity({ ...inputs, status: 'benchmarks' }, content).join('\n'), /benchmarks/);
  assert.match(validateCapacity({ ...inputs, occupancy_seconds: 0 }, content).join('\n'), /positive/);
});

test('capacity boundary checks a separately calculated small-payload fixture', async () => {
  const inputs = JSON.parse(await readFile(new URL('../docs/architecture/capacity-assumptions.json', import.meta.url), 'utf8'));
  const small = { ...inputs, documents_per_organization: 1, chunks_per_document: 1,
    embedding_dimensions: 1, bytes_per_dimension: 1, decimal_bytes_per_gb: 1,
    queries_per_organization_per_day: 1, seconds_per_day: 100, peak_multiplier: 1, occupancy_seconds: 1 };
  const content = '<!-- capacity-table:start -->\n' + [
    '| 10 | 10 | 10 | 10 | 10 | 0.1 | 0.1 | 1 |',
    '| 100 | 100 | 100 | 100 | 100 | 1 | 1 | 1 |',
    '| 1000 | 1000 | 1000 | 1000 | 1000 | 10 | 10 | 10 |',
    '| 10000 | 10000 | 10000 | 10000 | 10000 | 100 | 100 | 100 |'
  ].join('\n') + '\n<!-- capacity-table:end -->';
  assert.deepEqual(validateCapacity(small, content), []);
});

test('coverage manifest fails missing deliverables and unmapped PRD requirements', () => {
  const files = new Map([['docs/prd.md', '| FR-01 | A required behavior | Observable acceptance |']]);
  const manifest = { phase: 1, status: 'proposed', required_files: [], deliverables: [], requirements: [], adr_files: [] };
  const errors = validateManifest(manifest, files, []).join('\n');
  assert.match(errors, /fourteen/);
  assert.match(errors, /PRD requirements/);
  assert.match(errors, /eleven/);
});

test('Markdown checks reject unfinished fences without claiming full grammar validation', () => {
  const bad = validateMarkdown(new Map([['docs/bad.md', '# Diagram\n```mermaid\nflowchart LR\n A --> B']]));
  assert.match(bad.errors.join('\n'), /unclosed/);
  const good = validateMarkdown(new Map([['docs/good.md', '# Diagram\n```mermaid\nflowchart LR\n A --> B\n```']]));
  assert.deepEqual(good.errors, []);
  assert.equal(good.diagrams, 1);
});

test('complete repository documentation passes its declared consistency gates', async () => {
  const report = await validateDocumentation();
  assert.deepEqual(report.errors, []);
  assert.equal(report.deliverables, 14);
  assert.equal(report.requirements, 21);
  assert.equal(report.adrs, 11);
  assert.equal(report.tasks, 26);
});
