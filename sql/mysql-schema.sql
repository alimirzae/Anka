-- ANKA MySQL 8 / MariaDB compatible; utf8mb4 preserves all Turkish, Persian and Arabic scripts.
-- Keep timestamps as UTC ISO-8601 strings to preserve existing SQLite data exactly.
CREATE TABLE IF NOT EXISTS books (
 id VARCHAR(36) PRIMARY KEY, title VARCHAR(500) NOT NULL, author VARCHAR(300) NOT NULL,
 language VARCHAR(32) NOT NULL, original_script VARCHAR(120) NOT NULL,
 filename VARCHAR(255) NOT NULL, bytes BIGINT NOT NULL, created_utc VARCHAR(40) NOT NULL,
 KEY ix_books_title (title(190))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS anka_users (
 id VARCHAR(36) PRIMARY KEY, email VARCHAR(254) NOT NULL UNIQUE,
 display_name VARCHAR(100) NOT NULL, password_hash VARCHAR(255) NOT NULL,
 role VARCHAR(32) NOT NULL DEFAULT 'Reader', disabled TINYINT NOT NULL DEFAULT 0,
 created_utc VARCHAR(40) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS anka_user_shelves (
 user_id VARCHAR(36) NOT NULL, book_id VARCHAR(36) NOT NULL,
 added_utc VARCHAR(40) NOT NULL, PRIMARY KEY(user_id,book_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS anka_works (
 id VARCHAR(36) PRIMARY KEY, title VARCHAR(500) NOT NULL,
 author VARCHAR(300) NOT NULL, description TEXT NOT NULL,
 category VARCHAR(100) NOT NULL DEFAULT 'General', created_utc VARCHAR(40) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS anka_editions (
 book_id VARCHAR(36) PRIMARY KEY, work_id VARCHAR(36) NOT NULL,
 language VARCHAR(32) NOT NULL, script VARCHAR(120) NOT NULL,
 translator VARCHAR(150) NOT NULL DEFAULT '', content_status VARCHAR(40) NOT NULL DEFAULT 'complete',
 publisher_name VARCHAR(150) NOT NULL DEFAULT '', price_minor BIGINT NOT NULL DEFAULT 0,
 currency VARCHAR(12) NOT NULL DEFAULT 'IRR', KEY ix_editions_work (work_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS anka_book_access (
 book_id VARCHAR(36) PRIMARY KEY, access_mode VARCHAR(12) NOT NULL DEFAULT 'free',
 updated_utc VARCHAR(40) NOT NULL, CONSTRAINT ck_anka_access CHECK(access_mode IN ('free','manual'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS anka_manual_entitlements (
 user_id VARCHAR(36) NOT NULL, book_id VARCHAR(36) NOT NULL,
 granted_by VARCHAR(36) NOT NULL, reason VARCHAR(350) NOT NULL DEFAULT '',
 granted_utc VARCHAR(40) NOT NULL, PRIMARY KEY(user_id,book_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS anka_publisher_requests (
 user_id VARCHAR(36) PRIMARY KEY, statement TEXT NOT NULL,
 state VARCHAR(20) NOT NULL DEFAULT 'pending', requested_utc VARCHAR(40) NOT NULL,
 reviewed_utc VARCHAR(40) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS anka_book_moderation (
 book_id VARCHAR(36) PRIMARY KEY, uploader_id VARCHAR(36) NOT NULL,
 rights_statement TEXT NOT NULL, state VARCHAR(20) NOT NULL DEFAULT 'pending',
 reviewed_by VARCHAR(36) NULL, created_utc VARCHAR(40) NOT NULL,
 reviewed_utc VARCHAR(40) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS anka_publisher_submissions (
 id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL,
 book_id VARCHAR(36) NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'pending',
 rights_statement TEXT NOT NULL, submitted_utc VARCHAR(40) NOT NULL,
 reviewed_utc VARCHAR(40) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
