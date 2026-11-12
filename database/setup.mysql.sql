-- Execute as a MySQL administrator, then replace the placeholder password.
CREATE DATABASE IF NOT EXISTS anka CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'anka_app'@'localhost' IDENTIFIED BY 'REPLACE_WITH_LONG_RANDOM_PASSWORD';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX ON anka.* TO 'anka_app'@'localhost';
-- If connecting over TCP as 127.0.0.1, adjust the MySQL account host to match your server setup.
