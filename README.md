# AI Social Media Automation Platform

An agentic AI web application engineered to streamline the full lifecycle of social media content creation, review, scheduling, publishing, and analytics.

---

## 📌 Current Development Phase

> **Phase 4 — Planning Agent**
>
> The project has completed **Phase 1 (Project Foundation)**, **Phase 2 (LLM Service Layer)**, **Phase 3 (Research Agent)**, and **Phase 4 (Planning Agent)**. The platform now features autonomous topic discovery (Research Agent) and strategic content planning (Planning Agent) producing validated, source-grounded content strategy plans (`ContentPlan`). Copywriting, review, and orchestration will be implemented in subsequent phases.

---

## 🎯 Project Objective

The ultimate goal of the platform is to automate an intelligent content pipeline:

$$\text{Research} \longrightarrow \text{Planning} \longrightarrow \text{Writing} \longrightarrow \text{Critic} \longrightarrow \text{Human Approval} \longrightarrow \text{Publishing} \longrightarrow \text{Analytics} \longrightarrow \text{Memory}$$

### Agent Roadmap:
- [x] **1. Research Agent**: Discovers current niche trends and extracts grounded insights
- [x] **2. Planning Agent**: Formulates content strategy plans, angles, hooks, key points, and CTAs
- [ ] **3. Writer Agent**: Platform-tailored copy generation
- [ ] **4. Critic Agent**: Quality, policy, and brand voice verification

---

## 🏗️ System Architecture

### Multi-Agent Pipeline

```text
User / Niche Request
         │
         ▼
   ResearchAgent (Phase 3)
     ├──> SearchTool (Tavily / Mock Web Search)
     └──> LLMService (Provider-Agnostic Generation & Bounded Retries)
         │
         ▼
   ResearchResponse (Grounded Trends)
         │
         ▼
   PlanningAgent (Phase 4)
     └──> LLMService (Structured Content Strategy Generation)
         │
         ▼
   ContentPlan (Topic, Angle, Hook, Key Points, CTA, Sources)
```

- **Source Grounding**: Every plan is anchored to a specific research trend with verified citations.
- **Provider Decoupled**: Zero direct LLM vendor SDK dependencies in agent code.
- **Strategic Separation**: Clear separation between *Research Evidence* (facts) and *Content Strategy* (angle/perspective).
- **Resilience**: Layer-separated bounded retries for search, LLM inference, and agent validation.

For complete architectural details, see [docs/architecture.md](docs/architecture.md).

---

## 🛠️ Technology Stack

| Layer / Tool | Technology | Purpose |
|---|---|---|
| Language | Python 3.12 | Backend core language |
| Web Framework | FastAPI | High-performance REST API |
| Configuration | Pydantic Settings | Environment and config management |
| LLM Abstraction | LangChain Core & Groq | Provider-agnostic LLM integration |
| Default LLM | Groq (`llama-3.3-70b-versatile`) | Fast, cost-efficient inference |
| Web Research Tool | Tavily Search (`tavily-python`) | Real-time web intelligence |
| Testing | Pytest, HTTPX & pytest-asyncio | Automated unit & endpoint tests |

---

## 📂 Project Structure

```text
ai-social-media-automation/
├── backend/
│   ├── app/
│   │   ├── agents/          # AI Agent Implementations
│   │   │   ├── planning.py  # Planning Agent (Phase 4)
│   │   │   └── research.py  # Research Agent (Phase 3)
│   │   ├── api/             # Modular API routes
│   │   │   └── v1/
│   │   │       ├── health.py# Health check endpoint
│   │   │       └── router.py# Central v1 API router
│   │   ├── core/            # Core utilities (logging, etc.)
│   │   │   └── logging.py
│   │   ├── models/          # Domain Schemas
│   │   │   ├── planning.py  # PlanningRequest, ContentPlan, exceptions
│   │   │   └── research.py  # ResearchRequest, Trend, SearchResult, etc.
│   │   ├── services/        # Business logic & LLM services
│   │   │   └── llm/         # Centralized LLM Service Layer
│   │   │       ├── base.py       # Abstract LLMProvider interface
│   │   │       ├── exceptions.py # Domain exception hierarchy
│   │   │       ├── service.py    # Central LLMService orchestrator
│   │   │       └── providers/
│   │   │           └── groq.py   # Groq provider implementation
│   │   ├── tools/           # External tool integrations
│   │   │   └── research/    # Search tool abstraction & Tavily adapter
│   │   │       ├── base.py       # Abstract SearchTool interface
│   │   │       ├── mock.py       # Mock search tool for testing
│   │   │       └── tavily.py     # Tavily search tool adapter
│   │   ├── workflows/       # Future LangGraph workflows
│   │   ├── config.py        # Centralized Pydantic settings
│   │   └── main.py          # FastAPI application entry point
│   ├── tests/
│   │   ├── test_health.py         # Health endpoint unit tests
│   │   ├── test_llm_service.py    # LLM service, retry, and mock provider tests
│   │   ├── test_planning_agent.py # Planning Agent, schemas, and grounding tests
│   │   └── test_research_agent.py # Research Agent, schemas, and search tool tests
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

To enable live Groq and Tavily research in your local environment, add your API keys to `.env`:
```ini
GROQ_API_KEY=gsk_your_groq_api_key_here
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
LLM_TEMPERATURE=0.2

TAVILY_API_KEY=tvly_your_tavily_api_key_here
SEARCH_MAX_RETRIES=2
PLANNING_MAX_RETRIES=2
```

*(Note: Unit tests run completely offline using mocks and do NOT require API keys).*

---

## 💡 Example: Research → Planning Pipeline

```python
import asyncio
from backend.app.agents.planning import PlanningAgent
from backend.app.agents.research import ResearchAgent
from backend.app.models.planning import PlanningRequest
from backend.app.models.research import ResearchRequest

async def main():
    # 1. Discover trends with Research Agent
    research_agent = ResearchAgent()
    research_req = ResearchRequest(
        niche="Artificial Intelligence",
        audience="AI developers and students",
        platform="linkedin",
        keywords=["AI Agents", "Multi-Agent"],
        max_results=3,
    )
    research_res = await research_agent.research(research_req)
    print(f"Research discovered {research_res.total_results_found} trends.")

    # 2. Formulate Content Strategy with Planning Agent
    planning_agent = PlanningAgent()
    planning_req = PlanningRequest(
        research=research_res,
        niche="Artificial Intelligence",
        audience="AI developers and students",
        platform="linkedin",
        content_goal="educational",
    )
    plan = await planning_agent.plan(planning_req)

    print("\n--- CONTENT PLAN ---")
    print(f"Topic: {plan.topic}")
    print(f"Angle: {plan.angle}")
    print(f"Hook Direction: {plan.hook_direction}")
    print("Key Points:")
    for point in plan.key_points:
        print(f"  - {point}")
    print(f"CTA: {plan.cta_direction}")
    print(f"Sources: {', '.join(plan.source_references)}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 🏃 Running the Application

Start the local development server with Uvicorn:

```powershell
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

---

## 🧪 Running Tests

Execute the full automated test suite with pytest:

```powershell
pytest
```

Verbose output:
```powershell
pytest backend/tests -v
```
