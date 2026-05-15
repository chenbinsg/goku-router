CREATE TABLE IF NOT EXISTS organizations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL
) ENGINE=InnoDB CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    organization_id INT,
    FOREIGN KEY (organization_id) REFERENCES organizations(id)
) ENGINE=InnoDB CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS model_catalog (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_id VARCHAR(255) UNIQUE NOT NULL,
    provider VARCHAR(255),
    status VARCHAR(255)
) ENGINE=InnoDB CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS request_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT,
    project_id INT,
    model_catalog_id INT,
    status_code INT,
    latency FLOAT,
    FOREIGN KEY (organization_id) REFERENCES organizations(id),
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (model_catalog_id) REFERENCES model_catalog(id)
) ENGINE=InnoDB CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS billing_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_id INT,
    project_id INT,
    amount FLOAT,
    date DATETIME,
    FOREIGN KEY (organization_id) REFERENCES organizations(id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
) ENGINE=InnoDB CHARSET=utf8mb4;

-- Insert example data
INSERT INTO organizations (name) VALUES ('Example Organization');
INSERT INTO projects (name, organization_id) VALUES ('Example Project', 1);
INSERT INTO model_catalog (model_id, provider, status) VALUES ('model1', 'provider1', 'active');
