# Anka — Web-first Turkish ebook platform

## Decision (2026-11-09)

Build a **web-first** digital bookstore, library and EPUB reader using ASP.NET Core 10 (Razor Pages / SSR) for SEO-friendly catalog/account/admin pages, **ASP.NET Core JSON APIs** for state and reading data, and a **TypeScript browser reader** built on a standards-compliant EPUB engine. Keep the reader independent of the server-rendered storefront. Use PostgreSQL + EF Core, S3-compatible private object storage, background jobs, and a CDN. Deploy on IIS or containers; prioritize an installable PWA later, not native mobile applications now.

Do not build EPUB rendering in Razor itself. Evaluate Readium Web and epub.js with real RTL/Azeri test books before selecting the production renderer. Treat uploaded EPUB files as untrusted: validate ZIP entry limits/path traversal, sanitize active content, scan files, and serve isolated from the app origin.

## Language / script model

The product has three separately selectable **editions**, not three automatic UI translations:
- `az-Arab`: Azerbaijani written with Arabic script; RTL reading and appropriate line-breaking/font shaping.
- `az-Latn`: Azerbaijani written with Latin script; LTR.
- `tr-Latn`: Türkiye Turkish written with Latin script; LTR.

A work is the conceptual book; one work can have zero to three or more editions. Each edition has its own source, rights, EPUB asset, contents, ISBN (if applicable), publication state, version, and metadata. Locale/script are BCP 47 tags. The product interface itself can be localized separately. Do **not** assume a transliteration is equivalent to translation: Turkish of Türkiye and Azerbaijani need editorial translation, and Arabic↔Latin Azerbaijani transliteration needs exception dictionaries and human review.

## Domain

`Work -> Edition -> PublicationAsset / Chapter -> AnnotationAnchor`
`Author`, `Publisher`, `Category`, `RightsGrant`, `Price`, `Order`, `OrderItem`, `Entitlement`, `ReadingProgress`, `Bookmark`, `Highlight`, `Note`, `Collection`, `Review`, `UploadJob`, `ConversionJob`, `AuditEvent`.

Keep page/location anchors **per edition** (EPUB CFI or robust text quote/position anchors). Never copy raw CFI between different script editions; cross-edition mapping is a separate reviewed alignment feature.

## Workflows

1. Publisher/admin creates a Work with author, cover, categories, rights and metadata.
2. Upload an EPUB per edition or import structured manuscript and generate EPUB 3.3 using XHTML, nav, OPF, metadata, CSS, cover; set `page-progression-direction=rtl` for Arabic script and `ltr` for Latin editions.
3. Queue validation (EPUBCheck), security scan, preview, and editorial review; publish only approved versions.
4. Reader purchases or accesses an entitled edition, opens a protected reader session, adjusts type/font/theme, bookmarks, highlights and notes, syncs position across devices.
5. Public catalog pages remain indexable; book content and paid assets require authorization.

## Reader requirements

- Robust RTL/LTR, bidi for mixed digits/foreign names, suitable fonts, keyboard and touch navigation.
- Font scaling, margins, spacing, themes, continuous/paginated modes, table of contents, search, selection, notes, dictionary, progress and history.
- Offline access only with an explicit licensing/DRM strategy and appropriate encrypted caching; not simple public EPUB URLs.
- Accessibility: semantic chapters, image alt text, keyboard/screen reader, reduced motion, WCAG testing.

## Security / operations

Use ASP.NET Core Identity (or OIDC), policy-based roles (reader, publisher, editor, admin), CSRF protection, strict MIME/content verification, rate limits, authorization on all APIs, private object store, signed short-lived URLs, logs/audit, backups and no PII in telemetry. Consider watermarking as deterrence, not DRM; determine rights and payment provider jurisdictions before enabling sales.

## Incremental delivery

1. Foundation: SSR shell, locale/script model, catalog prototype, CI and configuration.
2. Persistence: EF Core migrations, work/edition management, accounts, authorization.
3. EPUB ingest/generate + EPUBCheck pipeline + private storage.
4. In-browser reader, notes, progress and three-edition tests.
5. Publisher tools, payments/entitlements, search, analytics, production hardening.

### Key reference standards

- W3C EPUB 3.3: https://www.w3.org/TR/epub-33/
- Readium Web: https://readium.org/web/
- epub.js: https://github.com/futurepress/epub.js

This document is an implementation blueprint, not a claim that all features are implemented.
