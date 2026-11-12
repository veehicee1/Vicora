"""
CBT Exam System - Python / Flask / SQLite  (100% offline, LAN based)
Admin console : http://SERVER-IP:8000/admin   (server machine only by default)
Students      : http://SERVER-IP:8000/
"""
import os, sys, io, csv, re, time, random, secrets, sqlite3, socket, threading, glob, json, uuid, hashlib, hmac, base64, urllib.request, urllib.error
from datetime import datetime
from functools import wraps
from flask import Flask, g, request, jsonify, session, send_file, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from tenant_migration import migrate_legacy_school
from school_scoped_migration import migrate_school_scoped_unique_keys
from multi_tenant import migrate_multi_tenant_schema, install_multi_tenant_routes, school_context, activate_tenant_views
import docx

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.environ.get('CBT_WEB') or os.path.join(getattr(sys, '_MEIPASS', HERE), 'web')
if os.environ.get('CBT_DATA'):
    DATA = os.environ['CBT_DATA']
elif getattr(sys, 'frozen', False):
    DATA = os.path.join(os.environ.get('PROGRAMDATA', os.path.expanduser('~')), 'CBTSystem')
else:
    DATA = os.path.join(HERE, 'data')
BK = os.path.join(DATA, 'backups')
os.makedirs(BK, exist_ok=True)
DB_PATH = os.path.join(DATA, 'cbt.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, role TEXT NOT NULL DEFAULT 'super_admin', active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS staff_exam_assignments(staff_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE, exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE, assigned_by TEXT, assigned_ts INTEGER, PRIMARY KEY(staff_id, exam_id));
CREATE TABLE IF NOT EXISTS classes(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, sync_uuid TEXT);
CREATE TABLE IF NOT EXISTS subjects(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, sync_uuid TEXT);
CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY, reg_no TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  class_id INTEGER NOT NULL REFERENCES classes(id), access_code TEXT NOT NULL, sync_uuid TEXT);
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, subject_id INTEGER NOT NULL REFERENCES subjects(id),
  text TEXT NOT NULL, a TEXT, b TEXT, c TEXT, d TEXT, answer TEXT NOT NULL, marks REAL DEFAULT 1,
  topic TEXT DEFAULT '', difficulty TEXT DEFAULT '', question_type TEXT DEFAULT 'objective',
  answer_text TEXT DEFAULT '', accepted_answers TEXT DEFAULT '[]', keywords TEXT DEFAULT '[]',
  answer_space TEXT DEFAULT 'medium', marking_mode TEXT DEFAULT 'exact', sync_uuid TEXT,
  UNIQUE(subject_id, text));
CREATE TABLE IF NOT EXISTS exams(id INTEGER PRIMARY KEY, title TEXT NOT NULL, subject_id INTEGER NOT NULL REFERENCES subjects(id),
  duration_min INTEGER NOT NULL, num_questions INTEGER NOT NULL, shuffle INTEGER DEFAULT 1, show_score INTEGER DEFAULT 0,
  pass_mark REAL DEFAULT 50, instructions TEXT DEFAULT '', status TEXT DEFAULT 'draft', created_ts INTEGER,
  objective_count INTEGER DEFAULT 0, theory_count INTEGER DEFAULT 0, camera_policy TEXT DEFAULT 'off', sync_uuid TEXT, sync_revision_hash TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS exam_classes(exam_id INTEGER REFERENCES exams(id) ON DELETE CASCADE,
  class_id INTEGER REFERENCES classes(id) ON DELETE CASCADE, PRIMARY KEY(exam_id, class_id));
CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE, token TEXT, device TEXT, start_ts INTEGER,
  last_seen INTEGER DEFAULT 0, extra_sec INTEGER DEFAULT 0, status TEXT DEFAULT 'in_progress', submitted_ts INTEGER,
  score REAL DEFAULT 0, total REAL DEFAULT 0, tab_switches INTEGER DEFAULT 0,
  paused_at INTEGER DEFAULT 0, paused_total_sec INTEGER DEFAULT 0, attempt_uuid TEXT, UNIQUE(exam_id, student_id));
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  exam_id INTEGER REFERENCES exams(id) ON DELETE CASCADE, title TEXT NOT NULL, body TEXT NOT NULL,
  emergency INTEGER DEFAULT 0, created_ts INTEGER NOT NULL, read_ts INTEGER DEFAULT 0, sender TEXT DEFAULT 'Admin');
CREATE TABLE IF NOT EXISTS session_questions(session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
  pos INTEGER, question_id INTEGER, opt_order TEXT, PRIMARY KEY(session_id, pos));
CREATE TABLE IF NOT EXISTS answers(session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE, question_id INTEGER,
  choice TEXT DEFAULT '', response_text TEXT DEFAULT '', flagged INTEGER DEFAULT 0, ts INTEGER,
  PRIMARY KEY(session_id, question_id));
CREATE TABLE IF NOT EXISTS theory_marks(session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
  question_id INTEGER, mark REAL DEFAULT 0, original_mark REAL DEFAULT NULL, feedback TEXT DEFAULT '',
  marked_by TEXT DEFAULT '', marked_ts INTEGER DEFAULT 0, PRIMARY KEY(session_id, question_id));
CREATE TABLE IF NOT EXISTS proctor_events(
  id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  request_id TEXT NOT NULL, event_type TEXT NOT NULL, server_ts INTEGER NOT NULL,
  client_ts INTEGER DEFAULT 0, details TEXT DEFAULT '{}',
  review_state TEXT DEFAULT 'Unreviewed', reviewed_by TEXT DEFAULT '',
  reviewed_ts INTEGER DEFAULT 0, review_note TEXT DEFAULT '',
  UNIQUE(session_id, request_id));
CREATE TABLE IF NOT EXISTS android_host_devices(
  device_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, label TEXT DEFAULT '',
  created_ts INTEGER NOT NULL, last_seen INTEGER DEFAULT 0, revoked_ts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS android_sync_receipts(
  id INTEGER PRIMARY KEY, attempt_uuid TEXT UNIQUE NOT NULL, device_id TEXT NOT NULL,
  session_id INTEGER NOT NULL REFERENCES sessions(id), payload_hash TEXT NOT NULL, synced_ts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS android_sync_conflicts(
  id INTEGER PRIMARY KEY, attempt_uuid TEXT UNIQUE NOT NULL, device_id TEXT NOT NULL,
  exam_sync_uuid TEXT DEFAULT '', student_sync_uuid TEXT DEFAULT '', reason TEXT NOT NULL,
  payload TEXT NOT NULL, created_ts INTEGER NOT NULL, review_state TEXT DEFAULT 'Unreviewed',
  reviewed_by TEXT DEFAULT '', reviewed_ts INTEGER DEFAULT 0, review_note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS android_sync_outbox(
  id INTEGER PRIMARY KEY, attempt_uuid TEXT UNIQUE NOT NULL, payload TEXT NOT NULL,
  status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, next_attempt_ts INTEGER DEFAULT 0,
  last_error TEXT DEFAULT '', created_ts INTEGER NOT NULL, synced_ts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts INTEGER, actor TEXT, action TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""


def raw():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA synchronous=NORMAL')  # safe with WAL, much faster commits
    return c


def init_db():
    c = raw()
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript(SCHEMA)
    # Additive staff RBAC migration: existing administrators retain their credentials
    # and become Super Admins; no examination or student records are rewritten.
    admin_cols = {r['name'] for r in c.execute('PRAGMA table_info(admins)').fetchall()}
    if 'role' not in admin_cols:
        c.execute("ALTER TABLE admins ADD COLUMN role TEXT NOT NULL DEFAULT 'super_admin'")
    if 'active' not in admin_cols:
        c.execute('ALTER TABLE admins ADD COLUMN active INTEGER NOT NULL DEFAULT 1')
    c.execute("UPDATE admins SET role='super_admin' WHERE role IS NULL OR role=''")
    c.execute('UPDATE admins SET active=1 WHERE active IS NULL')
    # Stable cross-device identities are additive; existing integer IDs remain unchanged.
    for table in ('classes', 'subjects', 'students', 'questions', 'exams'):
        cols = {r['name'] for r in c.execute(f'PRAGMA table_info({table})').fetchall()}
        if 'sync_uuid' not in cols:
            c.execute(f'ALTER TABLE {table} ADD COLUMN sync_uuid TEXT')
        for row in c.execute(f"SELECT id FROM {table} WHERE sync_uuid IS NULL OR sync_uuid='' ").fetchall():
            c.execute(f'UPDATE {table} SET sync_uuid=? WHERE id=?', (str(uuid.uuid4()), row['id']))
        c.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_sync_uuid ON {table}(sync_uuid)')
        c.execute(f'''CREATE TRIGGER IF NOT EXISTS trg_{table}_sync_uuid AFTER INSERT ON {table}
                      WHEN NEW.sync_uuid IS NULL OR NEW.sync_uuid=''
                      BEGIN UPDATE {table} SET sync_uuid=lower(hex(randomblob(4)))||'-'||
                      lower(hex(randomblob(2)))||'-4'||substr(lower(hex(randomblob(2))),2)||'-'||
                      substr('89ab',abs(random())%4+1,1)||substr(lower(hex(randomblob(2))),2)||'-'||
                      lower(hex(randomblob(6))) WHERE id=NEW.id; END''')
    session_cols_for_sync = {r['name'] for r in c.execute('PRAGMA table_info(sessions)').fetchall()}
    if 'attempt_uuid' not in session_cols_for_sync:
        c.execute('ALTER TABLE sessions ADD COLUMN attempt_uuid TEXT')
    for row in c.execute("SELECT id FROM sessions WHERE attempt_uuid IS NULL OR attempt_uuid='' ").fetchall():
        c.execute('UPDATE sessions SET attempt_uuid=? WHERE id=?', (str(uuid.uuid4()), row['id']))
    c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_attempt_uuid ON sessions(attempt_uuid)')
    # Additive migrations preserve all existing question and answer records.
    exam_cols = {r['name'] for r in c.execute('PRAGMA table_info(exams)').fetchall()}
    for col, definition in [('objective_count', 'INTEGER DEFAULT 0'), ('theory_count', 'INTEGER DEFAULT 0'), ('camera_policy', "TEXT DEFAULT 'off'"),
        ('android_host_sync_enabled', 'INTEGER DEFAULT 0'), ('sync_revision_hash', "TEXT DEFAULT ''")]:
        if col not in exam_cols:
            c.execute(f'ALTER TABLE exams ADD COLUMN {col} {definition}')
    question_cols = {r['name'] for r in c.execute('PRAGMA table_info(questions)').fetchall()}
    for col, definition in [
        ('question_type', "TEXT DEFAULT 'objective'"), ('answer_text', "TEXT DEFAULT ''"),
        ('accepted_answers', "TEXT DEFAULT '[]'"), ('keywords', "TEXT DEFAULT '[]'"),
        ('answer_space', "TEXT DEFAULT 'medium'"), ('marking_mode', "TEXT DEFAULT 'exact'")
    ]:
        if col not in question_cols:
            c.execute(f'ALTER TABLE questions ADD COLUMN {col} {definition}')
    theory_mark_cols = {r['name'] for r in c.execute('PRAGMA table_info(theory_marks)').fetchall()}
    if 'original_mark' not in theory_mark_cols:
        c.execute("ALTER TABLE theory_marks ADD COLUMN original_mark REAL DEFAULT NULL")
    answer_cols = {r['name'] for r in c.execute('PRAGMA table_info(answers)').fetchall()}
    if 'response_text' not in answer_cols:
        c.execute("ALTER TABLE answers ADD COLUMN response_text TEXT DEFAULT ''")
    if 'response_drawing' not in answer_cols:
        c.execute("ALTER TABLE answers ADD COLUMN response_drawing TEXT DEFAULT ''")
    # Additive migration: preserve existing student sessions and answer records.
    session_cols = {r['name'] for r in c.execute('PRAGMA table_info(sessions)').fetchall()}
    for col, definition in [('paused_at', 'INTEGER DEFAULT 0'), ('paused_total_sec', 'INTEGER DEFAULT 0')]:
        if col not in session_cols:
            c.execute(f'ALTER TABLE sessions ADD COLUMN {col} {definition}')
    if not c.execute('select 1 from admins').fetchone():
        c.execute('insert into admins(username,password_hash) values(?,?)', ('admin', generate_password_hash('admin123')))
        c.execute("insert or replace into settings values('default_pw','1')")
    defaults = {'secret': secrets.token_hex(32), 'school_name': os.environ.get('CBT_INITIAL_SCHOOL_NAME', 'CBT Examination Centre').strip()[:120] or 'CBT Examination Centre', 'allow_remote_admin': '0'}
    for k, v in defaults.items():
        c.execute('insert or ignore into settings values(?,?)', (k, v))
    migrate_legacy_school(c)
    c.commit()
    migrate_school_scoped_unique_keys(c)
    migrate_multi_tenant_schema(c)
    c.commit()
    c.close()


init_db()
app = Flask(__name__, static_folder=None)
_c = raw()
app.secret_key = _c.execute("select value from settings where key='secret'").fetchone()[0]
_c.close()
TRUST_PROXY = os.environ.get('CBT_TRUST_PROXY', '0').strip().lower() in ('1', 'true', 'yes')
SERVER_HOST = os.environ.get('CBT_HOST', '127.0.0.1' if TRUST_PROXY else '0.0.0.0').strip()
SERVER_PORT = int(os.environ.get('CBT_PORT', '8000'))
COOKIE_SECURE = os.environ.get('CBT_COOKIE_SECURE', '1' if TRUST_PROXY else '0').strip().lower() in ('1', 'true', 'yes')

REMOTE_STUDENT_ONLY = os.environ.get('CBT_REMOTE_STUDENT_ONLY', '0').strip().lower() in ('1', 'true', 'yes')
PUBLIC_HOSTING = os.environ.get('CBT_PUBLIC_HOSTING', '0').strip().lower() in ('1', 'true', 'yes')
PUBLIC_HOSTING_ADMIN = os.environ.get('CBT_PUBLIC_HOSTING_ADMIN', '0').strip().lower() in ('1', 'true', 'yes')
# Student-only route filtering also supports direct LAN listeners. Public cloud
# hosting is a distinct mode: the managed platform HTTPS proxy is trusted, while
# the Flask server itself binds to the platform interface and uses persistent storage.

# A local trusted proxy keeps Flask loopback-only. A managed public host has its
# own ingress proxy; trust its forwarded client/scheme/host headers for HTTPS
# cookies, rate limiting and secure remote-admin checks.
if TRUST_PROXY:
    if SERVER_HOST not in ('127.0.0.1', 'localhost', '::1'):
        raise RuntimeError('CBT_TRUST_PROXY=1 requires CBT_HOST to be loopback-only (127.0.0.1).')
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
elif PUBLIC_HOSTING:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# A local HTTPS tunnel/reverse proxy may forward to this LAN host over loopback.
# Trust only the scheme header from explicitly listed proxy source IPs; never
# trust forwarded client IP/host headers or allow remote Admin through this path.
class TrustedLocalProxyScheme:
    def __init__(self, application, trusted_ips):
        self.application = application
        self.trusted_ips = frozenset(ip.strip() for ip in trusted_ips if ip.strip())

    def __call__(self, environ, start_response):
        remote = environ.get('REMOTE_ADDR', '')
        forwarded_proto = environ.get('HTTP_X_FORWARDED_PROTO', '')
        proto = forwarded_proto.split(',')[0].strip().lower()
        if remote in self.trusted_ips and proto == 'https':
            environ['wsgi.url_scheme'] = 'https'
        return self.application(environ, start_response)


TRUSTED_SCHEME_PROXY_IPS = os.environ.get('CBT_TRUSTED_PROXY_IPS', '').split(',')
if TRUSTED_SCHEME_PROXY_IPS:
    app.wsgi_app = TrustedLocalProxyScheme(app.wsgi_app, TRUSTED_SCHEME_PROXY_IPS)

app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=COOKIE_SECURE,
    PERMANENT_SESSION_LIFETIME=12 * 3600,
    MAX_CONTENT_LENGTH=40 * 1024 * 1024
)



@app.before_request
def restrict_public_remote_surface():
    """When published through a trusted HTTPS proxy, expose only student routes."""
    remote_student_only = REMOTE_STUDENT_ONLY or os.environ.get("CBT_REMOTE_STUDENT_ONLY", "0").strip().lower() in ("1", "true", "yes")
    if not remote_student_only:
        return None
    if request.remote_addr in ('127.0.0.1', '::1', 'localhost'):
        return None
    path = request.path
    allowed_exact = {
        '/', '/home', '/home/', '/home/manifest.webmanifest', '/home/icon.svg',
        '/home/sw.js', '/gtmc-logo.jpg', '/vicora-logo.svg', '/vicora-icon.svg', '/api/public/school-logo', '/api/public/info'
    }
    if path in allowed_exact or path.startswith('/api/student/'):
        return None
    return err('Not found', 404)


# ---------------------------------------------------------------- helpers
def db():
    if 'db' not in g:
        g.db = raw()
    return g.db


@app.teardown_appcontext
def _close(_):
    d = g.pop('db', None)
    if d:
        d.close()


def qa(sql, a=()):
    return [dict(r) for r in db().execute(sql, a).fetchall()]


def q1(sql, a=()):
    r = db().execute(sql, a).fetchone()
    return dict(r) if r else None


def ex(sql, a=()):
    cur = db().execute(sql, a)
    db().commit()
    return cur


def getset(k, d=''):
    r = db().execute('select value from settings where key=?', (k,)).fetchone()
    return r[0] if r else d


def setset(k, v):
    ex('insert or replace into settings values(?,?)', (k, str(v)))


def audit(action):
    ex('insert into audit(ts,actor,action) values(?,?,?)', (int(time.time()), session.get('admin', 'system'), action))


def err(msg, code=400):
    return jsonify(error=msg), code


def fmt_ts(t):
    return datetime.fromtimestamp(t).strftime('%Y-%m-%d %H:%M') if t else ''


def grade(pct):
    return 'A' if pct >= 70 else 'B' if pct >= 60 else 'C' if pct >= 50 else 'D' if pct >= 45 else 'E' if pct >= 40 else 'F'


def question_fingerprint(text):
    """Normalize question wording while preserving mathematical operators and numbers."""
    value = str(text or "").replace("’", "'").replace("'", "")
    value = re.sub(r"<[^>]*>", " ", value).casefold()
    value = re.sub(r"\s*([+\-*/=<>%^])\s*", r"\1", value)
    value = re.sub(r"[^\w+\-*/=<>%^]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def gen_code():
    return ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))


FAILS = {}


def throttled(key, limit=10):
    now = time.time()
    FAILS[key] = [t for t in FAILS.get(key, []) if now - t < 300]
    return len(FAILS[key]) >= limit


def add_fail(key):
    FAILS.setdefault(key, []).append(time.time())


@app.before_request
def guard():
    p = request.path
    if p.startswith('/api/admin') or p == '/admin':
        local = request.remote_addr in ('127.0.0.1', '::1', 'localhost')
        hosted_secure_admin = PUBLIC_HOSTING and PUBLIC_HOSTING_ADMIN and COOKIE_SECURE and request.is_secure
        local_proxy_admin = TRUST_PROXY and COOKIE_SECURE and getset('allow_remote_admin', '0') == '1'
        if not local and not hosted_secure_admin and not local_proxy_admin:
            return err('Remote Admin access requires an explicitly enabled trusted HTTPS hosting or reverse-proxy configuration.', 403)


@app.get('/api/health')
def health():
    """Minimal readiness endpoint; deliberately exposes no school or student data."""
    try:
        db().execute('SELECT 1').fetchone()
        return jsonify(ok=True, service='gtmc-cbt', database='ready'), 200
    except Exception:
        app.logger.exception('Health check failed')
        return jsonify(ok=False, service='gtmc-cbt', database='unavailable'), 503


@app.after_request
def nocache(r):
    if request.path.startswith('/api/'):
        r.headers['Cache-Control'] = 'no-store'
    return r


ROLE_NAMES = {
    'super_admin': 'Super Admin',
    'exam_administrator': 'Exam Administrator',
    'invigilator': 'Invigilator',
    'examiner': 'Examiner / Marker',
    'auditor': 'Auditor',
}

def staff_permission(role, path, method):
    """Server-side allow-list. Unknown admin routes remain Super Admin only."""
    if role == 'super_admin':
        return True
    if path == '/api/admin/password':
        return True
    if role == 'exam_administrator':
        blocked = (
            path.startswith('/api/admin/staff') or path.startswith('/api/admin/settings')
            or path.startswith('/api/admin/school-logo') or path.startswith('/api/admin/server-info')
            or path.startswith('/api/admin/android-host') or path.startswith('/api/admin/backups')
            or path == '/api/admin/audit'
        )
        return path.startswith('/api/admin/') and not blocked
    if role == 'invigilator':
        allowed = (
            method == 'GET' and (
                path == '/api/admin/exams' or path == '/api/admin/classes'
                or path == '/api/admin/students/lookup' or path == '/api/admin/dashboard'
                or path.startswith('/api/admin/monitor/')
                or path.startswith('/api/admin/proctor/')
                or path.startswith('/api/admin/export/monitor/')
                or path == '/api/admin/messages'
            )
            or path.startswith('/api/admin/sessions/')
            or path.startswith('/api/admin/messages') and method == 'POST'
            or path.startswith('/api/admin/exams/') and path.endswith('/extend') and method == 'POST'
        )
        return allowed
    if role == 'examiner':
        return (
            method == 'GET' and path == '/api/admin/exams'
            or path == '/api/admin/dashboard'
            or path.startswith('/api/admin/theory/')
            or path.startswith('/api/admin/results/')
            or path.startswith('/api/admin/export/results/')
        )
    if role == 'auditor':
        return (
            method == 'GET' and (
                path == '/api/admin/exams' or path == '/api/admin/dashboard' or path == '/api/admin/audit'
                or path.startswith('/api/admin/results/')
                or path.startswith('/api/admin/export/results/')
                or path.startswith('/api/admin/export/monitor/')
            )
        )
    return False


def examiner_has_exam(username, exam_id):
    staff = q1('SELECT id FROM admins WHERE username=? AND active=1', (username,))
    if not staff:
        return False
    return bool(q1('SELECT 1 ok FROM staff_exam_assignments WHERE staff_id=? AND exam_id=?', (staff['id'], exam_id)))


def admin(f):
    @wraps(f)
    def w(*a, **k):
        username = session.get('admin')
        if not username:
            return err('Not logged in', 401)
        legacy_school_id = getset('vicora_legacy_school_id', '')
        # Existing signed-in browsers predate School Code sessions. Their old
        # cookie belongs to the original installation and is safely mapped to
        # the immutable legacy school during this compatibility transition.
        if not session.get('school_id') and legacy_school_id:
            session['school_id'] = legacy_school_id
        activate_tenant_views(db(), session['school_id'])
        staff = q1('SELECT username, role, active, school_id FROM admins WHERE username=? AND school_id=?', (username, session.get('school_id')))
        if not staff or not staff['active']:
            session.clear()
            return err('Staff account is inactive or unavailable. Sign in again.', 401)
        if request.path.startswith('/api/admin/backups') and session.get('school_id') != getset('vicora_legacy_school_id', ''):
            return err('School-specific backup and restore is being completed. Cross-school database backups are blocked.', 503)
        role = staff['role'] if staff['role'] in ROLE_NAMES else 'super_admin'
        session['admin_role'] = role
        if not staff_permission(role, request.path, request.method):
            return err('Your staff role does not have permission for this action.', 403)
        if role == 'examiner':
            assigned_route = re.search(r'/api/admin/(?:theory|results|export/results)/(\d+)$', request.path)
            if assigned_route and not examiner_has_exam(username, int(assigned_route.group(1))):
                return err('This examination has not been assigned to your marker account.', 403)
        return f(*a, **k)
    return w


# ---------------------------------------------------------------- file reading (xlsx / csv / docx)
ALIAS = {}
for canon, names in {
    'subject': 'subject subjectname', 'question': 'question questiontext questions q text',
    'a': 'a optiona option1 opta', 'b': 'b optionb option2 optb', 'c': 'c optionc option3 optc', 'd': 'd optiond option4 optd',
    'answer': 'answer correctanswer correct ans key', 'marks': 'marks mark point points',
    'topic': 'topic', 'difficulty': 'difficulty level',
    'regno': 'regno regnumber registrationnumber registrationno studentid examno examnumber admissionno admissionnumber',
    'name': 'name fullname studentname classname', 'class': 'class classroom grade',
    'code': 'accesscode code password pin'}.items():
    for n in names.split():
        ALIAS[n] = canon


def norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s or '').lower())


def sv(c):
    if c is None:
        return ''
    if isinstance(c, float) and c.is_integer():
        c = int(c)
    return str(c).strip()


def read_table(fs):
    fn = (fs.filename or '').lower()
    raw_rows = []
    if fn.endswith(('.xlsx', '.xlsm')):
        wb = openpyxl.load_workbook(fs.stream, read_only=True, data_only=True)
        raw_rows = [[sv(c) for c in r] for r in wb.worksheets[0].iter_rows(values_only=True)]
    elif fn.endswith('.csv'):
        txt = fs.stream.read().decode('utf-8-sig', errors='replace')
        raw_rows = [[sv(c) for c in r] for r in csv.reader(io.StringIO(txt))]
    elif fn.endswith('.docx'):
        d = docx.Document(fs.stream)
        for t in d.tables:
            for r in t.rows:
                raw_rows.append([c.text.strip() for c in r.cells])
    else:
        raise ValueError('Unsupported file type. Please upload .xlsx, .csv or .docx')
    raw_rows = [r for r in raw_rows if any(r)]
    if not raw_rows:
        raise ValueError('The file is empty (for Word files the data must be inside a table).')
    head = [ALIAS.get(norm(c)) for c in raw_rows[0]]
    if not any(head):
        raise ValueError('Header row not recognised. Download the template and use its column names.')
    hnorm = [norm(c) for c in raw_rows[0]]
    out = []
    for i, r in enumerate(raw_rows[1:], start=2):
        if [norm(c) for c in r] == hnorm:  # repeated header (multi-table Word docs)
            continue
        d = {k: v for k, v in zip(head, r) if k}
        d['_row'] = i
        out.append(d)
    return out


def parse_ans(v):
    v = (v or '').strip().upper()
    if re.fullmatch(r'[A-D]', v):
        return v
    if re.fullmatch(r'[1-4]', v):
        return 'ABCD'[int(v) - 1]
    m = re.search(r'(?:^|[^A-Z])([A-D])(?:[^A-Z]|$)', v)
    return m.group(1) if m else None


def validate_questions(rows, default_subject):
    existing = {(r['sn'].lower(), r['t'].strip().lower()) for r in qa(
        'select s.name sn, q.text t from questions q join subjects s on s.id=q.subject_id')}
    seen, valid, errors = set(), [], []
    for r in rows:
        n = r['_row']
        subj = (r.get('subject') or default_subject or '').strip()
        text = (r.get('question') or '').strip()
        opts = {k: (r.get(k) or '').strip() for k in 'abcd'}
        ans = parse_ans(r.get('answer'))
        if not subj:
            errors.append((n, 'Missing subject (add a Subject column or pick a default subject)')); continue
        if not text:
            errors.append((n, 'Question text is empty')); continue
        if sum(1 for v in opts.values() if v) < 2:
            errors.append((n, 'At least 2 options are required')); continue
        if not ans or not opts[ans.lower()]:
            errors.append((n, 'Answer must be A-D and point to a filled option')); continue
        try:
            marks = float(r.get('marks') or 1)
            if marks <= 0:
                raise ValueError
        except ValueError:
            errors.append((n, 'Marks must be a positive number')); continue
        key = (subj.lower(), text.lower())
        if key in existing or key in seen:
            errors.append((n, 'Duplicate question (already in bank or repeated in file)')); continue
        seen.add(key)
        valid.append(dict(subject=subj, text=text, a=opts['a'], b=opts['b'], c=opts['c'], d=opts['d'], answer=ans,
                          marks=marks, topic=r.get('topic', ''), difficulty=r.get('difficulty', ''), row=n))
    return valid, errors


IMPORTS = {}  # token -> dict(valid, errors, ts)


def get_or_create(table, name):
    r = db().execute(f'select id from {table} where lower(name)=lower(?)', (name,)).fetchone()
    if r:
        return r[0]
    return db().execute(f'insert into {table}(name) values(?)', (name,)).lastrowid


# ---------------------------------------------------------------- xlsx / docx output
def xlsx_resp(sheets, fname):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, headers, rows in sheets:
        ws = wb.create_sheet(title[:31])
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True, color='FFFFFF')
            c.fill = PatternFill('solid', fgColor='1F4E79')
            c.alignment = Alignment(horizontal='center')
        for r in rows:
            ws.append(list(r))
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if isinstance(c.value, str) and c.value[:1] in '=+-@':
                    c.data_type = 's'  # never let imported text become a formula
        for col in ws.columns:
            w = min(60, max(len(str(c.value or '')) for c in col) + 2)
            ws.column_dimensions[col[0].column_letter].width = max(8, w)
        ws.freeze_panes = 'A2'
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return send_file(bio, as_attachment=True, download_name=fname,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


TEMPLATES = {
    'questions': (['Subject', 'Question', 'OptionA', 'OptionB', 'OptionC', 'OptionD', 'Answer', 'Marks', 'Topic', 'Difficulty'],
                  [['Biology', 'Which organelle produces ATP?', 'Nucleus', 'Mitochondrion', 'Ribosome', 'Golgi body', 'B', 1, 'Cell Biology', 'Easy']]),
    'students': (['RegNo', 'Name', 'Class', 'AccessCode'], [['2026001', 'Ada Okafor', 'SS1 A', '']]),
    'classes': (['Name'], [['SS1 A'], ['SS1 B']]),
    'subjects': (['Name'], [['Biology'], ['Mathematics']]),
}


@app.get('/api/admin/template/<kind>/<fmt>')
@admin
def template(kind, fmt):
    if kind not in TEMPLATES or fmt not in ('xlsx', 'docx'):
        return err('Unknown template', 404)
    heads, sample = TEMPLATES[kind]
    if fmt == 'xlsx':
        return xlsx_resp([(kind.title(), heads, sample)], f'{kind}_template.xlsx')
    d = docx.Document()
    d.add_paragraph(f'{kind.title()} import template - keep the header row; one record per row. Delete this line and the sample rows.')
    t = d.add_table(rows=1, cols=len(heads))
    t.style = 'Table Grid'
    for i, h in enumerate(heads):
        t.rows[0].cells[i].text = h
    for s in sample:
        cells = t.add_row().cells
        for i, v in enumerate(s):
            cells[i].text = str(v)
    bio = io.BytesIO()
    d.save(bio)
    bio.seek(0)
    return send_file(bio, as_attachment=True, download_name=f'{kind}_template.docx',
                     mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')


# ---------------------------------------------------------------- pages
@app.get('/gtmc-logo.jpg')
def gtmc_logo():
    # Android stores the image beside the bundled web assets; Windows stores it at app root.
    logo_dir = WEB if os.path.isfile(os.path.join(WEB, 'gtmc-logo.jpg')) else HERE
    return send_from_directory(logo_dir, 'gtmc-logo.jpg', max_age=86400)


@app.get('/')
@app.get('/exam')
def student_page():
    return send_from_directory(WEB, 'student.html')



@app.get('/home')
@app.get('/home/')
def home_student_page():
    # Additional browser/PWA entry point; existing Android and school routes remain.
    return send_from_directory(WEB, 'student.html')


@app.get('/home/manifest.webmanifest')
def home_manifest():
    return send_from_directory(WEB, 'home-manifest.webmanifest', mimetype='application/manifest+json')


@app.get('/home/icon.svg')
def home_icon():
    return send_from_directory(WEB, 'home-icon.svg', mimetype='image/svg+xml')


@app.get('/home/sw.js')
def home_service_worker():
    response = send_from_directory(WEB, 'home-sw.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/home/'
    response.headers['Cache-Control'] = 'no-cache'
    return response


@app.get('/admin')
def admin_page():
    return send_from_directory(WEB, 'admin.html')


@app.get('/vicora-logo.svg')
def vicora_logo():
    return send_from_directory(WEB, 'vicora-logo.svg', mimetype='image/svg+xml', max_age=86400)


@app.get('/vicora-icon.svg')
def vicora_icon():
    return send_from_directory(WEB, 'vicora-icon.svg', mimetype='image/svg+xml', max_age=86400)


def school_logo_response(fallback):
    school = school_context(db(), request.args.get('school_code'))
    if not school:
        return send_from_directory(WEB, fallback, mimetype='image/svg+xml')
    activate_tenant_views(db(), school['school_id'])
    logo_data = getset('school_logo_data', '')
    logo_mime = getset('school_logo_mime', '')
    if logo_mime not in ('image/png', 'image/jpeg', 'image/webp') or not logo_data:
        return send_from_directory(WEB, fallback, mimetype='image/svg+xml')
    try:
        return send_file(io.BytesIO(base64.b64decode(logo_data, validate=True)),
                         mimetype=logo_mime, max_age=3600)
    except (ValueError, TypeError):
        return send_from_directory(WEB, fallback, mimetype='image/svg+xml')


@app.get('/school-logo')
def school_logo():
    return school_logo_response('home-icon.svg')


@app.get('/api/public/school-logo')
def public_school_logo():
    return school_logo_response('vicora-icon.svg')


@app.get('/api/public/info')
def public_info():
    try:
        theme = json.loads(getset('school_theme', '{}') or '{}')
    except (TypeError, ValueError):
        theme = {}
    school = school_context(db(), request.args.get('school_code'))
    if school:
        activate_tenant_views(db(), school['school_id'])
        school_name = getset('school_name') or school['name']
        school_theme = getset('school_theme', '{}') or '{}'
        try:
            theme = json.loads(school_theme)
        except (TypeError, ValueError):
            theme = {}
        return jsonify(school=school_name, school_code=school['school_code'],
                       school_id=school['school_id'], theme=theme,
                       school_logo_url='/api/public/school-logo?school_code=' + school['school_code'])
    return jsonify(school='VICORA CBT', school_code='', school_id='',
                   theme={}, school_logo_url='/vicora-icon.svg')


# ---------------------------------------------------------------- admin: auth & settings
@app.post('/api/admin/login')
def a_login():
    d = request.get_json(silent=True) or {}
    key = 'adm|' + str(request.remote_addr)
    if throttled(key):
        return err('Too many attempts. Wait 5 minutes.', 429)
    school = school_context(db(), d.get('school_code'))
    if not school:
        add_fail(key)
        return err('Enter a valid School Code. A School Code is required when more than one school is registered.', 401)
    activate_tenant_views(db(), school['school_id'])
    r = q1('select * from admins where lower(username)=lower(?) and school_id=?', (d.get('username', '').strip(), school['school_id']))
    if not r or not r['active'] or not check_password_hash(r['password_hash'], d.get('password', '')):
        add_fail(key)
        return err('Wrong username or password', 401)
    session.permanent = True
    session['admin'] = r['username']
    session['school_id'] = school['school_id']
    session['admin_role'] = r['role']
    if school['school_id'] == getset('vicora_legacy_school_id', ''):
        audit('Staff logged in: ' + r['username'] + ' (' + ROLE_NAMES.get(r['role'], r['role']) + ')')
    else:
        db().execute("INSERT INTO platform_audit(ts,actor,action,school_id) VALUES(?,?,?,?)",
                     (int(time.time()), r['username'], 'School administrator logged in', school['school_id']))
        db().commit()
    return jsonify(ok=True, user=r['username'], role=r['role'], role_name=ROLE_NAMES.get(r['role'], r['role']))


@app.post('/api/admin/logout')
def a_logout():
    session.clear()
    return jsonify(ok=True)


@app.get('/api/admin/me')
def a_me():
    username = session.get('admin')
    legacy_school_id = getset('vicora_legacy_school_id', '')
    if username and not session.get('school_id') and legacy_school_id:
        session['school_id'] = legacy_school_id
    if username and session.get('school_id'):
        activate_tenant_views(db(), session['school_id'])
    staff = q1('SELECT username, role, active, school_id FROM admins WHERE username=? AND school_id=?', (username, session.get('school_id'))) if username and session.get('school_id') else None
    if not staff or not staff['active']:
        session.clear()
        return jsonify(user=None, role=None, school=getset('school_name'))
    school = q1('SELECT name, school_code FROM schools WHERE school_id=?', (staff['school_id'],))
    return jsonify(user=staff['username'], role=staff['role'], role_name=ROLE_NAMES.get(staff['role'], staff['role']),
                   school=school['name'] if school else getset('school_name'),
                   school_id=staff['school_id'], school_code=school['school_code'] if school else '')


@app.post('/api/admin/password')
@admin
def a_pw():
    d = request.get_json() or {}
    r = q1('select * from admins where username=?', (session['admin'],))
    if not check_password_hash(r['password_hash'], d.get('old', '')):
        return err('Current password is wrong')
    if len(d.get('new', '')) < 6:
        return err('New password must be at least 6 characters')
    ex('update admins set password_hash=? where id=?', (generate_password_hash(d['new']), r['id']))
    setset('default_pw', '0')
    audit('Admin password changed')
    return jsonify(ok=True)


@app.get('/api/admin/settings')
@admin
def a_settings():
    try:
        theme = json.loads(getset('school_theme', '{}') or '{}')
    except (TypeError, ValueError):
        theme = {}
    return jsonify(school_name=getset('school_name'), allow_remote_admin=getset('allow_remote_admin') == '1',
                   theme=theme, school_logo_url='/api/public/school-logo')


@app.post('/api/admin/school-logo')
@admin
def a_school_logo_upload():
    upload = request.files.get('logo')
    if not upload or not upload.filename:
        return err('Choose a school logo image first.')
    if request.content_length and request.content_length > 2 * 1024 * 1024 + 65536:
        return err('Logo file must be 2 MB or smaller.')
    filename = upload.filename.lower()
    data = upload.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        return err('Logo file must be 2 MB or smaller.')
    if filename.endswith('.png') and data.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10])):
        ext = 'png'
    elif filename.endswith(('.jpg', '.jpeg')) and data.startswith(bytes([255, 216, 255])):
        ext = 'jpg'
    elif filename.endswith('.webp') and len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        ext = 'webp'
    else:
        return err('Use a valid PNG, JPG or WebP image.')
    mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'webp': 'image/webp'}[ext]
    # Keep the image in SQLite so normal database backups preserve school branding.
    setset('school_logo_data', base64.b64encode(data).decode('ascii'))
    setset('school_logo_mime', mime)
    audit('School interface logo updated')
    return jsonify(ok=True, school_logo_url='/api/public/school-logo')


@app.post('/api/admin/settings')
@admin
def a_settings_save():
    d = request.get_json() or {}
    setset('school_name', (d.get('school_name') or 'CBT Examination Centre').strip()[:100])
    if d.get('allow_remote_admin') and not (TRUST_PROXY and COOKIE_SECURE):
        return err('Remote Admin can only be enabled after trusted HTTPS reverse-proxy mode and secure cookies are configured.')
    setset('allow_remote_admin', '1' if d.get('allow_remote_admin') else '0')
    theme = d.get('theme') or {}
    allowed = {'primary', 'background', 'surface', 'text', 'sidebar'}
    clean = {}
    for key in allowed:
        value = str(theme.get(key, '')).strip()
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            return err('Theme colours must be valid six-digit hexadecimal colours.')
        clean[key] = value.lower()
    clean['mode'] = 'dark' if theme.get('mode') == 'dark' else 'light'
    clean['preset'] = str(theme.get('preset') or 'custom')[:30]
    setset('school_theme', json.dumps(clean, separators=(',', ':')))
    audit('School-wide appearance settings updated')
    return jsonify(ok=True, theme=clean)


def lan_ips():
    ips = set()
    try:
        for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(i[4][0])
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(i for i in ips if not i.startswith('127.'))


@app.get('/api/admin/server-info')
@admin
def server_info():
    return jsonify(
        ips=lan_ips(),
        port=SERVER_PORT,
        bind_host=SERVER_HOST,
        secure_reverse_proxy=TRUST_PROXY,
        remote_admin_enabled=getset('allow_remote_admin', '0') == '1',
        connection_hint='Use a listed LAN address on the school network. Remote access requires a separately configured HTTPS reverse proxy and a publicly reachable ISP address.'
    )


@app.get('/api/admin/dashboard')
@admin
def dashboard():
    now = int(time.time())
    n = lambda sql, a=(): db().execute(sql, a).fetchone()[0]
    return jsonify(
        students=n('select count(*) from students'), questions=n('select count(*) from questions'),
        subjects=n('select count(*) from subjects'), classes=n('select count(*) from classes'),
        exams=n('select count(*) from exams'), live=n("select count(*) from exams where status='live'"),
        writing=n("select count(*) from sessions where status='in_progress' and last_seen>?", (now - 30,)),
        submitted=n("select count(*) from sessions where status='submitted'"),
        per_subject=qa('select s.name, count(q.id) n from subjects s left join questions q on q.subject_id=s.id group by s.id order by n desc limit 12'),
        recent=[dict(r, when=fmt_ts(r['ts'])) for r in qa('select * from audit order by id desc limit 8')],
        default_pw=getset('default_pw') == '1')


@app.get('/api/admin/audit')
@admin
def audit_list():
    return jsonify([dict(r, when=fmt_ts(r['ts'])) for r in qa('select * from audit order by id desc limit 300')])



# ---------------------------------------------------------------- admin: staff accounts (Super Admin only)
@app.get('/api/admin/staff')
@admin
def staff_list():
    rows = qa('SELECT id, username, role, active FROM admins ORDER BY username')
    return jsonify(rows=[dict(r, role_name=ROLE_NAMES.get(r['role'], r['role'])) for r in rows])


@app.post('/api/admin/staff')
@admin
def staff_create():
    d = request.get_json(silent=True) or {}
    username = str(d.get('username') or '').strip()
    password = str(d.get('password') or '')
    role = str(d.get('role') or 'exam_administrator')
    if not re.fullmatch(r'[A-Za-z0-9_.@-]{3,80}', username):
        return err('Username must be 3-80 characters and use letters, numbers, dot, underscore, @ or hyphen.')
    if len(password) < 8:
        return err('New staff password must be at least 8 characters.')
    if role not in ROLE_NAMES:
        return err('Choose a valid staff role.')
    if q1('SELECT id FROM admins WHERE lower(username)=lower(?)', (username,)):
        return err('That username already exists.')
    ex('INSERT INTO admins(username,password_hash,role,active) VALUES(?,?,?,1)',
       (username, generate_password_hash(password), role))
    audit('Created staff account: ' + username + ' (' + ROLE_NAMES[role] + ')')
    return jsonify(ok=True)


@app.get('/api/admin/staff/<int:staff_id>/exams')
@admin
def staff_exam_list(staff_id):
    target = q1('SELECT id, role FROM admins WHERE id=?', (staff_id,))
    if not target:
        return err('Staff account not found.', 404)
    if target['role'] != 'examiner':
        return jsonify(exam_ids=[])
    rows = qa('SELECT exam_id FROM staff_exam_assignments WHERE staff_id=? ORDER BY exam_id', (staff_id,))
    return jsonify(exam_ids=[r['exam_id'] for r in rows])


@app.post('/api/admin/staff/<int:staff_id>/exams')
@admin
def staff_exam_save(staff_id):
    target = q1('SELECT id, username, role FROM admins WHERE id=?', (staff_id,))
    if not target:
        return err('Staff account not found.', 404)
    if target['role'] != 'examiner':
        return err('Only Examiner / Marker accounts can be assigned examinations.')
    d = request.get_json(silent=True) or {}
    raw_ids = d.get('exam_ids') or []
    if not isinstance(raw_ids, list):
        return err('Exam assignments must be a list.')
    try:
        exam_ids = sorted(set(int(x) for x in raw_ids))
    except (TypeError, ValueError):
        return err('Invalid examination selection.')
    for exam_id in exam_ids:
        if not q1('SELECT id FROM exams WHERE id=?', (exam_id,)):
            return err('One or more selected examinations no longer exist.')
    ex('DELETE FROM staff_exam_assignments WHERE staff_id=?', (staff_id,))
    for exam_id in exam_ids:
        ex('INSERT INTO staff_exam_assignments(staff_id,exam_id,assigned_by,assigned_ts) VALUES(?,?,?,?)',
           (staff_id, exam_id, session.get('admin'), int(time.time())))
    audit('Updated exam assignments for marker: ' + target['username'])
    return jsonify(ok=True, assigned=len(exam_ids))


@app.post('/api/admin/staff/<int:staff_id>/password')
@admin
def staff_password_reset(staff_id):
    target = q1('SELECT id, username FROM admins WHERE id=?', (staff_id,))
    if not target:
        return err('Staff account not found.', 404)
    d = request.get_json(silent=True) or {}
    password = str(d.get('password') or '')
    if len(password) < 8:
        return err('New staff password must be at least 8 characters.')
    ex('UPDATE admins SET password_hash=? WHERE id=?',
       (generate_password_hash(password), staff_id))
    audit('Reset staff password: ' + target['username'])
    return jsonify(ok=True)


@app.post('/api/admin/staff/<int:staff_id>')
@admin
def staff_update(staff_id):
    d = request.get_json(silent=True) or {}
    target = q1('SELECT id, username, role, active FROM admins WHERE id=?', (staff_id,))
    if not target:
        return err('Staff account not found.', 404)
    role = d.get('role', target['role'])
    active = d.get('active', target['active'])
    if role not in ROLE_NAMES or active not in (0, 1, True, False):
        return err('Invalid role or account status.')
    active = 1 if active else 0
    if target['username'] == session.get('admin') and (role != target['role'] or not active):
        return err('You cannot change your own role or deactivate your own account.')
    if target['role'] == 'super_admin' and (role != 'super_admin' or not active):
        remaining = q1("SELECT COUNT(*) n FROM admins WHERE role='super_admin' AND active=1 AND id<>?", (staff_id,))
        if not remaining or remaining['n'] < 1:
            return err('At least one active Super Admin account must remain.')
    ex('UPDATE admins SET role=?, active=? WHERE id=?', (role, active, staff_id))
    audit('Updated staff account: ' + target['username'] + ' (' + ROLE_NAMES[role] + ', ' + ('active' if active else 'inactive') + ')')
    return jsonify(ok=True)

# ---------------------------------------------------------------- admin: classes & subjects
def simple_crud(table, label):
    path = f'/api/admin/{table}'
    cnt = {'classes': 'select c.*, (select count(*) from students where class_id=c.id) n from classes c order by name',
           'subjects': 'select s.*, (select count(*) from questions where subject_id=s.id) n from subjects s order by name'}[table]

    def lst():
        return jsonify(qa(cnt))

    def add():
        name = ((request.get_json() or {}).get('name') or '').strip()
        if not name:
            return err('Name is required')
        if q1(f'select 1 from {table} where lower(name)=lower(?)', (name,)):
            return err(f'{label} already exists')
        ex(f'insert into {table}(name) values(?)', (name,))
        audit(f'Added {label.lower()} {name}')
        return jsonify(ok=True)

    def rm(i):
        if table == 'classes' and q1('select 1 from students where class_id=?', (i,)):
            return err('Class still has students. Delete or move them first.')
        if table == 'subjects' and (q1('select 1 from questions where subject_id=?', (i,)) or q1('select 1 from exams where subject_id=?', (i,))):
            return err('Subject still has questions or exams.')
        if table == 'classes' and q1('select 1 from exam_classes where class_id=?', (i,)):
            return err('Class is assigned to an exam.')
        ex(f'delete from {table} where id=?', (i,))
        audit(f'Deleted {label.lower()} #{i}')
        return jsonify(ok=True)
    app.add_url_rule(path, f'{table}_list', admin(lst), methods=['GET'])
    app.add_url_rule(path, f'{table}_add', admin(add), methods=['POST'])
    app.add_url_rule(path + '/<int:i>', f'{table}_rm', admin(rm), methods=['DELETE'])


simple_crud('classes', 'Class')
simple_crud('subjects', 'Subject')


@app.post('/api/admin/import/<kind>')
@admin
def import_file(kind):
    if kind not in ('classes', 'subjects', 'students', 'questions'):
        return err('Unknown import type', 404)
    f = request.files.get('file')
    if not f:
        return err('Choose a file first')
    try:
        rows = read_table(f)
    except Exception as e:
        return err(str(e))
    if kind == 'questions':
        valid, errors = validate_questions(rows, request.form.get('default_subject', ''))
        tok = secrets.token_hex(8)
        IMPORTS[tok] = dict(valid=valid, errors=errors, ts=time.time())
        for k in [k for k, v in IMPORTS.items() if time.time() - v['ts'] > 3600]:
            IMPORTS.pop(k, None)
        return jsonify(token=tok, valid=len(valid), errors=[dict(row=a, reason=b) for a, b in errors[:200]],
                       error_count=len(errors), total=len(rows))
    added = updated = 0
    errors = []
    if kind in ('classes', 'subjects'):
        table = kind
        for r in rows:
            name = (r.get('name') or r.get('subject') or r.get('class') or '').strip()
            if not name:
                errors.append(dict(row=r['_row'], reason='Empty name')); continue
            if q1(f'select 1 from {table} where lower(name)=lower(?)', (name,)):
                errors.append(dict(row=r['_row'], reason=f'{name}: already exists')); continue
            db().execute(f'insert into {table}(name) values(?)', (name,)); added += 1
    else:
        default_class = request.form.get('default_class', '').strip()
        for r in rows:
            reg, name = r.get('regno', '').strip(), r.get('name', '').strip()
            cls = (r.get('class') or default_class).strip()
            if not reg or not name or not cls:
                errors.append(dict(row=r['_row'], reason='RegNo, Name and Class are all required')); continue
            cid = get_or_create('classes', cls)
            old = db().execute('select id, access_code from students where lower(reg_no)=lower(?)', (reg,)).fetchone()
            code = (r.get('code') or '').strip().upper()
            if old:
                db().execute('update students set name=?, class_id=?, access_code=? where id=?', (name, cid, code or old['access_code'], old['id'])); updated += 1
            else:
                db().execute('insert into students(reg_no,name,class_id,access_code) values(?,?,?,?)', (reg, name, cid, code or gen_code())); added += 1
    db().commit()
    audit(f'Imported {kind}: {added} added, {updated} updated, {len(errors)} skipped')
    return jsonify(added=added, updated=updated, errors=errors[:200], error_count=len(errors))


@app.post('/api/admin/import/questions/commit')
@admin
def import_commit():
    imp = IMPORTS.get((request.get_json() or {}).get('token'))
    if not imp:
        return err('Import session expired. Upload the file again.')
    n = 0
    imp['valid'], valid = [], imp['valid']  # a second commit of the same token imports nothing
    for v in valid:
        sid = get_or_create('subjects', v['subject'])
        cur = db().execute('insert or ignore into questions(subject_id,text,a,b,c,d,answer,marks,topic,difficulty) values(?,?,?,?,?,?,?,?,?,?)',
                           (sid, v['text'], v['a'], v['b'], v['c'], v['d'], v['answer'], v['marks'], v['topic'], v['difficulty']))
        n += cur.rowcount
    db().commit()
    audit(f'Imported {n} questions')
    return jsonify(imported=n)


@app.get('/api/admin/import/errors/<tok>')
@admin
def import_errors(tok):
    imp = IMPORTS.get(tok)
    if not imp:
        return err('Expired', 404)
    return xlsx_resp([('Errors', ['Row', 'Reason'], imp['errors'])], 'import_errors.xlsx')


# ---------------------------------------------------------------- admin: students
@app.get('/api/admin/students')
@admin
def students_list():
    w, a = [], []
    if request.args.get('class_id'):
        w.append('s.class_id=?'); a.append(request.args['class_id'])
    if request.args.get('q'):
        w.append('(s.name like ? or s.reg_no like ?)'); a += [f"%{request.args['q']}%"] * 2
    W = ('where ' + ' and '.join(w)) if w else ''
    page = max(1, int(request.args.get('page', 1)))
    tot = db().execute(f'select count(*) from students s {W}', a).fetchone()[0]
    rows = qa(f'select s.*, c.name class from students s join classes c on c.id=s.class_id {W} order by c.name, s.name limit 100 offset ?', a + [(page - 1) * 100])
    return jsonify(total=tot, rows=rows, per=100)


@app.post('/api/admin/students')
@admin
def student_add():
    d = request.get_json() or {}
    reg, name, cls = (d.get('reg_no') or '').strip(), (d.get('name') or '').strip(), d.get('class_id')
    if not reg or not name or not cls:
        return err('RegNo, name and class are required')
    if q1('select 1 from students where lower(reg_no)=lower(?)', (reg,)):
        return err('RegNo already exists')
    ex('insert into students(reg_no,name,class_id,access_code) values(?,?,?,?)', (reg, name, cls, gen_code()))
    audit(f'Added student {reg}')
    return jsonify(ok=True)


@app.post('/api/admin/students/delete')
@admin
def student_delete():
    ids = (request.get_json() or {}).get('ids', [])
    for i in ids:
        db().execute('delete from students where id=?', (i,))
    db().commit()
    audit(f'Deleted {len(ids)} students')
    return jsonify(ok=True)


@app.post('/api/admin/students/regen')
@admin
def student_regen():
    d = request.get_json() or {}
    ids = d.get('ids') or [r['id'] for r in qa('select id from students where class_id=?', (d.get('class_id'),))]
    for i in ids:
        db().execute('update students set access_code=? where id=?', (gen_code(), i))
    db().commit()
    audit(f'Regenerated {len(ids)} access codes')
    return jsonify(count=len(ids))


@app.get('/api/admin/export/students')
@admin
def export_students():
    a, w = [], ''
    if request.args.get('class_id'):
        w, a = 'where s.class_id=?', [request.args['class_id']]
    rows = qa(f'select s.reg_no, s.name, c.name class, s.access_code from students s join classes c on c.id=s.class_id {w} order by c.name, s.name', a)
    return xlsx_resp([('Students', ['RegNo', 'Name', 'Class', 'AccessCode'], [list(r.values()) for r in rows])], 'students_access_codes.xlsx')


# ---------------------------------------------------------------- admin: questions
@app.get('/api/admin/questions')
@admin
def q_list():
    w, a = [], []
    if request.args.get('subject_id'):
        w.append('q.subject_id=?'); a.append(request.args['subject_id'])
    if request.args.get('q'):
        w.append('(q.text like ? or q.topic like ?)'); a += [f"%{request.args['q']}%"] * 2
    W = ('where ' + ' and '.join(w)) if w else ''
    page = max(1, int(request.args.get('page', 1)))
    tot = db().execute(f'select count(*) from questions q {W}', a).fetchone()[0]
    rows = qa(f'select q.*, s.name subject from questions q join subjects s on s.id=q.subject_id {W} order by q.id desc limit 50 offset ?', a + [(page - 1) * 50])
    return jsonify(total=tot, rows=rows, per=50)


def q_payload():
    d = request.get_json() or {}
    qtype = 'theory' if d.get('question_type') == 'theory' else 'objective'
    text = (d.get('text') or '').strip()
    if not d.get('subject_id') or not text:
        return None, 'Subject and question text are required'
    try:
        marks = float(d.get('marks') or 1)
        if marks <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return None, 'Marks must be a positive number'
    if qtype == 'theory':
        mode = d.get('marking_mode') if d.get('marking_mode') in ('exact','multiple','keyword','manual') else 'manual'
        space = d.get('answer_space') if d.get('answer_space') in ('short','medium','large','lined','math','diagram') else 'medium'
        answer_text = str(d.get('answer_text') or '').strip()
        accepted = d.get('accepted_answers') if isinstance(d.get('accepted_answers'), list) else []
        keywords = d.get('keywords') if isinstance(d.get('keywords'), list) else []
        if mode in ('exact','multiple') and not answer_text and not accepted:
            return None, 'Add at least one correct answer, or choose manual marking'
        p = (d['subject_id'], text, '', '', '', '', '', marks, d.get('topic',''), d.get('difficulty',''),
             'theory', answer_text, json.dumps(accepted), json.dumps(keywords), space, mode)
        return p, None
    opts = {k: (d.get(k) or '').strip() for k in 'abcd'}
    ans = parse_ans(d.get('answer'))
    if sum(1 for v in opts.values() if v) < 2:
        return None, 'At least 2 options are required'
    if not ans or not opts[ans.lower()]:
        return None, 'Correct answer must be one of the filled options'
    p = (d['subject_id'], text, opts['a'], opts['b'], opts['c'], opts['d'], ans, marks,
         d.get('topic', ''), d.get('difficulty', ''), 'objective', '', '[]', '[]', 'medium', 'exact')
    return p, None


@app.post('/api/admin/questions')
@admin
def q_add():
    p, e = q_payload()
    if e:
        return err(e)
    try:
        ex('insert into questions(subject_id,text,a,b,c,d,answer,marks,topic,difficulty,question_type,answer_text,accepted_answers,keywords,answer_space,marking_mode) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', p)
    except sqlite3.IntegrityError:
        return err('This question already exists in the subject')
    audit('Added a question')
    return jsonify(ok=True)


@app.put('/api/admin/questions/<int:i>')
@admin
def q_edit(i):
    p, e = q_payload()
    if e:
        return err(e)
    if q1('select 1 from session_questions where question_id=?', (i,)):
        return err('This question has already been used in an exam and cannot be edited.')
    try:
        ex('update questions set subject_id=?,text=?,a=?,b=?,c=?,d=?,answer=?,marks=?,topic=?,difficulty=?,question_type=?,answer_text=?,accepted_answers=?,keywords=?,answer_space=?,marking_mode=? where id=?', p + (i,))
    except sqlite3.IntegrityError:
        return err('Another identical question exists in this subject')
    return jsonify(ok=True)


@app.post('/api/admin/questions/delete')
@admin
def q_delete():
    ids = (request.get_json() or {}).get('ids', [])
    done = blocked = 0
    for i in ids:
        if q1('select 1 from session_questions where question_id=?', (i,)):
            blocked += 1
            continue
        db().execute('delete from questions where id=?', (i,)); done += 1
    db().commit()
    audit(f'Deleted {done} questions')
    return jsonify(deleted=done, blocked=blocked)


@app.get('/api/admin/export/questions')
@admin
def export_questions():
    a, w = [], ''
    if request.args.get('subject_id'):
        w, a = 'where q.subject_id=?', [request.args['subject_id']]
    rows = qa(f'select s.name sn,q.text,q.a,q.b,q.c,q.d,q.answer,q.marks,q.topic,q.difficulty from questions q join subjects s on s.id=q.subject_id {w} order by s.name,q.id', a)
    return xlsx_resp([('Questions', TEMPLATES['questions'][0], [list(r.values()) for r in rows])], 'question_bank.xlsx')


# ---------------------------------------------------------------- admin: exams
@app.get('/api/admin/exams')
@admin
def exams_list():
    rows = qa('''select e.*, s.name subject,
      (select group_concat(c.name, ', ') from exam_classes ec join classes c on c.id=ec.class_id where ec.exam_id=e.id) classes,
      (select count(*) from sessions where exam_id=e.id) sessions,
      (select count(*) from sessions where exam_id=e.id and status='submitted') submitted,
      (select count(*) from questions where subject_id=e.subject_id) pool
      from exams e join subjects s on s.id=e.subject_id order by e.id desc''')
    if session.get('admin_role') == 'examiner':
        staff = q1('SELECT id FROM admins WHERE username=?', (session.get('admin'),))
        assigned = {r['exam_id'] for r in qa('SELECT exam_id FROM staff_exam_assignments WHERE staff_id=?', (staff['id'],))} if staff else set()
        rows = [r for r in rows if r['id'] in assigned]
    return jsonify(rows)


@app.post('/api/admin/exams/<int:exam_id>/android-sync')
@admin
def set_exam_android_sync(exam_id):
    d = request.get_json(silent=True) or {}
    enabled = bool(d.get('enabled'))
    exam = q1('select id,title from exams where id=?', (exam_id,))
    if not exam:
        return err('Examination not found.', 404)
    ex('update exams set android_host_sync_enabled=? where id=?', (1 if enabled else 0, exam_id))
    audit(('Enabled' if enabled else 'Disabled') + f' automatic Android Host sync for exam {exam_id}')
    return jsonify(ok=True, exam_id=exam_id, enabled=enabled)


@app.post('/api/admin/exams')
@admin
def exam_add():
    d = request.get_json() or {}
    try:
        dur = int(d.get('duration_min'))
        if 'objective_questions' in d or 'theory_questions' in d:
            objective_count = int(d.get('objective_questions') or 0)
            theory_count = int(d.get('theory_questions') or 0)
            num = objective_count + theory_count
        else:
            num = int(d.get('num_questions'))
            objective_count, theory_count = num, 0
    except (TypeError, ValueError):
        return err('Duration and question counts must be whole numbers')
    title, sid, cids = (d.get('title') or '').strip(), d.get('subject_id'), d.get('class_ids') or []
    if not title or not sid or not cids or dur < 1 or num < 1 or objective_count < 0 or theory_count < 0:
        return err('Title, subject, classes, duration and at least one question are required')
    pool_rows = qa('select text,question_type from questions where subject_id=? order by id', (sid,))
    seen_bank = set()
    obj_pool = theory_pool = 0
    for row in pool_rows:
        key = ' '.join((row['text'] or '').casefold().split())
        if not key or key in seen_bank:
            continue
        seen_bank.add(key)
        if row['question_type'] == 'theory':
            theory_pool += 1
        else:
            obj_pool += 1
    if obj_pool < objective_count or theory_pool < theory_count:
        return err(f'Question bank shortage: {obj_pool} objective and {theory_pool} theory questions available; this exam requests {objective_count} objective and {theory_count} theory questions.')
    camera_policy = d.get('camera_policy', 'off')
    if camera_policy not in ('off', 'optional', 'required'):
        return err('Proctor Mode must be Off, Optional or Required')
    cur = ex('insert into exams(title,subject_id,duration_min,num_questions,shuffle,show_score,pass_mark,instructions,created_ts,objective_count,theory_count,camera_policy) values(?,?,?,?,?,?,?,?,?,?,?,?)',
             (title, sid, dur, num, 1 if d.get('shuffle', True) else 0, 1 if d.get('show_score') else 0,
              float(d.get('pass_mark') or 50), d.get('instructions', ''), int(time.time()), objective_count, theory_count, camera_policy))
    for c in cids:
        db().execute('insert or ignore into exam_classes values(?,?)', (cur.lastrowid, c))
    db().commit()
    audit(f'Created exam {title} (Proctor Mode: {camera_policy})')
    return jsonify(ok=True, id=cur.lastrowid)


@app.post('/api/admin/android-host/pairing-code')
@admin
def android_host_pairing_code():
    code = secrets.token_urlsafe(24)
    setset('android_host_pairing_hash', hashlib.sha256(code.encode('utf-8')).hexdigest())
    setset('android_host_pairing_expires', int(time.time()) + 600)
    audit('Generated a one-time Android Host pairing code')
    return jsonify(ok=True, pairing_code=code, expires_in_seconds=600)


@app.post('/api/android-host/pair')
def android_host_pair():
    if not request.is_secure and request.remote_addr not in ('127.0.0.1', '::1', 'localhost'):
        return err('Android Host pairing requires HTTPS.', 400)
    d = request.get_json(silent=True) or {}
    code = str(d.get('pairing_code') or '')
    try:
        device_id = str(uuid.UUID(str(d.get('device_id') or '')))
    except (ValueError, TypeError, AttributeError):
        return err('A valid device ID is required.')
    label = str(d.get('label') or 'GTMC Android Host')[:100]
    expected = getset('android_host_pairing_hash', '')
    expires = int(getset('android_host_pairing_expires', '0') or 0)
    supplied = hashlib.sha256(code.encode('utf-8')).hexdigest() if code else ''
    if not expected or int(time.time()) > expires or not hmac.compare_digest(expected, supplied):
        return err('Pairing code is invalid or expired.', 401)
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    ex('''insert into android_host_devices(device_id,token_hash,label,created_ts,last_seen,revoked_ts)
          values(?,?,?,?,?,0)
          on conflict(device_id) do update set token_hash=excluded.token_hash,label=excluded.label,
          created_ts=excluded.created_ts,last_seen=excluded.last_seen,revoked_ts=0''',
       (device_id, token_hash, label, int(time.time()), int(time.time())))
    setset('android_host_pairing_hash', '')
    setset('android_host_pairing_expires', '0')
    return jsonify(ok=True, device_id=device_id, device_token=token)


def _android_device_from_request():
    auth = request.headers.get('Authorization', '')
    token = auth[7:].strip() if auth.lower().startswith('bearer ') else ''
    device_id = str((request.get_json(silent=True) or {}).get('device_id') or '')
    if not token or not device_id:
        return None
    row = q1('select * from android_host_devices where device_id=? and revoked_ts=0', (device_id,))
    digest = hashlib.sha256(token.encode('utf-8')).hexdigest()
    if not row or not hmac.compare_digest(row['token_hash'], digest):
        return None
    ex('update android_host_devices set last_seen=? where device_id=?', (int(time.time()), device_id))
    return row



def _build_android_host_package(exam_id):
    exam = q1('select * from exams where id=?', (exam_id,))
    if not exam:
        return None
    subject = q1('select * from subjects where id=?', (exam['subject_id'],))
    if not subject:
        return None
    classes = qa('''select c.* from classes c join exam_classes ec on ec.class_id=c.id
                    where ec.exam_id=? order by c.name''', (exam_id,))
    class_ids = [row['id'] for row in classes]
    if not class_ids:
        return None
    marks = ','.join('?' for _ in class_ids)
    students = qa(f'''select s.* from students s where s.class_id in ({marks})
                      order by s.reg_no''', class_ids)
    questions = qa('select * from questions where subject_id=? order by id', (exam['subject_id'],))
    revision_hash = _android_exam_revision_hash(db(), exam_id)
    ex('update exams set sync_revision_hash=? where id=?', (revision_hash, exam_id))
    exam['sync_revision_hash'] = revision_hash
    class_uuid_by_id = {row['id']: row['sync_uuid'] for row in classes}
    package = {
        'schema_version': 1,
        'school_name': getset('school_name'),
        'exported_at': int(time.time()),
        'subject': {'sync_uuid': subject['sync_uuid'], 'name': subject['name']},
        'classes': [{'sync_uuid': row['sync_uuid'], 'name': row['name']} for row in classes],
        'students': [{'sync_uuid': row['sync_uuid'], 'reg_no': row['reg_no'], 'name': row['name'],
                      'class_sync_uuid': class_uuid_by_id.get(row['class_id'], ''),
                      'access_code': row['access_code']} for row in students],
        'questions': [{key: row.get(key) for key in ('sync_uuid','text','a','b','c','d','answer','marks','topic',
                      'difficulty','question_type','answer_text','accepted_answers','keywords','answer_space',
                      'marking_mode')} | {'subject_sync_uuid': subject['sync_uuid']} for row in questions],
        'exam': {key: exam.get(key) for key in ('sync_uuid','title','duration_min','num_questions','shuffle',
                 'show_score','pass_mark','instructions','objective_count','theory_count','camera_policy','sync_revision_hash')},
        'class_sync_uuids': [row['sync_uuid'] for row in classes],
    }
    roster = [{'sync_uuid': row['sync_uuid'], 'reg_no': row['reg_no'], 'name': row['name'],
               'class_sync_uuid': class_uuid_by_id.get(row['class_id'], ''),
               'access_code': row['access_code']} for row in students]
    roster_json = json.dumps(roster, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    package['roster_revision_hash'] = hashlib.sha256(roster_json.encode('utf-8')).hexdigest()
    return package


@app.post('/api/android-host/sync-pull')
def android_host_sync_pull():
    if not request.is_secure and request.remote_addr not in ('127.0.0.1', '::1', 'localhost'):
        return err('Android Host synchronisation requires HTTPS.', 400)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict) or len(request.get_data(cache=True) or b'') > 128 * 1024:
        return err('Invalid Android Host sync request.', 400)
    device = _android_device_from_request()
    if not device:
        return err('Android Host device is not paired or has been revoked.', 401)
    known = payload.get('known_revisions') or {}
    if not isinstance(known, dict) or len(known) > 5000:
        return err('Invalid known examination revision list.', 400)
    rows = qa('''select id,sync_uuid from exams
                 where android_host_sync_enabled=1 and sync_uuid is not null
                 order by id desc limit 50''')
    packages = []
    more_available = False
    max_response_bytes = 18 * 1024 * 1024
    for row in rows:
        package = _build_android_host_package(row['id'])
        if not package:
            continue
        exam = package['exam']
        revision_token = exam['sync_revision_hash'] + '.' + package['roster_revision_hash']
        if known.get(exam['sync_uuid']) == revision_token:
            continue
        candidate = packages + [package]
        encoded_size = len(json.dumps(candidate, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        if encoded_size > max_response_bytes:
            if not packages:
                return err('An approved examination package is larger than the automatic sync limit. Reduce its candidate/question package size or use the secure manual transfer.', 413)
            more_available = True
            break
        packages.append(package)
    return jsonify(ok=True, school=getset('school_name'), packages=packages,
                   more_available=more_available)

def _record_android_sync_conflict(payload, device_id, reason):
    try:
        attempt_uuid = str(uuid.UUID(str(payload.get('attempt_uuid') or '')))
    except (ValueError, TypeError, AttributeError):
        attempt_uuid = str(uuid.uuid4())
    safe_payload = json.dumps(payload, ensure_ascii=False)[:5 * 1024 * 1024]
    ex('''insert or ignore into android_sync_conflicts
        (attempt_uuid,device_id,exam_sync_uuid,student_sync_uuid,reason,payload,created_ts)
        values(?,?,?,?,?,?,?)''',
       (attempt_uuid, device_id, str(payload.get('exam_sync_uuid') or '')[:80],
        str(payload.get('student_sync_uuid') or '')[:80], reason[:500], safe_payload, int(time.time())))


@app.post('/api/android-host/sync-results')
def android_host_sync_results():
    if not request.is_secure and request.remote_addr not in ('127.0.0.1', '::1', 'localhost'):
        return err('Android Host synchronisation requires HTTPS.', 400)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return err('Invalid result synchronisation payload.')
    if len(request.get_data(cache=True) or b'') > 5 * 1024 * 1024:
        return err('Result package is larger than the 5 MB limit.', 413)
    device = _android_device_from_request()
    if not device:
        return err('Android Host device is not paired or has been revoked.', 401)
    try:
        attempt_uuid = str(uuid.UUID(str(payload.get('attempt_uuid') or '')))
    except (ValueError, TypeError, AttributeError):
        return err('Invalid attempt identity.')
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    prior = q1('select session_id,payload_hash from android_sync_receipts where attempt_uuid=?', (attempt_uuid,))
    if prior:
        if not hmac.compare_digest(prior['payload_hash'], payload_hash):
            _record_android_sync_conflict(payload, device['device_id'], 'A previously synchronised attempt was resent with different content.')
            return err('This attempt was already synchronised with different content. Admin review is required.', 409)
        row = q1('select score,total,status from sessions where id=?', (prior['session_id'],))
        return jsonify(ok=True, duplicate=True, synced=True, session_id=prior['session_id'],
                       score=row['score'], total=row['total'])
    exam_uuid = str(payload.get('exam_sync_uuid') or '')
    student_uuid = str(payload.get('student_sync_uuid') or '')
    exam = q1('select * from exams where sync_uuid=?', (exam_uuid,))
    student = q1('select * from students where sync_uuid=?', (student_uuid,))
    if not exam or not student:
        _record_android_sync_conflict(payload, device['device_id'], 'Exam or candidate identity is not present on the Windows Server. Import the matching exam package and retry.')
        return err('Exam or candidate is not recognised by the Windows Server. Import the matching host package, then retry.', 409)
    supplied_revision = str(payload.get('exam_revision_hash') or '')
    current_revision = _android_exam_revision_hash(db(), exam['id'])
    if not re.fullmatch(r'[a-f0-9]{64}', supplied_revision) or not hmac.compare_digest(current_revision, supplied_revision):
        _record_android_sync_conflict(payload, device['device_id'], 'The Windows Server exam content has changed since the Android Host package was exported. Re-export and review the exam before syncing this attempt.')
        return err('Exam revision mismatch. Admin review is required; this result was not imported.', 409)
    if not q1('select 1 from exam_classes where exam_id=? and class_id=?', (exam['id'], student['class_id'])):
        _record_android_sync_conflict(payload, device['device_id'], 'Candidate is not assigned to the synchronised examination.')
        return err('Candidate is not assigned to this examination. Admin review is required.', 409)
    if exam['status'] == 'draft':
        _record_android_sync_conflict(payload, device['device_id'], 'The matching Windows Server examination is still Draft.')
        return err('The matching Windows Server examination is still Draft. Open it on the school server before syncing results.', 409)
    existing = q1('select id,status,attempt_uuid from sessions where exam_id=? and student_id=?',
                  (exam['id'], student['id']))
    if existing:
        if existing.get('attempt_uuid') == attempt_uuid and existing['status'] == 'submitted':
            return jsonify(ok=True, duplicate=True, synced=True, session_id=existing['id'])
        _record_android_sync_conflict(payload, device['device_id'], 'A different attempt already exists for this candidate and examination on the Windows Server.')
        return err('A result already exists for this candidate and examination on the Windows Server. Admin review is required.', 409)
    questions = payload.get('questions')
    answers = payload.get('answers')
    if not isinstance(questions, list) or not isinstance(answers, list) or not questions:
        return err('The result package is missing its question list or answers.')
    if len(questions) != int(exam['num_questions']) or len(questions) > 500:
        return err('The submitted question count does not match the Windows Server examination.', 409)
    c = db()
    try:
        central_questions = {}
        for item in questions:
            if not isinstance(item, dict) or not item.get('question_sync_uuid'):
                raise ValueError('Invalid question identity in result package.')
            q = c.execute('select id,question_type from questions where sync_uuid=? and subject_id=?',
                          (item['question_sync_uuid'], exam['subject_id'])).fetchone()
            if not q or item['question_sync_uuid'] in central_questions:
                raise ValueError('Question identity is missing, duplicated or belongs to another subject.')
            central_questions[item['question_sync_uuid']] = q
        start_ts = int(payload.get('start_ts') or time.time())
        start_ts = max(0, min(start_ts, int(time.time()) + 300))
        sid = c.execute('''insert into sessions(exam_id,student_id,device,start_ts,last_seen,status,attempt_uuid)
                           values(?,?,?,?,?,'in_progress',?)''',
                        (exam['id'], student['id'], 'android-host:' + device['device_id'],
                         start_ts, int(time.time()), attempt_uuid)).lastrowid
        seen_positions = set()
        for item in questions:
            qid = central_questions[item['question_sync_uuid']]['id']
            pos = int(item.get('pos') or 0)
            opt_order = str(item.get('opt_order') or '')[:4]
            if pos < 1 or pos > len(questions) or pos in seen_positions:
                raise ValueError('Invalid or duplicated question order.')
            seen_positions.add(pos)
            c.execute('insert into session_questions(session_id,pos,question_id,opt_order) values(?,?,?,?)',
                      (sid, pos, qid, opt_order))
        seen_answers = set()
        for item in answers:
            if not isinstance(item, dict) or item.get('question_sync_uuid') not in central_questions:
                raise ValueError('Answer references a question outside this attempt.')
            key = item['question_sync_uuid']
            if key in seen_answers:
                raise ValueError('Duplicate answer record.')
            seen_answers.add(key)
            qtype = central_questions[key]['question_type']
            choice = str(item.get('choice') or '').upper()
            if qtype != 'theory' and choice not in ('', 'A', 'B', 'C', 'D'):
                raise ValueError('Invalid objective answer choice.')
            if qtype == 'theory':
                choice = ''
            response_text = str(item.get('response_text') or '')[:30000]
            response_drawing = str(item.get('response_drawing') or '')[:100000]
            c.execute('''insert into answers(session_id,question_id,choice,response_text,response_drawing,flagged,ts)
                         values(?,?,?,?,?,?,?)''',
                      (sid, central_questions[key]['id'], choice, response_text, response_drawing,
                       1 if item.get('flagged') else 0, int(time.time())))
        allowed_events = {'camera_declined','camera_permission_denied','camera_started','camera_unavailable',
                          'camera_interrupted','camera_stopped','page_hidden','page_visible',
                          'fullscreen_exited','preflight_passed','preflight_failed'}
        for event in payload.get('proctor_events', [])[:1000]:
            if not isinstance(event, dict) or event.get('event_type') not in allowed_events:
                continue
            request_id = str(event.get('request_id') or uuid.uuid4())[:80]
            c.execute('''insert or ignore into proctor_events
                (session_id,request_id,event_type,server_ts,client_ts,details)
                values(?,?,?,?,?,?)''',
                (sid, request_id, event['event_type'], int(time.time()), 0,
                 json.dumps({'source_device': device['device_id']})[:2000]))
        c.commit()
        finalize(c, sid)
        score = c.execute('select score,total,status from sessions where id=?', (sid,)).fetchone()
        c.execute('''insert into android_sync_receipts(attempt_uuid,device_id,session_id,payload_hash,synced_ts)
                     values(?,?,?,?,?)''',
                  (attempt_uuid, device['device_id'], sid, payload_hash, int(time.time())))
        c.commit()
    except (ValueError, TypeError, KeyError, sqlite3.IntegrityError) as exc:
        c.rollback()
        _record_android_sync_conflict(payload, device['device_id'], str(exc))
        return err('Result package rejected: ' + str(exc)[:250], 409)
    audit(f'Android Host result synchronised for session #{sid}')
    return jsonify(ok=True, synced=True, session_id=sid, score=score['score'], total=score['total'],
                   status=score['status'], scoring='recomputed_on_windows_server')


@app.get('/api/admin/android-host/status')
@admin
def android_host_sync_status():
    devices = qa('''select device_id,label,created_ts,last_seen,revoked_ts
                    from android_host_devices order by created_ts desc''')
    receipts = q1('select count(*) n,max(synced_ts) last_sync from android_sync_receipts') or {'n': 0, 'last_sync': 0}
    conflicts = qa('''select id,attempt_uuid,device_id,exam_sync_uuid,student_sync_uuid,reason,
                      created_ts,review_state,review_note,reviewed_by,reviewed_ts from android_sync_conflicts order by created_ts desc limit 200''')
    return jsonify(devices=devices, synced_count=receipts['n'], last_sync=receipts['last_sync'],
                   conflicts=conflicts)


@app.post('/api/admin/android-host/devices/<device_id>/revoke')
@admin
def android_host_revoke_device(device_id):
    row = q1('select device_id from android_host_devices where device_id=?', (device_id,))
    if not row:
        return err('Device not found', 404)
    ex('update android_host_devices set revoked_ts=? where device_id=?', (int(time.time()), device_id))
    audit(f'Revoked Android Host device {device_id}')
    return jsonify(ok=True)


@app.post('/api/admin/android-host/conflicts/<int:conflict_id>/review')
@admin
def android_host_review_conflict(conflict_id):
    d = request.get_json(silent=True) or {}
    state = d.get('review_state')
    if state not in ('Unreviewed', 'Reviewed', 'Needs follow-up', 'Resolved'):
        return err('Invalid conflict review state.')
    note = str(d.get('review_note') or '')[:2000]
    if not q1('select id from android_sync_conflicts where id=?', (conflict_id,)):
        return err('Sync conflict not found.', 404)
    ex('update android_sync_conflicts set review_state=?,reviewed_by=?,reviewed_ts=?,review_note=? where id=?',
       (state, session.get('admin', 'Admin'), int(time.time()), note, conflict_id))
    audit(f'Android sync conflict #{conflict_id} reviewed: {state}')
    return jsonify(ok=True)


@app.post('/api/admin/exams/<int:i>/proctor-policy')
@admin
def exam_proctor_policy(i):
    policy = (request.get_json(silent=True) or {}).get('camera_policy')
    if policy not in ('off', 'optional', 'required'):
        return err('Proctor Mode must be off, optional or required')
    if not q1('select id from exams where id=?', (i,)):
        return err('Exam not found', 404)
    if q1('select 1 from sessions where exam_id=? limit 1', (i,)):
        return err('Proctor policy is locked after the first student attempt has been created.', 409)
    ex('update exams set camera_policy=? where id=?', (policy, i))
    audit(f'Exam #{i} Proctor Mode set to {policy}')
    return jsonify(ok=True, camera_policy=policy)


@app.get('/api/admin/proctor/<int:eid>')
@admin
def proctor_events(eid):
    exam = q1('select id,title,camera_policy from exams where id=?', (eid,))
    if not exam:
        return err('Exam not found', 404)
    rows = qa('''select pe.id,pe.session_id,pe.event_type,pe.server_ts,pe.client_ts,pe.details,
        pe.review_state,pe.reviewed_by,pe.reviewed_ts,pe.review_note,
        st.name student,st.reg_no,s.status session_status
        from proctor_events pe join sessions s on s.id=pe.session_id
        join students st on st.id=s.student_id where s.exam_id=?
        order by pe.server_ts desc,pe.id desc limit 500''', (eid,))
    for row in rows:
        try: row['details'] = json.loads(row['details'] or '{}')
        except (TypeError, ValueError): row['details'] = {}
    return jsonify(exam=exam, rows=rows)


@app.post('/api/admin/proctor/events/<int:event_id>/review')
@admin
def proctor_event_review(event_id):
    d = request.get_json(silent=True) or {}
    state = d.get('review_state')
    if state not in ('Unreviewed', 'Reviewed - no concern', 'Needs follow-up'):
        return err('Invalid review state')
    note = str(d.get('review_note') or '').strip()[:2000]
    event = q1('select id,session_id from proctor_events where id=?', (event_id,))
    if not event:
        return err('Proctor event not found', 404)
    ex('update proctor_events set review_state=?,reviewed_by=?,reviewed_ts=?,review_note=? where id=?',
       (state, session.get('admin', 'Admin'), int(time.time()), note, event_id))
    audit(f'Proctor event #{event_id} reviewed: {state}')
    return jsonify(ok=True)


def _android_exam_revision_hash(conn, exam_id):
    """Canonical digest of all exam settings, assigned classes and marking content."""
    exam = conn.execute(
        """SELECT e.sync_uuid,e.title,e.duration_min,e.num_questions,e.shuffle,e.show_score,
                  e.pass_mark,e.instructions,e.objective_count,e.theory_count,e.camera_policy,
                  s.sync_uuid subject_sync_uuid
           FROM exams e JOIN subjects s ON s.id=e.subject_id WHERE e.id=?""",
        (exam_id,),
    ).fetchone()
    if not exam:
        raise ValueError("Examination not found for revision check.")
    classes = conn.execute(
        """SELECT c.sync_uuid FROM classes c JOIN exam_classes ec ON ec.class_id=c.id
           WHERE ec.exam_id=? ORDER BY c.sync_uuid""", (exam_id,)
    ).fetchall()
    questions = conn.execute(
        """SELECT sync_uuid,text,a,b,c,d,answer,marks,topic,difficulty,question_type,
                  answer_text,accepted_answers,keywords,answer_space,marking_mode
           FROM questions WHERE subject_id=(SELECT subject_id FROM exams WHERE id=?)
           ORDER BY sync_uuid""", (exam_id,)
    ).fetchall()
    exam_data = dict(exam)
    exam_data["shuffle"] = int(bool(exam_data.get("shuffle", 1)))
    exam_data["show_score"] = int(bool(exam_data.get("show_score", 0)))
    exam_data["pass_mark"] = float(exam_data.get("pass_mark") or 50)
    exam_data["instructions"] = str(exam_data.get("instructions") or "")
    exam_data["objective_count"] = int(exam_data.get("objective_count") or 0)
    exam_data["theory_count"] = int(exam_data.get("theory_count") or 0)
    exam_data["camera_policy"] = exam_data.get("camera_policy") or "off"
    question_data = []
    for row in questions:
        item = dict(row)
        for key in ("text", "a", "b", "c", "d", "answer", "topic", "difficulty",
                    "answer_text", "accepted_answers", "keywords"):
            item[key] = item.get(key) or ""
        item["marks"] = float(item.get("marks") or 1)
        item["question_type"] = item.get("question_type") or "objective"
        item["answer_space"] = item.get("answer_space") or "medium"
        item["marking_mode"] = item.get("marking_mode") or "exact"
        question_data.append(item)
    canonical = {
        "exam": exam_data,
        "classes": [row["sync_uuid"] for row in classes],
        "questions": question_data,
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@app.get('/api/admin/remote-host/package/<int:exam_id>')
@admin
def remote_host_package_export(exam_id):
    """Export one assigned exam and its minimum candidate/question data for a phone host."""
    exam = q1('select * from exams where id=?', (exam_id,))
    if not exam:
        return err('Exam not found', 404)
    subject = q1('select * from subjects where id=?', (exam['subject_id'],))
    classes = qa('''select c.* from classes c join exam_classes ec on ec.class_id=c.id
                    where ec.exam_id=? order by c.name''', (exam_id,))
    class_ids = [c['id'] for c in classes]
    if not class_ids:
        return err('This examination has no assigned classes.')
    marks = ','.join('?' for _ in class_ids)
    students = qa(f'''select s.* from students s where s.class_id in ({marks})
                      order by s.reg_no''', class_ids)
    questions = qa('select * from questions where subject_id=? order by id', (exam['subject_id'],))
    revision_hash = _android_exam_revision_hash(db(), exam_id)
    ex('update exams set sync_revision_hash=? where id=?', (revision_hash, exam_id))
    exam['sync_revision_hash'] = revision_hash
    class_uuid_by_id = {c['id']: c['sync_uuid'] for c in classes}
    package = {
        'schema_version': 1,
        'school_name': getset('school_name'),
        'exported_at': int(time.time()),
        'subject': {'sync_uuid': subject['sync_uuid'], 'name': subject['name']},
        'classes': [{'sync_uuid': c['sync_uuid'], 'name': c['name']} for c in classes],
        'students': [{'sync_uuid': st['sync_uuid'], 'reg_no': st['reg_no'], 'name': st['name'],
                      'class_sync_uuid': class_uuid_by_id.get(st['class_id'], ''),
                      'access_code': st['access_code']} for st in students],
        'questions': [{k: q.get(k) for k in ('sync_uuid','text','a','b','c','d','answer','marks','topic',
                      'difficulty','question_type','answer_text','accepted_answers','keywords','answer_space',
                      'marking_mode')} | {'subject_sync_uuid': subject['sync_uuid']} for q in questions],
        'exam': {k: exam.get(k) for k in ('sync_uuid','title','duration_min','num_questions','shuffle',
                 'show_score','pass_mark','instructions','objective_count','theory_count','camera_policy','sync_revision_hash')},
        'class_sync_uuids': [c['sync_uuid'] for c in classes],
    }
    response = jsonify(package)
    response.headers['Content-Disposition'] = 'attachment; filename="gtmc-android-host-exam.json"'
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.post('/api/admin/remote-host/package/import')
@admin
def remote_host_package_import():
    package = request.get_json(silent=True)
    if not isinstance(package, dict) or package.get('schema_version') != 1:
        return err('Unsupported or invalid Android Host exam package.')
    if len(request.get_data(cache=True) or b'') > 20 * 1024 * 1024:
        return err('Exam package is larger than the 20 MB import limit.', 413)
    exam_data, subject_data = package.get('exam'), package.get('subject')
    classes_data, students_data = package.get('classes'), package.get('students')
    questions_data = package.get('questions')
    if not isinstance(exam_data, dict) or not isinstance(subject_data, dict):
        return err('Package is missing its exam or subject.')
    if not all(isinstance(v, list) for v in (classes_data, students_data, questions_data)):
        return err('Package class, student and question lists are invalid.')
    if not exam_data.get('sync_uuid') or not subject_data.get('sync_uuid') or not exam_data.get('title') or not re.fullmatch(r'[a-f0-9]{64}', str(exam_data.get('sync_revision_hash') or '')):
        return err('Package is missing stable exam or subject identity.')
    if exam_data.get('camera_policy', 'off') not in ('off', 'optional', 'required'):
        return err('Package contains an invalid Proctor Mode policy.')
    c = db()
    try:
        subject = c.execute('select id,name from subjects where sync_uuid=?', (subject_data['sync_uuid'],)).fetchone()
        if not subject:
            subject = c.execute('select id,name,sync_uuid from subjects where lower(name)=lower(?)',
                                (subject_data['name'],)).fetchone()
            if subject and subject['sync_uuid'] not in (None, '', subject_data['sync_uuid']):
                raise ValueError('A subject with the same name has a different school identity.')
            if subject:
                c.execute('update subjects set sync_uuid=? where id=?', (subject_data['sync_uuid'], subject['id']))
                subject_id = subject['id']
            else:
                subject_id = c.execute('insert into subjects(name,sync_uuid) values(?,?)',
                                       (subject_data['name'], subject_data['sync_uuid'])).lastrowid
        else:
            subject_id = subject['id']

        class_ids = {}
        for item in classes_data:
            if not isinstance(item, dict) or not item.get('sync_uuid') or not item.get('name'):
                raise ValueError('Package contains an invalid class record.')
            row = c.execute('select id from classes where sync_uuid=?', (item['sync_uuid'],)).fetchone()
            if not row:
                row = c.execute('select id,sync_uuid from classes where lower(name)=lower(?)',
                                (item['name'],)).fetchone()
                if row and row['sync_uuid'] not in (None, '', item['sync_uuid']):
                    raise ValueError('A class with the same name has a different school identity.')
                if row:
                    c.execute('update classes set sync_uuid=? where id=?', (item['sync_uuid'], row['id']))
                    local_id = row['id']
                else:
                    local_id = c.execute('insert into classes(name,sync_uuid) values(?,?)',
                                         (item['name'], item['sync_uuid'])).lastrowid
            else:
                local_id = row['id']
            class_ids[item['sync_uuid']] = local_id

        for item in students_data:
            if not isinstance(item, dict) or not item.get('sync_uuid') or not item.get('reg_no') or not item.get('access_code'):
                raise ValueError('Package contains an invalid candidate record.')
            local_class = class_ids.get(item.get('class_sync_uuid'))
            if not local_class:
                raise ValueError('A candidate references a class not included in the package.')
            row = c.execute('select id,sync_uuid from students where sync_uuid=?',
                            (item['sync_uuid'],)).fetchone()
            if not row:
                row = c.execute('select id,sync_uuid from students where lower(reg_no)=lower(?)',
                                (item['reg_no'],)).fetchone()
                if row and row['sync_uuid'] not in (None, '', item['sync_uuid']):
                    raise ValueError('A candidate registration number belongs to a different school identity.')
            if row:
                c.execute('update students set sync_uuid=?,name=?,class_id=?,access_code=? where id=?',
                          (item['sync_uuid'], item['name'], local_class, item['access_code'], row['id']))
            else:
                c.execute('insert into students(reg_no,name,class_id,access_code,sync_uuid) values(?,?,?,?,?)',
                          (item['reg_no'], item['name'], local_class, item['access_code'], item['sync_uuid']))

        for item in questions_data:
            if not isinstance(item, dict) or not item.get('sync_uuid') or not item.get('text'):
                raise ValueError('Package contains an invalid question record.')
            if item.get('subject_sync_uuid') != subject_data['sync_uuid']:
                raise ValueError('A question belongs to a different subject.')
            row = c.execute('select id from questions where sync_uuid=?', (item['sync_uuid'],)).fetchone()
            values = (subject_id, item['text'], item.get('a') or '', item.get('b') or '',
                      item.get('c') or '', item.get('d') or '', item.get('answer') or '',
                      float(item.get('marks') or 1), item.get('topic') or '', item.get('difficulty') or '',
                      item.get('question_type') or 'objective', item.get('answer_text') or '',
                      item.get('accepted_answers') or '[]', item.get('keywords') or '[]',
                      item.get('answer_space') or 'medium', item.get('marking_mode') or 'exact')
            if row:
                c.execute('''update questions set subject_id=?,text=?,a=?,b=?,c=?,d=?,answer=?,marks=?,
                    topic=?,difficulty=?,question_type=?,answer_text=?,accepted_answers=?,keywords=?,
                    answer_space=?,marking_mode=? where id=?''', values + (row['id'],))
            else:
                same = c.execute('select id,sync_uuid from questions where subject_id=? and text=?',
                                 (subject_id, item['text'])).fetchone()
                if same and same['sync_uuid'] not in (None, '', item['sync_uuid']):
                    raise ValueError('A question with identical wording has a different school identity.')
                if same:
                    c.execute('update questions set sync_uuid=? where id=?', (item['sync_uuid'], same['id']))
                else:
                    c.execute('''insert into questions(subject_id,text,a,b,c,d,answer,marks,topic,difficulty,
                        question_type,answer_text,accepted_answers,keywords,answer_space,marking_mode,sync_uuid)
                        values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', values + (item['sync_uuid'],))

        existing_exam = c.execute('select id from exams where sync_uuid=?', (exam_data['sync_uuid'],)).fetchone()
        if existing_exam:
            if c.execute('select 1 from sessions where exam_id=? limit 1', (existing_exam['id'],)).fetchone():
                raise ValueError('This exam package has already been used for a student attempt and cannot overwrite it.')
            exam_id = existing_exam['id']
            c.execute('''update exams set title=?,subject_id=?,duration_min=?,num_questions=?,shuffle=?,
                show_score=?,pass_mark=?,instructions=?,objective_count=?,theory_count=?,camera_policy=?,sync_revision_hash=?,status='draft'
                where id=?''',
                (exam_data['title'], subject_id, int(exam_data['duration_min']), int(exam_data['num_questions']),
                 int(bool(exam_data.get('shuffle', 1))), int(bool(exam_data.get('show_score', 0))),
                 float(exam_data.get('pass_mark', 50)), str(exam_data.get('instructions') or ''),
                 int(exam_data.get('objective_count') or 0), int(exam_data.get('theory_count') or 0),
                 exam_data.get('camera_policy', 'off'), exam_data['sync_revision_hash'], exam_id))
            c.execute('delete from exam_classes where exam_id=?', (exam_id,))
        else:
            exam_id = c.execute('''insert into exams(title,subject_id,duration_min,num_questions,shuffle,show_score,
                pass_mark,instructions,status,created_ts,objective_count,theory_count,camera_policy,sync_uuid,sync_revision_hash)
                values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (exam_data['title'], subject_id, int(exam_data['duration_min']), int(exam_data['num_questions']),
                 int(bool(exam_data.get('shuffle', 1))), int(bool(exam_data.get('show_score', 0))),
                 float(exam_data.get('pass_mark', 50)), str(exam_data.get('instructions') or ''), 'draft',
                 int(time.time()), int(exam_data.get('objective_count') or 0), int(exam_data.get('theory_count') or 0),
                 exam_data.get('camera_policy', 'off'), exam_data['sync_uuid'], exam_data['sync_revision_hash'])).lastrowid
        # Only exams explicitly imported from the Windows Server are eligible for automatic result sync.
        c.execute('update exams set android_host_sync_enabled=1 where id=?', (exam_id,))
        for class_uuid in package.get('class_sync_uuids', []):
            if class_uuid not in class_ids:
                raise ValueError('Package references an unknown exam class.')
            c.execute('insert or ignore into exam_classes(exam_id,class_id) values(?,?)',
                      (exam_id, class_ids[class_uuid]))
        c.commit()
    except (ValueError, TypeError, KeyError, sqlite3.IntegrityError) as exc:
        c.rollback()
        return err(str(exc)[:300], 409)
    audit(f'Imported Android Host package for exam #{exam_id}; candidate and question records synchronised')
    return jsonify(ok=True, exam_id=exam_id, imported_students=len(students_data),
                   imported_questions=len(questions_data), status='draft',
                   message='Package imported. Review the exam and open it when ready.')


def finalize(c, sid):
    s = c.execute('select status from sessions where id=?', (sid,)).fetchone()
    if not s or s['status'] == 'submitted':
        return
    rows = c.execute('''select q.id,q.question_type,q.answer,q.answer_text,q.accepted_answers,q.keywords,
        q.marking_mode,q.marks,a.choice,a.response_text
        from session_questions sq join questions q on q.id=sq.question_id
        left join answers a on a.session_id=sq.session_id and a.question_id=sq.question_id
        where sq.session_id=?''', (sid,)).fetchall()
    score = total = 0.0
    for q in rows:
        marks = float(q['marks'] or 0); total += marks
        response = (q['response_text'] or '').strip()
        if q['question_type'] != 'theory':
            if q['choice'] == q['answer']:
                score += marks
            continue
        mode = q['marking_mode'] or 'manual'
        if mode == 'exact':
            if response.casefold().strip() == (q['answer_text'] or '').casefold().strip():
                score += marks
        elif mode == 'multiple':
            try:
                accepted = json.loads(q['accepted_answers'] or '[]')
            except ValueError:
                accepted = []
            accepted = [str(x).strip().casefold() for x in accepted]
            accepted.append((q['answer_text'] or '').strip().casefold())
            if response.casefold().strip() in accepted and response:
                score += marks
        elif mode == 'keyword':
            try:
                words = json.loads(q['keywords'] or '[]')
            except ValueError:
                words = []
            hits = sum(1 for word in words if str(word).casefold() in response.casefold())
            if words:
                score += marks * hits / len(words)
        # Manual marking is intentionally left at zero until a teacher awards marks.
    c.execute("update sessions set status='submitted', submitted_ts=?, score=?, total=? where id=?",
              (int(time.time()), round(score, 2), round(total, 2), sid))
    c.commit()


@app.post('/api/admin/exams/<int:i>/status')
@admin
def exam_status(i):
    st = (request.get_json() or {}).get('status')
    if st not in ('draft', 'live', 'paused', 'closed'):
        return err('Bad status')
    if st == 'paused':
        ex("update exams set status='paused' where id=?", (i,))
        ex("update sessions set paused_at=? where exam_id=? and status='in_progress' and paused_at=0", (int(time.time()), i))
    elif st == 'live':
        now = int(time.time())
        ex("update sessions set paused_total_sec=paused_total_sec+max(0,?-paused_at), paused_at=0 where exam_id=? and status='in_progress' and paused_at>0", (now, i))
        ex("update exams set status='live' where id=?", (i,))
    else:
        ex('update exams set status=? where id=?', (st, i))
        if st == 'closed':
            for r in qa("select id from sessions where exam_id=? and status='in_progress'", (i,)):
                finalize(db(), r['id'])
    audit(f'Exam #{i} set to {st}')
    return jsonify(ok=True)


@app.delete('/api/admin/exams/<int:i>')
@admin
def exam_delete(i):
    ex('delete from exams where id=?', (i,))
    audit(f'Deleted exam #{i}')
    return jsonify(ok=True)


@app.post('/api/admin/exams/<int:i>/extend')
@admin
def exam_extend(i):
    m = int((request.get_json() or {}).get('minutes', 0))
    ex("update sessions set extra_sec=extra_sec+? where exam_id=? and status='in_progress'", (m * 60, i))
    audit(f'Extended exam #{i} by {m} min for all')
    return jsonify(ok=True)


# ---------------------------------------------------------------- admin: live monitor & results
def time_left(s, dur_min):
    paused_at = int(s['paused_at'] or 0)
    now = paused_at if paused_at else int(time.time())
    paused_total = int(s['paused_total_sec'] or 0)
    elapsed = max(0, now - (s['start_ts'] or now) - paused_total)
    return max(0, int(dur_min * 60 + (s['extra_sec'] or 0) - elapsed))


def monitor_rows(eid):
    e = q1('select * from exams where id=?', (eid,))
    if not e:
        return None, []
    now = time.time()
    rows = qa('''select st.id sid, st.reg_no, st.name, c.name cls, s.id sess_id, s.status, s.start_ts, s.last_seen, s.extra_sec,
        s.tab_switches, s.score, s.total, s.paused_at,
        (select count(*) from session_questions where session_id=s.id) nq,
        (select count(*) from answers where session_id=s.id and (choice<>'' or response_text<>'' or (response_drawing<>'' and response_drawing<>'[]'))) na
        from students st join classes c on c.id=st.class_id
        join exam_classes ec on ec.class_id=st.class_id and ec.exam_id=?
        left join sessions s on s.student_id=st.id and s.exam_id=?
        order by c.name, st.name''', (eid, eid))
    for r in rows:
        if not r['sess_id']:
            r['state'] = 'not_started'
        elif r['status'] == 'submitted':
            r['state'] = 'submitted'
        else:
            r['state'] = 'paused' if e['status'] == 'paused' or (r['paused_at'] or 0) else ('writing' if now - (r['last_seen'] or 0) < 30 else 'offline')
            r['left'] = max(0, time_left(r, e['duration_min']))
    return e, rows


@app.get('/api/admin/monitor/<int:eid>')
@admin
def monitor(eid):
    e, rows = monitor_rows(eid)
    if not e:
        return err('Exam not found', 404)
    cnt = {k: sum(1 for r in rows if r['state'] == k) for k in ('not_started', 'writing', 'offline', 'paused', 'submitted')}
    return jsonify(exam=e, rows=rows, counts=cnt, total=len(rows))


@app.post('/api/admin/sessions/<int:sid>/action')
@admin
def session_action(sid):
    d = request.get_json() or {}
    act = d.get('action')
    if session.get('admin_role') == 'invigilator' and act not in ('pause', 'resume', 'extend'):
        return err('Invigilators may pause, resume or extend a candidate session, but cannot reset or force-submit it.', 403)
    session_row = q1('select s.*,e.status exam_status from sessions s join exams e on e.id=s.exam_id where s.id=?', (sid,))
    if not session_row:
        return err('Session not found', 404)
    if act == 'resume' and session_row['exam_status'] == 'paused':
        return err('Resume the whole examination first. Individual sessions cannot resume while the examination is paused.')
    if act == 'reset':
        ex('update sessions set token=NULL, device=NULL, last_seen=0 where id=?', (sid,))
    elif act == 'extend':
        ex('update sessions set extra_sec=extra_sec+? where id=?', (int(d.get('minutes', 0)) * 60, sid))
    elif act == 'pause':
        ex("update sessions set paused_at=? where id=? and status='in_progress' and paused_at=0", (int(time.time()), sid))
    elif act == 'resume':
        ex("update sessions set paused_total_sec=paused_total_sec+max(0,?-paused_at), paused_at=0 where id=? and paused_at>0", (int(time.time()), sid))
    elif act == 'submit':
        finalize(db(), sid)
    else:
        return err('Unknown action')
    audit(f'Session #{sid}: {act}')
    return jsonify(ok=True)


@app.get('/api/admin/theory/<int:eid>')
@admin
def theory_responses(eid):
    rows = qa('''select s.id session_id, st.name student, st.reg_no, c.name cls, q.id question_id,
        q.text question, q.marks max_marks, q.marking_mode, q.answer_text model_answer,
        a.response_text, a.response_drawing, tm.mark, tm.original_mark, tm.feedback, tm.marked_by
        from sessions s join students st on st.id=s.student_id join classes c on c.id=st.class_id
        join session_questions sq on sq.session_id=s.id join questions q on q.id=sq.question_id
        left join answers a on a.session_id=s.id and a.question_id=q.id
        left join theory_marks tm on tm.session_id=s.id and tm.question_id=q.id
        where s.exam_id=? and s.status='submitted' and q.question_type='theory'
        order by st.name,sq.pos''', (eid,))
    return jsonify(rows=rows)


@app.post('/api/admin/theory/mark')
@admin
def theory_mark():
    d = request.get_json() or {}
    try:
        sid, qid, mark = int(d.get('session_id')), int(d.get('question_id')), float(d.get('mark'))
    except (TypeError, ValueError):
        return err('Session, question and mark are required')
    q = q1('''select q.marks,q.marking_mode,q.answer_text,q.accepted_answers,q.keywords,
        a.response_text,s.exam_id from questions q
        join session_questions sq on sq.question_id=q.id
        join sessions s on s.id=sq.session_id
        left join answers a on a.session_id=s.id and a.question_id=q.id
        where s.id=? and q.id=? and q.question_type='theory' and s.status='submitted' ''', (sid,qid))
    if not q:
        return err('Submitted theory response not found', 404)
    if session.get('admin_role') == 'examiner' and not examiner_has_exam(session.get('admin'), q['exam_id']):
        return err('This examination has not been assigned to your marker account.', 403)
    if mark < 0 or mark > float(q['marks']):
        return err(f'Mark must be between 0 and {q["marks"]}')
    response = (q['response_text'] or '').strip()
    original_mark = 0.0
    if q['marking_mode'] == 'exact':
        original_mark = float(q['marks']) if response.casefold() == (q['answer_text'] or '').strip().casefold() else 0.0
    elif q['marking_mode'] == 'multiple':
        try: accepted = json.loads(q['accepted_answers'] or '[]')
        except ValueError: accepted = []
        accepted = [str(v).strip().casefold() for v in accepted] + [(q['answer_text'] or '').strip().casefold()]
        original_mark = float(q['marks']) if response.casefold() in accepted and response else 0.0
    elif q['marking_mode'] == 'keyword':
        try: words = json.loads(q['keywords'] or '[]')
        except ValueError: words = []
        hits = sum(1 for word in words if str(word).casefold() in response.casefold())
        original_mark = float(q['marks']) * hits / len(words) if words else 0.0
    ex('''insert into theory_marks(session_id,question_id,mark,original_mark,feedback,marked_by,marked_ts)
          values(?,?,?,?,?,?,?) on conflict(session_id,question_id) do update set
          mark=excluded.mark,original_mark=excluded.original_mark,feedback=excluded.feedback,
          marked_by=excluded.marked_by,marked_ts=excluded.marked_ts''',
       (sid,qid,mark,round(original_mark,2),str(d.get('feedback') or '')[:2000],session.get('admin','Admin'),int(time.time())))
    # Recalculate the complete result, retaining objective and automatic theory marks.
    rows = qa('''select q.id,q.question_type,q.answer,q.answer_text,q.accepted_answers,q.keywords,
        q.marking_mode,q.marks,a.choice,a.response_text,tm.mark manual_mark
        from session_questions sq join questions q on q.id=sq.question_id
        left join answers a on a.session_id=sq.session_id and a.question_id=q.id
        left join theory_marks tm on tm.session_id=sq.session_id and tm.question_id=q.id
        where sq.session_id=?''', (sid,))
    score = total = 0.0
    for item in rows:
        marks=float(item['marks'] or 0);total+=marks
        response=(item['response_text'] or '').strip()
        if item['question_type']!='theory':
            score += marks if item['choice']==item['answer'] else 0
        elif item['manual_mark'] is not None:
            score += float(item['manual_mark'])
        elif item['marking_mode']=='manual':
            score += 0
        elif item['marking_mode']=='exact':
            score += marks if response.casefold()==(item['answer_text'] or '').strip().casefold() else 0
        elif item['marking_mode']=='multiple':
            try: accepted=json.loads(item['accepted_answers'] or '[]')
            except ValueError: accepted=[]
            accepted=[str(v).strip().casefold() for v in accepted]+[(item['answer_text'] or '').strip().casefold()]
            score += marks if response.casefold() in accepted and response else 0
        elif item['marking_mode']=='keyword':
            try: words=json.loads(item['keywords'] or '[]')
            except ValueError: words=[]
            hits=sum(1 for word in words if str(word).casefold() in response.casefold())
            score += marks*hits/len(words) if words else 0
    ex('update sessions set score=?,total=? where id=?',(round(score,2),round(total,2),sid))
    audit(f'Marked theory question #{qid} for session #{sid}: {mark}/{q["marks"]}')
    return jsonify(ok=True,score=round(score,2),total=round(total,2))


def result_rows(eid):
    rows = qa('''select st.reg_no, st.name, c.name cls, s.status, s.score, s.total, s.tab_switches, s.start_ts, s.submitted_ts
        from sessions s join students st on st.id=s.student_id join classes c on c.id=st.class_id
        where s.exam_id=? and s.status='submitted' order by s.score desc, st.name''', (eid,))
    prev, rank = None, 0
    for i, r in enumerate(rows, 1):
        r['pct'] = round(r['score'] / r['total'] * 100, 1) if r['total'] else 0
        r['grade'] = grade(r['pct'])
        if r['score'] != prev:
            rank, prev = i, r['score']
        r['rank'] = rank
        r['mins'] = round(((r['submitted_ts'] or 0) - (r['start_ts'] or 0)) / 60, 1)
    return rows


@app.get('/api/admin/results/<int:eid>')
@admin
def results(eid):
    e = q1('select e.*, s.name subject from exams e join subjects s on s.id=e.subject_id where e.id=?', (eid,))
    if not e:
        return err('Exam not found', 404)
    rows = result_rows(eid)
    pcts = [r['pct'] for r in rows]
    dist = {g: sum(1 for r in rows if r['grade'] == g) for g in 'ABCDEF'}
    return jsonify(exam=e, rows=rows, dist=dist, count=len(rows),
                   avg=round(sum(pcts) / len(pcts), 1) if pcts else 0, high=max(pcts, default=0), low=min(pcts, default=0),
                   pass_rate=round(100 * sum(1 for p in pcts if p >= e['pass_mark']) / len(pcts), 1) if pcts else 0)


@app.get('/api/admin/export/results/<int:eid>')
@admin
def export_results(eid):
    e = q1('select e.*, s.name subject from exams e join subjects s on s.id=e.subject_id where e.id=?', (eid,))
    if not e:
        return err('Exam not found', 404)
    rows = result_rows(eid)
    body = [[r['rank'], r['reg_no'], r['name'], r['cls'], r['score'], r['total'], r['pct'], r['grade'],
             'PASS' if r['pct'] >= e['pass_mark'] else 'FAIL', r['tab_switches'], fmt_ts(r['start_ts']), r['mins']] for r in rows]
    pcts = [r['pct'] for r in rows]
    summary = [['School', getset('school_name')], ['Exam', e['title']], ['Subject', e['subject']], ['Candidates', len(rows)],
               ['Average %', round(sum(pcts) / len(pcts), 1) if pcts else 0], ['Highest %', max(pcts, default=0)],
               ['Lowest %', min(pcts, default=0)], ['Pass mark %', e['pass_mark']],
               ['Pass rate %', round(100 * sum(1 for p in pcts if p >= e['pass_mark']) / len(pcts), 1) if pcts else 0]]
    safe = re.sub(r'[^A-Za-z0-9_-]+', '_', e['title'])
    return xlsx_resp([('Results', ['Rank', 'RegNo', 'Name', 'Class', 'Score', 'Total', 'Percent', 'Grade', 'Remark', 'Tab switches', 'Started', 'Minutes used'], body),
                      ('Summary', ['Item', 'Value'], summary)], f'results_{safe}.xlsx')


@app.get('/api/admin/export/monitor/<int:eid>')
@admin
def export_monitor(eid):
    e, rows = monitor_rows(eid)
    if not e:
        return err('Exam not found', 404)
    body = [[r['reg_no'], r['name'], r['cls'], r['state'], f"{r['na'] or 0}/{r['nq'] or 0}", r['tab_switches'] or 0] for r in rows]
    return xlsx_resp([('Attendance', ['RegNo', 'Name', 'Class', 'Status', 'Answered', 'Tab switches'], body)], 'exam_attendance.xlsx')


# ---------------------------------------------------------------- admin: backup
def do_backup(tag='manual'):
    fn = f"cbt_{datetime.now():%Y%m%d_%H%M%S}_{tag}.db"
    src = raw()
    dst = sqlite3.connect(os.path.join(BK, fn))
    src.backup(dst)
    dst.close()
    src.close()
    autos = sorted(glob.glob(os.path.join(BK, '*_auto.db')))
    for old in autos[:-30]:
        os.remove(old)
    return fn


@app.get('/api/admin/backups')
@admin
def backups():
    fs = sorted(os.listdir(BK), reverse=True)
    return jsonify([dict(name=f, kb=os.path.getsize(os.path.join(BK, f)) // 1024) for f in fs if f.endswith('.db')])


@app.post('/api/admin/backups')
@admin
def backup_now():
    fn = do_backup('manual')
    audit(f'Backup created: {fn}')
    return jsonify(name=fn)


@app.get('/api/admin/backups/<name>')
@admin
def backup_dl(name):
    if not re.fullmatch(r'cbt_[0-9_]+_(manual|auto)(?:_pre_restore_[a-f0-9]{8})?\.db', name):
        return err('Bad name', 404)
    return send_from_directory(BK, name, as_attachment=True)


# ---------------------------------------------------------------- admin: student messaging
@app.get('/api/admin/messages')
@admin
def admin_messages():
    rows = qa("""select m.id,m.title,m.body,m.emergency,m.created_ts,m.read_ts,m.sender,
        st.name,st.reg_no,c.name cls,e.title exam_title
        from messages m join students st on st.id=m.student_id join classes c on c.id=st.class_id
        left join exams e on e.id=m.exam_id order by m.id desc limit 300""")
    return jsonify(rows=rows)


@app.post('/api/admin/messages')
@admin
def admin_send_message():
    d = request.get_json(silent=True) or {}
    title, body = (d.get('title') or '').strip(), (d.get('body') or '').strip()
    audience = d.get('audience') or 'all'
    if not title or not body or len(title) > 140 or len(body) > 3000:
        return err('Enter a title and message (maximum 3,000 characters).')
    exam_id = d.get('exam_id')
    if audience == 'student':
        ids = [r['id'] for r in qa('select id from students where id=?', (d.get('student_id'),))]
    elif audience == 'class':
        ids = [r['id'] for r in qa('select id from students where class_id=?', (d.get('class_id'),))]
    elif audience == 'exam':
        if not exam_id:
            return err('Choose an examination for this broadcast.')
        ids = [r['student_id'] for r in qa("select student_id from sessions where exam_id=? and status='in_progress'", (exam_id,))]
    else:
        ids = [r['id'] for r in qa('select id from students')]
    ids = list(dict.fromkeys(ids))
    if not ids:
        return err('No students matched this message.')
    now = int(time.time())
    db().executemany('insert into messages(student_id,exam_id,title,body,emergency,created_ts,sender) values(?,?,?,?,?,?,?)',
        [(sid, exam_id if audience == 'exam' else None, title, body, 1 if d.get('emergency') else 0, now, session.get('admin','Admin')) for sid in ids])
    db().commit()
    audit(f"Sent {'emergency ' if d.get('emergency') else ''}message to {len(ids)} students ({audience})")
    return jsonify(ok=True, recipients=len(ids))


@app.get('/api/admin/students/lookup')
@admin
def admin_student_lookup():
    q = (request.args.get('q') or '').strip()
    return jsonify(qa('select s.id,s.name,s.reg_no,c.name cls from students s join classes c on c.id=s.class_id where s.name like ? or s.reg_no like ? order by s.name limit 100', (f'%{q}%', f'%{q}%')))



# ---------------------------------------------------------------- student API
def student_by_creds(d):
    reg, code = (d.get('reg_no') or '').strip(), (d.get('code') or '').strip().upper()
    key = f'stu|{request.remote_addr}|{reg.lower()}'
    if throttled(key, 8):
        return None, err('Too many wrong attempts. Wait 5 minutes or ask the invigilator.', 429)
    school = school_context(db(), d.get('school_code'))
    if not school:
        add_fail(key)
        return None, err('Enter a valid School Code. A School Code is required when more than one school is registered.', 401)
    activate_tenant_views(db(), school['school_id'])
    st = q1('select s.*, c.name cls from students s join classes c on c.id=s.class_id where lower(s.reg_no)=lower(?) and s.school_id=?', (reg, school['school_id']))
    if not st or st['access_code'].upper() != code:
        add_fail(key)
        return None, err('Invalid registration number or access code', 401)
    return st, None


@app.post('/api/student/login')
def s_login():
    st, e = student_by_creds(request.get_json(silent=True) or {})
    if e:
        return e
    exams = qa('''select e.id, e.title, e.duration_min, e.num_questions, e.instructions, e.camera_policy, e.status exam_status, s.name subject, ses.status ses_status
        from exams e join subjects s on s.id=e.subject_id join exam_classes ec on ec.exam_id=e.id and ec.class_id=?
        left join sessions ses on ses.exam_id=e.id and ses.student_id=?
        where e.status='live' or (e.status='paused' and ses.id is not null) order by e.id''', (st['class_id'], st['id']))
    for x in exams:
        x['state'] = 'done' if x['ses_status'] == 'submitted' else 'resume' if x['ses_status'] else 'new'
    return jsonify(student=dict(name=st['name'], reg_no=st['reg_no'], cls=st['cls']), exams=exams)


@app.post('/api/student/inbox')
def student_inbox():
    st, error = student_by_creds(request.get_json(silent=True) or {})
    if error:
        return error
    rows = qa('select id,title,body,emergency,created_ts,sender from messages where student_id=? and read_ts=0 order by id', (st['id'],))
    return jsonify(rows=rows)


@app.post('/api/student/inbox/read')
def student_inbox_read():
    d = request.get_json(silent=True) or {}
    st, error = student_by_creds(d)
    if error:
        return error
    ids = d.get('ids') or []
    if ids:
        marks = ','.join('?' for _ in ids)
        db().execute(f'update messages set read_ts=? where student_id=? and id in ({marks})', [int(time.time()), st['id'], *ids])
        db().commit()
    return jsonify(ok=True)




@app.post('/api/student/grades')
def student_grades():
    st, error = student_by_creds(request.get_json(silent=True) or {})
    if error:
        return error
    rows = qa("""select e.title exam,s.score,s.total,s.submitted_ts,sub.name subject
        from sessions s join exams e on e.id=s.exam_id join subjects sub on sub.id=e.subject_id
        where s.student_id=? and s.status='submitted' and e.show_score=1
        and not exists (select 1 from session_questions sq join questions q on q.id=sq.question_id
          left join theory_marks tm on tm.session_id=sq.session_id and tm.question_id=q.id
          where sq.session_id=s.id and q.question_type='theory' and q.marking_mode='manual' and tm.mark is null)
        order by s.submitted_ts desc""", (st['id'],))
    for row in rows:
        row['percent'] = round(row['score'] / row['total'] * 100, 1) if row['total'] else 0
        row['grade'] = grade(row['percent'])
        row['submitted'] = fmt_ts(row['submitted_ts'])
    return jsonify(student=dict(name=st['name'], reg_no=st['reg_no']), rows=rows)



@app.post('/api/student/begin')
def s_begin():
    d = request.get_json(silent=True) or {}
    st, e = student_by_creds(d)
    if e:
        return e
    dev = (d.get('device') or '')[:64]
    exam = q1('''select e.* from exams e join exam_classes ec on ec.exam_id=e.id and ec.class_id=?
                 where e.id=? and e.status in ('live','paused') ''', (st['class_id'], d.get('exam_id')))
    if not exam:
        return err('This exam is not available. Ask the invigilator.')
    if exam['camera_policy'] == 'required' and d.get('camera_preflight') is not True:
        return err('This examination requires camera permission and a successful camera check before it can start.', 403)
    now = int(time.time())
    ses = q1('select * from sessions where exam_id=? and student_id=?', (exam['id'], st['id']))
    token = secrets.token_hex(16)
    if exam['status'] == 'paused' and not ses:
        return err('This examination is paused. Wait for the invigilator to resume it.', 409)
    if ses:
        if ses['status'] == 'submitted':
            return err('You have already submitted this exam.')
        if time_left(ses, exam['duration_min']) <= 0:
            finalize(db(), ses['id'])
            return err('Your time for this exam has ended.')
        if ses['device'] and ses['device'] != dev and now - (ses['last_seen'] or 0) < 30:
            return err('This account is active on another computer. Ask the invigilator to reset your login.', 409)
        ex('update sessions set token=?, device=?, last_seen=? where id=?', (token, dev, now, ses['id']))
    else:
        # Select unique question-bank IDs for this candidate's paper. A question
        # may appear again in another exam, but never twice in this exam session.
        question_rows = qa(
            'select id, text, question_type from questions where subject_id=? order by id', (exam['subject_id'],)
        )
        objective_required = int(exam['objective_count'] or 0)
        theory_required = int(exam['theory_count'] or 0)
        if objective_required + theory_required == 0:  # legacy exam created before theory support
            objective_required = int(exam['num_questions'])
        # Deduplicate wording across both sections so the same question cannot
        # appear twice even if copied into separate objective/theory records.
        seen_text, objective_pool, theory_pool = set(), [], []
        for row in question_rows:
            normalized_text = question_fingerprint(row['text'])
            if not normalized_text or normalized_text in seen_text:
                continue
            seen_text.add(normalized_text)
            (theory_pool if row['question_type'] == 'theory' else objective_pool).append(row['id'])
        if len(objective_pool) < objective_required or len(theory_pool) < theory_required:
            return err(
                f'Not enough unique questions for this paper. Required: {objective_required} objective '
                f'and {theory_required} theory; available: {len(objective_pool)} objective and '
                f'{len(theory_pool)} theory. Ask the administrator to add more different questions.',
                409
            )
        selected_ids = random.sample(objective_pool, objective_required) + random.sample(theory_pool, theory_required)
        if exam['shuffle']:
            random.shuffle(selected_ids)
        if not exam['shuffle']:
            selected_ids.sort()
        sid = db().execute('insert into sessions(exam_id,student_id,token,device,start_ts,last_seen,attempt_uuid) values(?,?,?,?,?,?,?)',
                           (exam['id'], st['id'], token, dev, now, now, str(uuid.uuid4()))).lastrowid
        for pos, qid in enumerate(selected_ids, 1):
            qrow = q1('select a,b,c,d from questions where id=?', (qid,))
            order = [k for k in 'ABCD' if qrow[k.lower()]]
            if exam['shuffle']:
                random.shuffle(order)
            db().execute('insert into session_questions values(?,?,?,?)', (sid, pos, qid, ''.join(order)))
        # Final integrity check before commit; rollback rather than issue a
        # paper if a duplicate somehow enters the session-question table.
        duplicate = q1(
            'select question_id from session_questions where session_id=? '
            'group by question_id having count(*)>1 limit 1', (sid,)
        )
        if duplicate:
            db().rollback()
            return err('The system detected a repeated question and stopped paper generation. Please contact the administrator.', 500)
        db().commit()
    return jsonify(token=token)


def final_info():
    s = q1('select score,total from sessions where id=?', (g.ses['id'],))
    pending_manual = q1('''select 1 from session_questions sq join questions q on q.id=sq.question_id
        left join theory_marks tm on tm.session_id=sq.session_id and tm.question_id=q.id
        where sq.session_id=? and q.question_type='theory' and q.marking_mode='manual' and tm.mark is null limit 1''',
        (g.ses['id'],))
    if g.exam['show_score'] and s and not pending_manual:
        pct = round(s['score'] / s['total'] * 100, 1) if s['total'] else 0
        return dict(score=s['score'], total=s['total'], pct=pct)
    return {}


def sauth(f):
    @wraps(f)
    def w(*a, **k):
        tok = request.headers.get('X-Token', '')
        s = q1("select * from sessions where token=? and token is not null and token<>''", (tok,)) if tok else None
        if not s:
            return err('Session expired. Please log in again.', 401)
        activate_tenant_views(db(), s['school_id'])
        s = q1("select * from sessions where token=? and token is not null and token<>''", (tok,))
        if not s:
            return err('Session expired. Please log in again.', 401)
        e = q1('select * from exams where id=?', (s['exam_id'],))
        g.ses, g.exam = s, e
        if s['status'] == 'submitted':
            return jsonify(done=True, **final_info())
        if e['status'] == 'paused' or (s['paused_at'] or 0):
            g.ses, g.exam = s, e
            st = q1('select name,reg_no from students where id=?', (s['student_id'],))
            return jsonify(paused=True, remaining=time_left(s, e['duration_min']), student=st, title=e['title'], exam_id=e['id'])
        if e['status'] != 'live' or time_left(s, e['duration_min']) <= 0:
            finalize(db(), s['id'])
            g.ses = q1('select * from sessions where id=?', (s['id'],))
            return jsonify(done=True, **final_info())
        ex('update sessions set last_seen=? where id=?', (int(time.time()), s['id']))
        return f(*a, **k)
    return w


@app.get('/api/student/paper')
@sauth
def s_paper():
    rows = qa('''select sq.pos, q.id, q.text, q.a, q.b, q.c, q.d, q.question_type,
        q.answer_space, q.marks, sq.opt_order from session_questions sq
        join questions q on q.id=sq.question_id where sq.session_id=? order by sq.pos''', (g.ses['id'],))
    qs = [dict(id=r['id'], pos=r['pos'], text=r['text'], type=r['question_type'] or 'objective',
               answer_space=r['answer_space'] or 'medium', marks=r['marks'],
               options=[dict(k=k, t=r[k.lower()]) for k in (r['opt_order'] or '') if r[k.lower()]]) for r in rows]
    ans = {r['question_id']: dict(choice=r['choice'], response_text=r['response_text'] or '',
             response_drawing=r['response_drawing'] or '', flagged=r['flagged'])
           for r in qa('select * from answers where session_id=?', (g.ses['id'],))}
    st = q1('select s.name,s.reg_no,c.name cls from students s join classes c on c.id=s.class_id where s.id=?', (g.ses['student_id'],))
    school_row = q1('SELECT name FROM schools WHERE school_id=?', (g.ses['school_id'],))
    if g.ses['school_id'] == getset('vicora_legacy_school_id', ''):
        school_name = getset('school_name') or 'VICORA CBT'
    else:
        school_name = (school_row['name'] if school_row else '') or 'VICORA CBT'
    return jsonify(title=g.exam['title'], exam_id=g.exam['id'], remaining=time_left(g.ses, g.exam['duration_min']), questions=qs, answers=ans,
                   student=st, school=school_name)


@app.post('/api/student/answer')
@sauth
def s_answer():
    d = request.get_json(silent=True) or {}
    qid, choice = d.get('qid'), (d.get('choice') or '').upper()
    response_text = str(d.get('response_text') or '')[:30000]
    response_drawing = str(d.get('response_drawing') or '')[:100000]
    q = q1('select q.question_type from session_questions sq join questions q on q.id=sq.question_id where sq.session_id=? and sq.question_id=?',
           (g.ses['id'], qid))
    if not q:
        return err('Bad question')
    if q['question_type'] != 'theory' and choice not in ('', 'A', 'B', 'C', 'D'):
        return err('Bad choice')
    if q['question_type'] == 'theory':
        choice = ''
    db().execute('DELETE FROM answers WHERE session_id=? AND question_id=?',
                 (g.ses['id'], qid))
    ex('''insert into answers(session_id,question_id,choice,response_text,response_drawing,flagged,ts)
          values(?,?,?,?,?,?,?)''',
       (g.ses['id'], qid, choice, response_text, response_drawing,
        1 if d.get('flagged') else 0, int(time.time())))
    return jsonify(ok=True, remaining=time_left(g.ses, g.exam['duration_min']))


@app.post('/api/student/heartbeat')
@sauth
def s_heartbeat():
    return jsonify(ok=True, remaining=time_left(g.ses, g.exam['duration_min']))


@app.post('/api/student/proctor-event')
@sauth
def s_proctor_event():
    if g.exam.get('camera_policy', 'off') == 'off':
        return err('Proctor Mode is off for this examination.', 409)
    d = request.get_json(silent=True) or {}
    event_type = str(d.get('event_type') or '')
    allowed = {'camera_declined', 'camera_permission_denied', 'camera_started',
               'camera_unavailable', 'camera_interrupted', 'camera_stopped',
               'page_hidden', 'page_visible', 'fullscreen_exited',
               'preflight_passed', 'preflight_failed'}
    if event_type not in allowed:
        return err('Unsupported Proctor Mode event.')
    request_id = str(d.get('request_id') or '')[:80]
    if not request_id:
        return err('A unique event request_id is required.')
    details = d.get('details') if isinstance(d.get('details'), dict) else {}
    safe_details = json.dumps(details, ensure_ascii=False)[:2000]
    try:
        client_ts = max(0, min(int(d.get('client_ts') or 0), int(time.time()) + 300))
    except (TypeError, ValueError):
        client_ts = 0
    db().execute('''insert or ignore into proctor_events
        (session_id,request_id,event_type,server_ts,client_ts,details)
        values(?,?,?,?,?,?)''',
        (g.ses['id'], request_id, event_type, int(time.time()), client_ts, safe_details))
    db().commit()
    return jsonify(ok=True, accepted=True)


@app.post('/api/student/event')
@sauth
def s_event():
    ex('update sessions set tab_switches=tab_switches+1 where id=?', (g.ses['id'],))
    return jsonify(ok=True)


@app.post('/api/student/submit')
@sauth
def s_submit():
    finalize(db(), g.ses['id'])
    return jsonify(done=True, **final_info())


# ---------------------------------------------------------------- background worker & server
def worker():
    last_bk = 0
    while True:
        try:
            c = raw()
            now = int(time.time())
            for r in c.execute('''select s.id from sessions s join exams e on e.id=s.exam_id where s.status='in_progress'
                                  and (e.status!='live' or ?-s.start_ts>=e.duration_min*60+s.extra_sec)''', (now,)).fetchall():
                finalize(c, r['id'])
            live = c.execute("select 1 from exams where status='live'").fetchone()
            c.close()
            if live and now - last_bk > 600:
                do_backup('auto')
                last_bk = now
        except Exception as e:  # never let the worker die
            print('worker error:', e)
        time.sleep(5)


def start_background():
    threading.Thread(target=worker, daemon=True).start()


def serve(host=None, port=None):
    host = host or SERVER_HOST
    port = int(port or SERVER_PORT)
    try:
        from waitress import serve as wserve
    except ImportError:
        app.run(host=host, port=port, threaded=True)
        return
    wserve(app, host=host, port=port, threads=32)


install_multi_tenant_routes(app, db, err)

if __name__ == '__main__':
    start_background()
    print(f'GTMC CBT server listening on {SERVER_HOST}:{SERVER_PORT}')
    if TRUST_PROXY:
        print('Trusted local HTTPS reverse proxy mode is enabled; backend is loopback-only.')
    else:
        print('LAN mode: use a listed school-network IP. Do not expose this HTTP port directly to the internet.')
    serve()
