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
        # OpenAI official API — primary for GPT models
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
        # Remote Qwen server — INACTIVE: LAN host 192.168.x.x not reachable from this machine.
        # Configure PROVIDER_REMOTE_QWEN_BASE_URL and set status=active only when reachable.
        "name": "remote_qwen",
        "adapter_type": "openai_compatible",
        "status": "inactive",
        "health_status": "unknown",
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
        # Local Qwen 2.5-14B via llama.cpp on port 8080
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
        # Local DeepSeek-R1-7B via llama.cpp on port 8081
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
    {
        # OpenRouter — primary for Qwen3.6 and Qwen-series models
        # PROVIDER_OPENROUTER_API_KEY must be set in .env
        "name": "openrouter",
        "adapter_type": "openai_compatible",
        "status": "active",
        "health_status": "healthy",
        "priority": 150,
        "input_cost_per_1k": 0.05,
        "output_cost_per_1k": 0.20,
        "avg_latency_ms": 1200.0,
        "capability_tags": "chat,tool_calling,structured_output",
        "supports_zdr": False,
        "data_collection_mode": "allow",
        "supported_parameters": "temperature,top_p,max_tokens,stop,tools,tool_choice,response_format",
        "max_input_tokens": 128000,
        "max_output_tokens": 32768,
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
    # OpenAI GPT models → official API primary, openrouter backup
    ("gpt-4o-mini",           "openai_official", "gpt-4o-mini"),
    ("gpt-4o",                "openai_official", "gpt-4o"),
    ("gpt-4-turbo",           "openai_official", "gpt-4-turbo"),
    ("gpt-3.5-turbo",         "openai_official", "gpt-3.5-turbo"),
    ("gpt-4",                 "openai_official", "gpt-4"),
    # Qwen3.6 → openrouter (sole provider; remote_qwen unreachable)
    ("qwen3.6",               "openrouter",      "Qwen3.6-35B-A3B-FP8"),
    # Qwen-series aliases → openrouter
    ("qwen-max",              "openrouter",      "Qwen3.6-35B-A3B-FP8"),
    ("qwen-turbo",            "openrouter",      "Qwen3.6-35B-A3B-FP8"),
    # Qwen 2.5-14B → openrouter primary, local_qwen fallback
    ("qwen2.5-14b",           "openrouter",      "Qwen3.6-35B-A3B-FP8"),
    ("qwen2.5-14b",           "local_qwen",      "qwen2.5-14b"),
    # Local Qwen 2.5-7B
    ("qwen2.5-7b-instruct",   "local_qwen",      "qwen2.5-7b-instruct"),
    # DeepSeek reasoning model → local only
    ("deepseek-r1-7b",        "local_deepseek",  "deepseek-r1-7b"),
    ("deepseek-r1",           "local_deepseek",  "deepseek-r1-7b"),
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
    # GPT models: official API preferred, openrouter as backup
    ("gpt-4o-mini",          "openai_official", "openrouter"),
    ("gpt-4o",               "openai_official", "openrouter"),
    ("gpt-4-turbo",          "openai_official", "openrouter"),
    ("gpt-3.5-turbo",        "openai_official", "openrouter"),
    ("gpt-4",                "openai_official", "openrouter"),
    # Qwen3.6: openrouter only (remote_qwen is inactive/unreachable)
    ("qwen3.6",              "openrouter",      None),
    # Qwen aliases: openrouter only
    ("qwen-max",             "openrouter",      None),
    ("qwen-turbo",           "openrouter",      None),
    # Qwen 2.5-14B: openrouter preferred, local fallback
    ("qwen2.5-14b",          "openrouter",      "local_qwen"),
    # DeepSeek: local only
    ("deepseek-r1-7b",       "local_deepseek",  None),
    ("deepseek-r1",          "local_deepseek",  None),
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
