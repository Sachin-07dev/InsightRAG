import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { bootstrapLocal } from './bootstrap-local.mjs';

const work = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../work');

async function fixture(run) {
  await mkdir(work, { recursive: true });
  const root = await mkdtemp(path.join(work, 'bootstrap-test-'));
  try {
    await run(root);
  } finally {
    const resolved = path.resolve(root);
    if (!resolved.startsWith(work + path.sep)) throw new Error('Refusing cleanup outside work directory');
    await rm(resolved, { recursive: true });
  }
}

test('bootstrap creates unpredictable separate credentials and preserves them on rerun', async () => {
  await fixture(async (root) => {
    assert.equal((await bootstrapLocal(root)).files, 10);
    const secret = (name) => readFile(path.join(root, '.secrets', name), 'utf8');
    const owner = (await secret('postgres_password')).trim();
    const runtime = (await secret('runtime_db_password')).trim();
    assert.match(owner, /^[a-f0-9]{64}$/);
    assert.match(runtime, /^[a-f0-9]{64}$/);
    assert.notEqual(owner, runtime);
    const signingKey = (await secret('signed_job_key')).trim();
    assert.match(signingKey, /^[a-f0-9]{64}$/);
    assert.notEqual(signingKey, runtime);
    const before = await secret('database_url');
    await bootstrapLocal(root);
    assert.equal(await secret('database_url'), before);
    assert.ok(before.includes('@postgres:5432/insightrag'));
    assert.ok((await secret('host_database_url')).includes('@127.0.0.1:5432/insightrag'));
  });
});

test('bootstrap refuses inconsistent URL credentials without overwriting them', async () => {
  await fixture(async (root) => {
    await bootstrapLocal(root);
    const filename = path.join(root, '.secrets', 'database_url');
    await writeFile(filename, 'deliberately-inconsistent-test-value\n');
    await assert.rejects(bootstrapLocal(root), /refusing to overwrite/);
    assert.equal(await readFile(filename, 'utf8'), 'deliberately-inconsistent-test-value\n');
  });
});

test('bootstrap rejects malformed existing password files', async () => {
  await fixture(async (root) => {
    await mkdir(path.join(root, '.secrets'));
    await writeFile(path.join(root, '.secrets', 'postgres_password'), 'invalid-fixture\n');
    await assert.rejects(bootstrapLocal(root), /Invalid local password file/);
  });
});
