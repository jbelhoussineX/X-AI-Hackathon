"""Local SQLite persistence; refreshes commit atomically and never overwrite on failure."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def source_id(url):
    # Do not merge different paths, queries or document versions on a guess.
    return hashlib.sha256(url.encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS watches (
                    id TEXT PRIMARY KEY, topic TEXT NOT NULL, mode TEXT NOT NULL,
                    created_at TEXT NOT NULL, UNIQUE(topic, mode));
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, watch_id TEXT NOT NULL REFERENCES watches(id),
                    started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '', context TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS one_running
                    ON runs(watch_id) WHERE status='running';
                CREATE TABLE IF NOT EXISTS documents (
                    watch_id TEXT NOT NULL REFERENCES watches(id), id TEXT NOT NULL,
                    url TEXT NOT NULL, title TEXT NOT NULL, snapshot TEXT,
                    report TEXT NOT NULL, context TEXT NOT NULL,
                    PRIMARY KEY(watch_id, id));
                CREATE TABLE IF NOT EXISTS versions (
                    watch_id TEXT NOT NULL, document_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, snapshot TEXT NOT NULL,
                    PRIMARY KEY(watch_id, document_id, fingerprint));
                CREATE TABLE IF NOT EXISTS results (
                    run_id TEXT NOT NULL REFERENCES runs(id), document_id TEXT NOT NULL,
                    report TEXT NOT NULL, PRIMARY KEY(run_id, document_id));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_watch(self, topic, mode='demo'):
        topic = topic.strip()
        if not topic or len(topic) > 300 or mode not in ('demo', 'live'):
            raise ValueError('Sujet requis (300 caractères maximum).')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO watches VALUES (?,?,?,?)',
                       (uuid4().hex, topic, mode, now()))
            return db.execute('SELECT id FROM watches WHERE topic=? AND mode=?',
                              (topic, mode)).fetchone()['id']

    def watches(self, mode):
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                'SELECT * FROM watches WHERE mode=? ORDER BY created_at', (mode,))]

    def watch(self, watch_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM watches WHERE id=?', (watch_id,)).fetchone()
            if row is None:
                raise ValueError('Veille introuvable.')
            return dict(row)

    def documents(self, watch_id):
        with self.connect() as db:
            rows = [dict(r) for r in db.execute(
                'SELECT * FROM documents WHERE watch_id=? ORDER BY id', (watch_id,))]
        for row in rows:
            for key in ('snapshot', 'report', 'context'):
                row[key] = json.loads(row[key]) if row[key] else None
        return rows

    def runs(self, watch_id):
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                'SELECT * FROM runs WHERE watch_id=? ORDER BY started_at DESC', (watch_id,))]

    def begin(self, watch_id):
        run_id = uuid4().hex
        try:
            with self.connect() as db:
                db.execute('INSERT INTO runs(id,watch_id,started_at,status) VALUES(?,?,?,?)',
                           (run_id, watch_id, now(), 'running'))
        except sqlite3.IntegrityError as exc:
            raise ValueError('Actualisation déjà en cours ou veille absente.') from exc
        return run_id

    def fail(self, run_id, detail):
        with self.connect() as db:
            db.execute("UPDATE runs SET status='failed',finished_at=?,detail=? WHERE id=? AND status='running'",
                       (now(), detail, run_id))

    def finish(self, run_id, items, context):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            run = db.execute("SELECT * FROM runs WHERE id=? AND status='running'", (run_id,)).fetchone()
            if run is None:
                raise ValueError('Actualisation inactive.')
            watch_id = run['watch_id']
            for item in items:
                snapshot = item['snapshot']
                db.execute('''INSERT INTO documents VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(watch_id,id) DO UPDATE SET title=excluded.title,
                    snapshot=COALESCE(excluded.snapshot,documents.snapshot),
                    report=excluded.report,context=excluded.context''',
                    (watch_id, item['id'], item['url'], item['title'],
                     json.dumps(snapshot) if snapshot else None,
                     json.dumps(item['report']), json.dumps(item['context'])))
                if snapshot:
                    fingerprint = source_id(snapshot['scope'] + '\n' + snapshot['text'])
                    db.execute('INSERT OR IGNORE INTO versions VALUES(?,?,?,?)',
                               (watch_id, item['id'], fingerprint, json.dumps(snapshot)))
                db.execute('INSERT INTO results VALUES(?,?,?)',
                           (run_id, item['id'], json.dumps(item['report'])))
            status = 'partial' if (not items or context.get('incomplete') or any(
                i['report']['change_type'] == 'unconfirmed' for i in items)) else 'completed'
            db.execute('UPDATE runs SET status=?,finished_at=?,context=? WHERE id=?',
                       (status, now(), json.dumps(context), run_id))
