# API Configuration & Multi-Model / Multi-Key Failover Guide

This guide explains how Finora routes LLM requests through the LiteLLM gateway, how automatic failovers and credit-exhaustion recovery work, and the exact steps to add new API keys or models for task-based routing and backup redundancy.

---

## 1. How the LLM Failover System Works in Finora

The system uses a two-tier resilience architecture:

1. **Application-Layer Fallback Chain (`backend/app/llm/gateway.py`):**
   - Each agent has an assigned `default_alias` (primary model) and an optional `fallback_alias` (secondary backup model).
   - When an AI request runs, the gateway builds a model execution chain: `[res.model, res.fallback]`.
   - If the primary model fails due to:
     - `401 Unauthorized` (invalid/expired key)
     - `402 Payment Required` (credits exhausted / quota exceeded)
     - `429 Too Many Requests` (rate limits)
     - `500/502/503/504 Server Errors`
     - Network timeouts
   - The gateway automatically switches to the `fallback_alias` seamlessly. Every attempt, failure reason, and fallback usage is tracked in the `llm_call_logs` table.

2. **Proxy-Layer Key Rotation (`infrastructure/litellm/config.yaml`):**
   - LiteLLM supports deploying multiple keys under the **exact same model alias**.
   - If you provide multiple keys (e.g. `CENT_AI_KEY_1` and `CENT_AI_KEY_2`), LiteLLM performs round-robin load-balancing and automatically shifts traffic away from any key that returns `429` or `402`.

---

## 2. Step-by-Step Configuration Guide

### Step 1: Add the API Key to Environment Files

Add the API key to both `.env` files:

1. **Root `.env` (`ca-firm-system/.env`):**
   ```env
   # Existing key
   CENT_AI_KEY=cai_...

   # New keys (examples)
   GEMINI_API_KEY=AIza...
   GROQ_API_KEY=gsk_...
   OPENAI_API_KEY=sk-...
   CENT_AI_KEY_BACKUP=cai_...
   ```

2. **Backend `.env` (`ca-firm-system/backend/.env`):**
   Add the identical environment variable to this file as well.

---

### Step 2: Configure the Model in LiteLLM Proxy

Open `infrastructure/litellm/config.yaml` and add your provider configuration under `model_list`.

#### Option A: Adding a Different Model as a Backup (e.g. Gemini / Groq)
```yaml
model_list:
  # Primary Model (CentAI)
  - model_name: gpt-6-luna
    litellm_params:
      model: openai/gpt-6-luna:free
      api_base: https://api.cent-ai.dev/v1
      api_key: os.environ/CENT_AI_KEY
      drop_params: true

  # Backup Model 1: Google Gemini Flash
  - model_name: gemini-fast
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY

  # Backup Model 2: Groq Llama 3
  - model_name: groq-llama
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY
```

#### Option B: Multiple API Keys for the Same Model (Auto Key Failover)
If you have multiple API keys for the same provider, list them under the **same** `model_name`:
```yaml
  # Primary Key
  - model_name: gpt-6-luna
    litellm_params:
      model: openai/gpt-6-luna:free
      api_base: https://api.cent-ai.dev/v1
      api_key: os.environ/CENT_AI_KEY
      drop_params: true

  # Backup Key (LiteLLM auto-fails over if Key 1 runs out of credits)
  - model_name: gpt-6-luna
    litellm_params:
      model: openai/gpt-6-luna:free
      api_base: https://api.cent-ai.dev/v1
      api_key: os.environ/CENT_AI_KEY_BACKUP
      drop_params: true
```

---

### Step 3: Register Model in LLM Catalog (`backend/app/llm/catalog.py`)

Every model served by LiteLLM must be registered in `backend/app/llm/catalog.py` under the `MODELS` dictionary:

```python
MODELS: Final[dict[str, ModelSpec]] = {
    # ...
    ModelSpec(
        "gemini-fast", "Gemini fast", "Google",
        "Fast, inexpensive backup model with very long context.",
        1_000_000, frozenset({CAP_STRUCTURED, CAP_TOOLS}), "economy",
    ),
    ModelSpec(
        "gpt-6-luna", "GPT-6 Luna (Free)", "CentAI",
        "Free-tier model via CentAI gateway.",
        128_000, frozenset({CAP_STRUCTURED, CAP_TOOLS}), "economy",
    ),
}
```

> **Note:** A project test asserts that the model names in `infrastructure/litellm/config.yaml` and `backend/app/llm/catalog.py` match. Keep both files in sync.

---

### Step 4: Restart LiteLLM Container

Whenever you update `config.yaml` or `.env`, recreate the LiteLLM proxy container so it loads the changes:

```powershell
docker compose up -d --force-recreate litellm
```

Verify that the models are actively served:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:4000/models" -Headers @{"Authorization"="Bearer sk-litellm-local-key"}
```

---

### Step 5: Enable the Model and Set Fallbacks in Database

You can configure models via the UI (Model Settings page) or via SQL.

#### 1. Enable the Backup Model for Your Firm:
```sql
INSERT INTO llm_model_settings (id, firm_id, alias, enabled, updated_at)
VALUES (gen_random_uuid(), '7c5f3de5-4fa3-4b78-8278-8a036bc13f5c', 'gemini-fast', true, now())
ON CONFLICT (firm_id, alias) DO UPDATE SET enabled = true, updated_at = now();
```

#### 2. Set the Fallback Model on Agents:
```sql
-- Automatically fail over to gemini-fast if gpt-6-luna runs out of credits or fails:
UPDATE llm_agent_configs
SET fallback_alias = 'gemini-fast', updated_at = now()
WHERE firm_id = '7c5f3de5-4fa3-4b78-8278-8a036bc13f5c'
  AND default_alias = 'gpt-6-luna';
```

---

## 3. Task-Based Routing (Assigning Different Models per Task)

You can assign specific models to specific tasks (e.g. use a lightweight, fast model for intent classification, but a heavy reasoning model for financial calculations or reports).

1. **Enable Task Overrides Policy:**
   ```sql
   UPDATE llm_firm_policies
   SET allow_task_overrides = true, config_version = config_version + 1
   WHERE firm_id = '7c5f3de5-4fa3-4b78-8278-8a036bc13f5c';
   ```

2. **Assign Task-Specific Model:**
   ```sql
   -- Route CA Review Intent Classification to a fast model:
   INSERT INTO llm_task_overrides (id, firm_id, agent, task, alias, set_at)
   VALUES (
       gen_random_uuid(),
       '7c5f3de5-4fa3-4b78-8278-8a036bc13f5c',
       'ca_review',
       'classify_intent',
       'gemini-fast',
       now()
   )
   ON CONFLICT (firm_id, agent, task) DO UPDATE SET alias = 'gemini-fast', set_at = now();
   ```

---

## 4. Verification & Health Monitoring

To verify your model failover and view usage:
1. **Audit Logs:** Check table `llm_call_logs` to see each call's model alias, status (`ok` or `error`), latency, and whether `fallback_used` is `true`.
2. **Connectivity Test Endpoint:**
   ```http
   POST /api/v1/llm/models/{alias}/test
   ```
   Admin check endpoint sending a harmless prompt to verify provider connectivity and key validity without impacting production workflows.
