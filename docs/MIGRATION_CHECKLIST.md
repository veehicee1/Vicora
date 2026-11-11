# VICORA migration checklist

## Completed
- [x] Independent private repository verified: `veehicee1/Vicora`.
- [x] VICORA product foundation and scope documented.
- [x] Original repository remains untouched.

## Remaining for a complete source migration
- [ ] Obtain a complete export of the latest `sheggun1/CBT-GTMC` source tree.
- [ ] Include backend/API source and configuration templates.
- [ ] Include Android host and proctor source.
- [ ] Include Windows desktop, server and installer source.
- [ ] Include tests, CI workflows, scripts, static assets and documentation.
- [ ] Compare branch, tag and commit inventory against the source repository.
- [ ] Scan files for secrets and school/student data.
- [ ] Build and test the independent VICORA application.
- [ ] Upload verified application source and the ZIP package.
- [ ] Obtain approval before production deployment.

## Security
- Never commit credentials, API keys, database URLs, signing keys or access tokens.
- Use environment-variable templates with placeholder names only.
- Do not copy school/student production data into this repository.
- Rotate credentials if any were exposed in an earlier workflow.
