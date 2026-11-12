"""Durable Android Host result outbox and HTTPS delivery to the Windows CBT Server.

This module deliberately owns only the Android-local outbox. The Windows Server
remains authoritative and recomputes objective/automatic scores on receipt.
"""
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request

MAX_PAYLOAD_BYTES = 5 * 1024 * 1024


def _connect(data_dir):
    path = os.path.join(data_dir, "cbt.db")
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _outbox_columns(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(android_sync_outbox)")}


def _ensure_outbox(conn):
    columns = _outbox_columns(conn)
    if not columns:
        raise RuntimeError("Android result outbox is missing. Update the CBT app before syncing.")
    required = {"attempt_uuid", "payload", "status", "attempts", "next_attempt_ts",
                "last_error", "created_ts", "synced_ts"}
    if not required.issubset(columns):
        raise RuntimeError("Android result outbox schema is incomplete; no CBT records were changed.")


def _local_exam_revision_hash(conn, exam_id):
    exam = conn.execute(
        """SELECT e.sync_uuid,e.title,e.duration_min,e.num_questions,e.shuffle,e.show_score,
                  e.pass_mark,e.instructions,e.objective_count,e.theory_count,e.camera_policy,
                  s.sync_uuid subject_sync_uuid
           FROM exams e JOIN subjects s ON s.id=e.subject_id WHERE e.id=?""",
        (exam_id,),
    ).fetchone()
    if not exam:
        raise ValueError("Imported examination is missing its subject or revision data.")
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
    import hashlib
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

def _make_payload(conn, session_row):
    exam = conn.execute("SELECT sync_uuid,sync_revision_hash FROM exams WHERE id=?", (session_row["exam_id"],)).fetchone()
    student = conn.execute("SELECT sync_uuid FROM students WHERE id=?", (session_row["student_id"],)).fetchone()
    if not exam or not exam["sync_uuid"] or not student or not student["sync_uuid"]:
        raise ValueError("Exam or student has no cross-device identity. Import the matching host package and ask Admin to review.")
    current_revision = _local_exam_revision_hash(conn, session_row["exam_id"])
    if not exam["sync_revision_hash"] or current_revision != exam["sync_revision_hash"]:
        raise ValueError("The imported exam was changed on this phone after package import. Re-import the approved package before another attempt.")
    questions = conn.execute(
        """SELECT q.sync_uuid question_sync_uuid,sq.pos,sq.opt_order
           FROM session_questions sq JOIN questions q ON q.id=sq.question_id
           WHERE sq.session_id=? ORDER BY sq.pos""", (session_row["id"],)
    ).fetchall()
    if not questions or any(not q["question_sync_uuid"] for q in questions):
        raise ValueError("One or more examination questions have no cross-device identity.")
    answers = conn.execute(
        """SELECT q.sync_uuid question_sync_uuid,a.choice,a.response_text,a.response_drawing,a.flagged
           FROM answers a JOIN questions q ON q.id=a.question_id
           WHERE a.session_id=? ORDER BY q.id""", (session_row["id"],)
    ).fetchall()
    events = conn.execute(
        """SELECT request_id,event_type FROM proctor_events
           WHERE session_id=? ORDER BY id LIMIT 1000""", (session_row["id"],)
    ).fetchall()
    return {
        "attempt_uuid": session_row["attempt_uuid"],
        "exam_sync_uuid": exam["sync_uuid"],
        "exam_revision_hash": exam["sync_revision_hash"],
        "student_sync_uuid": student["sync_uuid"],
        "start_ts": int(session_row["start_ts"] or 0),
        "questions": [dict(q) for q in questions],
        "answers": [dict(a) for a in answers],
        "proctor_events": [dict(e) for e in events],
    }


def queue_completed_attempts(conn):
    """Snapshot newly submitted attempts once; never rewrite an existing outbox item."""
    _ensure_outbox(conn)
    sessions = conn.execute(
        """SELECT s.id,s.exam_id,s.student_id,s.attempt_uuid,s.start_ts
           FROM sessions s JOIN exams e ON e.id=s.exam_id
           LEFT JOIN android_sync_outbox o ON o.attempt_uuid=s.attempt_uuid
           WHERE s.status='submitted' AND s.attempt_uuid IS NOT NULL
             AND e.android_host_sync_enabled=1 AND o.attempt_uuid IS NULL
           ORDER BY s.submitted_ts,s.id"""
    ).fetchall()
    created = 0
    now = int(time.time())
    for row in sessions:
        try:
            payload = _make_payload(conn, row)
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
                raise ValueError("Result package exceeds the 5 MB Windows Server limit.")
            conn.execute(
                """INSERT OR IGNORE INTO android_sync_outbox
                   (attempt_uuid,payload,status,attempts,next_attempt_ts,last_error,created_ts,synced_ts)
                   VALUES(?,?,'pending',0,0,'',?,0)""",
                (row["attempt_uuid"], encoded, now),
            )
            created += 1
        except (ValueError, TypeError, KeyError) as exc:
            # Preserve the attempt and mark a reviewable local outbox record;
            # never delete or alter its original answers or score.
            payload = json.dumps({"attempt_uuid": row["attempt_uuid"], "local_session_id": row["id"]})
            conn.execute(
                """INSERT OR IGNORE INTO android_sync_outbox
                   (attempt_uuid,payload,status,attempts,next_attempt_ts,last_error,created_ts,synced_ts)
                   VALUES(?,?,'conflict',0,0,?,?,0)""",
                (row["attempt_uuid"], payload, str(exc)[:500], now),
            )
    conn.commit()
    return created


def _set_state(conn, attempt_uuid, status, attempts, next_ts, error="", synced_ts=0):
    conn.execute(
        """UPDATE android_sync_outbox SET status=?,attempts=?,next_attempt_ts=?,
           last_error=?,synced_ts=? WHERE attempt_uuid=?""",
        (status, attempts, next_ts, str(error)[:500], synced_ts, attempt_uuid),
    )
    conn.commit()


def sync_once(data_dir, server_url, device_id, device_token):
    """Queue completed attempts and deliver due records. Returns False only for retryable work."""
    if not server_url.startswith("https://") or not device_id or not device_token:
        raise ValueError("Pair the Android Host with a trusted HTTPS Windows Server first.")
    conn = _connect(data_dir)
    retryable = False
    try:
        _ensure_outbox(conn)
        queue_completed_attempts(conn)
        # Claim rows in a short write transaction so periodic and immediate
        # WorkManager jobs cannot upload the same attempt concurrently. A lease
        # lets a later worker recover if Android kills this worker mid-request.
        now = int(time.time())
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """SELECT attempt_uuid,payload,attempts FROM android_sync_outbox
               WHERE status IN ('pending','retry','syncing') AND next_attempt_ts<=?
               ORDER BY created_ts LIMIT 20""", (now,)
        ).fetchall()
        for claimed in rows:
            conn.execute(
                "UPDATE android_sync_outbox SET status='syncing',next_attempt_ts=? WHERE attempt_uuid=?",
                (now + 180, claimed["attempt_uuid"]),
            )
        conn.commit()
        endpoint = server_url.rstrip("/") + "/api/android-host/sync-results"
        for row in rows:
            attempt = int(row["attempts"] or 0) + 1
            try:
                payload = json.loads(row["payload"])
                payload["device_id"] = device_id
                body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                if len(body) > MAX_PAYLOAD_BYTES:
                    _set_state(conn, row["attempt_uuid"], "conflict", attempt, 0,
                               "Result package exceeds the 5 MB Windows Server limit.")
                    continue
                request = urllib.request.Request(
                    endpoint, data=body, method="POST",
                    headers={
                        "Authorization": "Bearer " + device_token,
                        "Content-Type": "application/json; charset=utf-8",
                        "Accept": "application/json",
                    },
                )
                with urllib.request.urlopen(request, timeout=25) as response:
                    status = response.getcode()
                    response_body = response.read(65536).decode("utf-8", "replace")
                result = json.loads(response_body or "{}")
                if 200 <= status < 300 and result.get("ok") and result.get("synced"):
                    _set_state(conn, row["attempt_uuid"], "synced", attempt, 0, "", int(time.time()))
                else:
                    _set_state(conn, row["attempt_uuid"], "retry", attempt,
                               int(time.time()) + min(3600, 15 * (2 ** min(attempt - 1, 8))),
                               result.get("error", "Windows Server did not acknowledge this result."))
                    retryable = True
            except urllib.error.HTTPError as exc:
                detail = exc.read(65536).decode("utf-8", "replace")
                try:
                    message = json.loads(detail).get("error", "Windows Server rejected the result.")
                except Exception:
                    message = "Windows Server returned HTTP " + str(exc.code)
                if exc.code in (401, 403):
                    _set_state(conn, row["attempt_uuid"], "auth_error", attempt, 0, message)
                elif exc.code == 409 or exc.code == 413 or (400 <= exc.code < 500 and exc.code != 429):
                    _set_state(conn, row["attempt_uuid"], "conflict", attempt, 0, message)
                else:
                    _set_state(conn, row["attempt_uuid"], "retry", attempt,
                               int(time.time()) + min(3600, 15 * (2 ** min(attempt - 1, 8))), message)
                    retryable = True
            except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                _set_state(conn, row["attempt_uuid"], "retry", attempt,
                           int(time.time()) + min(3600, 15 * (2 ** min(attempt - 1, 8))),
                           str(exc) or "Network unavailable.")
                retryable = True
        return not retryable
    finally:
        conn.close()



def _ensure_package_state(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS android_sync_package_state(
        exam_sync_uuid TEXT PRIMARY KEY, revision_hash TEXT NOT NULL,
        status TEXT NOT NULL, last_error TEXT DEFAULT '', updated_ts INTEGER NOT NULL)""")
    conn.commit()


def _import_exam_package(conn, package):
    """Import one approved Windows package without replacing any exam with attempts."""
    if not isinstance(package, dict) or package.get("schema_version") != 1:
        raise ValueError("Unsupported examination package schema.")
    exam = package.get("exam") or {}
    subject = package.get("subject") or {}
    classes = package.get("classes")
    students = package.get("students")
    questions = package.get("questions")
    revision = str(exam.get("sync_revision_hash") or "")
    exam_uuid = str(exam.get("sync_uuid") or "")
    subject_uuid = str(subject.get("sync_uuid") or "")
    import re
    if (not re.fullmatch(r"[a-f0-9]{64}", revision) or not exam_uuid or not subject_uuid
            or not exam.get("title") or not all(isinstance(x, list) for x in (classes, students, questions))):
        raise ValueError("The examination package is incomplete or has an invalid revision.")
    if exam.get("camera_policy", "off") not in ("off", "optional", "required"):
        raise ValueError("The package contains an invalid proctor policy.")
    remote_school = str(package.get("school_name") or "").strip()
    local_school_row = conn.execute("SELECT value FROM settings WHERE key='school_name'").fetchone()
    local_school = str(local_school_row["value"] if local_school_row else "").strip()
    if remote_school and local_school and remote_school.casefold() != local_school.casefold():
        raise ValueError("This Android Host belongs to a different school identity. Do not mix school databases.")
    if remote_school and not local_school:
        setting_columns = {row[1] for row in conn.execute("PRAGMA table_info(settings)")}
        if "school_id" in setting_columns:
            legacy = conn.execute(
                "SELECT value FROM settings WHERE key='vicora_legacy_school_id' ORDER BY rowid LIMIT 1"
            ).fetchone()
            legacy_school_id = legacy["value"] if legacy else ""
            if not legacy_school_id:
                school_row = conn.execute(
                    "SELECT school_id FROM schools WHERE is_legacy_default=1 LIMIT 1"
                ).fetchone()
                legacy_school_id = school_row["school_id"] if school_row else ""
            if not legacy_school_id:
                raise ValueError("This Android Host has no initialized school identity.")
            conn.execute(
                "INSERT OR REPLACE INTO settings(key,value,school_id) VALUES('school_name',?,?)",
                (remote_school, legacy_school_id),
            )
        else:
            conn.execute("""INSERT INTO settings(key,value) VALUES('school_name',?)
                            ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (remote_school,))

    existing_exam = conn.execute("SELECT id FROM exams WHERE sync_uuid=?", (exam_uuid,)).fetchone()
    exam_unchanged = False
    if existing_exam:
        local_id = existing_exam["id"]
        current = _local_exam_revision_hash(conn, local_id)
        exam_unchanged = current == revision
        if not exam_unchanged and conn.execute("SELECT 1 FROM sessions WHERE exam_id=? LIMIT 1", (local_id,)).fetchone():
            raise ValueError("This examination has candidate attempts. A changed package cannot overwrite it; administrator review is required.")

    subject_row = conn.execute("SELECT id FROM subjects WHERE sync_uuid=?", (subject_uuid,)).fetchone()
    if subject_row:
        subject_id = subject_row["id"]
        conn.execute("UPDATE subjects SET name=? WHERE id=?", (str(subject.get("name") or ""), subject_id))
    else:
        subject_row = conn.execute("SELECT id,sync_uuid FROM subjects WHERE lower(name)=lower(?)",
                                   (str(subject.get("name") or ""),)).fetchone()
        if subject_row and subject_row["sync_uuid"] not in (None, "", subject_uuid):
            raise ValueError("A subject with the same name has a different school identity.")
        if subject_row:
            subject_id = subject_row["id"]
            conn.execute("UPDATE subjects SET sync_uuid=? WHERE id=?", (subject_uuid, subject_id))
        else:
            subject_id = conn.execute("INSERT INTO subjects(name,sync_uuid) VALUES(?,?)",
                                      (str(subject.get("name") or ""), subject_uuid)).lastrowid

    class_ids = {}
    for item in classes:
        if not isinstance(item, dict) or not item.get("sync_uuid") or not item.get("name"):
            raise ValueError("The package contains an invalid class.")
        row = conn.execute("SELECT id FROM classes WHERE sync_uuid=?", (item["sync_uuid"],)).fetchone()
        if not row:
            row = conn.execute("SELECT id,sync_uuid FROM classes WHERE lower(name)=lower(?)",
                               (item["name"],)).fetchone()
            if row and row["sync_uuid"] not in (None, "", item["sync_uuid"]):
                raise ValueError("A class with the same name has a different school identity.")
            if row:
                local_class = row["id"]
                conn.execute("UPDATE classes SET sync_uuid=? WHERE id=?", (item["sync_uuid"], local_class))
            else:
                local_class = conn.execute("INSERT INTO classes(name,sync_uuid) VALUES(?,?)",
                                           (item["name"], item["sync_uuid"])).lastrowid
        else:
            local_class = row["id"]
            conn.execute("UPDATE classes SET name=? WHERE id=?", (item["name"], local_class))
        class_ids[item["sync_uuid"]] = local_class

    for item in students:
        if not isinstance(item, dict) or not item.get("sync_uuid") or not item.get("reg_no") or not item.get("access_code"):
            raise ValueError("The package contains an invalid candidate record.")
        class_id = class_ids.get(item.get("class_sync_uuid"))
        if not class_id:
            raise ValueError("A candidate references a class missing from this package.")
        row = conn.execute("SELECT id FROM students WHERE sync_uuid=?", (item["sync_uuid"],)).fetchone()
        if not row:
            row = conn.execute("SELECT id,sync_uuid FROM students WHERE lower(reg_no)=lower(?)",
                               (item["reg_no"],)).fetchone()
            if row and row["sync_uuid"] not in (None, "", item["sync_uuid"]):
                raise ValueError("A registration number belongs to a different school identity.")
        if row:
            conn.execute("""UPDATE students SET sync_uuid=?,reg_no=?,name=?,class_id=?,access_code=?
                            WHERE id=?""",
                         (item["sync_uuid"], item["reg_no"], item.get("name") or "",
                          class_id, item["access_code"], row["id"]))
        else:
            conn.execute("""INSERT INTO students(reg_no,name,class_id,access_code,sync_uuid)
                            VALUES(?,?,?,?,?)""",
                         (item["reg_no"], item.get("name") or "", class_id,
                          item["access_code"], item["sync_uuid"]))

    for item in questions:
        if not isinstance(item, dict) or not item.get("sync_uuid") or not item.get("text"):
            raise ValueError("The package contains an invalid question.")
        if item.get("subject_sync_uuid") != subject_uuid:
            raise ValueError("A question belongs to a different subject.")
        values = (subject_id, item["text"], item.get("a") or "", item.get("b") or "",
                  item.get("c") or "", item.get("d") or "", item.get("answer") or "",
                  float(item.get("marks") or 1), item.get("topic") or "", item.get("difficulty") or "",
                  item.get("question_type") or "objective", item.get("answer_text") or "",
                  item.get("accepted_answers") or "[]", item.get("keywords") or "[]",
                  item.get("answer_space") or "medium", item.get("marking_mode") or "exact")
        row = conn.execute("SELECT id FROM questions WHERE sync_uuid=?", (item["sync_uuid"],)).fetchone()
        if row:
            conn.execute("""UPDATE questions SET subject_id=?,text=?,a=?,b=?,c=?,d=?,answer=?,marks=?,
                topic=?,difficulty=?,question_type=?,answer_text=?,accepted_answers=?,keywords=?,
                answer_space=?,marking_mode=? WHERE id=?""", values + (row["id"],))
        else:
            same = conn.execute("SELECT id,sync_uuid FROM questions WHERE subject_id=? AND text=?",
                                (subject_id, item["text"])).fetchone()
            if same and same["sync_uuid"] not in (None, "", item["sync_uuid"]):
                raise ValueError("A question with identical wording has a different identity.")
            if same:
                conn.execute("UPDATE questions SET sync_uuid=? WHERE id=?", (item["sync_uuid"], same["id"]))
            else:
                conn.execute("""INSERT INTO questions(subject_id,text,a,b,c,d,answer,marks,topic,difficulty,
                    question_type,answer_text,accepted_answers,keywords,answer_space,marking_mode,sync_uuid)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", values + (item["sync_uuid"],))

    if existing_exam:
        exam_id = existing_exam["id"]
        if not exam_unchanged:
            conn.execute("""UPDATE exams SET title=?,subject_id=?,duration_min=?,num_questions=?,shuffle=?,
                show_score=?,pass_mark=?,instructions=?,objective_count=?,theory_count=?,camera_policy=?,
                sync_revision_hash=?,status='draft' WHERE id=?""",
                (exam["title"], subject_id, int(exam["duration_min"]), int(exam["num_questions"]),
                 int(bool(exam.get("shuffle", 1))), int(bool(exam.get("show_score", 0))),
                 float(exam.get("pass_mark", 50)), str(exam.get("instructions") or ""),
                 int(exam.get("objective_count") or 0), int(exam.get("theory_count") or 0),
                 exam.get("camera_policy", "off"), revision, exam_id))
            conn.execute("DELETE FROM exam_classes WHERE exam_id=?", (exam_id,))
    else:
        exam_id = conn.execute("""INSERT INTO exams(title,subject_id,duration_min,num_questions,shuffle,
            show_score,pass_mark,instructions,status,created_ts,objective_count,theory_count,camera_policy,
            sync_uuid,sync_revision_hash,android_host_sync_enabled)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
            (exam["title"], subject_id, int(exam["duration_min"]), int(exam["num_questions"]),
             int(bool(exam.get("shuffle", 1))), int(bool(exam.get("show_score", 0))),
             float(exam.get("pass_mark", 50)), str(exam.get("instructions") or ""), "draft",
             int(time.time()), int(exam.get("objective_count") or 0), int(exam.get("theory_count") or 0),
             exam.get("camera_policy", "off"), exam_uuid, revision)).lastrowid
    conn.execute("UPDATE exams SET android_host_sync_enabled=1 WHERE id=?", (exam_id,))
    class_uuids = package.get("class_sync_uuids") or []
    for class_uuid in class_uuids:
        if class_uuid not in class_ids:
            raise ValueError("The package references an unknown assigned class.")
        conn.execute("INSERT OR IGNORE INTO exam_classes(exam_id,class_id) VALUES(?,?)",
                     (exam_id, class_ids[class_uuid]))
    actual = _local_exam_revision_hash(conn, exam_id)
    if actual != revision:
        raise ValueError("Imported package revision does not match its content; no exam was activated.")
    return {"exam_sync_uuid": exam_uuid, "revision_hash": revision, "status": "imported"}


def pull_packages_once(data_dir, server_url, device_id, device_token):
    """Fetch only administrator-approved exam packages; never overwrite attempts."""
    if not server_url.startswith("https://") or not device_id or not device_token:
        raise ValueError("A trusted HTTPS pairing is required before exam synchronisation.")
    conn = _connect(data_dir)
    try:
        _ensure_package_state(conn)
        known = {row["exam_sync_uuid"]: row["revision_hash"] for row in conn.execute(
            "SELECT exam_sync_uuid,revision_hash FROM android_sync_package_state")}
        body = json.dumps({"device_id": device_id, "known_revisions": known},
                          separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(
            server_url.rstrip("/") + "/api/android-host/sync-pull", data=body, method="POST",
            headers={"Authorization": "Bearer " + device_token,
                     "Content-Type": "application/json; charset=utf-8", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                result = json.loads(response.read(20 * 1024 * 1024 + 1).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ValueError("Android Host pairing was revoked or is no longer valid.")
            raise
        if not result.get("ok") or not isinstance(result.get("packages"), list):
            raise ValueError("Windows Server returned an invalid examination sync response.")
        for package in result["packages"]:
            exam = package.get("exam") or {}
            exam_uuid = str(exam.get("sync_uuid") or "")
            revision = str(exam.get("sync_revision_hash") or "")
            roster_revision = str(package.get("roster_revision_hash") or "")
            if not exam_uuid or not revision or not roster_revision:
                continue
            revision_token = revision + "." + roster_revision
            previous = conn.execute(
                "SELECT revision_hash FROM android_sync_package_state WHERE exam_sync_uuid=?",
                (exam_uuid,)).fetchone()
            if previous and previous["revision_hash"] == revision_token:
                continue
            try:
                conn.execute("BEGIN IMMEDIATE")
                outcome = _import_exam_package(conn, package)
                conn.execute("""INSERT INTO android_sync_package_state
                    (exam_sync_uuid,revision_hash,status,last_error,updated_ts) VALUES(?,?,?,'',?)
                    ON CONFLICT(exam_sync_uuid) DO UPDATE SET revision_hash=excluded.revision_hash,
                    status=excluded.status,last_error='',updated_ts=excluded.updated_ts""",
                    (exam_uuid, revision_token, outcome["status"], int(time.time())))
                conn.commit()
            except (ValueError, TypeError, KeyError, sqlite3.IntegrityError) as exc:
                conn.rollback()
                conn.execute("""INSERT INTO android_sync_package_state
                    (exam_sync_uuid,revision_hash,status,last_error,updated_ts) VALUES(?,?,'conflict',?,?)
                    ON CONFLICT(exam_sync_uuid) DO UPDATE SET revision_hash=excluded.revision_hash,
                    status='conflict',last_error=excluded.last_error,updated_ts=excluded.updated_ts""",
                    (exam_uuid, revision_token, str(exc)[:500], int(time.time())))
                conn.commit()
        return True
    finally:
        conn.close()


def local_status(data_dir):
    conn = _connect(data_dir)
    try:
        _ensure_outbox(conn)
        rows = conn.execute(
            "SELECT status,COUNT(*) n FROM android_sync_outbox GROUP BY status"
        ).fetchall()
        result = {row["status"]: row["n"] for row in rows}
        result["total"] = sum(result.values())
        return result
    finally:
        conn.close()


def local_status_json(data_dir):
    """JSON-safe status summary for the on-device Admin screen; no candidate data."""
    return json.dumps(local_status(data_dir), sort_keys=True)


def reset_auth_errors(data_dir):
    """Requeue only authentication-blocked rows after an Admin has paired again."""
    conn = _connect(data_dir)
    try:
        _ensure_outbox(conn)
        conn.execute("UPDATE android_sync_outbox SET status='pending',attempts=0,next_attempt_ts=0,last_error='' WHERE status='auth_error'")
        conn.commit()
    finally:
        conn.close()
