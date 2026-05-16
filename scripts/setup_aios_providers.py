"""
One-shot setup: migrate model_catalog schema and seed providers/models/routes for AIOS.
Run from repo root: python scripts/setup_aios_providers.py
"""
import os
import sys

# Load .env
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.isfile(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

import pymysql
import re

db_url = os.environ.get("DATABASE_URL", "")
m = re.match(r"mysql\+pymysql://([^:]+):([^@]*)@([^:/]+):?(\d*)/(.+)", db_url)
if not m:
    print("ERROR: DATABASE_URL not set or not mysql+pymysql://")
    sys.exit(1)

user, password, host, port, dbname = m.groups()
port = int(port) if port else 3306

conn = pymysql.connect(host=host, port=port, user=user, password=password, database=dbname, autocommit=True)
cur = conn.cursor()

print("=== Migrating model_catalog table ===")

# Check current model_catalog columns
cur.execute("DESCRIBE model_catalog")
cols = {row[0] for row in cur.fetchall()}
print(f"  Existing columns: {cols}")

if "provider_id" not in cols:
    print("  Adding provider_id column...")
    cur.execute("ALTER TABLE model_catalog ADD COLUMN provider_id INT")

if "provider_model_name" not in cols:
    print("  Adding provider_model_name column...")
    cur.execute("ALTER TABLE model_catalog ADD COLUMN provider_model_name VARCHAR(255)")

# Remove UNIQUE constraint on model_id if present (multiple entries per model_id allowed now)
cur.execute("""
    SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS
    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'model_catalog'
    AND CONSTRAINT_TYPE = 'UNIQUE' AND CONSTRAINT_NAME != 'PRIMARY'
""", (dbname,))
unique_constraints = [row[0] for row in cur.fetchall()]
for constraint in unique_constraints:
    print(f"  Dropping UNIQUE constraint '{constraint}' from model_catalog...")
    cur.execute(f"ALTER TABLE model_catalog DROP INDEX `{constraint}`")

# Clear old demo data
print("\n=== Clearing old demo data ===")
cur.execute("DELETE FROM route_rules")
cur.execute("DELETE FROM model_catalog")
cur.execute("DELETE FROM providers")
print("  Cleared route_rules, model_catalog, providers.")

print("\n=== Inserting providers ===")
providers = [
    {
        "name": "openai_official",
        "adapter_type": "openai_compatible",
        "status": "active",
        "health_status": "healthy",
        "priority": 100,
        "input_cost_per_1k": 0.15,
        "output_cost_per_1k": 0.60,
        "avg_latency_ms": 800.0,
        "capability_tags": "chat,tool_calling,structured_output,multimodal",
        "supports_zdr": False,
        "data_collection_mode": "allow",
        "supported_parameters": "temperature,top_p,max_tokens,stop,tools,tool_choice,response_format",
        "max_input_tokens": 128000,
        "max_output_tokens": 16384,
    },
    {
        "name": "remote_qwen",
        "adapter_type": "openai_compatible",
        "status": "active",
        "health_status": "healthy",
        "priority": 200,
        "input_cost_per_1k": 0.002,
        "output_cost_per_1k": 0.006,
        "avg_latency_ms": 400.0,
        "capability_tags": "chat,tool_calling,structured_output",
        "supports_zdr": True,
        "data_collection_mode": "deny",
        "supported_parameters": "temperature,top_p,max_tokens,stop,tools,tool_choice,response_format",
        "max_input_tokens": 32768,
        "max_output_tokens": 8192,
    },
    {
        "name": "local_qwen",
        "adapter_type": "openai_compatible",
        "status": "active",
        "health_status": "healthy",
        "priority": 300,
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
        "avg_latency_ms": 600.0,
        "capability_tags": "chat,tool_calling,structured_output",
        "supports_zdr": True,
        "data_collection_mode": "deny",
        "supported_parameters": "temperature,top_p,max_tokens,stop,tools,tool_choice,response_format",
        "max_input_tokens": 32768,
        "max_output_tokens": 8192,
    },
    {
        "name": "local_deepseek",
        "adapter_type": "openai_compatible",
        "status": "active",
        "health_status": "healthy",
        "priority": 400,
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
        "avg_latency_ms": 900.0,
        "capability_tags": "chat,structured_output",
        "supports_zdr": True,
        "data_collection_mode": "deny",
        "supported_parameters": "temperature,top_p,max_tokens,stop,response_format",
        "max_input_tokens": 32768,
        "max_output_tokens": 8192,
    },
]

provider_ids = {}
for p in providers:
    cur.execute("""
        INSERT INTO providers
          (name, adapter_type, status, health_status, priority,
           input_cost_per_1k, output_cost_per_1k, avg_latency_ms,
           capability_tags, supports_zdr, data_collection_mode,
           supported_parameters, max_input_tokens, max_output_tokens)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        p["name"], p["adapter_type"], p["status"], p["health_status"], p["priority"],
        p["input_cost_per_1k"], p["output_cost_per_1k"], p["avg_latency_ms"],
        p["capability_tags"], p["supports_zdr"], p["data_collection_mode"],
        p["supported_parameters"], p["max_input_tokens"], p["max_output_tokens"],
    ))
    provider_ids[p["name"]] = cur.lastrowid
    print(f"  Inserted provider '{p['name']}' → id={cur.lastrowid}")

print("\n=== Inserting model catalog ===")
# model_id : [(provider_name, provider_model_name)]
model_entries = [
    # OpenAI models → openai_official primary, remote_qwen backup
    ("gpt-4o-mini",     "openai_official", "gpt-4o-mini"),
    ("gpt-4o-mini",     "remote_qwen",     "qwen2.5-14b"),
    ("gpt-4o",          "openai_official", "gpt-4o"),
    ("gpt-4o",          "remote_qwen",     "qwen2.5-14b"),
    # Qwen model → remote first, local fallback
    ("qwen2.5-14b",     "remote_qwen",     "qwen2.5-14b"),
    ("qwen2.5-14b",     "local_qwen",      "qwen2.5-14b"),
    # DeepSeek reasoning model → local only
    ("deepseek-r1-7b",  "local_deepseek",  "deepseek-r1-7b"),
    ("deepseek-r1",     "local_deepseek",  "deepseek-r1-7b"),
]

for model_id, provider_name, provider_model_name in model_entries:
    pid = provider_ids[provider_name]
    cur.execute("""
        INSERT INTO model_catalog (model_id, provider_id, provider_model_name, status)
        VALUES (%s, %s, %s, 'active')
    """, (model_id, pid, provider_model_name))
    print(f"  {model_id} → {provider_name} ({provider_model_name})")

print("\n=== Inserting route rules ===")
# Primary + backup for each logical model_id the router client will request
route_rules = [
    ("gpt-4o-mini",    "openai_official", "remote_qwen"),
    ("gpt-4o",         "openai_official", "remote_qwen"),
    ("qwen2.5-14b",    "remote_qwen",     "local_qwen"),
    ("deepseek-r1-7b", "local_deepseek",  None),
    ("deepseek-r1",    "local_deepseek",  None),
]

for model_id, preferred, backup in route_rules:
    pref_id = provider_ids[preferred]
    back_id = provider_ids[backup] if backup else None
    cur.execute("""
        INSERT INTO route_rules (model_id, preferred_provider_id, backup_provider_id, timeout_ms)
        VALUES (%s, %s, %s, 30000)
        ON DUPLICATE KEY UPDATE
          preferred_provider_id=VALUES(preferred_provider_id),
          backup_provider_id=VALUES(backup_provider_id),
          timeout_ms=VALUES(timeout_ms)
    """, (model_id, pref_id, back_id))
    backup_label = f" → backup: {backup}" if backup else ""
    print(f"  {model_id} → preferred: {preferred}{backup_label}")

conn.close()
print("\n✓ Setup complete. Restart the router for changes to take effect.")
