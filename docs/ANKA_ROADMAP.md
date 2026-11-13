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
- [x] Initial email/password accounts with PBKDF2 hashes, HTTP-only secure cookie login and IP rate limit; **pending:** email verification, password reset, OTP, account administration and automated security tests.
- [x] Initial Reader/Publisher role claims and server-side upload restriction; **pending:** administrative role workflow, editor roles, role revocation validation and full multi-tenant authorization audit.
- [x] Remove anonymous access to `POST /api/books` (Publisher/Admin role required, same-origin guard); **pending:** license declaration, pending-content review workflow and ownership checks across all reader/file endpoints.
- [ ] Automated tests for auth, authorization, persistent data, uploads, and migration; working backup/restore.
- [ ] Database migrations preserve existing SQLite and EPUB assets. Design MySQL migration, do not destructively switch in production.

### P1 — ANKA Store (in progress)
- [x] Minimal public catalog and book detail prototypes.
- [x] `/store` searchable public catalog with title/author and script/language filters; **pending:** category, format, price, rights and advanced faceted filters.
- [x] Initial additive `anka_works` + `anka_editions` schema with canonical work ID and independent edition language, script, translator, publisher and content state; **pending:** normalized author/translator/publisher entities and formal license proof attachments.
- [x] Independent edition records with admin association (`/api/admin/editions/{id}/link`) and visible version selector; **pending:** proofreading workflow, aligned previews and editor-reviewed authentic translation content.
- [x] Basic dynamic `/store/book/{id}` detail page with edition language, author, format, size, read and save-to-shelf; **pending:** real cover, publisher, category, rights, chapter list, sample, editions and review state.
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
- [x] Account publisher application, administrator approval and secure publisher submission with own status dashboard; **pending:** publisher organizations, multiple staff and organization-scoped approvals.
- [ ] Upload cover, EPUB/PDF/audio, metadata, category, publication rights, edition script/language, pricing.
- [x] Pending/approved/rejected transitions for publisher and book submissions, preserving rights statements and reviewer; **pending:** draft editing, withdraw/unpublish, full action audit history and publisher notifications.
- [ ] Royalty reports, publisher sales and settlement, content versioning.
- [x] Rights declaration required and uploaded books remain hidden before manual admin approval; **pending:** actual evidence attachments and legal verification process.

### P4 — My Library, audio and subscriptions (not complete)
- [x] First per-user saved bookshelf (`/my-library`) backed by SQLite and authenticated API; **pending:** purchased/free entitlements, collections, favorites, reading status and cross-device progress.
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

## 2026-11-13 phase-one and phase-two implementation checkpoint
- Added `AnkaAccountService.cs`: SQLite account tables, hashed passwords, identity roles, shelf and publisher submission skeleton table.
- Added `/account`: minimal email/password register, login, logout (no real OTP or verified-email recovery yet).
- Added `/my-library`: saved book cards per logged-in user.
- Added `/store/book/{id}`: book detail metadata, reading and add-to-library.
- Public upload `POST /api/books` no longer accepts anonymous users. Existing public book downloads remain accessible. **Do not treat uploads as commercial content:** entitlement, licensing and editorial approval are not complete.
- Publisher role assignment requires a configured 32+ character `ANKA_PUBLISHER_SETUP_KEY` secret and an authenticated account; never commit that secret.
- DataProtection keys persisted in `App_Data/keys`; protect the directory, back it up and set secure IIS file ACLs.
- **No live paid checkout or payment processor is configured.** Never mark phase-two commerce complete without server-verified payments.
- Next priorities: publisher approval workflow and pending-only uploads, authorized content delivery, catalog metadata/edition relationships, database tests, email/OTP verification, payment integration (after providing processor).

## 2026-11-13 additional phases 1–3 implementation
- Admin role bootstraps once using a 32-byte random key stored outside public web root in `App_Data/admin-setup-key.txt`, optionally overridden by `ANKA_ADMIN_SETUP_KEY`. No first-user auto-admin race condition.
- Admin management page `/admin`: approve/reject publisher registration requests and submitted books. Publisher `/publisher`: request approval and see own submission states.
- Publisher upload `/upload` requires authenticated current Publisher/Admin role, proof-of-rights statement, title/author, independent language and script, category, synopsis, translator and publisher metadata.
- Public catalog, book details, file API and server-side reader exclude pending or rejected publisher submissions; book insertion and pending moderation record are one SQLite transaction.
- `anka_works` and `anka_editions` are additive tables preserving existing book IDs, SQLite data and files. Admin can group language editions of the same work; machine transliterations remain labeled unreviewed.
- Store supports title/author, language and category filters; product detail lists independent editions, synopsis, translator and publisher.
- Manual-access book mode and administrator-granted reading entitlements allow authorized access **without** any payment processor; no actual bank charges or fake wallet transactions. Read/file/shelf API permissions are checked by server.
- The `1234` test PIN is **only** usable in ASP.NET Core Development over loopback; it is disabled on published IIS Production. Normal sign-in uses strong passwords, not email/SMS OTP.
- Automated GitHub Actions smoke tests now verify Production startup, health, public catalog, anonymous upload rejection, admin endpoint protection and absence of the test PIN route.
- DataProtection keys and the SQLite App_Data directory must be backed up and ACL-protected. App_Data is excluded from publish artifacts.
- See `docs/ANKA_ADMIN_SETUP.md` for one-time manager activation.
- **Phase 1–3 remain partially incomplete**, notably email/phone verification/password reset, comprehensive tests and edit/revoke roles, formal author/publisher entities and licensed translations, true viewport-reflow pagination and PDF/audio support, full submission history/withdrawal, verified financial checkout/credit ledger, advanced search and reviews. Do not claim the product finished until those are implemented and browser-tested.
