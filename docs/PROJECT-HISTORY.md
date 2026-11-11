# GTMC CBT – Complete Project History

## Full project history (reconstructed from GitHub records)

This section expands the original artifact-only list into a project development register. It is based on the repository's pull requests, release records, commits and Actions history available at the time this report was updated (11 November 2026).

### Project timeline

| Period (UTC) | Recorded milestone |
|---|---|
| 31 October 2026 | Earliest workflow activity currently visible in GitHub Actions. The earliest visible run is [CI run 41218900943](https://github.com/sheggun1/CBT-GTMC/actions/runs/41218900943). This is the earliest record found in the Actions history checked, not necessarily the date the idea or source code was first created. |
| 8 November 2026 | First recorded pull requests (#1–#13): Admin dashboard/mobile layout, offline Windows and Android packaging, separate Admin and Examination apps, central school-server connection, answer recovery during interruptions, Wi-Fi/hotspot hosting and Android release signing. |
| 8–9 November 2026 | Android startup/file-picker fixes, exam creation/question-bank fixes, UI refresh, cloud-sync/API planning and prototype, backup/restore safety and packaging, diagnostics, and initial desktop clients. |
| 9–10 November 2026 | Electron desktop Admin and Examination clients, Windows Server diagnostics, separate offline installers, per-user installation fixes, and the combined desktop improvements. |
| 11 November 2026 | Theory examination and marking, admin-controlled school-wide themes, installer packaging fixes, three separate offline installers, lightweight Examination runtime settings and RAM test documentation, and this historical report. |

### Pull-request development register

The register below records the pull requests found in the repository. “Merged” means GitHub records a merge; it does not mean the feature has been tested on the school's live server. PR #41 was still open when this report was checked.

| PR | Date merged (UTC) | Development change | GitHub record |
|---:|---|---|---|
| 1 | 8 Nov 2026 | Improve CBT administrator dashboard and mobile layout | [PR #1](https://github.com/sheggun1/CBT-GTMC/pull/1) |
| 2 | 8 Nov 2026 | Add dual-mode offline Windows and Android packaging | [PR #2](https://github.com/sheggun1/CBT-GTMC/pull/2) |
| 3 | 8 Nov 2026 | Add mobile Admin Console access to Android CBT app | [PR #3](https://github.com/sheggun1/CBT-GTMC/pull/3) |
| 4 | 8 Nov 2026 | Split GTMC CBT into Admin and Examination apps | [PR #4](https://github.com/sheggun1/CBT-GTMC/pull/4) |
| 5 | 8 Nov 2026 | Start central-server architecture and UI/UX refresh | [PR #5](https://github.com/sheggun1/CBT-GTMC/pull/5) |
| 6 | 8 Nov 2026 | Connect Admin and Examination apps to one central school server | [PR #6](https://github.com/sheggun1/CBT-GTMC/pull/6) |
| 7 | 8 Nov 2026 | Harden desktop connection preferences and add quality checks | [PR #7](https://github.com/sheggun1/CBT-GTMC/pull/7) |
| 8 | 8 Nov 2026 | Preserve student answers during temporary network interruptions | [PR #8](https://github.com/sheggun1/CBT-GTMC/pull/8) |
| 9 | 8 Nov 2026 | Fix Admin server settings JavaScript syntax | [PR #9](https://github.com/sheggun1/CBT-GTMC/pull/9) |
| 10 | 8 Nov 2026 | Add offline Wi-Fi and hotspot exam hosting | [PR #10](https://github.com/sheggun1/CBT-GTMC/pull/10) |
| 11 | 8 Nov 2026 | Add permanent signing for Android release APKs | [PR #11](https://github.com/sheggun1/CBT-GTMC/pull/11) |
| 12 | 8 Nov 2026 | Prevent accidental exit from Android Admin startup dialog | [PR #12](https://github.com/sheggun1/CBT-GTMC/pull/12) |
| 13 | 8 Nov 2026 | Fix Android Admin startup mode choices visibility | [PR #13](https://github.com/sheggun1/CBT-GTMC/pull/13) |
| 14 | 9 Nov 2026 | Fix Android Admin file picker for imports | [PR #14](https://github.com/sheggun1/CBT-GTMC/pull/14) |
| 15 | 9 Nov 2026 | Fix exam creation button event binding | [PR #15](https://github.com/sheggun1/CBT-GTMC/pull/15) |
| 16 | 9 Nov 2026 | Fix question correct-answer selection when saving | [PR #16](https://github.com/sheggun1/CBT-GTMC/pull/16) |
| 17 | 9 Nov 2026 | Fix exam creation button binding inside modal | [PR #17](https://github.com/sheggun1/CBT-GTMC/pull/17) |
| 18 | 9 Nov 2026 | Fix exam creation handler syntax | [PR #18](https://github.com/sheggun1/CBT-GTMC/pull/18) |
| 19 | 9 Nov 2026 | Refresh Admin and Student UI/UX | [PR #19](https://github.com/sheggun1/CBT-GTMC/pull/19) |
| 20 | 9 Nov 2026 | Fix Android hotspot hosting mode switching | [PR #20](https://github.com/sheggun1/CBT-GTMC/pull/20) |
| 21 | 9 Nov 2026 | Plan cloud sync and Google Drive backup architecture | [PR #21](https://github.com/sheggun1/CBT-GTMC/pull/21) |
| 22 | 9 Nov 2026 | Define GTMC CBT cloud API contract | [PR #22](https://github.com/sheggun1/CBT-GTMC/pull/22) |
| 23 | 9 Nov 2026 | Add isolated Apps Script cloud API prototype | [PR #23](https://github.com/sheggun1/CBT-GTMC/pull/23) |
| 24 | 9 Nov 2026 | Add isolated backup safety regression tests | [PR #24](https://github.com/sheggun1/CBT-GTMC/pull/24) |
| 25 | 9 Nov 2026 | Document safe backup and restore architecture | [PR #25](https://github.com/sheggun1/CBT-GTMC/pull/25) |
| 26 | 9 Nov 2026 | Add safe offline SQLite restore utility | [PR #26](https://github.com/sheggun1/CBT-GTMC/pull/26) |
| 27 | 9 Nov 2026 | Fix cross-platform safe restore tests | [PR #27](https://github.com/sheggun1/CBT-GTMC/pull/27) |
| 28 | 9 Nov 2026 | Fix isolated backup download regression test | [PR #28](https://github.com/sheggun1/CBT-GTMC/pull/28) |
| 29 | 9 Nov 2026 | Package restore engine for Windows and Android | [PR #29](https://github.com/sheggun1/CBT-GTMC/pull/29) |
| 30 | 9 Nov 2026 | Upload Windows restore utility as separate artifact | [PR #30](https://github.com/sheggun1/CBT-GTMC/pull/30) |
| 31 | 9 Nov 2026 | Fix standalone Examination app window | [PR #31](https://github.com/sheggun1/CBT-GTMC/pull/31) |
| 32 | 9 Nov 2026 | Fix Windows packaging of embedded Examination window | [PR #32](https://github.com/sheggun1/CBT-GTMC/pull/32) |
| 33 | 9 Nov 2026 | Add diagnostics for Windows Server Examination launcher | [PR #33](https://github.com/sheggun1/CBT-GTMC/pull/33) |
| 34 | 9 Nov 2026 | Add visible console diagnostics for Examination startup | [PR #34](https://github.com/sheggun1/CBT-GTMC/pull/34) |
| 35 | 9 Nov 2026 | Build uniquely named Windows Server Examination diagnostic | [PR #35](https://github.com/sheggun1/CBT-GTMC/pull/35) |
| 36 | 9 Nov 2026 | Fix Windows build workflow newline handling | [PR #36](https://github.com/sheggun1/CBT-GTMC/pull/36) |
| 37 | 9 Nov 2026 | Add standalone Electron Examination desktop client | [PR #37](https://github.com/sheggun1/CBT-GTMC/pull/37) |
| 38 | 9 Nov 2026 | Add standalone Electron Admin desktop app | [PR #38](https://github.com/sheggun1/CBT-GTMC/pull/38) |
| 39 | 9 Nov 2026 | Add Electron Examination client | [PR #39](https://github.com/sheggun1/CBT-GTMC/pull/39) |
| 40 | 10 Nov 2026 | Add separate offline Windows installer for Examination | [PR #40](https://github.com/sheggun1/CBT-GTMC/pull/40) |
| 41 | Open at report time | Add separate offline Windows installer for Admin — **not merged at report time** | [PR #41](https://github.com/sheggun1/CBT-GTMC/pull/41) |
| 42 | 10 Nov 2026 | Fix Admin offline installer to install per Windows user | [PR #42](https://github.com/sheggun1/CBT-GTMC/pull/42) |
| 43 | 11 Nov 2026 | Build combined GTMC CBT desktop improvements | [PR #43](https://github.com/sheggun1/CBT-GTMC/pull/43) |
| 44 | 11 Nov 2026 | Add Theory Examination to desktop update | [PR #44](https://github.com/sheggun1/CBT-GTMC/pull/44) |
| 45 | 11 Nov 2026 | Develop Theory Examination and Admin Theme Manager | [PR #45](https://github.com/sheggun1/CBT-GTMC/pull/45) |
| 46 | 11 Nov 2026 | Package GTMC CBT as one combined Windows installer | [PR #46](https://github.com/sheggun1/CBT-GTMC/pull/46) |
| 47 | 11 Nov 2026 | Provide separate fresh and update installers | [PR #47](https://github.com/sheggun1/CBT-GTMC/pull/47) |
| 48 | 11 Nov 2026 | Fix Windows installer source and output paths | [PR #48](https://github.com/sheggun1/CBT-GTMC/pull/48) |
| 49 | 11 Nov 2026 | Fix source paths for both Windows installers | [PR #49](https://github.com/sheggun1/CBT-GTMC/pull/49) |
| 50 | 11 Nov 2026 | Add three separate uncompressed offline CBT installers | [PR #50](https://github.com/sheggun1/CBT-GTMC/pull/50) |
| 51 | 11 Nov 2026 | Fix Windows installer compression verification | [PR #51](https://github.com/sheggun1/CBT-GTMC/pull/51) |
| 52 | 11 Nov 2026 | Add lightweight Examination runtime settings and RAM load-test plan | [PR #52](https://github.com/sheggun1/CBT-GTMC/pull/52) |
| 53 | 11 Nov 2026 | Add automatic CBT artifact and version report | [PR #53](https://github.com/sheggun1/CBT-GTMC/pull/53) |

### Published Android release history

These are tagged GitHub releases with signed release APK assets. They are separate from debug APK artifacts used for testing.

| Release tag | Published (UTC) | Admin APK | Examination APK | Release notes |
|---|---|---|---|---|
| v1.0.1 | 8 Nov 2026 | [Download Admin APK](https://github.com/sheggun1/CBT-GTMC/releases/download/v1.0.1/app-admin-release.apk) | [Download Examination APK](https://github.com/sheggun1/CBT-GTMC/releases/download/v1.0.1/app-examination-release.apk) | Initial release line covering Admin dashboard/mobile access, separate Admin and Examination apps, central server connection, answer recovery, Wi-Fi/hotspot hosting and Android signing. [Release page](https://github.com/sheggun1/CBT-GTMC/releases/tag/v1.0.1) |
| v1.0.2 | 8 Nov 2026 | [Download Admin APK](https://github.com/sheggun1/CBT-GTMC/releases/download/v1.0.2/app-admin-release.apk) | [Download Examination APK](https://github.com/sheggun1/CBT-GTMC/releases/download/v1.0.2/app-examination-release.apk) | Android Admin startup dialog safety fix. [Release page](https://github.com/sheggun1/CBT-GTMC/releases/tag/v1.0.2) |
| v1.0.3 | 9 Nov 2026 | [Download Admin APK](https://github.com/sheggun1/CBT-GTMC/releases/download/v1.0.3/app-admin-release.apk) | [Download Examination APK](https://github.com/sheggun1/CBT-GTMC/releases/download/v1.0.3/app-examination-release.apk) | Android Admin startup mode-choice visibility fix. [Release page](https://github.com/sheggun1/CBT-GTMC/releases/tag/v1.0.3) |

### Full build and source history

- [All GitHub Actions workflow runs](https://github.com/sheggun1/CBT-GTMC/actions) — GitHub reported **395 workflow runs** when this report was checked. This includes successful, failed and repeated attempts; a failed run is retained as history and is not a downloadable successful build.
- [All repository commits](https://github.com/sheggun1/CBT-GTMC/commits/main) — source-code change history.
- [All pull requests](https://github.com/sheggun1/CBT-GTMC/pulls?q=is%3Apr) — review and merge history.
- [All releases](https://github.com/sheggun1/CBT-GTMC/releases) — tagged release packages.

The oldest Actions activity found in the records checked is 31 October 2026. The first recorded pull request is #1 on 8 November 2026. These are the earliest records surfaced by the current repository queries; they should not be treated as proof that no earlier local or unpushed work existed.

### How to interpret the history

- A pull request records a proposed code change; a merged PR means that change entered the target branch.
- A successful workflow means that particular automated job completed. It does not prove installation or real-world school testing.
- An artifact is a downloadable output from a build. Not every commit or pull request produces an installer.
- A release is a separately tagged and published package. Do not confuse release APKs with debug APKs.
- Failed builds are intentionally part of the historical record so that previous problems and their later fixes can be traced.
- GitHub Actions artifact downloads can expire under repository retention settings. The run and PR links remain useful history even if an artifact is no longer downloadable.
