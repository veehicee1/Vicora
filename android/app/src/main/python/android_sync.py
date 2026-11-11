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
