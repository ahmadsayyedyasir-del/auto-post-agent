# AI Social Media Automation Platform

An agentic AI web application engineered to streamline the full lifecycle of social media content creation, review, scheduling, publishing, and analytics.

---

## 📌 Current Development Phase

> **Phase 2 — LLM Service & Provider Abstraction**
>
> The project has completed **Phase 1 (Project Foundation)** and **Phase 2 (LLM Service Layer)**. This phase establishes a decoupled, provider-agnostic LLM service abstraction with Groq (`ChatGroq`) as the initial implementation, native Pydantic structured output support, centralized configuration, and bounded retry error handling. Autonomous agents and LangGraph workflows will be built on top of this layer in subsequent phases.

---

## 🎯 Project Objective

The ultimate goal of the platform is to automate an intelligent content pipeline:

$$\text{Research} \longrightarrow \text{Planning} \longrightarrow \text{Writing} \longrightarrow \text{Critic} \longrightarrow \text{Human Approval} \longrightarrow \text{Publishing} \longrightarrow \text{Analytics} \longrightarrow \text{Memory}$$

Future autonomous agents will include:
- **Research Agent**: Trend analysis and source intelligence
- **Planning Agent**: Content calendar and strategy design
- **Writer Agent**: Platform-tailored copy generation
- **Critic Agent**: Quality, policy, and brand voice verification

---

## 🏗️ System Architecture

### LLM Service Layer (Phase 2)

Future agents interact **only** with `LLMService`, completely isolated from provider-specific SDKs:

```text
Agent (Research / Writer / Critic)
         │
         ▼
    LLMService  (Bounded Retries & Factory)
         │
         ▼
   <<LLMProvider>>  (Abstract Interface)
         │
         ▼
    GroqProvider  (ChatGroq Adapter)
```

- **Provider Agnostic**: Switch providers (e.g. from Groq to OpenAI or Anthropic) via configuration without touching agent logic.
- **Structured Outputs**: Native generation of typed Pydantic models via `service.generate_structured(...)`.
- **Bounded Retries**: Automated exponential backoff for transient upstream failures.
- **Security**: Zero credential leakage in logs or exceptions.

For complete architectural details, see [docs/architecture.md](docs/architecture.md).

---

## 🛠️ Technology Stack

| Layer / Tool | Technology | Purpose |
|---|---|---|
| Language | Python 3.12 | Backend core language |
| Web Framework | FastAPI | High-performance REST API |
| ASGI Server | Uvicorn | Async HTTP server |
| Configuration | Pydantic Settings | Environment and config management |
| LLM Abstraction | LangChain Core & Groq | Provider-agnostic LLM integration |
| Default LLM | Groq (`llama-3.3-70b-versatile`) | Fast, cost-efficient inference |
| Testing | Pytest, HTTPX & pytest-asyncio | Automated unit & endpoint tests |

---

## 📂 Project Structure

```text
ai-social-media-automation/
├── backend/
│   ├── app/
│   │   ├── agents/          # Future AI agent implementations
│   │   ├── api/             # Modular API routes
│   │   │   └── v1/
│   │   │       ├── health.py# Health check endpoint
│   │   │       └── router.py# Central v1 API router
│   │   ├── core/            # Core utilities (logging, etc.)
│   │   │   └── logging.py
│   │   ├── models/          # Future database models & schemas
│   │   ├── services/        # Business logic & integrations
│   │   │   └── llm/         # Centralized LLM Service Layer
│   │   │       ├── base.py       # Abstract LLMProvider interface
│   │   │       ├── exceptions.py # Domain exception hierarchy
│   │   │       ├── service.py    # Central LLMService orchestrator
│   │   │       └── providers/
│   │   │           └── groq.py   # Groq provider implementation
│   │   ├── tools/           # Future agent tool definitions
│   │   ├── workflows/       # Future LangGraph workflows
│   │   ├── config.py        # Centralized Pydantic settings
│   │   └── main.py          # FastAPI application entry point
│   ├── tests/
│   │   ├── test_health.py      # Health endpoint unit tests
│   │   └── test_llm_service.py # LLM service, retry, and mock provider tests
│   └── requirements.txt     # Backend dependencies
├── data/                    # Local data storage (.gitkeep)
├── docs/
│   └── architecture.md      # System architecture documentation
├── frontend/                # Future React + Vite application
├── .env.example             # Environment configuration template
├── .gitignore               # Git ignore rules
├── pytest.ini               # Pytest configuration
└── README.md                # Project documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites

- Python 3.12 installed
- Git

### 2. Create and Activate Virtual Environment

**Windows (PowerShell):**
```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```powershell
pip install -r backend/requirements.txt
```

### 4. Configure Environment

Copy `.env.example` to create your local `.env` file:

```powershell
cp .env.example .env
```

To enable live Groq inference in your local environment, add your key to `.env`:
```ini
GROQ_API_KEY=gsk_your_groq_api_key_here
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
LLM_TEMPERATURE=0.2
LLM_MAX_RETRIES=3
```

*(Note: Unit tests run offline using mocks and do NOT require an API key).*

---

## 🏃 Running the Application

Start the local development server with Uvicorn:

```powershell
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Once running, interactive documentation is accessible at:
- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 🧪 Running Tests

Execute the automated test suite with pytest:

```powershell
pytest
```

Verbose output:
```powershell
pytest backend/tests -v
```
