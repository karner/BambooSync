# Input Workflow Design

Architecture decisions for the note classification and routing pipeline built on top of the Bamboo Slate sync system.

---

## 1. Pipeline Overview

After `sync.py` downloads and renders a note as PNG, a classification and routing stage runs before the note body is processed:

```
PNG
 └─▶ Vision API (top 20% of image) ──▶ first line text
      └─▶ parse: VAULT_NAME + DOC_TYPE + optional KEY=value pairs
           └─▶ resolve vault path from env var
                └─▶ load vault's _slate-config.md
                     └─▶ validate completeness
                          ├─▶ complete ──▶ transcribe body ──▶ dispatch to handler
                          │                                        └─▶ write to {vault}/ingest/
                          └─▶ incomplete ──▶ write partial to pipeline _pending/
                                             └─▶ write missing-info subtask to {vault}/ingest/
```

The vault's `ingest/` directory is the single drop point. The vault (via its own automations, Templater, Dataview, etc.) handles routing files from `ingest/` into their correct internal locations.

Full note body transcription (Ollama/Moondream) runs only after routing is confirmed — not before.

---

## 2. First-Line Convention

Every note begins with a structured header line:

```
VAULT_NAME  DOC_TYPE  [KEY=value ...]
```

Examples:
```
WORK  TASK  PROJECT=alpha PRIORITY=high
WORK  TASK_UPDATE  ID=task-42
PERSONAL  WORKFLOW  WF=weekly-review
WORK  DIAGRAM  TYPE=flowchart
RESEARCH  NOTE  TAGS=idea,ux
```

Rules:
- `VAULT_NAME` resolves to env var `VAULT_<NAME>_PATH` (case-folded)
- `DOC_TYPE` must be in the vault's `accepted_types` list
- Key=value pairs are type-specific; missing required ones trigger the subtask mechanism
- If Vision API cannot extract a valid header, the note is quarantined to `./unrouted/`

**Decision:** Routing is encoded in the first line so Vision only reads a small, predictable region of the PNG. This avoids sending the full note to an LLM before knowing where it belongs.

---

## 3. Vault Routing via Environment Variables

```
VAULT_WORK_PATH=/Users/mathiaskarner/Documents/work-vault
VAULT_PERSONAL_PATH=/Users/mathiaskarner/Documents/personal-vault
VAULT_RESEARCH_PATH=/Users/mathiaskarner/Documents/research-vault
```

The pipeline maps `VAULT_{NAME}_PATH` at runtime. If the env var is absent, the note is quarantined to `./unrouted/YYYYMMDD_HHMMSS.png` with a log warning.

`config.toml` can hold vault paths as a fallback (consistent with the existing `config.toml` pattern in `sync.py`), but env vars take precedence.

**Decision:** Environment variables keep vault paths out of the codebase and allow per-machine configuration without code changes.

---

## 4. Apple Vision API for First-Line Extraction

The macOS Vision framework (`VNRecognizeTextRequest`) scans the **top 20% of the note PNG** to extract text, then selects the topmost bounding-box region as the first line.

**Implementation:** PyObjC bindings via `pyobjc-framework-Vision` — native Python, no subprocess, runs on-device with Neural Engine acceleration.

**Division of responsibility:**
- Vision: first-line extraction only — fast, offline, no LLM required
- LLM (Ollama): full note body transcription — runs after routing is confirmed

**Decision:** Routing decisions must not require a full LLM call. Vision is faster, works offline, and is deterministic enough for structured header parsing.

---

## 5. AI Handler Registry (Pluggable Backends)

The pipeline must not hardcode any AI backend. Different workflows may use different models, and new backends must be addable without modifying core pipeline code.

**Design: handler registry pattern**

A handler is any callable that accepts `(note_body: str, context: dict) -> str` and returns the processed result. Handlers are registered by name at startup:

```python
HANDLER_REGISTRY = {
    "ollama-moondream": OllamaHandler(...),
    "ollama-gemma":     OllamaHandler(model="gemma4:26b"),
    "claude":           ClaudeHandler(...),
    "openai":           OpenAIHandler(...),
    # add new handlers without changing dispatch logic
}
```

Each workflow definition in the vault specifies which handler to use via a `handler:` field. If omitted, a default handler from `config.toml` is used.

**Extension:** Adding a new backend means implementing the handler interface and registering it — no changes to the validation gate, dispatcher, or vault config.

**Decision:** Vault owners can switch AI backends per workflow by editing their `_slate-config.md` or workflow definition files. The pipeline stays backend-agnostic.

---

## 6. Vault-Internal Rules File (`_slate-config.md`)

Each vault contains `_slate-config.md` at its root. The pipeline reads it on every dispatch. A template is provided at `_slate-config.template.md`.

**What the rules file governs:**
- Accepted document types for this vault
- Required and optional fields per type
- Which types trigger workflows (and where workflow definitions live)
- Default AI handler for this vault
- Diagram type definitions including allowed elements

**Decision:** Rules stay in the vault, not in pipeline code. Vault owners control their own intake rules. The vault is self-documenting — its rules are readable by anyone opening it.

---

## 7. Validation Gate

Before any handler runs, the pipeline:

1. Reads the vault's `_slate-config.md`
2. Checks that all `required_fields` for the detected `DOC_TYPE` are present (from first-line key=value pairs and/or transcribed body)
3. Decides one of three outcomes:

| Outcome | Condition | Action |
|---------|-----------|--------|
| **Dispatch to workflow** | All fields present + `triggers_workflow: true` | Load workflow definition, pass to configured AI handler, write result to `{vault}/ingest/` |
| **Direct write** | All fields present + `triggers_workflow: false` | Write structured markdown to `{vault}/ingest/` |
| **Incomplete** | One or more required fields missing | Write partial note to pipeline `_pending/`, write missing-info subtask to `{vault}/ingest/` |

**Decision:** AI workflows only run with complete inputs. Partial context produces unreliable outputs. The gate makes gaps explicit and actionable rather than silently processing broken notes.

---

## 8. Incomplete Notes → Follow-up Subtask

When a note is missing required fields:

1. The partial note is written to the **pipeline's** `_pending/YYYYMMDD_HHMMSS_partial.md` (not the vault — it's not ready)
2. A missing-info subtask is written to **`{vault}/ingest/`** so it appears in the vault's normal workflow

```markdown
---
type: MISSING_INFO
original_file: _pending/YYYYMMDD_HHMMSS_partial.md
created: YYYY-MM-DD HH:MM
vault: VAULT_NAME
doc_type: DOC_TYPE
---

## Missing fields for [DOC_TYPE]

- [ ] `field_name` — [what is needed, e.g. "project this task belongs to"]
- [ ] `field_name` — [what is needed]

Resolve by writing a TASK_UPDATE note referencing the original, or editing _pending directly and re-triggering.
```

**Decision:** Incomplete notes are held in the pipeline (not in the vault) until resolved. Only the subtask goes to the vault, making the gap visible without polluting the vault with half-formed content.

---

## 9. Output: Single Ingest Directory

All pipeline output — completed notes, workflow results, diagrams, missing-info subtasks — is written to `{vault}/ingest/`. The vault handles routing from there using its own automations.

**Ingest file naming:**
```
{vault}/ingest/YYYYMMDD_HHMMSS_{DOC_TYPE}.md
```

Files carry a `type:` field in YAML frontmatter so the vault can route them:

```yaml
---
type: TASK          # or TASK_UPDATE, WORKFLOW, DIAGRAM, NOTE, MISSING_INFO
created: YYYY-MM-DD HH:MM
source: bamboo-slate
vault: VAULT_NAME
---
```

**Decision:** A single drop point keeps the pipeline simple. The vault's existing automation layer (Templater, Dataview, Obsidian plugins) is better suited to routing content within the vault than pipeline code is. The pipeline's job ends at ingest.

---

## 10. Cross-Vault Collection

A vault can collect files from other vaults that are relevant to it. This is a vault-side concern — the pipeline writes to the target vault only; any cross-vault collection is handled by the vaults themselves.

**Mechanism (vault-side):** Each vault can define a `cross_vault_watch` list in `_slate-config.md`. A separate background process (or Obsidian plugin) monitors those vaults' `ingest/` directories and copies or symlinks relevant files.

Relevance is defined per vault — e.g., the RESEARCH vault might collect any note tagged `research` from the WORK vault's ingest.

**Decision:** Cross-vault collection is not the pipeline's responsibility. The pipeline routes to one vault per note (as specified in the first line). Vaults define their own collection rules. This keeps the pipeline's scope narrow.

---

## 11. Diagrams: Mermaid / PlantUML with Restricted Elements

Primary output formats: **Mermaid** and **PlantUML**. Other formats can be added.

**Element restriction:** Each diagram type definition in `_slate-config.md` carries an `allowed_elements` list. When the AI transcribes a handwritten diagram, the prompt includes this list as a hard constraint — the AI may only emit elements from it.

This prevents hallucinated syntax, keeps diagrams valid, and lets vault owners control the vocabulary of each diagram type without changing pipeline code.

Example definition in `_slate-config.md`:
```yaml
diagram_type: flowchart
format: mermaid
allowed_elements:
  - "flowchart TD"
  - "flowchart LR"
  - "-->"
  - "---"
  - "-.->"
  - "[rectangular label]"
  - "{diamond decision}"
  - "(rounded)"
```

The AI prompt for diagram transcription becomes:
> "Convert this handwritten diagram to Mermaid syntax. You may only use the following elements: [list]. Do not introduce any syntax not in this list."

**Decision:** Element restriction is defined in the vault (not hardcoded in the pipeline), so vault owners can tighten or expand the vocabulary per diagram type. The pipeline just passes the list into the AI prompt.

---

## 12. Open Questions

All previously open questions are now resolved. No outstanding blockers.

Implementation order:
1. Vision API first-line extractor
2. Vault router + env var resolver
3. `_slate-config.md` parser
4. Validation gate
5. Handler registry + default Ollama handler
6. Ingest writer (with YAML frontmatter)
7. Missing-info subtask generator
8. Diagram handler with element-restricted prompts
9. Cross-vault collection (vault-side, out of pipeline scope)
