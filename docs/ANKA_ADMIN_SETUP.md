# ANKA — Initial Admin and Publisher Review (without email or payment gateway)

## Production prerequisites
- ANKA remains deployed from `main` to `anka.iyashil.com`.
- SQLite and all EPUBs in `C:\inetpub\anka.iyashil.com\App_Data` must survive deployment and be backed up.
- `App_Data` must be **outside public/static file serving**, accessible only to the ANKA app pool identity and trusted server administrators.
- No email provider, SMS provider or payment gateway is required for this temporary approval workflow.

## One-time first administrator (server operator only)
1. On the website, register a regular account at `/account` using an email and a strong password (minimum 12 characters). Sign in.
2. On the **IIS server itself**, open PowerShell with sufficient permissions and read the one-time key:

   ```powershell
   (Get-Content 'C:\inetpub\anka.iyashil.com\App_Data\admin-setup-key.txt' -Raw).Trim()
   ```

3. While signed in, open `https://anka.iyashil.com/admin/setup`, paste that secret and click Activate.
4. The server upgrades that account to Admin only if there is no active administrator; the setup file is deleted immediately after a successful activation.
5. Sign out and sign back in so the session receives the new Admin role. Then open `/admin`.

**Do not send the setup key in chat/email, hard-code it in GitHub, or expose App_Data.**
An environment variable named `ANKA_ADMIN_SETUP_KEY` (32+ characters) can alternatively supply the one-time key. Once an administrator exists, bootstrap cannot run again.

## Publisher workflow
- Reader registers and signs in at `/account`.
- Reader opens `/publisher` and submits a publisher identity / publishing-rights statement.
- Admin visits `/admin` and approves or rejects the application.
- The approved publisher must sign out and sign back in to refresh their role.
- Publisher opens `/upload`, selects an EPUB, title, author, language, category and contributors, and includes an explicit publishing-rights declaration.
- The submission is stored as **pending** and is not listed in public Store, Library, file/download or server-side reader until approved.
- Admin visits `/admin` and approves or rejects each book independently. The full audit and rights text stays in SQLite.
- Admin can link a newly approved translation to an existing Work ID so editions appear together.
- ANKA supports the default `تورکجه` (az-Arab), `Türkçe` (tr) and `Az.Turkce` (az-Latn). *Machine transliterations are not proofread translations.*

## Manual book access without payment gateway
- All legacy, authorized free books remain public.
- Admin can change an approved book to **manual authorization required**, then grant that book to a specific registered email through `/admin`.
- Only readers with the grant and administrators can access restricted EPUB files and reading endpoints.
- No payment, invoice, bank transfer verification or fake wallet balance is recorded.
- Do not mark paid sales or subscription purchases as functional. A trusted gateway and transaction verification will be required for commercial checkout.

## Development PIN 1234
- `1234` is available **only** via a development-only `/api/account/test-login` endpoint on loopback.
- It is NOT an OTP sent by email or SMS, and it is NOT available on production IIS.
- It requires an already registered test account and its email.
- Production login uses strong passwords and secured HTTP-only cookies until a legitimate OTP delivery provider is configured.

## Verification
1. Confirm GitHub Actions Release Build and IIS Deploy succeed.
2. Confirm `/api/health` returns HTTP 200.
3. Test register/login/logout, unauthenticated upload rejection, publisher approval, pending book hiding, admin book approval, manual access grants and browser reader behavior.
4. Review database migration, persistent key backup and access logs before enabling public author uploads at scale.

This is a temporary secure workflow, **not a claim** that payment, subscriptions, full PDF/audio, multi-device offline sync or every roadmap requirement is completed.
