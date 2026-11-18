# ANKA — SQLite → MySQL cutover (production-safe)

**Status: development branch only. Never merge or publish until all gates pass.**

## Scope
All structured application records are stored in MySQL: accounts, password hashes, role assignments, books and edition metadata, publishers/moderation, user shelves, manual access rights and entitlements. The EPUB binary files and ASP.NET Core DataProtection key ring stay in the existing persistent IIS `App_Data` folder. Do **not** copy database rows alone and discard keys or EPUBs.

Branch: `feature/mysql-transition`. Only `main` deploys to IIS; this branch intentionally cannot deploy automatically.

## Database preparation
1. Create a **new empty** MySQL database (e.g. `anka`) using `utf8mb4`; assign a dedicated user with rights limited to that database. Never reuse another project's application database.
2. Restrict MySQL network exposure to the IIS host, enable transport encryption for remote connections, and securely store credentials outside source control.
3. Configure ASP.NET Core environment variable `ConnectionStrings__AnkaMySql` (as a service/app pool environment setting or a protected IIS config secret), e.g. `Server=127.0.0.1;Port=3306;Database=anka;User ID=anka_app;Password=REDACTED;CharSet=utf8mb4;`. Never commit actual passwords.
4. MySQL provider: `MySqlConnector` NuGet 2.6.2, connection source: `AnkaDatabase.cs`; schema: `sql/mysql-schema.sql`. Missing connection strings deliberately block startup rather than silently creating empty SQLite data.
5. Verify MySQL service is running and the application user can connect. Keep the current IIS site on SQLite until cutover is approved.

## Safe data-transfer procedure
1. Put the site into a controlled maintenance window **after** a full externally stored backup of the SQLite database, WAL/SHM-consistent snapshot, EPUBs, and DataProtection keys. Existing `scripts/backup-anka.py` currently needs Windows SQLite-handle regression fixes; do not rely on a backup that has not passed independent verification.
2. Use only the verified, standalone SQLite backup copy named `anka.db` as input; never the live IIS `App_Data\anka.db`.
3. On the migration host, install `mysql-connector-python` into a dedicated Python environment.
4. Set `ANKA_MYSQL_PASSWORD` securely for the migration process. Run the importer first without `--apply` to inspect table counts, then with `--apply`. The destination **must be empty**. It runs an integrity check, copies all 10 known tables, and verifies full row fingerprints before transaction commit. Unknown source columns cause a hard failure.
5. Validate totals of users, books, publishers, access grants and reading shelves. Validate specific non-ASCII title/author text. Verify every `books.filename` exists under IIS `App_Data\epubs`.
6. Restore-test the backup and execute application auth/reader/ownership tests against a **separate staging deployment** using the MySQL copy. Do not expose publisher upload or account setup publicly during testing.
7. Once tested, temporarily stop site writes, refresh a final consistent SQLite snapshot, **recreate the empty MySQL staging target**, repeat migration, verify counts/hashes and perform the controlled production cutover.
8. Publish the MySQL branch only after code review and passing CI. Check `/api/health`, account login, book lists, authorized EPUB downloads, publisher workflows, UI languages, and user libraries. The first-admin setup key and DataProtection keys persist on the IIS filesystem.
9. Keep the original SQLite snapshot and existing binaries for a tested rollback. **Do not allow writes to both SQLite and MySQL in parallel**; rollback after MySQL takes writes requires reconciling those writes.

## Example importer (replace hostname and database/user)
```powershell
$env:ANKA_MYSQL_PASSWORD = Read-Host "MySQL migration password"
$repo = "C:\actions-runner\_work\Anka\Anka"
python -m pip install mysql-connector-python
python "$repo\scripts\migrate-sqlite-to-mysql.py" --sqlite-snapshot "D:\AnkaBackups\snapshot\anka.db" --host 127.0.0.1 --database anka --user anka_migrator
# Only once the empty-target checks pass:
python "$repo\scripts\migrate-sqlite-to-mysql.py" --sqlite-snapshot "D:\AnkaBackups\snapshot\anka.db" --host 127.0.0.1 --database anka --user anka_migrator --apply
Remove-Item Env:\ANKA_MYSQL_PASSWORD
```

## Mandatory acceptance gates
- [ ] MySQL connection from Windows IIS identity verified.
- [ ] Latest branch restored/build successful on .NET 10 (no unresolved compiler errors).
- [ ] SQLite backup regression tests pass on Windows and independent restore validation passes.
- [ ] Migration dry-run counts match production snapshot and apply succeeds on isolated MySQL.
- [ ] All 10 migrated tables have verified row fingerprints.
- [ ] EPUB filesystem and DataProtection keys retained, inventories checked.
- [ ] Role revocation, publisher ownership and purchase/manual-entitlement boundaries tested.
- [ ] A staging web deployment passes health and interactive smoke tests.
- [ ] Production publish, cutover, monitored rollback and post-cutover backups prepared.

**Important:** This migration does not implement missing OTP, phone fields, reviews or reading-progress tables. Those features require separate schema and application work; the existing ANKA records are preserved in MySQL.
