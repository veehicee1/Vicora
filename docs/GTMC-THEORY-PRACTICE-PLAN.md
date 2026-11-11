# GTMC CBT Desktop Update: Existing Improvements and Theory Examination

Status: Draft implementation scope. This document records the agreed work; it does not claim the new Theory Examination features are implemented.

## 1. Existing desktop improvements already merged in PR #43

Keep these improvements as part of the current CBT application and preserve them during further development:

- Live examination monitoring and candidate status.
- Session pause/resume, including individual candidate controls.
- Recovery of interrupted student sessions.
- Automatic saving and visible save status.
- Stronger examination controls for administrators, including pause/resume, close, time extension, login reset and force submission.
- Display the student's name and registration number in the examination interface.
- Student calculator (standard and scientific).
- Student Grades section, showing grades only when the school has published them.
- Admin-to-student messaging, including class/all/individual recipients, urgent messages and message history/read status.
- Student inbox for receiving messages.

These features were merged into GitHub main in PR #43. They still require deployment and testing on the school server; merging does not mean they have been installed there.

## 2. New work in this update: Theory Examination

- Add theory questions to the existing CBT application, alongside the existing objective examination.
- Allow an examination to contain objective and theory sections together when configured, while also supporting the appropriate section-only setup.
- Provide a clear answer workspace for long-form typed responses, with autosave and recovery.
- Let the teacher/admin configure the answer workspace per question, such as a large blank area, lined answer sheet, fill-in boxes, mathematics working area or a specialised response area.
- Provide mathematics input for fractions, powers, roots, symbols, equations and normal written explanations in the same response.
- Provide tools for students to draw graphs, plot coordinates, sketch curves and create geometry diagrams/shapes/angles where required.
- Let the teacher/admin configure marks, answer keys and marking method for each theory question.
- Support these selectable marking methods:
  - Exact-answer automatic marking.
  - Multiple acceptable answers.
  - Keyword/rule-based marking.
  - Mathematical marking with configured partial marks.
  - Manual teacher marking.
- Support partial marks where configured.
- Allow teachers to review and override automatically awarded marks, while retaining the original automatic mark and the adjusted mark for audit/history.
- Keep question marks and final theory scores within the official examination result workflow.
- AI-assisted marking is excluded from this update.

## 3. Separate future project: Practice Mode

Practice Mode is postponed and must be developed later as a completely separate application, not added to the current CBT desktop update. Its requirements are retained for that future project:

- Practice by subject, topic, difficulty or teacher-created set.
- Objective and theory practice questions.
- Optional timer, unlimited attempts, progress tracking and practice history.
- Correct answers and explanations are revealed only after the student completes and submits the practice test, never after each individual question.
- Practice scores must never alter official examination grades, official examination history or official results.

Do not implement Practice Mode in this update.

## 4. Deferred work

- Mobile camera connection and front-camera proctoring, including head-movement or sound monitoring, remain a separate future update.
- AI-assisted theory marking remains excluded for now.

## 5. Compatibility and safeguards

- Preserve existing CBT features, examination records, scores and historical data.
- Keep the school-server/LAN workflow and offline use; no mandatory cloud dependency.
- Make database changes non-destructively, with safe migrations and backups.
- Keep the application suitable for Windows Server 2016 and multiple students/admins using separate RDP accounts.
- Test recovery, autosave, monitoring, messaging, objective exams, theory answers, marking and result integrity before release.

## 6. Release condition

This is a draft scope only. Do not merge or install on the live server until implementation is complete, automated checks pass, and the user approves testing.
