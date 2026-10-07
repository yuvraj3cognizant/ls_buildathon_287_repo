# Deployment & Run Guide

This guide covers: (1) running the platform locally, (2) the exact AWS
permissions and resources it needs, and (3) deploying it on AWS for a
Build-A-Thon demo.

---

## 1. Prerequisites

- Python 3.11+
- AWS CLI configured with credentials that can reach the resources below
- The following AWS resources already exist (per project spec):
  - Region: `us-east-1`
  - Bedrock model: `amazon.nova-pro-v1:0` (model access enabled in Bedrock console)
  - Athena database: `clinical_db` with tables `clinical_trials`, `patient_data`, `trial_sites`, `adverse_events`, `study_metrics`
  - Athena output location: `s3://287-my-clinical-data/athena_results/`
  - S3 bucket: `287-my-clinical-data`
  - Bedrock Knowledge Base: `287-knowledge-base-rag` (ingested with the 5 document types)
  - An AgentCore Code Interpreter resource (custom or the AWS-managed default sandbox)

---

## 2. Running locally

All commands below run from the **project root** (the directory containing
`app/`, `src/`, and `requirements.txt`).

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate         # Windows: .\venv\Scripts\Activate.ps1

# 2. Install dependencies (bedrock-agentcore is already in requirements.txt)
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env             # Windows: Copy-Item .env.example .env

# 4. Authenticate to AWS
aws login
```

Edit `.env` and fill in the two values that are specific to your account
(everything else already matches the resources described in the project
spec):

```
KNOWLEDGE_BASE_ID=<your Bedrock Knowledge Base ID, e.g. ABCD1234EF>
CODE_INTERPRETER_IDENTIFIER=<your AgentCore Code Interpreter identifier>
```

> The Knowledge Base **ID** (not the name `287-knowledge-base-rag`) is
> required by the Bedrock Agent Runtime API. Find it in the Bedrock
> console under Knowledge Bases → your KB → "Knowledge base ID".

```bash
# 5. Run the app
streamlit run app/streamlit_app.py     # Windows shortcut: .\run_app.ps1
```

The app opens at `http://localhost:8501`. Try questions like:
- *"How many patients dropped out of each trial?"* → SQL Agent
- *"What safety concerns were raised in the medical monitor review for Trial 002?"* → RAG Agent
- *"Which sites have the highest dropout rate, and what do the monitoring reports say about those sites?"* → Hybrid (SQL + RAG)
- *"Analyze adverse event trends by severity and give me recommendations with a chart."* → Analyst Agent (full self-healing loop)

### Running tests

```bash
pip install pytest
pytest            # config lives in pytest.ini (testpaths=tests, pythonpath=.)
```

The connectivity checks in `scripts/` hit AWS directly and are **not** part of
the pytest suite — run them by hand to confirm credentials and model access:

```bash
python scripts/check_bedrock_connection.py   # boto3 client can be created
python scripts/check_nova_model.py           # amazon.nova-pro-v1:0 responds
```

---

## 3. Required IAM permissions

Attach a policy equivalent to the following to whichever role/user runs
the app (locally this is your CLI credentials; on AWS this is the
execution role of the compute service you choose in Section 4).

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockInvoke",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:Converse",
        "bedrock:ConverseStream"
      ],
      "Resource": "*"
    },
    {
      "Sid": "BedrockKnowledgeBase",
      "Effect": "Allow",
      "Action": [
        "bedrock:Retrieve",
        "bedrock:RetrieveAndGenerate"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AthenaQuery",
      "Effect": "Allow",
      "Action": [
        "athena:StartQueryExecution",
        "athena:GetQueryExecution",
        "athena:GetQueryResults",
        "athena:StopQueryExecution"
      ],
      "Resource": "*"
    },
    {
      "Sid": "GlueCatalogForAthena",
      "Effect": "Allow",
      "Action": [
        "glue:GetTable",
        "glue:GetTables",
        "glue:GetDatabase",
        "glue:GetDatabases",
        "glue:GetPartitions"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3DataAndAthenaResults",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::287-my-clinical-data",
        "arn:aws:s3:::287-my-clinical-data/*"
      ]
    },
    {
      "Sid": "AgentCoreCodeInterpreter",
      "Effect": "Allow",
      "Action": [
        "bedrock-agentcore:StartCodeInterpreterSession",
        "bedrock-agentcore:StopCodeInterpreterSession",
        "bedrock-agentcore:InvokeCodeInterpreter"
      ],
      "Resource": "*"
    }
  ]
}
```

Scope `Resource` fields down to specific ARNs before any production use —
`"*"` is used here to keep the Build-A-Thon setup unblocked.

---

## 4. Deploying on AWS

Three deployment paths, roughly in order of Build-A-Thon-friendliness:

### Option A — AWS App Runner (fastest to demo)

1. Push the project to a Git repo (GitHub/CodeCommit).
2. Add a minimal `Dockerfile` (not included by default, since local run
   doesn't need one):

   ```dockerfile
   FROM python:3.11-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt bedrock-agentcore
   COPY . .
   EXPOSE 8501
   CMD ["streamlit", "run", "app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
   ```

3. In the App Runner console: **Create service** → source = your repo (or
   an ECR image you build/push with the Dockerfile above) → set the IAM
   **instance role** to a role with the policy from Section 3 → set the
   env vars from `.env` as App Runner environment variables → deploy.
4. App Runner gives you a public HTTPS URL — that's your demo link.

### Option B — Amazon ECS Fargate (more production-shaped)

1. Build and push the same Docker image to **ECR**:
   ```bash
   aws ecr create-repository --repository-name lifesci-agentic-platform
   docker build -t lifesci-agentic-platform .
   aws ecr get-login-password | docker login --username AWS --password-stdin <account_id>.dkr.ecr.us-east-1.amazonaws.com
   docker tag lifesci-agentic-platform:latest <account_id>.dkr.ecr.us-east-1.amazonaws.com/lifesci-agentic-platform:latest
   docker push <account_id>.dkr.ecr.us-east-1.amazonaws.com/lifesci-agentic-platform:latest
   ```
2. Create an ECS Fargate service:
   - Task definition: 1 vCPU / 2GB memory is enough for the MVP.
   - Container port: 8501.
   - Task execution role: standard ECS execution role.
   - **Task role** (this is the one the app's boto3 calls actually use):
     attach the Section 3 policy.
   - Environment variables: same as `.env`.
3. Put the service behind an **Application Load Balancer** on port 80/443.
4. Security group: allow inbound 80/443 from your demo network.

### Option C — Single EC2 instance (simplest, least "production")

1. Launch an EC2 instance (e.g. `t3.medium`, Amazon Linux 2023) with an
   **instance profile** carrying the Section 3 policy.
2. SSH in, install Python 3.11 and git, clone/copy the project.
3. Follow Section 2's local run steps.
4. Run Streamlit bound to all interfaces so it's reachable:
   ```bash
   streamlit run app/streamlit_app.py --server.port=8501 --server.address=0.0.0.0
   ```
5. Open port 8501 in the instance's security group for your demo network,
   or put a reverse proxy (nginx) in front on port 80/443.
6. For persistence across reboots, run it under `systemd` or `tmux`/`screen`.

---

## 5. Setting up the AgentCore Code Interpreter (if not already provisioned)

If your account doesn't yet have a Code Interpreter resource:

1. In the Bedrock AgentCore console, create a **Code Interpreter**
   resource (or use the AWS-managed default sandbox identifier, which
   requires no explicit creation — check current AgentCore console
   guidance, since this is a newer service and setup steps evolve).
2. Copy its identifier into `CODE_INTERPRETER_IDENTIFIER` in `.env`.
3. Confirm the execution role calling it has the
   `bedrock-agentcore:*CodeInterpreter*` permissions from Section 3.

---

## 6. Setting up the Bedrock Knowledge Base (if not already ingested)

If `287-knowledge-base-rag` needs (re)ingestion:

1. Upload the five document types into `s3://287-my-clinical-data/` under
   a documents prefix (e.g. `kb-source-docs/`).
2. In the Bedrock console → Knowledge Bases → your KB → **Data source** →
   point it at that S3 prefix → **Sync**.
3. Wait for the sync job to reach `COMPLETE` before querying — the RAG
   Agent will return empty chunks (and the UI will show a `partial`
   status) if the KB hasn't finished indexing.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| SQL Agent returns `"error": "Forbidden keyword..."` | Model generated non-SELECT SQL | Rephrase the question; the validator is intentionally strict (read-only) |
| RAG Agent status is `partial` with 0 chunks | KB not synced, or wrong `KNOWLEDGE_BASE_ID` | Re-check Section 6, confirm KB ID in `.env` |
| Analyst Agent always fails after 3 retries | `CODE_INTERPRETER_IDENTIFIER` invalid, or IAM missing `bedrock-agentcore:*` | Re-check Section 5 and the IAM policy in Section 3 |
| `EnvironmentError: Required environment variable...` on startup | `.env` not created/filled | `cp .env.example .env` and fill in the two account-specific values |
| Athena query hangs / times out | Athena output location bucket policy blocks writes, or workgroup misconfigured | Confirm `ATHENA_OUTPUT_LOCATION` bucket exists and the role can `s3:PutObject` there |
