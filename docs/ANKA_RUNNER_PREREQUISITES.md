# ANKA self-hosted Windows runner prerequisites

## Verified blocker (2026-11-15)
GitHub Actions run [#175](https://github.com/alimirzae/Anka/actions/runs/43674235118) compiled the .NET 10 app successfully, but **did not deploy**. The required SQLite backup regression gate failed because neither `python` nor `py -3` was available to the runner service. Do **not** disable this gate or treat a successful compile as a successful deployment.

## One-time administrator action
1. Install a maintained **64-bit Python 3** release from the official Python distribution on the self-hosted Windows machine. Use an installation accessible to the GitHub Actions runner **service identity** (not just the interactive administrator).
2. Ensure the interpreter is on the service account's PATH, or configure the service environment so `python --version` or `py -3 --version` works in a **new runner job**. Restart the runner service if its environment was changed.
3. In a runner job, verify:
   ```powershell
   python --version
   python -m unittest discover -s tests -p 'test_backup_anka.py' -v
   ```
   If using the launcher instead, run `py -3 -m unittest discover -s tests -p 'test_backup_anka.py' -v`.
4. Trigger the ANKA workflow on `main` and inspect the **SQLite backup safety** step, subsequent publish/deploy steps and live health checks. Never manually copy or replace `App_Data`, production SQLite files, EPUB assets or DataProtection keys as a workaround.

## Security and acceptance
- Keep the backup tests mandatory and fail-closed; do not install Python by downloading unverified binaries in the workflow.
- The tests use temporary fixtures, not production data.
- This runner prerequisite does **not** complete the roadmap's backup/restore acceptance criterion: actual restore rehearsals, EPUB copies and DataProtection-key recovery are still required.
- Keep paid checkout disabled until a verified payment provider is configured. Keep test PIN 1234 restricted to isolated loopback Development; preserve the default `az-Arab` UI.
