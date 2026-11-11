# GTMC CBT Examination — RAM and RDP load test

## Why this test exists

The school server has 16 GB RAM and up to 50 students may run the Examination client at the same time through separate Windows RDP sessions. Installer size is not a RAM measurement. This test records memory used by the packaged CBTExamination.exe processes and the server's available physical memory.

## What the current optimisation changes

The Examination desktop launcher disables a small set of browser background services not needed by this fixed-purpose CBT client: background networking, component updates, browser sync, default browser apps, and first-run setup. Normal foreground HTTP/HTTPS traffic to the school CBT server, Chromium rendering, GPU behaviour, sandboxing, context isolation, and Node integration settings remain intact. Chromium background-tab throttling remains enabled.

These are conservative configuration changes, not a promise of a particular RAM saving. The real result must be measured on the school's Windows Server.

## Important test conditions

- Use a test/staging server, not during a real examination.
- Use the same Windows Server version, RDP configuration, network, CBT data volume, and examination content planned for school use.
- Test with the actual 50 student accounts and 50 simultaneous RDP sessions.
- Have students perform realistic actions: login, open the exam, navigate questions, use required calculator or mathematics input, save answers, and submit.
- Do not disable antivirus, Windows security, Electron sandboxing, or examination monitoring to improve a test score.
- Keep normal school server services running so the result reflects real use.

## Test procedure

1. Record the server's idle memory before opening CBT.
2. Start the examination application in 1 RDP session and run the monitor for 10–15 minutes.
3. Repeat with 10, 20, 30, then 50 simultaneous RDP sessions. Do not jump straight to 50 if the server becomes unstable.
4. At each stage, keep the examination open and perform normal question navigation and answer saving.
5. Record server available memory, CPU utilisation, and whether any RDP session freezes, disconnects, or loses work.
6. Repeat the same test with the previous build and the optimised build under comparable conditions.
7. Compare peak and steady-state private memory per session, server available memory, CPU load, and examination reliability.

## Collecting process memory

Copy scripts/measure-examination-memory.ps1 to the server. Open PowerShell as Administrator in the folder containing the script and run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\measure-examination-memory.ps1 -IntervalSeconds 5 -DurationMinutes 30 -OutputPath .\gtmc-examination-memory.csv
```

The CSV records per-RDP-session totals and an ALL row every five seconds. PrivateMemoryMB is useful for comparing application memory; WorkingSetMB shows resident memory. ServerAvailableMemoryMB records available physical memory at the same time.

The script matches the packaged CBTExamination.exe process name, including Chromium child processes that use the same executable image. If a future packaging change changes that image name, update the script before relying on its totals.

## Acceptance decision

Do not approve a 50-student deployment based on installer success alone. Approve only after the 50-session test completes without crashes, freezes, lost answers, or sustained memory growth, and the server retains a safe memory reserve for Windows Server and the CBT backend. Record measured results; do not infer them from installer size.