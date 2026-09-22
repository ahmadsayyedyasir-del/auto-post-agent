# AI Social Media Automation Platform - System Architecture

## Overview

The **AI Social Media Automation Platform** is an enterprise-grade agentic AI system designed to automate end-to-end social media content creation, review, scheduling, publishing, and analytics.

---

## 1. Currently Implemented Architecture

The codebase currently implements:
- **Phase 1: Project Foundation** (FastAPI core, configuration, logging, health endpoints, pytest)
- **Phase 2: LLM Service Layer** (Provider-agnostic LLM abstraction, Groq adapter, structured output, bounded retries)
- **Phase 3: Research Agent** (Topic discovery, search tool abstraction, Tavily integration, source grounding, trend validation)
- **Phase 4: Planning Agent** (Content strategy formulation, trend evaluation, hook/key-points/CTA design, source grounding)

### 1.1 System Architecture Diagram

```mermaid
graph TD
    Client[HTTP Client / API] -->|GET /health| FastAPI[FastAPI App Instance]
    Client -->|GET /api/v1/health| V1Router[Modular API v1 Router]
    FastAPI --> V1Router
    FastAPI --> Config[Centralized Config: pydantic-settings]
    FastAPI --> Logging[Centralized Logging: logging.basicConfig]
    Config --> EnvFile[Environment Variables: .env / .env.example]

    ResearchRequest[ResearchRequest] --> ResearchAgent[1. Research Agent]
    
    subgraph Research Subsystem [Phase 3: Trend Discovery]
        ResearchAgent -->|1. Formulate Query| SearchTool[<<interface>> SearchTool]
        SearchTool <|.. TavilySearchTool[TavilySearchTool: AsyncTavilyClient]
        SearchTool <|.. MockSearchTool[MockSearchTool: Offline & Testing]
        SearchTool -->|2. Normalized SearchResult items| ResearchAgent
        ResearchAgent -->|3. Grounded Prompt| LLMService[Central LLMService]
        LLMService -->|4. Structured ExtractedTrends| ResearchAgent
        ResearchAgent --> ResearchResponse[Structured ResearchResponse]
    end

    ResearchResponse --> PlanningRequest[PlanningRequest]
    
    subgraph Planning Subsystem [Phase 4: Content Strategy]
        PlanningRequest --> PlanningAgent[2. Planning Agent]
        PlanningAgent -->|Evaluate & Plan Prompt| LLMService
        LLMService -->|Structured ContentPlan| PlanningAgent
        PlanningAgent -->|Grounding & Source Verification| ContentPlan[Structured ContentPlan]
    end

    subgraph LLM Service Layer [Phase 2: Provider Agnostic]
        LLMService -->|Bounded Retries & Factory| LLMProvider[<<interface>> LLMProvider]
        LLMProvider <|.. GroqProvider[GroqProvider: ChatGroq]
        LLMProvider <|.. FutureProvider[Future Providers: OpenAI / Anthropic]
    end

    Config --> LLMService
    Config --> TavilySearchTool
```

---

## 2. Agent Responsibilities & Pipeline Workflow

The multi-agent content generation lifecycle establishes clear role separation across stages:

```text
┌─────────────────────────┐
│   1. RESEARCH AGENT     │  Answers: "What is happening and what topics are relevant?"
│        (Phase 3)        │  Produces: ResearchResponse (grounded trends & search evidence)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   2. PLANNING AGENT     │  Answers: "What content should we create from this research?"
│        (Phase 4)        │  Produces: ContentPlan (topic, angle, hook, key points, CTA)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│    3. WRITER AGENT      │  Answers: "How should the actual post be written?"
│    (Future Phase 5)     │  Produces: DraftPost (platform-tailored copy & formatting)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│    4. CRITIC AGENT      │  Answers: "Is the copy accurate, brand-aligned, and engaging?"
│    (Future Phase 6)     │  Produces: ReviewFeedback & Quality Score
└─────────────────────────┘
```

---

## 3. Planning Agent Architecture (Phase 4)

### 3.1 Role & Boundaries

The **Planning Agent** bridges research and writing:
- **Inputs**: A structured `PlanningRequest` containing the `ResearchResponse` from Phase 3, plus target platform, audience, content goals, preferred tone, and content format.
- **Outputs**: A validated `ContentPlan` detailing topic, angle, hook direction, structured key points, call to action, and verified source citations.
- **Strict Boundary**: The Planning Agent does **not** generate final post copy or hashtags. It defines the editorial and strategic blueprint for the Writer Agent.

### 3.2 Domain Schemas & Exceptions

- **`PlanningRequest`**: Encapsulates `research: ResearchResponse`, `niche`, `audience`, `platform`, `language`, `content_goal`, `preferred_tone`, and `content_type`.
- **`ContentPlan`**: Structured output including `topic`, `angle`, `platform`, `audience`, `language`, `content_type`, `tone`, `hook_direction`, `key_points` (validated list >= 1), `cta_direction`, `source_references`, `selected_trend_topic`, and `reasoning`.
- **Custom Exceptions**:
  - `PlanningError`: Base exception for planning domain.
  - `EmptyResearchError`: Raised when input research contains no trends.
  - `UngroundedPlanError`: Raised when output violates grounding rules.
  - `PlanningValidationFailedError`: Raised when retry limits are exhausted.

### 3.3 Research Grounding & Anti-Hallucination

1. **Topic Anchoring**: The planned topic is validated against trends in `ResearchResponse.trends`.
2. **Source Citation Grounding**: The agent verifies that all `source_references` match real URLs or domain sources in the retrieved research data. If unsupported URLs are returned, they are sanitized and mapped to the matching trend's legitimate source.
3. **Research Fact vs. Content Strategy**: The agent clearly distinguishes factual source evidence from editorial perspective/angle.
4. **Empty Research Guard**: Rejects ungrounded execution if `ResearchResponse.trends` is empty with `EmptyResearchError`.

---

## 4. Implemented Modules Overview

| Subsystem | Module | Purpose |
|---|---|---|
| **Core App** | `backend/app/main.py` | FastAPI application initialization and lifespan management |
| **Configuration** | `backend/app/config.py` | Type-safe settings with environment variable loading |
| **Logging** | `backend/app/core/logging.py` | Centralized structured logging formatting |
| **Health API** | `backend/app/api/v1/health.py` | Basic liveness and readiness health check endpoints |
| **LLM Interface** | `backend/app/services/llm/base.py` | `LLMProvider` abstract base class defining `generate` & `generate_structured` |
| **LLM Exceptions** | `backend/app/services/llm/exceptions.py` | Hierarchical domain exceptions for configuration, provider, and response errors |
| **Groq Adapter** | `backend/app/services/llm/providers/groq.py` | `GroqProvider` implementing `LLMProvider` via LangChain's `ChatGroq` |
| **LLM Orchestrator** | `backend/app/services/llm/service.py` | `LLMService` with provider registry and bounded backoff retries |
| **Research Schemas** | `backend/app/models/research.py` | Pydantic models for inputs, search outputs, trends, and responses |
| **Search Tools** | `backend/app/tools/research/` | Abstract `SearchTool`, `TavilySearchTool`, and `MockSearchTool` |
| **Research Agent** | `backend/app/agents/research.py` | Topic discovery and source-grounded trend extraction |
| **Planning Schemas** | `backend/app/models/planning.py` | `PlanningRequest`, `ContentPlan`, and planning exceptions |
| **Planning Agent** | `backend/app/agents/planning.py` | Content strategy formulation and source-grounded planning |

---

## 5. Planned for Future Phases (Not Implemented Yet)

The following components represent future architecture milestones and are **not** yet implemented in Phase 4:

### 5.1 Writer Agent (Phase 5)
- Generates platform-specific social copy (Twitter/X threads, LinkedIn posts) implementing the `ContentPlan`.

### 5.2 Critic Agent (Phase 6)
- Evaluates draft content against quality metrics, brand guidelines, and factual consistency.

### 5.3 LangGraph Orchestration & Human-in-the-Loop (Phase 7)
- Coordinates Research → Planning → Writer → Critic → Human Approval graph with state transitions.

### 5.4 Database & Persistence Layer (Phase 8)
- SQLite with SQLAlchemy and Alembic migrations for local development; PostgreSQL for production.

### 5.5 Frontend Application & Publishing (Phase 9)
- React + Vite Single Page Application (SPA) and social media publishing engine with OAuth integrations.
