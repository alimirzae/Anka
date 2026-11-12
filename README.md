# Anka — Blazor Server + SQLite (Phase 1)

.NET 10 ASP.NET Core Blazor Server with interactive server rendering, SQLite, and EPUB.js.
No authentication in the prototype. The upload endpoint is public unless access is restricted at IIS/reverse proxy.

## Storage
- Database: `C:\inetpub\anka.iyashil.com\App_Data\anka.db`
- Uploaded EPUB: `C:\inetpub\anka.iyashil.com\App_Data\epubs`
- Both folders are created on startup and retained across deployments.
- **No MySQL and no production connection string required.** SQLite works automatically.
- `App_Data` is outside the web-exposed `wwwroot`.

## Server (one-time)
1. Install the .NET 10 ASP.NET Core Hosting Bundle and restart IIS once after installation if necessary.
2. Run elevated PowerShell:
   `& "C:\Program Files\dotnet\dotnet.exe" --list-runtimes`
3. To configure the site and set folder ACLs, run `scripts/configure-anka-iis-sqlite.ps1` from an administrator PowerShell.
   The script checks the Anka IIS binding and grants Full Control to its **IIS application pool identity** for only the Anka directory, and Modify to **NETWORK SERVICE** for publishing.
4. GitHub workflow `anka-deploy.yml` builds, stages, and deploys; it preserves `App_Data` and never requires a MySQL readiness marker.
5. Confirm `https://anka.iyashil.com/api/health` returns JSON.

## Important
- **Public upload without login is unsafe on the public internet.** Before exposing the app, restrict POST `/api/books` to trusted IPs at the reverse proxy, IIS URL authorization, or another upload gateway. Do not assume `DisableAntiforgery()` provides upload protection.
- Back up `App_Data` including the SQLite database and EPUB files.
- Only distribute ebooks with verified redistribution rights; free downloads are not automatically public domain.
- Latin Azerbaijani and Arabic-script Azerbaijani are separately supported interface languages; automatic book-script conversion is not yet completed.
- EPUB.js and JSZip currently load from CDN and need internet connectivity.
