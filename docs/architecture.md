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
- **Phase 5: Writer / Generation Agent** (Platform-aware copy generation, plan adherence, length validation, source citation grounding)
- **Phase 6: Critic / Reviewer Agent** (Deterministic quality checks, source grounding verification, structured LLM evaluation, APPROVED/REVISE decision logic)

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

    ContentPlan --> WriterRequest[WriterRequest]

    subgraph Writer Subsystem [Phase 5: Copy Generation]
        WriterRequest --> WriterAgent[3. Writer Agent]
        WriterAgent -->|Platform-Aware Prompt| LLMService
        LLMService -->|Structured SocialPost| WriterAgent
        WriterAgent -->|Plan Adherence & Length Check| SocialPost[Structured SocialPost]
    end

    SocialPost --> ReviewRequest[ReviewRequest]
    ContentPlan --> ReviewRequest
    ResearchResponse -.-> ReviewRequest

    subgraph Critic Subsystem [Phase 6: Quality Review]
        ReviewRequest --> CriticAgent[4. Critic Agent]
        CriticAgent -->|Deterministic Checks| QualityRules[Rule-Based Validation]
        CriticAgent -->|Structured Review Prompt| LLMService
        LLMService -->|Structured Review Findings| CriticAgent
        CriticAgent -->|Decision Fusion: APPROVED / REVISE| CriticResult[Structured CriticResult]
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
│        (Phase 5)        │  Produces: SocialPost (platform-tailored copy, hashtags, grounding)
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│    4. CRITIC AGENT      │  Answers: "Is the copy accurate, brand-aligned, and engaging?"
│        (Phase 6)        │  Produces: CriticResult (APPROVED / REVISE, actionable feedback)
└───────────┬─────────────┘
            │
            ├──► [APPROVED] ──► Human Review / Future Publishing Engine
            │
            └──► [REVISE]   ──► Writer Agent Iteration Loop (Future LangGraph Phase 7)
```

---

## 3. Critic / Reviewer Agent Architecture (Phase 6)

### 3.1 Role & Boundaries

The **Critic Agent** provides independent quality assurance and compliance evaluation:
- **Inputs**: A structured `ReviewRequest` containing the `SocialPost`, `ContentPlan`, optional `ResearchResponse`, and optional `brand_guidelines`.
- **Outputs**: A structured `CriticResult` containing `decision` (`APPROVED` or `REVISE`), `issues`, `feedback`, `checks: QualityChecks`, `verified_sources`, and `unverified_claims`.
- **Strict Boundary**: The Critic Agent evaluates and diagnoses issues, but **never rewrites the post copy**. It provides clear, actionable feedback for subsequent Writer Agent revision iterations.

### 3.2 Evaluation Dimensions & Quality Checks

1. **Relevance & Topic Alignment**: Verifies that the post addresses the planned topic and angle without topic divergence.
2. **Plan Adherence**: Ensures inclusion of key points, intended format, language, and audience targeting.
3. **Source Grounding & Anti-Hallucination**: Verifies all cited URLs/sources against supplied research trends and planned references. Flags unsupported or fabricated citations.
4. **Clarity & Structure**: Assesses readability, formatting whitespace, opening hook strength, and coherence.
5. **Tone & Platform Fit**: Enforces platform-specific voice (professional for LinkedIn, punchy for X/Twitter).
6. **Platform Length Constraints**: Enforces deterministic length bounds (e.g. ≤350 chars for X/Twitter single posts).
7. **Call to Action (CTA)**: Ensures the concluding prompt aligns with `ContentPlan.cta_direction`.
8. **Hashtags**: Validates hashtag counts and formats against platform standards.
9. **Originality & Repetition**: Detects verbatim duplicate sentences or excessive filler.

### 3.3 Deterministic & LLM Decision Fusion Logic

The final verdict is derived deterministically:
$$\text{Final Decision} = \begin{cases} \text{REVISE} & \text{if any deterministic check fails or deterministic issue is found} \\ \text{REVISE} & \text{if LLM evaluation recommends REVISE or finds defects} \\ \text{APPROVED} & \text{if all deterministic checks and LLM quality checks pass with zero defects} \end{cases}$$

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
| **Content Schemas** | `backend/app/models/content.py` | `WriterRequest`, `SocialPost`, and writer exceptions |
| **Writer Agent** | `backend/app/agents/writer.py` | Platform-tailored social copy generation, length validation, and citation grounding |
| **Critic Schemas** | `backend/app/models/critic.py` | `ReviewRequest`, `CriticResult`, `QualityChecks`, and critic exceptions |
| **Critic Agent** | `backend/app/agents/critic.py` | Quality assurance, source grounding verification, and APPROVED/REVISE decision logic |

---

## 5. Planned for Future Phases (Not Implemented Yet)

The following components represent future architecture milestones and are **not** yet implemented in Phase 6:

### 5.1 LangGraph Orchestration & Human-in-the-Loop (Phase 7)
- Coordinates Research → Planning → Writer → Critic → Review/Revision Loop with StateGraph and conditional edges.

### 5.2 Database & Persistence Layer (Phase 8)
- SQLite with SQLAlchemy and Alembic migrations for local development; PostgreSQL for production.

### 5.3 Frontend Application & Publishing (Phase 9)
- React + Vite Single Page Application (SPA) and social media publishing engine with OAuth integrations.
