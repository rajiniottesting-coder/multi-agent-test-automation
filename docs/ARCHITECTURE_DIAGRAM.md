# Architecture Diagram

This file renders natively on GitHub when viewed in the browser. The Mermaid source is also valuable on its own — paste it into [mermaid.live](https://mermaid.live) to edit.

## Pipeline overview

```mermaid
flowchart TB
    subgraph JIRA["🎫 Jira Cloud"]
        Story["📋 Story<br/>label: ai-ready"]
        TC["📝 Test Cases<br/>(linked issues)"]
    end

    subgraph PIPELINE["🔄 Pipeline"]
        A1["🤖 Agent 1: Analyst<br/>agent1_analyst.py"]
        H1{{"🛑 Human Gate<br/>label: human-approved"}}
        A2["🤖 Agent 2: Coder<br/>agent2_coder.py"]
        PR["🔀 GitHub PR<br/>auto/KEY-feature-name"]
        A3["🤖 Agent 3: Reviewer<br/>agent3_reviewer.py"]
        H2{{"🛑 Human Gate<br/>PR review + merge"}}
        A4["🤖 Agent 4: Runner<br/>agent4_runner.yml"]
        A5["🤖 Agent 5: Reporter<br/>agent5_reporter.py"]
    end

    subgraph LLM["🧠 LLM"]
        Gemini["Google Gemini 2.5 Flash<br/>+ Pydantic structured output"]
    end

    Story -->|"reads requirement"| A1
    A1 -->|"creates 5–8 issues"| TC
    A1 -->|"label: ai-processed"| Story
    TC --> H1
    H1 -->|"approved"| A2
    A2 -->|"generates code,<br/>opens PR"| PR
    A2 -->|"label: ai-coded"| Story
    PR --> A3
    A3 -->|"posts review<br/>comment"| PR
    PR --> H2
    H2 -->|"merged"| A4
    A4 -->|"junit.xml +<br/>HTML report"| A5
    A5 -->|"summary comment +<br/>label: tests-run"| Story

    A1 <-.->|"prompt +<br/>structured output"| Gemini
    A2 <-.->|"plan + per-file<br/>generation"| Gemini
    A3 <-.->|"review prompt"| Gemini
    A5 <-.->|"summary prompt"| Gemini

    classDef agent fill:#4a90e2,stroke:#2c5aa0,color:#fff
    classDef human fill:#f5a623,stroke:#b07415,color:#fff
    classDef jira fill:#0052cc,stroke:#003d99,color:#fff
    classDef llm fill:#34a853,stroke:#1e7733,color:#fff
    classDef artifact fill:#9b9b9b,stroke:#666,color:#fff

    class A1,A2,A3,A4,A5 agent
    class H1,H2 human
    class Story,TC jira
    class Gemini llm
    class PR artifact
```

## Component view

```mermaid
flowchart LR
    subgraph CFG["⚙️ Configuration Layer"]
        CY["config.yaml<br/>app_under_test, agents, browser"]
        ENV[".env<br/>secrets"]
        AC["AppContext<br/>app_context.py"]
        CY --> AC
        ENV --> AC
    end

    subgraph DATA["📦 Data Layer"]
        INV["app_inventory/<app>.json<br/>pages, selectors, methods"]
        REF["features/<ref>.feature<br/>tests/step_defs/test_<ref>.py<br/>pages/<ref>_page.py"]
        ACMD["prompts/app_context.md<br/>app-specific analyst guidance"]
    end

    subgraph PROMPTS["📝 Prompts Layer<br/>(app-agnostic + placeholders)"]
        P1["agent1_analyst.md"]
        P2P["agent2_coder_plan.md"]
        P2G["agent2_coder_generate.md"]
        P3["agent3_reviewer.md"]
        P5["agent5_reporter.md"]
    end

    subgraph AGENTS["🤖 Agents Layer<br/>(app-agnostic)"]
        AG1["agent1_analyst.py"]
        AG2["agent2_coder.py"]
        AG3["agent3_reviewer.py"]
        AG5["agent5_reporter.py"]
    end

    subgraph CLIENTS["🔌 External Adapters"]
        JC["jira_client.py<br/>Jira API"]
        GC["github_client.py<br/>GitHub API"]
        LC["llm_client.py<br/>Gemini + retry/quota"]
    end

    AC --> AG1
    AC --> AG2
    AC --> AG3
    INV -.uses.-> AC
    REF -.uses.-> AC
    ACMD -.uses.-> AG1

    AG1 --> P1
    AG2 --> P2P
    AG2 --> P2G
    AG3 --> P3
    AG5 --> P5

    AG1 --> JC
    AG1 --> LC
    AG2 --> JC
    AG2 --> GC
    AG2 --> LC
    AG3 --> GC
    AG3 --> LC
    AG5 --> JC
    AG5 --> LC

    classDef cfg fill:#e8f4f8,stroke:#4a90e2
    classDef data fill:#fef5e7,stroke:#f5a623
    classDef prompt fill:#e8f5e9,stroke:#34a853
    classDef agent fill:#e3f2fd,stroke:#2c5aa0
    classDef client fill:#f3e5f5,stroke:#8e24aa

    class CY,ENV,AC cfg
    class INV,REF,ACMD data
    class P1,P2P,P2G,P3,P5 prompt
    class AG1,AG2,AG3,AG5 agent
    class JC,GC,LC client
```

## Agent 2 internal flow (two-stage generation)

```mermaid
sequenceDiagram
    participant U as User / Scan
    participant A2 as Agent 2 (Coder)
    participant J as Jira
    participant L as LLM (Gemini)
    participant V as Validators
    participant G as GitHub

    U->>A2: --story SCRUM-5
    A2->>A2: AppContext.load()
    A2->>J: get linked Test Cases
    J-->>A2: list of test cases
    A2->>A2: dedup against<br/>existing scenarios

    Note over A2,L: STAGE 1 — Plan
    A2->>L: prompt + CodePlan schema
    L-->>A2: CodePlan (file paths,<br/>branch name, PR title)
    A2->>A2: validate_no_reserved_paths

    Note over A2,L: STAGE 2 — Per-file generation
    loop for each file in plan
        A2->>L: prompt + file metadata
        L-->>A2: file content (text)
        A2->>A2: extract from markdown fences
    end

    Note over A2,V: Hard validators
    A2->>V: validate_filename_consistency
    V-->>A2: errors / corrections
    A2->>V: validate_step_definitions_complete
    V-->>A2: errors / OK

    Note over A2,G: Push & open PR
    A2->>G: create branch
    A2->>G: commit each file
    A2->>G: open PR
    G-->>A2: PR URL
    A2->>J: label parent ai-coded
```

## State / labels lifecycle

```mermaid
stateDiagram-v2
    [*] --> ai_ready: Human creates story
    ai_ready --> ai_processed: Agent 1 runs

    state human_review <<choice>>
    ai_processed --> human_review: Human reviews TCs
    human_review --> human_approved: ✅ Approve
    human_review --> ai_skip: ❌ Reject
    human_review --> ai_processed: Edit & retry

    human_approved --> ai_coded: Agent 2 runs

    state pr_state <<choice>>
    ai_coded --> pr_state: Human reviews PR
    pr_state --> tests_run: Merge → Agent 4+5 run
    pr_state --> ai_regenerate: Request changes

    ai_regenerate --> ai_coded: Agent 2 runs<br/>(rev2 branch)

    tests_run --> [*]
    ai_skip --> [*]: Story closed (skipped)
```

## Updating this diagram

1. Edit the Mermaid blocks above directly in this `.md` file
2. Preview on [mermaid.live](https://mermaid.live) to verify rendering
3. GitHub renders Mermaid natively in `.md` files — no extra build step

The `README.md` and `docs/GUIDE.md` link to this file. If you change the high-level pipeline, update both:
- `README.md` — the ASCII art under "Architecture"
- `docs/GUIDE.md` — the ASCII art under "Architecture"
- This file — the Mermaid source
