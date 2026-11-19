/** Create ignored local-development credentials without overwriting an existing installation. */
import { randomBytes } from 'node:crypto';
import { chmod, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export async function bootstrapLocal(root = projectRoot) {
  const directory = path.join(root, '.secrets');
  await mkdir(directory, { recursive: true, mode: 0o700 });
  if (process.platform !== 'win32') await chmod(directory, 0o700);

  async function password(name) {
    const filename = path.join(directory, name);
    try {
      const existing = (await readFile(filename, 'utf8')).trim();
      if (!/^[a-f0-9]{64}$/.test(existing)) throw new Error(`Invalid local password file: ${name}`);
      if (process.platform !== 'win32') await chmod(filename, 0o644);
      return existing;
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      try {
        // Files are readable by container users. The parent directory is private on Unix.
        await writeFile(filename, randomBytes(32).toString('hex') + '\n', { flag: 'wx', mode: 0o644 });
      } catch (writeError) {
        if (writeError.code !== 'EEXIST') throw writeError;
      }
      return password(name);
    }
  }

  async function writeStable(name, content) {
    const filename = path.join(directory, name);
    try {
      await writeFile(filename, content + '\n', { flag: 'wx', mode: 0o644 });
      if (process.platform !== 'win32') await chmod(filename, 0o644);
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      if ((await readFile(filename, 'utf8')).trim() !== content) {
        throw new Error(`Existing ${name} disagrees with password files; refusing to overwrite credentials.`);
      }
      if (process.platform !== 'win32') await chmod(filename, 0o644);
    }
  }

  const ownerPassword = await password('postgres_password');
  const runtimePassword = await password('runtime_db_password');
  const redisPassword = await password('redis_password');
  await password('signed_job_key');
  const database = (host, user, secret) => `postgresql+asyncpg://${user}:${secret}@${host}:5432/insightrag`;
  const redis = (host) => `redis://default:${redisPassword}@${host}:6379/0`;
  await writeStable('database_url', database('postgres', 'insightrag_runtime', runtimePassword));
  await writeStable('migration_database_url', database('postgres', 'insightrag_migrator', ownerPassword));
  await writeStable('redis_url', redis('redis'));
  await writeStable('host_database_url', database('127.0.0.1', 'insightrag_runtime', runtimePassword));
  await writeStable('host_migration_database_url', database('127.0.0.1', 'insightrag_migrator', ownerPassword));
  await writeStable('host_redis_url', redis('127.0.0.1'));
  return { directory, files: 10 };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const result = await bootstrapLocal();
    console.log(`Local credentials ready (${result.files} files in .secrets); no credential values printed.`);
    console.log('Existing credentials preserved. Do not delete or rotate files while keeping an initialized database volume.');
  } catch (error) {
    console.error(`Local bootstrap failed: ${error.message}`);
    process.exitCode = 1;
  }
}
