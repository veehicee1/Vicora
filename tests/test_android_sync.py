"""Regression tests for the Android Host durable result outbox."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "android", "app", "src", "main", "python"))
import android_sync  # noqa: E402


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def read(self, size=-1):
        return self.payload.encode("utf-8")


class AndroidSyncOutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gtmc-android-sync-")
        self.data_dir = self.temp.name
        self.db_path = os.path.join(self.data_dir, "cbt.db")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE subjects(id INTEGER PRIMARY KEY, sync_uuid TEXT);
            CREATE TABLE classes(id INTEGER PRIMARY KEY, sync_uuid TEXT);
            CREATE TABLE exams(
                id INTEGER PRIMARY KEY, sync_uuid TEXT, android_host_sync_enabled INTEGER DEFAULT 0,
                sync_revision_hash TEXT DEFAULT '', title TEXT, duration_min INTEGER, num_questions INTEGER,
                shuffle INTEGER, show_score INTEGER, pass_mark REAL, instructions TEXT,
                objective_count INTEGER, theory_count INTEGER, camera_policy TEXT, subject_id INTEGER
            );
            CREATE TABLE exam_classes(exam_id INTEGER, class_id INTEGER);
            CREATE TABLE students(id INTEGER PRIMARY KEY, sync_uuid TEXT, class_id INTEGER);
            CREATE TABLE sessions(
                id INTEGER PRIMARY KEY, exam_id INTEGER, student_id INTEGER,
                status TEXT, attempt_uuid TEXT, start_ts INTEGER, submitted_ts INTEGER
            );
            CREATE TABLE questions(
                id INTEGER PRIMARY KEY, sync_uuid TEXT, subject_id INTEGER, text TEXT,
                a TEXT,b TEXT,c TEXT,d TEXT,answer TEXT,marks REAL,topic TEXT,difficulty TEXT,
                question_type TEXT,answer_text TEXT,accepted_answers TEXT,keywords TEXT,
                answer_space TEXT,marking_mode TEXT
            );
            CREATE TABLE session_questions(
                session_id INTEGER, pos INTEGER, question_id INTEGER, opt_order TEXT
            );
            CREATE TABLE answers(
                session_id INTEGER, question_id INTEGER, choice TEXT,
                response_text TEXT, response_drawing TEXT, flagged INTEGER
            );
            CREATE TABLE proctor_events(
                id INTEGER PRIMARY KEY, session_id INTEGER, request_id TEXT, event_type TEXT
            );
            CREATE TABLE android_sync_outbox(
                id INTEGER PRIMARY KEY, attempt_uuid TEXT UNIQUE NOT NULL, payload TEXT NOT NULL,
                status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0,
                next_attempt_ts INTEGER DEFAULT 0, last_error TEXT DEFAULT '',
                created_ts INTEGER NOT NULL, synced_ts INTEGER DEFAULT 0
            );
            INSERT INTO subjects VALUES(1,'subject-sync-uuid');
            INSERT INTO classes VALUES(1,'class-sync-uuid');
            INSERT INTO exams VALUES(1,'exam-sync-uuid',1,'','Test Exam',30,2,1,0,50,'',1,1,'optional',1);
            INSERT INTO exams VALUES(2,'unrelated-exam',0,'','Local Only',30,2,1,0,50,'',1,1,'off',1);
            INSERT INTO exam_classes VALUES(1,1);
            INSERT INTO exam_classes VALUES(2,1);
            INSERT INTO students VALUES(1,'student-sync-uuid',1);
            INSERT INTO questions VALUES(1,'question-one-uuid',1,'Objective question','A','B','C','D','B',1,'','', 'objective','','[]','[]','medium','exact');
            INSERT INTO questions VALUES(2,'question-two-uuid',1,'Theory question','','','','','',2,'','', 'theory','model answer','[]','[]','medium','manual');
            INSERT INTO sessions VALUES(1,1,1,'submitted','attempt-stable-uuid',100,200);
            INSERT INTO sessions VALUES(2,2,1,'submitted','standalone-only-attempt',100,200);
            INSERT INTO session_questions VALUES(1,1,1,'ABCD');
            INSERT INTO session_questions VALUES(1,2,2,'DCBA');
            INSERT INTO answers VALUES(1,1,'B','','',0);
            INSERT INTO answers VALUES(1,2,'','A written theory response','[[[0.1,0.2],[0.3,0.4]]]',1);
            INSERT INTO proctor_events VALUES(1,1,'event-1','camera_interrupted');
        """)
        revision = android_sync._local_exam_revision_hash(conn, 1)
        conn.execute("UPDATE exams SET sync_revision_hash=? WHERE id=1", (revision,))
        conn.commit()
        conn.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_completed_attempt_is_snapshotted_once_with_theory_and_proctor_data(self):
        conn = android_sync._connect(self.data_dir)
        self.assertEqual(android_sync.queue_completed_attempts(conn), 1)
        self.assertEqual(android_sync.queue_completed_attempts(conn), 0)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM android_sync_outbox").fetchone()[0], 1)
        row = conn.execute("SELECT * FROM android_sync_outbox").fetchone()
        payload = json.loads(row["payload"])
        self.assertEqual(row["status"], "pending")
        self.assertEqual(payload["attempt_uuid"], "attempt-stable-uuid")
        self.assertEqual(payload["exam_sync_uuid"], "exam-sync-uuid")
        self.assertEqual(len(payload["exam_revision_hash"]), 64)
        self.assertEqual(len(payload["questions"]), 2)
        self.assertEqual(payload["answers"][1]["response_text"], "A written theory response")
        self.assertEqual(payload["answers"][1]["response_drawing"], "[[[0.1,0.2],[0.3,0.4]]]")
        self.assertEqual(payload["proctor_events"][0]["event_type"], "camera_interrupted")
        conn.close()

    def test_changed_local_exam_revision_is_quarantined(self):
        conn = android_sync._connect(self.data_dir)
        conn.execute("UPDATE questions SET text='Changed after package import' WHERE id=1")
        conn.commit()
        android_sync.queue_completed_attempts(conn)
        row = conn.execute("SELECT status,last_error FROM android_sync_outbox").fetchone()
        self.assertEqual(row["status"], "conflict")
        self.assertIn("changed on this phone", row["last_error"])
        conn.close()

    @patch("android_sync.urllib.request.urlopen")
    def test_only_server_acknowledgement_marks_attempt_synced(self, urlopen):
        urlopen.return_value = FakeResponse('{"ok":true,"synced":true,"session_id":88}')
        self.assertTrue(android_sync.sync_once(
            self.data_dir, "https://school.example", "device-uuid", "long-device-token"
        ))
        conn = android_sync._connect(self.data_dir)
        row = conn.execute("SELECT status,synced_ts FROM android_sync_outbox").fetchone()
        self.assertEqual(row["status"], "synced")
        self.assertGreater(row["synced_ts"], 0)
        conn.close()
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://school.example/api/android-host/sync-results")
        self.assertEqual(request.get_header("Authorization"), "Bearer long-device-token")

    @patch("android_sync.urllib.request.urlopen")
    def test_parallel_worker_cannot_claim_the_same_active_attempt(self, urlopen):
        def first_request(request, timeout):
            # Simulate another WorkManager job starting while this request is in flight.
            self.assertTrue(android_sync.sync_once(
                self.data_dir, "https://school.example", "device-uuid", "long-device-token"
            ))
            return FakeResponse('{"ok":true,"synced":true,"session_id":88}')
        urlopen.side_effect = first_request
        self.assertTrue(android_sync.sync_once(
            self.data_dir, "https://school.example", "device-uuid", "long-device-token"
        ))
        self.assertEqual(urlopen.call_count, 1)
        conn = android_sync._connect(self.data_dir)
        self.assertEqual(conn.execute("SELECT status FROM android_sync_outbox").fetchone()["status"], "synced")
        conn.close()

    @patch("android_sync.urllib.request.urlopen")
    def test_server_conflict_is_quarantined_not_overwritten_or_retried(self, urlopen):
        from urllib.error import HTTPError
        urlopen.side_effect = HTTPError(
            "https://school.example/api/android-host/sync-results", 409, "Conflict", {},
            __import__("io").BytesIO(b'{"error":"Admin review required"}')
        )
        self.assertTrue(android_sync.sync_once(
            self.data_dir, "https://school.example", "device-uuid", "long-device-token"
        ))
        conn = android_sync._connect(self.data_dir)
        row = conn.execute("SELECT status,last_error FROM android_sync_outbox").fetchone()
        self.assertEqual(row["status"], "conflict")
        self.assertIn("Admin review", row["last_error"])
        conn.close()

    @patch("android_sync.urllib.request.urlopen")
    def test_network_failure_keeps_attempt_pending_for_backoff_retry(self, urlopen):
        urlopen.side_effect = OSError("network unavailable")
        self.assertFalse(android_sync.sync_once(
            self.data_dir, "https://school.example", "device-uuid", "long-device-token"
        ))
        conn = android_sync._connect(self.data_dir)
        row = conn.execute("SELECT status,attempts,next_attempt_ts FROM android_sync_outbox").fetchone()
        self.assertEqual(row["status"], "retry")
        self.assertEqual(row["attempts"], 1)
        self.assertGreater(row["next_attempt_ts"], 0)
        conn.close()


if __name__ == "__main__":
    unittest.main()
