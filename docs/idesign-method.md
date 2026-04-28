---
domain: work
tags: [work, career, skills, ea]
status: active
updated: 2026-03-11
fileHash: 6f934aed4de99e204f310460741d2011
dependencies: []
---

# iDesign Method & Standards

> **AI Instructions:** Load this file when the user asks to analyze, design, or reorganize a software system's architecture using the iDesign Method, or when the user asks about IDesign coding standards. This is the single hub for all iDesign content. Load the sub-files listed in Related only when deeper detail is needed.

---

## What iDesign Is

The iDesign Method, established by Juval Löwy, is a system design approach based on **Volatility-Based Decomposition (VBD)**. Systems are decomposed not by function or data, but by what is likely to change — grouping volatile elements together and isolating them from stable ones. The result is a layered service architecture with strict call-chain rules.

Two standards govern the method:

| Standard | Version | Scope |
|---|---|---|
| [IDesign Design Standard](../IDesign%20Design%20Standard.pdf) | 1.0 (Nov 2019) | System design, project design, service contracts |
| [IDesign C# Coding Standard](../IDesign%20C%23%20Coding%20Standard%202.4.pdf) | 2.4 (Jul 2011) | Naming, coding practices, project settings |

**Key resource:** *Righting Software* — Juval Löwy (Addison-Wesley, 2020)

---

## Design Standard Directives

**Prime Directive:** Never design against the requirements.

1. Avoid functional decomposition
2. Decompose based on volatility
3. Provide a composable design
4. Offer features as aspects of integration, not implementation
5. Design iteratively, build incrementally
6. Design the project to build the system
7. Drive educated decisions with viable options (schedule, cost, risk)
8. Build the project along its critical path
9. Be on time throughout the project

---

## Service Types (Component Taxonomy)

Every component must be classified into one of five types:

| Type | Symbol | Volatility Encapsulated | Role |
|---|---|---|---|
| **Client** | C | UI / initiation | Entry point; knows "what" the user wants |
| **Manager** | M | Workflow | Orchestrates; knows "when" to do things |
| **Engine** | E | Algorithm | Pure functions; knows "how" to do things |
| **ResourceAccess** | RA | Storage / resource | Dumb CRUD; knows "where" data lives |
| **Utility** | U | Cross-cutting | Callable by anyone (logging, config, security) |

---

## Closed Architecture (Call Chain)

```
Client
  └─▶ Manager ─▶ Engine
              ─▶ ResourceAccess ─▶ Resource
              ─▶ [queued call to one other Manager per use case]

All ─▶ Utility
```

### Interaction Rules (what IS allowed)
- All components can call Utilities
- Managers and Engines can call ResourceAccess
- Managers can call Engines
- Managers can queue calls to **one** other Manager per use case

### Interaction Don'ts (what is NOT allowed)
- Clients do not call multiple Managers in the same use case
- Managers do not queue to more than one Manager in the same use case
- Engines do not receive queued calls
- ResourceAccess does not receive queued calls
- Clients do not publish events
- Engines do not publish events
- ResourceAccess does not publish events
- Resources do not publish events
- Engines, ResourceAccess, and Resources do not subscribe to events

### Layer Rules
- Do not call up
- Do not call sideways (except queued Manager→Manager)
- Do not call more than one layer down
- Resolve attempts to open the architecture using queued calls or async event publishing

---

## Cardinality Guidelines

- Max **5 Managers** in a system without subsystems
- Max **handful** of subsystems
- Max **3 Managers** per subsystem
- Strive for a golden ratio of Engines to Managers
- ResourceAccess components may access more than one Resource if necessary

---

## System Design Guidelines

### Requirements
- Capture required behavior, not required functionality
- Describe behavior with use cases; use activity diagrams for nested conditions
- Eliminate solutions masquerading as requirements
- Validate design by ensuring it supports all core use cases

### Attributes
- Volatility decreases top-down (Clients most volatile, Resources least)
- Reuse increases top-down
- Do not encapsulate changes to the nature of the business
- Managers should be almost expendable
- Design should be symmetric
- Never use public communication channels for internal system interactions

---

## Service Contract Design Guidelines

1. Design reusable service contracts
2. Strive for **3–5 operations** per contract
3. Avoid contracts with a single operation; reject contracts with ≥20 operations
4. Avoid property-like operations
5. Limit contracts per service to **1 or 2**
6. Only the architect or competent senior developers design contracts

---

## Decomposition Process

When analyzing or designing a system, follow this sequence:

1. **Identify use cases** — list all system behaviors from the outside in
2. **Identify volatility axes** — for each behavior, ask: *what is likely to change independently?*
3. **Classify components** — assign each component a service type (C / M / E / RA / U)
4. **Draw the call chain** — map dependencies; every arrow must follow the interaction rules
5. **Check violations** — apply the Analysis Checklist below
6. **Propose restructuring** — rename, split, merge, or re-layer components to comply
7. **Document decisions** — record why each component was placed where it was

---

## Analysis Checklist

> Use when reviewing a project structure for iDesign compliance.

### Layer Violations
- [ ] Does any Client call something other than a Manager or Utility?
- [ ] Does any Client call multiple Managers in the same use case?
- [ ] Does any Client publish events?
- [ ] Does any Manager queue calls to more than one Manager in the same use case?
- [ ] Does any Engine receive queued calls?
- [ ] Does any Engine publish events or subscribe to events?
- [ ] Does any Engine call another Engine? (shared logic → Utility)
- [ ] Does any ResourceAccess call another ResourceAccess? (cross-RA logic → Manager/Engine)
- [ ] Does any ResourceAccess receive queued calls, publish events, or subscribe to events?
- [ ] Are there any circular dependencies?

### Decomposition Quality
- [ ] Is each Manager responsible for exactly one functional area / use case group?
- [ ] Is each Engine encapsulating a single volatile algorithm or rule set?
- [ ] Is each ResourceAccess component abstracted behind an interface?
- [ ] Are cross-cutting concerns (logging, auth, config) isolated in Utilities?
- [ ] Are there components that mix types (e.g., a Manager that also does data access)?

### Volatility Assessment
- [ ] Are volatile elements (algorithms, business rules) isolated from stable ones?
- [ ] Would a change to one component force changes in another? (indicates wrong grouping)
- [ ] Are there "god components" touching too many concerns? (candidate for split)

### Cardinality
- [ ] More than 5 Managers without subsystems?
- [ ] More than 3 Managers per subsystem?

---

## Project Analysis Template

> Fill in when analyzing a concrete project.

**Project:** [Name]
**Date:** [YYYY-MM-DD]
**Source:** [e.g., GitHub / Confluence / Description]

### Current Structure
```
[Paste or describe the existing component/folder/service structure here]
```

### Classification

| Component | Current name | Proposed type | Notes / Issues |
|---|---|---|---|
| [Component] | [Name] | [C / M / E / RA / U] | [e.g., mixes Manager and RA concerns] |

### Violations Found

| # | Violation type | Components involved | Severity |
|---|---|---|---|
| 1 | [e.g., Manager queues to two Managers] | [A → B, A → C] | High / Medium / Low |

### Proposed Restructuring

```
[Proposed structure: renamed/split/merged components in correct layers]
```

### Rationale

| Decision | Why |
|---|---|
| [e.g., Split XService into XManager + XEngine] | [Mixes orchestration and algorithm — separated by volatility] |

---

## C# Coding Standard 2.4 — Key Rules

For full rules see sub-files. Critical summary:

**Naming:** `m_PascalCase` for private fields (e.g., `m_Number`), `I` prefix for interfaces, PascalCase for types/methods/constants, camelCase for locals/parameters.

**Size limits:** Max 500 lines/file, 200 lines/method, 5 arguments/method, 120 chars/line.

**Interface design:** 3–5 members ideal; max 20; never 1; at least 2:1 method-to-property ratio.

**Documentation philosophy:** Avoid method-level docs; code should be self-explanatory; document only operational assumptions and algorithm insights; use external docs for API reference.

**Framework guidelines:** See [idesign-csharp-standard.md](idesign-csharp-standard.md) §4.3–4.8 for Multithreading, Serialization, Remoting, Security, System.Transactions, Enterprise Services.

---

## Active Tasks

| Task | Status | Due |
|---|---|---|
| [Task 1] | In Progress | [Date] |

---

## Related

**Sub-files:**
- [enterprise/work/idesign-csharp-standard.md](idesign-csharp-standard.md) — Full IDesign C# Coding Standard 2.4 compliance reference (all sections)
- [enterprise/work/idesign-code-documentation.md](idesign-code-documentation.md) — Documentation standards aligned with IDesign philosophy
- [enterprise/work/idesign-quick-reference.md](idesign-quick-reference.md) — Quick-reference card for day-to-day C# development

**Cross-domain connections:**
- [enterprise/work/career.md](career.md) — mastery of iDesign is a key architecture skill and career differentiator
- [enterprise/work/ea-services.md](ea-services.md) — iDesign informs EA governance and architecture service delivery
- [personal/learning/skills.md](../personal/learning/skills.md) — iDesign / VBD is tracked as a skill to develop and apply

---

## Notes & Decisions

| Date | Note |
|---|---|
| [YYYY-MM-DD] | [e.g., Agreed with team to use iDesign as standard for all greenfield projects] |
