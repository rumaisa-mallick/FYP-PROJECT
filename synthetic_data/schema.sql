-- ============================================================================
-- Projexa MVP - MySQL schema (PROPOSED)
-- ----------------------------------------------------------------------------
-- Engine: InnoDB   Charset: utf8mb4
--
-- This schema is designed to match the output of
-- synthetic_data/generate_synthetic_data.py and to support:
--   * FastAPI /ai/assign  -> employee capacity + task estimated_hours
--   * FastAPI /ai/risk    -> task status/due dates, task_dependencies, project health
--   * React dashboard     -> projects, tasks, employees read model
--
-- It is a NORMALIZED design: departments/users/skills/projects/tasks/dependencies,
-- with join tables for the many-to-many relations (employee_skills) and a
-- self-referencing FK for the org hierarchy (employees.manager_id).
--
-- Review with the backend owner (Mariyum) before freezing; adjust ENUM values,
-- column widths and decimal precision to taste - the generator emits values that
-- fit within these definitions.
-- ============================================================================

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS task_dependencies;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS employee_skills;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS skills;
DROP TABLE IF EXISTS departments;
SET FOREIGN_KEY_CHECKS = 1;


-- ----------------------------------------------------------------------------
-- departments : organisational units
-- ----------------------------------------------------------------------------
CREATE TABLE departments (
  department_id  INT UNSIGNED NOT NULL AUTO_INCREMENT,
  name           VARCHAR(100) NOT NULL,
  cost_center    VARCHAR(20)  NOT NULL,
  location       VARCHAR(100) NOT NULL,
  PRIMARY KEY (department_id),
  UNIQUE KEY uq_departments_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ----------------------------------------------------------------------------
-- skills : master list of skills (categories group related skills)
-- ----------------------------------------------------------------------------
CREATE TABLE skills (
  skill_id  INT UNSIGNED NOT NULL AUTO_INCREMENT,
  name      VARCHAR(100) NOT NULL,
  category  VARCHAR(50)  NOT NULL,
  PRIMARY KEY (skill_id),
  UNIQUE KEY uq_skills_name (name),
  KEY idx_skills_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ----------------------------------------------------------------------------
-- employees : the "users" of the system (50 seeded)
-- ----------------------------------------------------------------------------
CREATE TABLE employees (
  employee_id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
  full_name              VARCHAR(150) NOT NULL,
  email                  VARCHAR(180) NOT NULL,
  title                  VARCHAR(120) NOT NULL,
  seniority              ENUM('Junior','Mid','Senior','Lead') NOT NULL,
  department_id          INT UNSIGNED NOT NULL,
  manager_id             INT UNSIGNED NULL,
  employment_type        ENUM('Full-time','Part-time','Contract') NOT NULL DEFAULT 'Full-time',
  weekly_capacity_hours  DECIMAL(5,2) NOT NULL DEFAULT 40.00,
  hire_date              DATE NOT NULL,
  is_active              TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (employee_id),
  UNIQUE KEY uq_employees_email (email),
  KEY idx_employees_department (department_id),
  KEY idx_employees_manager (manager_id),
  CONSTRAINT fk_employees_department
    FOREIGN KEY (department_id) REFERENCES departments (department_id),
  CONSTRAINT fk_employees_manager
    FOREIGN KEY (manager_id) REFERENCES employees (employee_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ----------------------------------------------------------------------------
-- employee_skills : many-to-many employees <-> skills, with proficiency
-- ----------------------------------------------------------------------------
CREATE TABLE employee_skills (
  employee_id       INT UNSIGNED NOT NULL,
  skill_id          INT UNSIGNED NOT NULL,
  proficiency       TINYINT UNSIGNED NOT NULL,  -- 1 (novice) .. 5 (expert)
  years_experience  DECIMAL(4,1) NOT NULL DEFAULT 0,
  PRIMARY KEY (employee_id, skill_id),
  KEY idx_emp_skills_skill (skill_id),
  CONSTRAINT fk_emp_skills_employee
    FOREIGN KEY (employee_id) REFERENCES employees (employee_id) ON DELETE CASCADE,
  CONSTRAINT fk_emp_skills_skill
    FOREIGN KEY (skill_id) REFERENCES skills (skill_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ----------------------------------------------------------------------------
-- projects : 10 seeded projects, each owned by a department + a manager
-- ----------------------------------------------------------------------------
CREATE TABLE projects (
  project_id       INT UNSIGNED NOT NULL AUTO_INCREMENT,
  code             VARCHAR(20)  NOT NULL,
  name             VARCHAR(150) NOT NULL,
  department_id    INT UNSIGNED NOT NULL,
  manager_id       INT UNSIGNED NULL,
  client           VARCHAR(150) NOT NULL,
  status           ENUM('Planned','Active','On Hold','Completed') NOT NULL,
  priority         ENUM('Low','Medium','High','Critical') NOT NULL,
  health           ENUM('Green','Amber','Red') NOT NULL,
  start_date       DATE NOT NULL,
  target_end_date  DATE NOT NULL,
  budget_usd       DECIMAL(12,2) NOT NULL,
  PRIMARY KEY (project_id),
  UNIQUE KEY uq_projects_code (code),
  KEY idx_projects_department (department_id),
  KEY idx_projects_manager (manager_id),
  KEY idx_projects_status (status),
  CONSTRAINT fk_projects_department
    FOREIGN KEY (department_id) REFERENCES departments (department_id),
  CONSTRAINT fk_projects_manager
    FOREIGN KEY (manager_id) REFERENCES employees (employee_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ----------------------------------------------------------------------------
-- tasks : 300 seeded tasks (the unit of work / workload + risk signal)
-- ----------------------------------------------------------------------------
CREATE TABLE tasks (
  task_id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
  project_id         INT UNSIGNED NOT NULL,
  title              VARCHAR(200) NOT NULL,
  description        VARCHAR(500) NOT NULL,
  required_skill_id  INT UNSIGNED NULL,
  assignee_id        INT UNSIGNED NULL,             -- NULL = unassigned
  status             ENUM('Backlog','To Do','In Progress','In Review','Done','Blocked') NOT NULL,
  priority           ENUM('Low','Medium','High','Critical') NOT NULL,
  complexity         TINYINT UNSIGNED NOT NULL,     -- 1 .. 5
  estimated_hours    DECIMAL(6,2) NOT NULL,
  actual_hours       DECIMAL(6,2) NULL,             -- NULL until Done
  start_date         DATE NOT NULL,
  due_date           DATE NOT NULL,
  completed_date     DATE NULL,                     -- NULL until Done
  created_at         DATETIME NOT NULL,
  PRIMARY KEY (task_id),
  KEY idx_tasks_project (project_id),
  KEY idx_tasks_assignee (assignee_id),
  KEY idx_tasks_status (status),
  KEY idx_tasks_due (due_date),
  KEY idx_tasks_skill (required_skill_id),
  CONSTRAINT fk_tasks_project
    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
  CONSTRAINT fk_tasks_assignee
    FOREIGN KEY (assignee_id) REFERENCES employees (employee_id) ON DELETE SET NULL,
  CONSTRAINT fk_tasks_skill
    FOREIGN KEY (required_skill_id) REFERENCES skills (skill_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ----------------------------------------------------------------------------
-- task_dependencies : directed edges between tasks (acyclic by construction).
-- Feeds dependency-chain risk detection in FastAPI /ai/risk.
-- ----------------------------------------------------------------------------
CREATE TABLE task_dependencies (
  predecessor_task_id  INT UNSIGNED NOT NULL,
  successor_task_id    INT UNSIGNED NOT NULL,
  dependency_type      ENUM('Finish-to-Start','Start-to-Start','Finish-to-Finish','Start-to-Finish')
                       NOT NULL DEFAULT 'Finish-to-Start',
  lag_days             SMALLINT NOT NULL DEFAULT 0,
  PRIMARY KEY (predecessor_task_id, successor_task_id),
  KEY idx_dep_successor (successor_task_id),
  CONSTRAINT fk_dep_predecessor
    FOREIGN KEY (predecessor_task_id) REFERENCES tasks (task_id) ON DELETE CASCADE,
  CONSTRAINT fk_dep_successor
    FOREIGN KEY (successor_task_id) REFERENCES tasks (task_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
