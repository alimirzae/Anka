# Anka

Web-first digital library and EPUB publishing platform for three Turkish reading editions:

- `az-Arab` — Azerbaijani in Arabic script (RTL)
- `az-Latn` — Azerbaijani in Latin script (LTR)
- `tr-Latn` — Türkiye Turkish in Latin script (LTR)

## Development

Requires .NET 10 SDK.

```bash
dotnet run --project src/Anka.Web
```

Open the localhost URL printed by ASP.NET Core. The starter site includes a responsive landing page, three edition cards, `GET /api/editions/locales`, and `GET /health`.

**Status:** Foundation prototype only; EPUB import/export/reader, authentication, payments and catalog persistence are **not yet implemented**.

See [architecture and phased roadmap](docs/ARCHITECTURE.md).
