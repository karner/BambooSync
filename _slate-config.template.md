# Slate Config — [Vault Name]

Read by the bamboo-slate pipeline to validate and route incoming handwritten notes.
Keep this file at the vault root as `_slate-config.md`. Do not rename it.

All processed notes are written to this vault's `ingest/` directory.
The vault's own automations route files from `ingest/` into their final locations.

---

## Vault Identity

```yaml
vault_name: VAULTNAME          # must match the VAULT_<NAME>_PATH env var key
default_handler: ollama-gemma  # AI handler used when a workflow does not specify one
```

---

## Accepted Document Types

Types not listed here are rejected and quarantined by the pipeline.

```yaml
accepted_types:
  - TASK
  - TASK_UPDATE
  - WORKFLOW
  - DIAGRAM
  - NOTE
```

---

## Field Definitions

### TASK — create a new task

```yaml
doc_type: TASK
required_fields:
  - title        # short description of the task
  - project      # which project this belongs to
optional_fields:
  - priority     # high / medium / low
  - due          # YYYY-MM-DD
  - assignee     # person responsible
  - tags
triggers_workflow: false
```

### TASK_UPDATE — update an existing task

```yaml
doc_type: TASK_UPDATE
required_fields:
  - id           # identifier of the existing task
  - update       # description of what is being changed or added
optional_fields:
  - status       # open / in-progress / done / blocked
  - due          # revised due date
  - assignee
triggers_workflow: false
```

### WORKFLOW — trigger a named workflow

The `wf` value must match a filename (without `.md`) inside `workflow_dir`.

```yaml
doc_type: WORKFLOW
required_fields:
  - wf           # workflow name, e.g. wf=weekly-review → workflows/weekly-review.md
optional_fields:
  - context      # free-form context passed to the workflow as input
  - priority     # high / medium / low
  - handler      # overrides vault default_handler for this run
triggers_workflow: true
workflow_dir: workflows        # relative to vault root
```

Workflow definition files (`workflows/*.md`) specify the AI prompt template and may include a `handler:` field in their frontmatter to override the vault default.

### DIAGRAM — capture a hand-drawn diagram

The `type` value must match a key in `diagram_types` below.

```yaml
doc_type: DIAGRAM
required_fields:
  - type         # must match a key in diagram_types
optional_fields:
  - title
  - description
  - handler      # overrides vault default_handler
triggers_workflow: false
```

### NOTE — general note or ideation

```yaml
doc_type: NOTE
required_fields: []
optional_fields:
  - tags
  - project
triggers_workflow: false
```

---

## Diagram Types

Each diagram type defines its output format and the elements the AI is allowed to emit.
The pipeline passes `allowed_elements` as a hard constraint in the AI transcription prompt.

```yaml
diagram_types:

  flowchart:
    format: mermaid
    allowed_elements:
      - "flowchart TD"
      - "flowchart LR"
      - "-->"
      - "---"
      - "-.->"
      - "[rectangular label]"
      - "{diamond decision}"
      - "(rounded node)"
      - "((circle))"

  sequence:
    format: plantuml
    allowed_elements:
      - "@startuml / @enduml"
      - "participant"
      - "actor"
      - "->"
      - "-->"
      - "note left / note right / note over"
      - "activate / deactivate"
      - "loop"
      - "alt / else"

  mindmap:
    format: mermaid
    allowed_elements:
      - "mindmap"
      - "root node (indented with spaces)"
      - "::icon()"
      - "child node"

  # Add further types here. Each must have format and allowed_elements.
```

---

## Cross-Vault Collection

List other vaults whose ingest content this vault should collect.
Each entry specifies which `doc_types` and/or `tags` are relevant.
Collection is handled by a vault-side process, not the pipeline.

```yaml
cross_vault_watch:
  - vault: WORK
    collect_if:
      doc_types: [NOTE, TASK]
      tags: [research, shared]
  # - vault: PERSONAL
  #   collect_if:
  #     doc_types: [NOTE]
```

---

## Registered AI Handlers

The pipeline's handler registry is configured in `config.toml`. This section documents
which handler names are available so workflow authors can reference them correctly.

```yaml
# Available handler names (defined in pipeline config.toml):
#   ollama-moondream  — local vision model, good for raw transcription
#   ollama-gemma      — local LLM, good for structured output and reasoning
#   claude            — Anthropic Claude API (requires ANTHROPIC_API_KEY)
#   openai            — OpenAI API (requires OPENAI_API_KEY)
#
# To add a new handler, register it in config.toml and implement the handler
# interface in the pipeline. No changes to this file needed.
```
