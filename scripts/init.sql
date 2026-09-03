-- Medical AI System - MySQL Initialization
-- This script runs automatically when the MySQL container starts for the first time.

CREATE DATABASE IF NOT EXISTS medical_ai_system
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON medical_ai_system.* TO 'medical_user'@'%';
FLUSH PRIVILEGES;
