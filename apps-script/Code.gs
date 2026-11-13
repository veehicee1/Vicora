/**
 * VICORA Central School Management API
 * Google Apps Script + Google Sheets + Google Drive.
 *
 * IMPORTANT:
 * - This service manages school tenancy and administration metadata.
 * - It is NOT the high-volume CBT answer/scoring engine.
 * - Do not put secrets in source code. Configure Script Properties as documented.
 * - Deploy only after configuring the spreadsheet and platform admin key.
 */

const VICORA = Object.freeze({
  VERSION: '1.0.0',
  DB_PROPERTY: 'VICORA_DATABASE_ID',
  DRIVE_PROPERTY: 'VICORA_STORAGE_FOLDER_ID',
  ADMIN_KEY_PROPERTY: 'VICORA_PLATFORM_ADMIN_KEY',
  SESSION_HOURS: 12,
  SCHOOL_CODE_PREFIX: 'VIC',
  SHEETS: {
    Applications: ['application_id','school_name','school_type','country','state','address','contact_name','contact_email','contact_phone','status','submitted_at','reviewed_at','reviewed_by','decision_note'],
    Schools: ['school_id','school_code','school_name','school_type','country','state','address','contact_name','contact_email','contact_phone','status','created_at','approved_at','plan_name','trial_days','trial_started_at','trial_expires_at','subscription_status'],
    Users: ['user_id','school_id','name','email','role','password_salt','password_hash','active','created_at','last_login'],
    Sessions: ['session_id','token_hash','user_id','school_id','expires_at','created_at','revoked'],
    Classes: ['record_id','school_id','name','level','active','updated_at'],
    Subjects: ['record_id','school_id','name','code','level','active','updated_at'],
    Students: ['record_id','school_id','admission_number','full_name','class_name','active','updated_at'],
    Questions: ['question_id','school_id','subject_id','question_type','question_text','option_a','option_b','option_c','option_d','correct_answer','explanation','marks','difficulty','status','created_by','created_at','updated_at'],
    Exams: ['exam_id','school_id','title','subject_id','duration_minutes','total_marks','instructions','status','start_at','end_at','shuffle_questions','shuffle_options','show_result','created_by','created_at','updated_at','published_at'],
    ExamQuestions: ['record_id','school_id','exam_id','question_id','question_order','marks','created_at'],
    ExamAssignments: ['assignment_id','school_id','exam_id','class_name','candidate_count','created_at'],
    ExamAudit: ['event_id','school_id','exam_id','actor_id','action','details_json','created_at'],
    Devices: ['device_id','school_id','device_name','platform','device_token_hash','status','last_seen','created_at'],
    SyncEvents: ['event_id','school_id','device_id','entity_type','entity_id','operation','payload_json','created_at'],
    Audit: ['audit_id','school_id','actor_id','action','details_json','created_at']
  }
});

function doGet(e) {
  const action = String((e && e.parameter && e.parameter.action) || 'health');
  if (action === 'health') {
    return json_({ ok: true, service: 'VICORA Central Apps Script API', version: VICORA.VERSION, timestamp: new Date().toISOString() });
  }
  if (action === 'resolveSchool') {
    const code = String((e.parameter && e.parameter.code) || '').trim().toUpperCase();
    const school = findOne_('Schools', 'school_code', code);
    if (!school || school.status !== 'approved') return json_({ ok: false, error: 'School Code not found or not active.' });
    return json_({ ok: true, school: publicSchool_(school) });
  }
  return json_({ ok: false, error: 'Unsupported GET action.' });
}

function doPost(e) {
  try {
    const body = e && e.postData && e.postData.contents ? JSON.parse(e.postData.contents) : {};
    const action = String(body.action || '');
    let result;
    switch (action) {
      case 'applySchool': result = applySchool_(body); break;
      case 'admin.listApplications': requirePlatformAdmin_(body); result = listApplications_(); break;
      case 'admin.decideApplication': requirePlatformAdmin_(body); result = decideApplication_(body); break;
      case 'admin.listSchools': requirePlatformAdmin_(body); result = listSchools_(); break;
      case 'admin.assignTrial': requirePlatformAdmin_(body); result = assignTrial_(body); break;
      case 'activateSchool': result = activateSchool_(body); break;
      case 'login': result = login_(body); break;
      case 'logout': result = logout_(body); break;
      case 'account.create': result = createAccount_(body); break;
      case 'class.save': result = saveSchoolRecord_(body, 'Classes', ['name','level']); break;
      case 'subject.save': result = saveSchoolRecord_(body, 'Subjects', ['name','code','level']); break;
      case 'student.save': result = saveStudent_(body); break;
      case 'question.list': result = listQuestions_(body); break;
      case 'question.save': result = saveQuestion_(body); break;
      case 'question.delete': result = deleteQuestion_(body); break;
      case 'exam.list': result = listExams_(body); break;
      case 'exam.save': result = saveExam_(body); break;
      case 'exam.delete': result = deleteExam_(body); break;
      case 'exam.questions.set': result = setExamQuestions_(body); break;
      case 'exam.assign': result = assignExamClasses_(body); break;
      case 'host.enroll': result = enrollHost_(body); break;
      case 'host.heartbeat': result = hostHeartbeat_(body); break;
      case 'host.revoke': result = revokeHost_(body); break;
      case 'sync.push': result = syncPush_(body); break;
      case 'sync.pull': result = syncPull_(body); break;
      case 'school.profile': result = schoolProfile_(body); break;
      case 'auth.context': result = authContext_(body); break;
      default: throw new Error('Unsupported action: ' + action);
    }
    return json_({ ok: true, data: result });
  } catch (error) {
    return json_({ ok: false, error: safeError_(error) });
  }
}

/**
 * Run once manually from the Apps Script editor.
 * Creates a dedicated VICORA spreadsheet and a Drive storage folder.
 */
function initializeVicoraBackend() {
  const props = PropertiesService.getScriptProperties();
  let spreadsheetId = props.getProperty(VICORA.DB_PROPERTY);
  let ss;
  if (spreadsheetId) {
    ss = SpreadsheetApp.openById(spreadsheetId);
  } else {
    ss = SpreadsheetApp.create('VICORA Central Database');
    spreadsheetId = ss.getId();
    props.setProperty(VICORA.DB_PROPERTY, spreadsheetId);
  }
  Object.keys(VICORA.SHEETS).forEach(function(name) {
    let sheet = ss.getSheetByName(name);
    if (!sheet) sheet = ss.insertSheet(name);
    const headers = VICORA.SHEETS[name];
    if (sheet.getLastRow() === 0) {
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
      sheet.setFrozenRows(1);
    } else {
      const existing = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), 1)).getValues()[0].map(String);
      headers.forEach(function(header) {
        if (existing.indexOf(header) === -1) {
          sheet.getRange(1, sheet.getLastColumn() + 1).setValue(header);
        }
      });
    }
  });
  const oldDefault = ss.getSheetByName('Sheet1');
  if (oldDefault && ss.getSheets().length > 1 && oldDefault.getLastRow() === 0) ss.deleteSheet(oldDefault);
  let folderId = props.getProperty(VICORA.DRIVE_PROPERTY);
  if (!folderId) {
    const folder = DriveApp.createFolder('VICORA School Storage');
    folderId = folder.getId();
    props.setProperty(VICORA.DRIVE_PROPERTY, folderId);
  }
  return {
    message: 'VICORA database initialized. Add VICORA_PLATFORM_ADMIN_KEY in Script Properties before deployment.',
    spreadsheetUrl: ss.getUrl(),
    storageFolderUrl: DriveApp.getFolderById(folderId).getUrl(),
    sheets: Object.keys(VICORA.SHEETS)
  };
}

function applySchool_(b) {
  const name = required_(b.schoolName, 'School name', 160);
  const contact = required_(b.contactName, 'Contact name', 120);
  const email = validEmail_(b.contactEmail);
  const phone = required_(b.contactPhone, 'Contact phone', 40);
  const duplicate = findRows_('Applications', 'contact_email', email).some(function(r) {
    return ['pending','approved'].indexOf(r.status) !== -1;
  }) || findRows_('Schools', 'contact_email', email).length > 0;
  if (duplicate) throw new Error('An application or school account already exists for this email.');
  const row = {
    application_id: Utilities.getUuid(), school_name: name,
    school_type: clean_(b.schoolType || 'Secondary', 60),
    country: clean_(b.country || 'Nigeria', 80), state: clean_(b.state || '', 80),
    address: clean_(b.address || '', 240), contact_name: contact,
    contact_email: email, contact_phone: phone, status: 'pending',
    submitted_at: new Date().toISOString(), reviewed_at: '', reviewed_by: '', decision_note: ''
  };
  appendObject_('Applications', row);
  return { applicationId: row.application_id, status: 'pending', message: 'Application received for VICORA review.' };
}

function listApplications_() {
  return readObjects_('Applications').sort(function(a,b) {
    return String(b.submitted_at).localeCompare(String(a.submitted_at));
  });
}

function decideApplication_(b) {
  const id = required_(b.applicationId, 'Application ID', 80);
  const application = findOne_('Applications', 'application_id', id);
  if (!application) throw new Error('Application not found.');
  if (application.status !== 'pending') throw new Error('This application has already been reviewed.');
  const decision = String(b.decision || '').toLowerCase();
  const note = clean_(b.note || '', 500);
  const sheet = sheet_('Applications');
  const rowNumber = rowNumberByValue_(sheet, 'application_id', id);
  if (decision === 'reject') {
    updateObjectRow_(sheet, rowNumber, { status: 'rejected', reviewed_at: new Date().toISOString(), reviewed_by: 'platform-admin', decision_note: note });
    audit_('', 'application.rejected', { applicationId: id, note: note });
    return { applicationId: id, status: 'rejected' };
  }
  if (decision !== 'approve') throw new Error('Decision must be approve or reject.');
  const trialDays = validTrialDays_(b.trialDays);
  const schoolId = Utilities.getUuid();
  const schoolCode = generateSchoolCode_();
  const activationToken = randomToken_();
  const school = {
    school_id: schoolId, school_code: schoolCode, school_name: application.school_name,
    school_type: application.school_type, country: application.country, state: application.state,
    address: application.address, contact_name: application.contact_name,
    contact_email: application.contact_email, contact_phone: application.contact_phone,
    status: 'approved', created_at: new Date().toISOString(), approved_at: new Date().toISOString(),
    plan_name: 'Free Trial', trial_days: trialDays, trial_started_at: new Date().toISOString(),
    trial_expires_at: new Date(Date.now() + trialDays * 86400000).toISOString(), subscription_status: 'trial'
  };
  appendObject_('Schools', school);
  const salt = randomToken_();
  appendObject_('Users', {
    user_id: Utilities.getUuid(), school_id: schoolId, name: application.contact_name,
    email: application.contact_email, role: 'school_admin', password_salt: salt,
    password_hash: 'PENDING_ACTIVATION:' + sha256_(activationToken),
    active: 'pending', created_at: new Date().toISOString(), last_login: ''
  });
  updateObjectRow_(sheet, rowNumber, { status: 'approved', reviewed_at: new Date().toISOString(), reviewed_by: 'platform-admin', decision_note: note });
  audit_(schoolId, 'school.approved', { schoolCode: schoolCode });
  let emailSent = false;
  try {
    MailApp.sendEmail({
      to: application.contact_email,
      subject: 'Your VICORA school application has been approved',
      body: 'Your school has been approved on VICORA.\nSchool: ' + application.school_name +
        '\nSchool Code: ' + schoolCode + '\nActivation token: ' + activationToken +
        '\nPlease activate your school administrator account using the VICORA activation page. This token can only be used once.'
    });
    emailSent = true;
  } catch (mailError) {
    console.warn('Approval email could not be sent: ' + mailError);
  }
  return { schoolId: schoolId, schoolCode: schoolCode, activationToken: activationToken, contactEmail: application.contact_email, emailSent: emailSent, trialDays: trialDays, trialExpiresAt: school.trial_expires_at };
}

function activateSchool_(b) {
  const token = required_(b.activationToken, 'Activation token', 200);
  const email = validEmail_(b.email);
  const password = String(b.password || '');
  if (password.length < 12) throw new Error('Use a password of at least 12 characters.');
  const users = readObjects_('Users');
  const user = users.find(function(u) {
    return String(u.email).toLowerCase() === email && String(u.active) === 'pending' &&
      String(u.password_hash) === 'PENDING_ACTIVATION:' + sha256_(token);
  });
  if (!user) throw new Error('Activation token or email is invalid, expired or already used.');
  const salt = randomToken_();
  const sheet = sheet_('Users');
  const rowNumber = rowNumberByValue_(sheet, 'user_id', user.user_id);
  updateObjectRow_(sheet, rowNumber, { password_salt: salt, password_hash: sha256_(salt + password), active: 'true' });
  audit_(user.school_id, 'school_admin.activated', { userId: user.user_id });
  return { activated: true, schoolCode: findOne_('Schools', 'school_id', user.school_id).school_code };
}

function login_(b) {
  const code = required_(b.schoolCode, 'School Code', 40).toUpperCase();
  const email = validEmail_(b.email);
  const password = String(b.password || '');
  const school = findOne_('Schools', 'school_code', code);
  if (!school || school.status !== 'approved') throw new Error('School Code is invalid or inactive.');
  assertSchoolTrialActive_(school);
  const user = readObjects_('Users').find(function(u) {
    return u.school_id === school.school_id && String(u.email).toLowerCase() === email && String(u.active) === 'true';
  });
  if (!user || user.password_hash !== sha256_(user.password_salt + password)) throw new Error('Email or password is incorrect.');
  const token = randomToken_();
  const expires = new Date(Date.now() + VICORA.SESSION_HOURS * 3600000).toISOString();
  appendObject_('Sessions', { session_id: Utilities.getUuid(), token_hash: sha256_(token), user_id: user.user_id, school_id: school.school_id, expires_at: expires, created_at: new Date().toISOString(), revoked: 'false' });
  const userSheet = sheet_('Users');
  updateObjectRow_(userSheet, rowNumberByValue_(userSheet, 'user_id', user.user_id), { last_login: new Date().toISOString() });
  audit_(school.school_id, 'user.login', { userId: user.user_id });
  return { sessionToken: token, expiresAt: expires, school: publicSchool_(school), user: { userId: user.user_id, name: user.name, email: user.email, role: user.role } };
}

function logout_(b) {
  const auth = requireSession_(b);
  const tokenHash = sha256_(String(b.sessionToken));
  const sessions = readObjects_('Sessions');
  const sessionRow = sessions.find(function(s) { return s.token_hash === tokenHash && s.revoked !== 'true'; });
  if (sessionRow) updateObjectRow_(sheet_('Sessions'), rowNumberByValue_(sheet_('Sessions'), 'session_id', sessionRow.session_id), { revoked: 'true' });
  audit_(auth.schoolId, 'user.logout', { userId: auth.userId });
  return { loggedOut: true };
}

function createAccount_(b) {
  const auth = requireSession_(b);
  requireRole_(auth, ['school_admin','school_owner']);
  const name = required_(b.name, 'Name', 120);
  const email = validEmail_(b.email);
  const role = String(b.role || 'teacher');
  if (['school_admin','school_owner','teacher','exam_officer','viewer'].indexOf(role) === -1) throw new Error('Invalid account role.');
  if (readObjects_('Users').some(function(u) { return u.school_id === auth.schoolId && String(u.email).toLowerCase() === email; })) throw new Error('This email already has an account in this school.');
  const temporaryPassword = randomToken_().slice(0, 20);
  const salt = randomToken_();
  const user = { user_id: Utilities.getUuid(), school_id: auth.schoolId, name: name, email: email, role: role, password_salt: salt, password_hash: sha256_(salt + temporaryPassword), active: 'true', created_at: new Date().toISOString(), last_login: '' };
  appendObject_('Users', user);
  audit_(auth.schoolId, 'account.created', { userId: user.user_id, role: role });
  try { MailApp.sendEmail(email, 'Your VICORA account', 'Your VICORA account is ready. Temporary password: ' + temporaryPassword + '\nPlease sign in and change it.'); } catch (e) {}
  return { userId: user.user_id, email: email, role: role, temporaryPassword: temporaryPassword };
}

function saveSchoolRecord_(b, table, fields) {
  const auth = requireSession_(b);
  requireRole_(auth, ['school_admin','school_owner','exam_officer']);
  const id = clean_(b.recordId || '', 100) || Utilities.getUuid();
  const sheet = sheet_(table);
  const existingRow = rowNumberByValue_(sheet, 'record_id', id, true);
  const values = { record_id: id, school_id: auth.schoolId, updated_at: new Date().toISOString(), active: 'true' };
  fields.forEach(function(field) { values[field] = required_(b[field], field, 160); });
  if (existingRow) {
    const existing = objectAtRow_(sheet, existingRow);
    if (existing.school_id !== auth.schoolId) throw new Error('Record not found in this school.');
    updateObjectRow_(sheet, existingRow, values);
  } else {
    appendObject_(table, values);
  }
  audit_(auth.schoolId, table.toLowerCase() + '.saved', { recordId: id });
  return { recordId: id, saved: true };
}

function saveStudent_(b) {
  const auth = requireSession_(b);
  requireRole_(auth, ['school_admin','school_owner','exam_officer']);
  const admission = required_(b.admissionNumber, 'Admission number', 80);
  const name = required_(b.fullName, 'Student name', 160);
  const className = required_(b.className, 'Class', 80);
  const sheet = sheet_('Students');
  const existing = readObjects_('Students').find(function(s) { return s.school_id === auth.schoolId && s.admission_number === admission; });
  const values = { record_id: existing ? existing.record_id : Utilities.getUuid(), school_id: auth.schoolId, admission_number: admission, full_name: name, class_name: className, active: 'true', updated_at: new Date().toISOString() };
  if (existing) updateObjectRow_(sheet, rowNumberByValue_(sheet, 'record_id', existing.record_id), values);
  else appendObject_('Students', values);
  audit_(auth.schoolId, 'student.saved', { admissionNumber: admission });
  return { recordId: values.record_id, saved: true };
}

function enrollHost_(b) {
  const auth = requireSession_(b);
  requireRole_(auth, ['school_admin','school_owner']);
  const deviceToken = randomToken_();
  const device = { device_id: Utilities.getUuid(), school_id: auth.schoolId, device_name: clean_(b.deviceName || 'VICORA Host', 120), platform: clean_(b.platform || 'unknown', 40), device_token_hash: sha256_(deviceToken), status: 'active', last_seen: new Date().toISOString(), created_at: new Date().toISOString() };
  appendObject_('Devices', device);
  audit_(auth.schoolId, 'host.enrolled', { deviceId: device.device_id, platform: device.platform });
  return { deviceId: device.device_id, deviceToken: deviceToken };
}

function hostHeartbeat_(b) {
  const auth = requireHost_(b);
  const sheet = sheet_('Devices');
  updateObjectRow_(sheet, rowNumberByValue_(sheet, 'device_id', auth.deviceId), { last_seen: new Date().toISOString() });
  return { deviceId: auth.deviceId, status: 'active', serverTime: new Date().toISOString() };
}

function revokeHost_(b) {
  const auth = requireSession_(b);
  requireRole_(auth, ['school_admin','school_owner']);
  const id = required_(b.deviceId, 'Device ID', 100);
  const device = findOne_('Devices', 'device_id', id);
  if (!device || device.school_id !== auth.schoolId) throw new Error('Host not found in this school.');
  updateObjectRow_(sheet_('Devices'), rowNumberByValue_(sheet_('Devices'), 'device_id', id), { status: 'revoked' });
  audit_(auth.schoolId, 'host.revoked', { deviceId: id });
  return { revoked: true };
}

function syncPush_(b) {
  const auth = requireHost_(b);
  const events = Array.isArray(b.events) ? b.events : [];
  if (!events.length || events.length > 100) throw new Error('Submit between 1 and 100 sync events per request.');
  const existingIds = new Set(readObjects_('SyncEvents').filter(function(r) { return r.school_id === auth.schoolId; }).map(function(r) { return r.event_id; }));
  const accepted = [];
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    events.forEach(function(event) {
      const id = required_(event.eventId, 'Event ID', 100);
      if (existingIds.has(id)) return;
      const type = required_(event.entityType, 'Entity type', 60);
      const operation = required_(event.operation, 'Operation', 30);
      const payload = JSON.stringify(event.payload || {});
      if (payload.length > 45000) throw new Error('A sync event exceeds the supported payload size.');
      appendObject_('SyncEvents', { event_id: id, school_id: auth.schoolId, device_id: auth.deviceId, entity_type: type, entity_id: clean_(event.entityId || '', 120), operation: operation, payload_json: payload, created_at: new Date().toISOString() });
      existingIds.add(id);
      accepted.push(id);
    });
  } finally {
    lock.releaseLock();
  }
  audit_(auth.schoolId, 'sync.push', { accepted: accepted.length });
  return { acceptedEventIds: accepted, received: events.length };
}

function syncPull_(b) {
  const auth = requireHost_(b);
  const after = String(b.after || '');
  const rows = readObjects_('SyncEvents').filter(function(r) {
    return r.school_id === auth.schoolId && r.created_at > after;
  }).sort(function(a,b) { return a.created_at.localeCompare(b.created_at); }).slice(0, 200);
  return { events: rows.map(function(r) { return { eventId: r.event_id, entityType: r.entity_type, entityId: r.entity_id, operation: r.operation, payload: JSON.parse(r.payload_json || '{}'), createdAt: r.created_at }; }), nextCursor: rows.length ? rows[rows.length - 1].created_at : after };
}

function schoolProfile_(b) {
  const auth = requireSession_(b);
  const school = findOne_('Schools', 'school_id', auth.schoolId);
  return { school: publicSchool_(school), users: readObjects_('Users').filter(function(u) { return u.school_id === auth.schoolId; }).map(function(u) { return { userId: u.user_id, name: u.name, email: u.email, role: u.role, active: u.active }; }), classes: scoped_('Classes', auth.schoolId), subjects: scoped_('Subjects', auth.schoolId), students: scoped_('Students', auth.schoolId), devices: scoped_('Devices', auth.schoolId).map(function(d) { return { deviceId: d.device_id, name: d.device_name, platform: d.platform, status: d.status, lastSeen: d.last_seen }; }) };
}

function authContext_(b) {
  const auth = requireSession_(b);
  const user = findOne_('Users', 'user_id', auth.userId);
  if (!user || user.school_id !== auth.schoolId || String(user.active) !== 'true') {
    throw new Error('User account is inactive or unavailable.');
  }
  const allowedRoles = ['school_admin','school_owner','teacher','exam_officer','viewer'];
  if (allowedRoles.indexOf(String(user.role)) === -1) {
    throw new Error('User role is not authorized for this service.');
  }
  return {
    userId: auth.userId,
    schoolId: auth.schoolId,
    role: String(user.role),
    name: String(user.name || '')
  };
}


function requireExamManager_(b) {
  const auth = requireSession_(b);
  requireRole_(auth, ['school_admin','school_owner','exam_officer']);
  return auth;
}

function examAudit_(auth, examId, action, details) {
  appendObject_('ExamAudit', {
    event_id: Utilities.getUuid(), school_id: auth.schoolId, exam_id: examId || '',
    actor_id: auth.userId, action: action, details_json: JSON.stringify(details || {}),
    created_at: new Date().toISOString()
  });
}

function positiveInteger_(value, label, max) {
  const number = Number(value);
  if (!Number.isInteger(number) || number < 1 || number > max) {
    throw new Error(label + ' must be a whole number between 1 and ' + max + '.');
  }
  return number;
}

function listQuestions_(b) {
  const auth = requireExamManager_(b);
  const subjectId = clean_(b.subjectId || '', 100);
  const status = clean_(b.status || '', 30);
  const rows = scoped_('Questions', auth.schoolId).filter(function(q) {
    return (!subjectId || q.subject_id === subjectId) && (!status || q.status === status);
  }).sort(function(a, z) { return String(z.updated_at).localeCompare(String(a.updated_at)); });
  return { questions: rows.map(function(q) {
    return {
      questionId: q.question_id, subjectId: q.subject_id, questionType: q.question_type,
      questionText: q.question_text, options: { A:q.option_a, B:q.option_b, C:q.option_c, D:q.option_d },
      correctAnswer: q.correct_answer, explanation: q.explanation, marks: Number(q.marks || 1),
      difficulty: q.difficulty, status: q.status, createdAt: q.created_at, updatedAt: q.updated_at
    };
  }) };
}

function saveQuestion_(b) {
  const auth = requireExamManager_(b);
  const id = clean_(b.questionId || '', 100) || Utilities.getUuid();
  const type = String(b.questionType || 'mcq').toLowerCase();
  if (['mcq','theory'].indexOf(type) === -1) throw new Error('Question type must be MCQ or theory.');
  const text = required_(b.questionText, 'Question text', 10000);
  const subjectId = required_(b.subjectId, 'Subject', 100);
  const subject = findOne_('Subjects', 'record_id', subjectId);
  if (!subject || subject.school_id !== auth.schoolId || subject.active !== 'true') throw new Error('Select an active subject belonging to your school.');
  const options = b.options && typeof b.options === 'object' ? b.options : {};
  const optionA = type === 'mcq' ? required_(options.A, 'Option A', 2000) : '';
  const optionB = type === 'mcq' ? required_(options.B, 'Option B', 2000) : '';
  const optionC = type === 'mcq' ? required_(options.C, 'Option C', 2000) : '';
  const optionD = type === 'mcq' ? required_(options.D, 'Option D', 2000) : '';
  const answer = clean_(b.correctAnswer || '', 2000);
  if (type === 'mcq' && ['A','B','C','D'].indexOf(answer.toUpperCase()) === -1) throw new Error('For an MCQ, choose A, B, C or D as the correct answer.');
  if (type === 'theory' && !answer) throw new Error('Enter the model answer or marking guide for the theory question.');
  const status = String(b.status || 'draft').toLowerCase();
  if (['draft','active','archived'].indexOf(status) === -1) throw new Error('Question status must be draft, active or archived.');
  const now = new Date().toISOString();
  const sheet = sheet_('Questions');
  const row = rowNumberByValue_(sheet, 'question_id', id, true);
  const existing = row ? objectAtRow_(sheet, row) : null;
  if (existing && existing.school_id !== auth.schoolId) throw new Error('Question not found in this school.');
  const values = {
    question_id:id, school_id:auth.schoolId, subject_id:subjectId, question_type:type,
    question_text:text, option_a:optionA, option_b:optionB, option_c:optionC, option_d:optionD,
    correct_answer:type === 'mcq' ? answer.toUpperCase() : answer,
    explanation:clean_(b.explanation || '', 4000), marks:positiveInteger_(b.marks || 1, 'Marks', 1000),
    difficulty:clean_(b.difficulty || 'medium', 30), status:status,
    created_by:existing ? existing.created_by : auth.userId,
    created_at:existing ? existing.created_at : now, updated_at:now
  };
  if (row) updateObjectRow_(sheet, row, values); else appendObject_('Questions', values);
  audit_(auth.schoolId, 'question.saved', { questionId:id, subjectId:subjectId });
  return { questionId:id, saved:true };
}

function deleteQuestion_(b) {
  const auth = requireExamManager_(b);
  const id = required_(b.questionId, 'Question ID', 100);
  const question = findOne_('Questions', 'question_id', id);
  if (!question || question.school_id !== auth.schoolId) throw new Error('Question not found in this school.');
  const used = scoped_('ExamQuestions', auth.schoolId).some(function(r) { return r.question_id === id; });
  if (used) {
    updateObjectRow_(sheet_('Questions'), rowNumberByValue_(sheet_('Questions'), 'question_id', id), { status:'archived', updated_at:new Date().toISOString() });
    audit_(auth.schoolId, 'question.archived', { questionId:id, reason:'Question is attached to an exam.' });
    return { questionId:id, archived:true };
  }
  updateObjectRow_(sheet_('Questions'), rowNumberByValue_(sheet_('Questions'), 'question_id', id), { status:'archived', updated_at:new Date().toISOString() });
  audit_(auth.schoolId, 'question.archived', { questionId:id });
  return { questionId:id, archived:true };
}

function listExams_(b) {
  const auth = requireExamManager_(b);
  const rows = scoped_('Exams', auth.schoolId).sort(function(a,z) { return String(z.updated_at).localeCompare(String(a.updated_at)); });
  return { exams:rows.map(function(e) {
    const questionRows = scoped_('ExamQuestions', auth.schoolId).filter(function(q) { return q.exam_id === e.exam_id; });
    const assignments = scoped_('ExamAssignments', auth.schoolId).filter(function(a) { return a.exam_id === e.exam_id; });
    return {
      examId:e.exam_id, title:e.title, subjectId:e.subject_id, durationMinutes:Number(e.duration_minutes || 0),
      totalMarks:Number(e.total_marks || 0), instructions:e.instructions, status:e.status,
      startAt:e.start_at, endAt:e.end_at, shuffleQuestions:e.shuffle_questions === 'true',
      shuffleOptions:e.shuffle_options === 'true', showResult:e.show_result === 'true',
      questionCount:questionRows.length, questionIds:questionRows.map(function(q) { return q.question_id; }), assignedClasses:assignments.map(function(a) { return a.class_name; }),
      createdAt:e.created_at, updatedAt:e.updated_at
    };
  }) };
}

function saveExam_(b) {
  const auth = requireExamManager_(b);
  const id = clean_(b.examId || '', 100) || Utilities.getUuid();
  const title = required_(b.title, 'Exam title', 180);
  const subjectId = required_(b.subjectId, 'Subject', 100);
  const subject = findOne_('Subjects', 'record_id', subjectId);
  if (!subject || subject.school_id !== auth.schoolId || subject.active !== 'true') throw new Error('Select an active subject belonging to your school.');
  const status = String(b.status || 'draft').toLowerCase();
  if (['draft','scheduled','closed'].indexOf(status) === -1) throw new Error('Exam status must be draft, scheduled or closed. Live publishing is not enabled yet.');
  const startAt = clean_(b.startAt || '', 40);
  const endAt = clean_(b.endAt || '', 40);
  if (startAt && endAt && new Date(endAt).getTime() <= new Date(startAt).getTime()) throw new Error('Exam end time must be after its start time.');
  const sheet = sheet_('Exams');
  const row = rowNumberByValue_(sheet, 'exam_id', id, true);
  const existing = row ? objectAtRow_(sheet, row) : null;
  if (existing && existing.school_id !== auth.schoolId) throw new Error('Exam not found in this school.');
  if (existing && existing.status === 'published') throw new Error('A published exam cannot be edited through this setup API.');
  const now = new Date().toISOString();
  const questionRows = scoped_('ExamQuestions', auth.schoolId).filter(function(q) { return q.exam_id === id; });
  const totalMarks = questionRows.reduce(function(sum, q) { return sum + Number(q.marks || 0); }, 0);
  const values = {
    exam_id:id, school_id:auth.schoolId, title:title, subject_id:subjectId,
    duration_minutes:positiveInteger_(b.durationMinutes, 'Duration in minutes', 1440),
    total_marks:totalMarks, instructions:clean_(b.instructions || '', 5000), status:status,
    start_at:startAt, end_at:endAt, shuffle_questions:String(b.shuffleQuestions === true),
    shuffle_options:String(b.shuffleOptions === true), show_result:String(b.showResult === true),
    created_by:existing ? existing.created_by : auth.userId, created_at:existing ? existing.created_at : now,
    updated_at:now, published_at:existing ? existing.published_at : ''
  };
  if (row) updateObjectRow_(sheet, row, values); else appendObject_('Exams', values);
  examAudit_(auth, id, 'exam.saved', { title:title, status:status });
  return { examId:id, saved:true, totalMarks:totalMarks };
}

function deleteExam_(b) {
  const auth = requireExamManager_(b);
  const id = required_(b.examId, 'Exam ID', 100);
  const exam = findOne_('Exams', 'exam_id', id);
  if (!exam || exam.school_id !== auth.schoolId) throw new Error('Exam not found in this school.');
  if (['published','closed'].indexOf(exam.status) !== -1) throw new Error('A published or closed exam cannot be deleted.');
  updateObjectRow_(sheet_('Exams'), rowNumberByValue_(sheet_('Exams'), 'exam_id', id), { status:'archived', updated_at:new Date().toISOString() });
  examAudit_(auth, id, 'exam.archived', {});
  return { examId:id, archived:true };
}

function setExamQuestions_(b) {
  const auth = requireExamManager_(b);
  const examId = required_(b.examId, 'Exam ID', 100);
  const exam = findOne_('Exams', 'exam_id', examId);
  if (!exam || exam.school_id !== auth.schoolId) throw new Error('Exam not found in this school.');
  if (exam.status !== 'draft') throw new Error('Only draft exams can have their question list changed.');
  if (!Array.isArray(b.questions) || b.questions.length < 1 || b.questions.length > 200) throw new Error('Add between 1 and 200 questions to the exam.');
  const seen = {};
  const prepared = b.questions.map(function(item, index) {
    const questionId = required_(item.questionId, 'Question ID', 100);
    if (seen[questionId]) throw new Error('A question cannot be added to the same exam twice.');
    seen[questionId] = true;
    const question = findOne_('Questions', 'question_id', questionId);
    if (!question || question.school_id !== auth.schoolId || question.status !== 'active') throw new Error('Every selected question must be active and belong to your school.');
    if (question.subject_id !== exam.subject_id) throw new Error('All exam questions must belong to the exam subject.');
    return { question_id:questionId, question_order:index + 1, marks:positiveInteger_(item.marks || question.marks, 'Question marks', 1000) };
  });
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    const sheet = sheet_('ExamQuestions');
    for (let r = sheet.getLastRow(); r >= 2; r--) {
      const record = objectAtRow_(sheet, r);
      if (record.school_id === auth.schoolId && record.exam_id === examId) sheet.deleteRow(r);
    }
    prepared.forEach(function(q) {
      appendObject_('ExamQuestions', {
        record_id:Utilities.getUuid(), school_id:auth.schoolId, exam_id:examId,
        question_id:q.question_id, question_order:q.question_order, marks:q.marks, created_at:new Date().toISOString()
      });
    });
  } finally { lock.releaseLock(); }
  const total = prepared.reduce(function(sum, q) { return sum + q.marks; }, 0);
  updateObjectRow_(sheet_('Exams'), rowNumberByValue_(sheet_('Exams'), 'exam_id', examId), { total_marks:total, updated_at:new Date().toISOString() });
  examAudit_(auth, examId, 'exam.questions_updated', { count:prepared.length, totalMarks:total });
  return { examId:examId, questionCount:prepared.length, totalMarks:total };
}

function assignExamClasses_(b) {
  const auth = requireExamManager_(b);
  const examId = required_(b.examId, 'Exam ID', 100);
  const exam = findOne_('Exams', 'exam_id', examId);
  if (!exam || exam.school_id !== auth.schoolId) throw new Error('Exam not found in this school.');
  if (exam.status !== 'draft' && exam.status !== 'scheduled') throw new Error('Only draft or scheduled exams can be assigned to classes.');
  if (!Array.isArray(b.classNames) || b.classNames.length < 1 || b.classNames.length > 100) throw new Error('Select at least one class.');
  const classes = scoped_('Classes', auth.schoolId);
  const names = [];
  b.classNames.forEach(function(value) {
    const name = required_(value, 'Class name', 100);
    if (names.indexOf(name) !== -1) throw new Error('A class can only be assigned once.');
    if (!classes.some(function(c) { return c.name === name && c.active === 'true'; })) throw new Error('Class ' + name + ' is not an active class in your school.');
    names.push(name);
  });
  const sheet = sheet_('ExamAssignments');
  for (let r = sheet.getLastRow(); r >= 2; r--) {
    const record = objectAtRow_(sheet, r);
    if (record.school_id === auth.schoolId && record.exam_id === examId) sheet.deleteRow(r);
  }
  names.forEach(function(name) {
    appendObject_('ExamAssignments', {
      assignment_id:Utilities.getUuid(), school_id:auth.schoolId, exam_id:examId,
      class_name:name, candidate_count:0, created_at:new Date().toISOString()
    });
  });
  examAudit_(auth, examId, 'exam.classes_assigned', { classes:names });
  return { examId:examId, assignedClasses:names };
}

function requirePlatformAdmin_(b) {
  const expected = PropertiesService.getScriptProperties().getProperty(VICORA.ADMIN_KEY_PROPERTY);
  if (!expected || String(b.adminKey || '') !== expected) throw new Error('Platform administrator access is not configured or the key is invalid.');
}

function requireSession_(b) {
  const token = required_(b.sessionToken, 'Session token', 300);
  const hash = sha256_(token);
  const sessionRow = readObjects_('Sessions').find(function(s) { return s.token_hash === hash && s.revoked !== 'true' && new Date(s.expires_at).getTime() > Date.now(); });
  if (!sessionRow) throw new Error('Session expired or invalid. Please sign in again.');
  const school = findOne_('Schools', 'school_id', sessionRow.school_id);
  if (!school) throw new Error('School account was not found.');
  assertSchoolTrialActive_(school);
  return { userId: sessionRow.user_id, schoolId: sessionRow.school_id, role: findOne_('Users','user_id',sessionRow.user_id).role };
}

function requireHost_(b) {
  const id = required_(b.deviceId, 'Device ID', 100);
  const token = required_(b.deviceToken, 'Device token', 300);
  const device = findOne_('Devices', 'device_id', id);
  if (!device || device.status !== 'active' || device.device_token_hash !== sha256_(token)) throw new Error('Host credentials are invalid or revoked.');
  const school = findOne_('Schools', 'school_id', device.school_id);
  if (!school) throw new Error('School account was not found.');
  assertSchoolTrialActive_(school);
  return { deviceId: id, schoolId: device.school_id };
}

function requireRole_(auth, roles) {
  if (roles.indexOf(auth.role) === -1) throw new Error('Your account role cannot perform this action.');
}

function listSchools_() {
  return readObjects_('Schools').map(publicSchool_);
}

function publicSchool_(s) {
  return {
    schoolId: s.school_id, schoolCode: s.school_code, name: s.school_name,
    schoolType: s.school_type, country: s.country, state: s.state, status: s.status,
    planName: s.plan_name || '', trialDays: Number(s.trial_days || 0),
    trialStartedAt: s.trial_started_at || '', trialExpiresAt: s.trial_expires_at || '',
    subscriptionStatus: s.subscription_status || 'unassigned'
  };
}

function validTrialDays_(value) {
  const days = Number(value);
  if (!Number.isInteger(days) || days < 1 || days > 365) throw new Error('Choose a trial period between 1 and 365 days.');
  return days;
}

function assertSchoolTrialActive_(school) {
  if (!school.subscription_status || school.subscription_status === 'unassigned') throw new Error('Your school has been approved, but a trial period has not yet been assigned. Contact the VICORA platform administrator.');
  if (school.subscription_status !== 'trial' || !school.trial_expires_at || new Date(school.trial_expires_at).getTime() <= Date.now()) {
    throw new Error('Your VICORA free trial has expired. Contact the VICORA platform administrator to extend your access.');
  }
}

function assignTrial_(b) {
  const schoolId = required_(b.schoolId, 'School ID', 100);
  const days = validTrialDays_(b.trialDays);
  const school = findOne_('Schools', 'school_id', schoolId);
  if (!school || school.status !== 'approved') throw new Error('Approved school not found.');
  const now = new Date();
  const expires = new Date(now.getTime() + days * 86400000);
  updateObjectRow_(sheet_('Schools'), rowNumberByValue_(sheet_('Schools'), 'school_id', schoolId), { plan_name: 'Free Trial', trial_days: days, trial_started_at: now.toISOString(), trial_expires_at: expires.toISOString(), subscription_status: 'trial' });
  audit_(schoolId, 'subscription.trial_assigned', { trialDays: days, expiresAt: expires.toISOString() });
  return { schoolId: schoolId, trialDays: days, expiresAt: expires.toISOString(), subscriptionStatus: 'trial' };
}

function scoped_(table, schoolId) {
  return readObjects_(table).filter(function(r) { return r.school_id === schoolId; });
}

function audit_(schoolId, action, details) {
  appendObject_('Audit', { audit_id: Utilities.getUuid(), school_id: schoolId || '', actor_id: 'system-or-authenticated-user', action: action, details_json: JSON.stringify(details || {}), created_at: new Date().toISOString() });
}

function generateSchoolCode_() {
  let code;
  do { code = VICORA.SCHOOL_CODE_PREFIX + '-' + randomToken_().replace(/[^A-Z0-9]/g,'').toUpperCase().slice(0,8); }
  while (findOne_('Schools', 'school_code', code));
  return code;
}

function randomToken_() {
  return Utilities.getUuid().replace(/-/g,'') + Utilities.getUuid().replace(/-/g,'');
}

function sha256_(value) {
  const bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, String(value), Utilities.Charset.UTF_8);
  return bytes.map(function(b) { const v = (b < 0 ? b + 256 : b).toString(16); return v.length === 1 ? '0' + v : v; }).join('');
}

function validEmail_(value) {
  const email = required_(value, 'Email', 180).toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('Enter a valid email address.');
  return email;
}

function required_(value, label, max) {
  const result = clean_(value, max);
  if (!result) throw new Error(label + ' is required.');
  return result;
}

function clean_(value, max) {
  return String(value == null ? '' : value).replace(/[\u0000-\u001F\u007F]/g,' ').trim().slice(0, max || 500);
}

function safeError_(error) {
  const message = error && error.message ? error.message : String(error || 'Unknown error.');
  return message.slice(0, 400);
}

function json_(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(ContentService.MimeType.JSON);
}

function spreadsheet_() {
  const id = PropertiesService.getScriptProperties().getProperty(VICORA.DB_PROPERTY);
  if (!id) throw new Error('Run initializeVicoraBackend() from the Apps Script editor first.');
  return SpreadsheetApp.openById(id);
}

function sheet_(name) {
  const sheet = spreadsheet_().getSheetByName(name);
  if (!sheet) throw new Error('Database sheet missing: ' + name + '. Run initializeVicoraBackend().');
  return sheet;
}

function readObjects_(name) {
  const sheet = sheet_(name);
  const values = sheet.getDataRange().getValues();
  if (values.length < 2) return [];
  const headers = values[0].map(String);
  return values.slice(1).filter(function(row) { return row.some(function(v) { return v !== ''; }); }).map(function(row) {
    const obj = {};
    headers.forEach(function(h, i) { obj[h] = row[i] instanceof Date ? row[i].toISOString() : String(row[i] == null ? '' : row[i]); });
    return obj;
  });
}

function findRows_(name, field, value) {
  return readObjects_(name).filter(function(row) { return String(row[field]).toLowerCase() === String(value).toLowerCase(); });
}

function findOne_(name, field, value) {
  return findRows_(name, field, value)[0] || null;
}

function appendObject_(name, obj) {
  const sheet = sheet_(name);
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(String);
  const row = headers.map(function(header) { return Object.prototype.hasOwnProperty.call(obj, header) ? obj[header] : ''; });
  sheet.appendRow(row);
}

function rowNumberByValue_(sheet, field, value, allowMissing) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(String);
  const col = headers.indexOf(field);
  if (col < 0) throw new Error('Column missing: ' + field);
  if (sheet.getLastRow() < 2) return allowMissing ? 0 : null;
  const found = sheet.getRange(2, col + 1, sheet.getLastRow() - 1, 1).createTextFinder(String(value)).matchEntireCell(true).findNext();
  if (!found) return allowMissing ? 0 : null;
  return found.getRow();
}

function objectAtRow_(sheet, rowNumber) {
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(String);
  const values = sheet.getRange(rowNumber, 1, 1, headers.length).getValues()[0];
  const obj = {};
  headers.forEach(function(h, i) { obj[h] = String(values[i] == null ? '' : values[i]); });
  return obj;
}

function updateObjectRow_(sheet, rowNumber, updates) {
  if (!rowNumber || rowNumber < 2) throw new Error('Record not found.');
  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(String);
  const range = sheet.getRange(rowNumber, 1, 1, headers.length);
  const values = range.getValues()[0];
  headers.forEach(function(header, i) {
    if (Object.prototype.hasOwnProperty.call(updates, header)) values[i] = updates[header];
  });
  range.setValues([values]);
}
