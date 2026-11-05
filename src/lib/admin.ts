import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { randomUUID, timingSafeEqual } from 'node:crypto';
import { data } from './demo';

export function authorized(request: Request) {
  const expected = process.env.SCRIPTURA_ADMIN_TOKEN;
  const auth = request.headers.get('authorization');
  if (!expected || !auth?.startsWith('Bearer ')) return false;
  const a = Buffer.from(expected); const b = Buffer.from(auth.slice(7));
  return a.length === b.length && timingSafeEqual(a, b);
}
function openDb() {
  const dbPath = resolve(process.env.SCRIPTURA_DEMO_DB || '.local/demo.sqlite');
  mkdirSync(dirname(dbPath), { recursive: true, mode: 0o700 });
  const db = new DatabaseSync(dbPath);
  db.exec(`PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS samples (id TEXT PRIMARY KEY, fixture_version_id TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS audit (id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, event TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
    CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;`);
  return db;
}
export function createSample(fixtureVersionId: unknown) {
  if (typeof fixtureVersionId !== 'string' || !data.claim_versions.some((c) => c.id === fixtureVersionId)) throw new Error('Choose an existing synthetic fixture version');
  const db = openDb(); const id = randomUUID(); const now = new Date().toISOString();
  try {
    db.exec('BEGIN IMMEDIATE');
    db.prepare('INSERT INTO samples VALUES (?, ?, ?)').run(id, fixtureVersionId, now);
    db.prepare('INSERT INTO audit VALUES (?, ?, ?, ?)').run(randomUUID(), id, 'extraction', now);
    db.exec('COMMIT');
    return { id, fixture_version_id: fixtureVersionId, created_at: now, review_status: 'extracted' };
  } catch (e) { db.exec('ROLLBACK'); throw e; } finally { db.close(); }
}
export function listSamples() { const db = openDb(); try { return db.prepare('SELECT * FROM samples ORDER BY created_at, id').all(); } finally { db.close(); } }
export function listAudit(id?: string | null) { const db = openDb(); try { return id ? db.prepare('SELECT * FROM audit WHERE entity_id = ? ORDER BY created_at, id').all(id) : db.prepare('SELECT * FROM audit ORDER BY created_at, id').all(); } finally { db.close(); } }
export function addReview(id: unknown, event: unknown) {
  if (typeof id !== 'string' || (event !== 'review' && event !== 'approval')) throw new Error('Expected sample_id and review or approval event');
  const db = openDb();
  try {
    if (!db.prepare('SELECT id FROM samples WHERE id = ?').get(id)) throw new Error('Sample not found');
    const now = new Date().toISOString();
    db.prepare('INSERT INTO audit VALUES (?, ?, ?, ?)').run(randomUUID(), id, event, now);
    return { entity_id: id, event, created_at: now, note: 'Demo event only; does not verify or publish a claim' };
  } finally { db.close(); }
}
