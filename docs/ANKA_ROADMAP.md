# ANKA — Product Roadmap / نقشه راه اجرایی

**Status:** active · **Canonical branch:** `main` · **Deployment:** `anka.iyashil.com` (IIS) · **Initial database:** SQLite.

## Product scope and language rules
ANKA is a minimalist, multilingual digital book platform with these three primary product areas:
- **ANKA Store** — discover/search books, categories, offers, book details and later orders/subscriptions.
- **ANKA Reader** — EPUB first; distraction-free paged reader, touch swipe, offline-capable reading subject to rights, chapters, bookmarks, notes, highlights, dictionary, translation, personal reading progress.
- **ANKA Publisher** — publisher book submissions, independent editions, author/translator metadata, licensing, review, pricing, sales reports.
- **My Library** is shared across the three areas; users own their library and access permissions.
No concerts, theatre, events, seat selection, ticketing or other ANKA Art scope.

Language display names are **تورکجه** = `az-Arab` (Arabic alphabet, default UI and RTL), **Türkçe** = `tr` (Istanbul Turkish Latin), **Az.Turkce** = `az-Latn` (Azerbaijani Turkish Latin), plus **فارسی** = `fa`, **English** = `en`. The user's explicit UI choice should persist; a new visitor gets `az-Arab`. A *sample* or *machine transliteration* must never be advertised as a completed professional translation.

## UI principles
Preserve the existing uncluttered ANKA identity (white background, restrained navy/blue and accents, Anka bird). Mobile-first, fast, accessible touch targets and clean RTL/LTR. Don't clone Fidibo assets, artwork, branding or source code; use it as an interaction benchmark only.

## Work stages and acceptance criteria

### P0 — Safety, persistence, product architecture (not complete)
- [ ] Authentication: passwordless OTP or secure identity, rate limits and account management.
- [ ] Roles: reader, publisher, reviewer/editor, administrator. Scope every API query to authorized user/organization.
- [ ] Replace unauthenticated public `POST /api/books` with protected publisher-only upload workflow; validate EPUB ZIP safety, metadata, licenses, and ownership.
- [ ] Automated tests for auth, authorization, persistent data, uploads, and migration; working backup/restore.
- [ ] Database migrations preserve existing SQLite and EPUB assets. Design MySQL migration, do not destructively switch in production.

### P1 — ANKA Store (in progress)
- [x] Minimal public catalog and book detail prototypes.
- [ ] Dedicated coherent `/store` catalog with filters for title, author, and edition language, category, format, availability (free/paid).
- [ ] Canonical Book/BookEdition, Author, Publisher, Translator, Category and BookLicense model.
- [ ] One book may have three or more **independent authentic** editions, each with rights, review state, content and preview.
- [ ] Detailed product page (cover, edition options, review state, chapter list, sample, attributes, publisher, rights).
- [ ] Pricing, offers and checkout backed by trusted payment processor with server-verified paid entitlements; don't simulate paid purchases.
- [ ] Ratings/reviews with moderation, recommendations, wishlists and search facets.

### P2 — ANKA Reader (in progress)
- [x] Basic EPUB reading, browser progress, side arrows, keyboard support and touch-swipe initial implementation.
- [x] Three-column layout with separate scrollable reading viewport and chapter-panel prototype.
- [ ] Responsive **true viewport-based pagination**; avoid requiring a vertical scroll to complete each nominal page. Fix line layout when font changes.
- [ ] Mobile and desktop manual QA of swipe, gesture conflicts, RTL/LTR, touch selection and keyboard.
- [ ] Personal synced progress, bookmarks and highlights on server; offline access with rights checks.
- [ ] Notes, dictionary, in-context translation selector with explicit privacy notice, font family/size/spacing settings.
- [ ] EPUB and PDF format support and accessibility testing.

### P3 — ANKA Publisher (not complete)
- [x] Prototype upload page exists; currently **public and unsafe** — restrict before public use.
- [ ] Publisher organization onboarding/approval, authenticated dashboard, book submission workflow.
- [ ] Upload cover, EPUB/PDF/audio, metadata, category, publication rights, edition script/language, pricing.
- [ ] Draft/review/approve/publish/reject/withdraw lifecycle and audit log.
- [ ] Royalty reports, publisher sales and settlement, content versioning.
- [ ] Copyright and license verification before public distribution.

### P4 — My Library, audio and subscriptions (not complete)
- [ ] Per-user shelf: owned, free, currently reading, finished, favorite, collections, synchronize devices.
- [ ] Authorized audiobook/podcast streaming, resume position, offline where legally permitted.
- [ ] Subscription plan, billing, entitlement expiration and cancellation/refunds.

## CI/CD and automation gates
- Only `main` is the active ANKA integration and IIS deployment branch.
- Each meaningful change must run GitHub Actions build verification and IIS deployment health checks.
- Preserve `App_Data`, SQLite database and EPUBs; never delete or reset production content.
- A passing compile is **not** proof of correctness: add runtime/browser tests and audit explicitly.
- Hourly ANKA progress checks should read this file, validate current CI status and deliver verified progress only. Continue while incomplete; flag anything requiring user authorization or external configuration.
- Once all acceptance criteria pass, recommend disabling the hourly task; do not call the project complete from compilation alone.

## Implementation status history
- 2026-11-13: feature audit shows minimal book catalog, EPUB, multilingual UI and immersive reader prototype. Store commerce, auth, personal data boundaries, publisher workflow, payments, synchronized data, true reflow pagination and full authorized translations are pending.
