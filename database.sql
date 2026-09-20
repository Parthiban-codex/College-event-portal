
CREATE DATABASE IF NOT EXISTS `college_event_planner` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `college_event_planner`;

-- 1. Students Table
CREATE TABLE IF NOT EXISTS `students` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL,
    `email` VARCHAR(150) NOT NULL UNIQUE,
    `roll_number` VARCHAR(50) NOT NULL UNIQUE,
    `department` VARCHAR(100) NOT NULL,
    `year_of_study` VARCHAR(20) NOT NULL,
    `phone` VARCHAR(20) NOT NULL,
    `password_hash` VARCHAR(255) NOT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Central Administrators Table
CREATE TABLE IF NOT EXISTS `admins` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL,
    `email` VARCHAR(150) NOT NULL UNIQUE,
    `role` VARCHAR(50) NOT NULL DEFAULT 'Administrator',
    `password_hash` VARCHAR(255) NOT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Clubs Table
CREATE TABLE IF NOT EXISTS `clubs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(150) NOT NULL,
    `code` VARCHAR(50) NOT NULL UNIQUE,
    `category` VARCHAR(50) NOT NULL,
    `faculty_advisor_name` VARCHAR(100) NOT NULL,
    `description` TEXT,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Club Members Table (Faculty, Leader, Coordinator, Volunteer)
CREATE TABLE IF NOT EXISTS `club_members` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `club_id` INT NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `email` VARCHAR(150) NOT NULL UNIQUE,
    `phone` VARCHAR(20) NOT NULL,
    `department` VARCHAR(100) NOT NULL,
    `role` ENUM('faculty', 'leader', 'ex_leader', 'coordinator', 'volunteer') NOT NULL DEFAULT 'volunteer',
    `password_hash` VARCHAR(255) NOT NULL,
    `member_code` VARCHAR(64) NOT NULL UNIQUE,
    `qr_code_image` VARCHAR(255) NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`club_id`) REFERENCES `clubs`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Venues Table
CREATE TABLE IF NOT EXISTS `venues` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(100) NOT NULL,
    `building` VARCHAR(100) NOT NULL,
    `capacity` INT NOT NULL DEFAULT 100,
    `location_details` TEXT,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. Events Table with Multi-Tier Approval Workflow
CREATE TABLE IF NOT EXISTS `events` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `title` VARCHAR(200) NOT NULL,
    `category` VARCHAR(50) NOT NULL,
    `description` TEXT NOT NULL,
    `venue_id` INT NULL,
    `event_date` DATE NOT NULL,
    `start_time` TIME NOT NULL,
    `end_time` TIME NOT NULL,
    `capacity` INT NOT NULL DEFAULT 50,
    `fee` DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    `banner_image` VARCHAR(255) NULL,
    `payment_qr_image` VARCHAR(255) NULL,
    `upi_id` VARCHAR(100) NULL,
    `club_id` INT NULL,
    `created_by_member_id` INT NULL,
    `attendance_incharge_member_id` INT NULL,
    `created_by` INT NULL,
    `status` ENUM('pending_faculty', 'pending_admin', 'upcoming', 'ongoing', 'completed', 'rejected', 'cancelled') NOT NULL DEFAULT 'upcoming',
    `faculty_approved_at` DATETIME NULL,
    `faculty_remarks` TEXT NULL,
    `admin_approved_at` DATETIME NULL,
    `admin_remarks` TEXT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`venue_id`) REFERENCES `venues`(`id`) ON DELETE SET NULL,
    FOREIGN KEY (`club_id`) REFERENCES `clubs`(`id`) ON DELETE SET NULL,
    FOREIGN KEY (`created_by_member_id`) REFERENCES `club_members`(`id`) ON DELETE SET NULL,
    FOREIGN KEY (`attendance_incharge_member_id`) REFERENCES `club_members`(`id`) ON DELETE SET NULL,
    FOREIGN KEY (`created_by`) REFERENCES `admins`(`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. Event Deletion Requests (Club -> Admin)
CREATE TABLE IF NOT EXISTS `event_deletion_requests` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `event_id` INT NOT NULL,
    `requested_by_member_id` INT NOT NULL,
    `requested_by_role` VARCHAR(50) NOT NULL,
    `requested_by_name` VARCHAR(100) NOT NULL,
    `reason` TEXT NOT NULL,
    `status` ENUM('pending', 'approved', 'rejected') NOT NULL DEFAULT 'pending',
    `admin_remarks` TEXT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `reviewed_at` DATETIME NULL,
    FOREIGN KEY (`event_id`) REFERENCES `events`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`requested_by_member_id`) REFERENCES `club_members`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. Registrations & Attendance Table
CREATE TABLE IF NOT EXISTS `registrations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `student_id` INT NOT NULL,
    `event_id` INT NOT NULL,
    `ticket_code` VARCHAR(64) NOT NULL UNIQUE,
    `payment_status` ENUM('free', 'pending', 'verified', 'rejected') NOT NULL DEFAULT 'free',
    `payment_ref_no` VARCHAR(100) NULL,
    `payment_screenshot` VARCHAR(255) NULL,
    `status` ENUM('registered', 'approved', 'rejected', 'attended', 'cancelled') NOT NULL DEFAULT 'registered',
    `qr_code_image` VARCHAR(255) NULL,
    `registered_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `attended_at` DATETIME NULL,
    `attended_by_member_id` INT NULL,
    FOREIGN KEY (`student_id`) REFERENCES `students`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`event_id`) REFERENCES `events`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`attended_by_member_id`) REFERENCES `club_members`(`id`) ON DELETE SET NULL,
    UNIQUE KEY `unique_student_event` (`student_id`, `event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9. Announcements / Notice Board Table
CREATE TABLE IF NOT EXISTS `notifications` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `title` VARCHAR(200) NOT NULL,
    `message` TEXT NOT NULL,
    `event_id` INT NULL,
    `target_audience` ENUM('all', 'registered_students', 'admins', 'clubs') NOT NULL DEFAULT 'all',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`event_id`) REFERENCES `events`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 10. Feedback Table
CREATE TABLE IF NOT EXISTS `feedback` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `student_id` INT NOT NULL,
    `event_id` INT NOT NULL,
    `rating` INT NOT NULL CHECK (`rating` >= 1 AND `rating` <= 5),
    `comments` TEXT,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`student_id`) REFERENCES `students`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`event_id`) REFERENCES `events`(`id`) ON DELETE CASCADE,
    UNIQUE KEY `unique_student_feedback` (`student_id`, `event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
