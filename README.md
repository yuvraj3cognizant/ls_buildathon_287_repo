# Life Sciences Agentic AI Platform (MVP)

An AWS-native, multi-agent platform that lets Life Sciences users ask
natural-language questions about clinical trial data — both structured
(Athena/SQL) and unstructured (protocols, monitoring reports, safety
reviews, investigation reports) — and get back answers, insights,
recommendations, and charts without writing SQL or manually reading
documents.

## Architecture at a glance

```
User Question
      │
      ▼
Orchestrator Agent  ──(classifies intent)──▶ STRUCTURED / UNSTRUCTURED / HYBRID / ANALYTICAL
      │
      ├──▶ SQL Agent      ──▶ Amazon Athena (clinical_db)
      ├──▶ RAG Agent       ──▶ Bedrock Knowledge Base (287-knowledge-base-rag)
      └──▶ Analyst Agent   ──▶ AgentCore Code Interpreter (self-healing loop, max 3 retries)
      │
      ▼
Streamlit UI (agent flow, generated SQL, sources, charts, summary, final answer)
```

Full architecture rationale, folder structure, and design decisions are in
`docs/ARCHITECTURE.md` (see the original design conversation) — this
README focuses on what you need to run and deploy the MVP.

## Project layout

```
ls_buildathon_287/                 # <-- project root (run all commands here)
├── app/                    # Streamlit frontend
│   ├── streamlit_app.py
│   └── ui/                 # sidebar, chat, sql/rag/analyst panels, session state
├── src/
│   ├── config/              # settings.py, aws_config.py, constants.py
│   ├── llm/                 # centralized Bedrock/Strands model factory
│   ├── models/               # pydantic data contracts between agents
│   ├── services/             # Athena / Bedrock / KB / S3 / Code Interpreter boundary
│   ├── tools/                 # Strands @tool wrappers over services
│   ├── prompts/                # system prompts + shared schema context
│   ├── agents/
│   │   ├── orchestrator/
│   │   ├── sql_agent/
│   │   ├── rag_agent/
│   │   └── analyst_agent/     # planner, code_generator, self_healing_loop
│   └── utils/                  # logger, retry, exceptions, timers, validators
├── tests/
├── scripts/                     # standalone AWS connectivity checks
├── docs/DEPLOYMENT_AND_RUN.md   # <-- start here to run/deploy
├── requirements.txt
├── pytest.ini
├── run_app.ps1                  # Windows launcher (uses ./venv)
└── .env.example
```

## Quick start

See **`docs/DEPLOYMENT_AND_RUN.md`** for full step-by-step local run and AWS
deployment instructions, IAM permissions needed, and troubleshooting.

Windows (PowerShell) — the `venv/` in this repo is already provisioned:

```powershell
aws login                        # refresh AWS credentials
.\run_app.ps1                    # opens http://localhost:8501
```

From scratch, on any platform:

```bash
python -m venv venv
venv/Scripts/python -m pip install -r requirements.txt   # Linux/macOS: venv/bin/python
cp .env.example .env   # fill in your KB ID and Code Interpreter identifier
streamlit run app/streamlit_app.py
```

## Design principles

- **No duplicate code**: every AWS service call has exactly one owning
  module in `src/services/`; agents and tools never call boto3 directly.
- **Centralized cross-cutting concerns**: logging (`utils/logger.py`),
  retry (`utils/retry.py`), and exceptions (`utils/exceptions.py`) are
  singular, shared modules.
- **Typed contracts**: agents pass `AgentRequest` / `AgentResponse`
  (pydantic) objects, not free-text strings, so the UI can render structured
  panels reliably.
- **Self-healing Analyst Agent**: generates Python → executes in AgentCore
  Code Interpreter → on failure, feeds the traceback back to the model for
  a fix → retries up to `MAX_ANALYST_RETRIES` (default 3), capped by
  `MAX_EXECUTION_SECONDS` (default 120s) wall-clock.
