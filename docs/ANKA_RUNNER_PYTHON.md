# ANKA Windows runner — Python 3 prerequisite

The self-hosted Windows runner must have a real Python 3 interpreter available to its **runner service account**, not merely to an interactive administrator. Deployment intentionally stops before Publish when backup safety tests cannot run.

## Verified failure (2026-11-15)

GitHub Actions run [43755031038](https://github.com/alimirzae/Anka/actions/runs/43755031038), job `132937167026`, successfully restored and built the .NET project, then failed at **Test SQLite backup safety using temporary fixtures** with:

```
No working Python 3 interpreter found for the runner service account.
```

This is a runner prerequisite failure, **not** evidence that the backup tests failed. The later commit `a0a9fb5` corrected test discovery, but does not install Python.

## Provisioning checklist (administrator action)

1. Install a supported Python 3 release system-wide on the Windows runner from the official Python distribution. Avoid the Microsoft Store app execution alias. Do not install into the IIS application directory or `App_Data`.
2. Confirm the interpreter is executable by the Windows service identity running GitHub Actions (the run above used NETWORK SERVICE), with read/execute permission on its installation path. Avoid granting write permissions to the IIS app pool or repository code.
3. Set `ANKA_PYTHON_EXE` to the **absolute** path of the verified `python.exe` in the runner service environment, or ensure `python`/`py -3` is genuinely resolvable by that identity. Restart the runner service to load environment changes.
4. From the same service identity, verify `python.exe -c "import sys,sqlite3,unittest; print(sys.version)"` succeeds. Python's standard library is sufficient; no pip packages are required.
5. Re-run the ANKA GitHub Actions workflow on `main`. Require successful backup tests, staging validation, deployment, health and security smoke tests before reporting a successful deploy.
6. Confirm production `App_Data`, SQLite, EPUB assets and DataProtection keys remain preserved. Test a **copy** of the backup in an isolated directory; never restore over live production data.

**Fail-closed rule:** do not skip Python tests, replace their result with a success marker, or enable deployment just to get a green build. Do not enable the `1234` development test-login route in Production.

## Acceptance evidence

Record the successful workflow run URL, test counts, publish/deploy outcome, health probes, and isolated restore result in the roadmap. Until those exist, CI and production release remain unverified.
