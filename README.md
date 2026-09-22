# AI Social Media Automation Platform

An agentic AI web application engineered to streamline the full lifecycle of social media content creation, review, scheduling, publishing, and analytics.

---

## 📌 Current Development Phase

> **Phase 1 — Project Foundation**
>
> The project is currently in **Phase 1 (Project Foundation)**. This phase establishes the initial backend structure, centralized configuration, logging, health check endpoints, dependency setup, and automated testing. AI agents, workflows, and social media integrations will be implemented in subsequent phases.

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

## 🏗️ Current Architecture (Phase 1)

The Phase 1 architecture delivers a lightweight, extensible foundation:

- **Web Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12)
- **Configuration**: [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) loading typed settings from `.env`
- **Logging**: Centralized standard library logging with customizable log levels (`INFO`, `WARNING`, `ERROR`, `DEBUG`)
- **API Routing**: Modular router layout under `backend/app/api/` for easy route addition
- **Testing**: `pytest` and `httpx` for test execution

For an in-depth architectural breakdown, see [docs/architecture.md](docs/architecture.md).

---

## 🛠️ Technology Stack (Phase 1)

| Layer / Tool | Technology | Purpose |
|---|---|---|
| Language | Python 3.12 | Backend core language |
| Web Framework | FastAPI | High-performance REST API |
| ASGI Server | Uvicorn | Async HTTP server |
| Configuration | Pydantic Settings | Environment and config management |
| Testing | Pytest & HTTPX | Automated unit & endpoint tests |

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
│   │   ├── services/        # Future business logic services
│   │   ├── tools/           # Future agent tool definitions
│   │   ├── workflows/       # Future LangGraph workflows
│   │   ├── config.py        # Centralized Pydantic settings
│   │   └── main.py          # FastAPI application entry point
│   ├── tests/
│   │   └── test_health.py   # Health endpoint unit tests
│   └── requirements.txt     # Minimal Phase 1 dependencies
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

*(Optional: adjust `APP_NAME`, `LOG_LEVEL`, `PORT`, etc., in `.env`)*

---

## 🏃 Running the Application

Start the local development server with Uvicorn:

```powershell
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Once running, the interactive documentation is accessible at:
- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 🩺 Example Health Endpoint

Send a `GET` request to verify the server is running:

### Request:
```bash
curl http://127.0.0.1:8000/health
```

### Response (200 OK):
```json
{
  "status": "healthy"
}
```

Modular endpoint:
```bash
curl http://127.0.0.1:8000/api/v1/health
```

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
