# VICORA product module register

| Module | Planned responsibility | Current status |
|---|---|---|
| VICORA School | School setup, classes, subjects, students, staff, fees and administration | Scope documented; full source not yet imported |
| VICORA CBT | Question banks, exam scheduling, secure delivery, marking and results | Legacy reference files exist outside this repository; full source not yet imported |
| VICORA Learn | E-library, curriculum, schemes, notes, assignments and practice | Scope documented |
| VICORA Admin | Platform and school configuration, roles, audit and operations | Scope documented |
| VICORA Parent | Parent access, results, announcements and enquiries | Scope documented |
| VICORA Analytics | Broadsheets, rankings, trends and exports | Scope documented |
| VICORA AI | Curriculum-aligned educational assistance | Scope documented |
| VICORA Host | Android local host, durable sync and proctor mode | Architecture notes documented |
| VICORA Desktop | Windows admin/examination clients and server tools | Architecture notes documented |

## Non-negotiable principles

- Preserve existing features and historical data.
- Make additive, controlled changes; do not discard the existing implementation.
- Keep school data isolated by tenant/workspace.
- Enforce permissions on the server, not only in the interface.
- Maintain offline operation and reliable result synchronisation where required.
- Use the approved curriculum as the source of truth for learning content.
