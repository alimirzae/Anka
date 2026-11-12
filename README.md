# ANKA — EPUB library (Phase 1)

ASP.NET Core 10, MySQL, EPUB.js. Anonymous local/community prototype: public upload is intentionally **not authenticated** and must be protected at the reverse proxy before Internet exposure. Use a private or IP-allowlisted staging environment.

## Features
- MySQL-backed EPUB collection and validated EPUB uploads (50 MB max)
- Persian, Azerbaijani Latin, Azerbaijani Arabic-script and Turkish interface
- Browser EPUB reader (pagination/scrolling, dark mode, font size, table of contents, progress, selection, copying, highlights)
- Responsive desktop/mobile interface
- No authentication, payments, or online dictionary API

## Setup
1. Install .NET 10 SDK, ASP.NET Core Hosting Bundle, and MySQL 8+; create a database with `utf8mb4` and a limited DB account allowed to create tables initially.
2. Set Windows machine/service environment variable `ANKA_MYSQL_CONNECTION`, e.g. `Server=127.0.0.1;Port=3306;Database=anka;User ID=anka_app;Password=REPLACE_ME;SslMode=Preferred;`. **Never commit credentials**.
3. `dotnet restore Anka.csproj && dotnet build Anka.csproj -c Release && dotnet publish Anka.csproj -c Release -o publish`.
4. IIS: dedicated app pool "No Managed Code" and matching ASP.NET Core Hosting Bundle. Site physical path `C:\inetpub\anka.iyashil.com`; allow the runner service write access only to this folder and private EPUB storage.
5. Use `/api/health` to test health. On first startup the app creates its `books` table.
6. CDN scripts must load (JSZip and epub.js); for full offline operation vendor them locally and update the CSP.

## Legal and safety
Free-to-read is not the same as free-to-redistribute. Only upload books with verified distribution rights. For a public site, add authentication or a trusted network restriction and abuse prevention before allowing uploads. EPUB markup is untrusted; scripted content is disabled. Validate and scan uploaded files on the production server. LocalStorage highlights/progress are per-browser. No automated text transliteration is claimed: a book in Azerbaijani Latin script remains Latin until a properly converted Arabic-script edition is supplied.

## Pipeline
`.github/workflows/anka-deploy.yml` requires a self-hosted Windows runner labeled `anka`. If another `.csproj` is added to the root tree, adjust discovery to select the web app. Configure DB credentials as **service machine environment variable** for the app process, not GitHub source control.
