#!/usr/bin/env python3
"""
Development CLI for the OCR/ingest pipeline.

Feeds a PNG directly into the pipeline and writes Markdown to stdout (or a file).
Bypasses BLE sync entirely — useful for iterating on OCR quality and AI prompts.

Progress and diagnostic output go to stderr; Markdown goes to stdout, so the
result is pipe-friendly:

  python tools/ingest.py note.png | pbcopy
  python tools/ingest.py note.png -o result.md

Stages and override flags:

  Stage 1 — Apple Vision OCR
    --first-line TEXT   Skip Vision; use TEXT as the header line.
                        Format: "VAULT_NAME  DOC_TYPE  [key=value ...]"
                        e.g.  "WORK TASK  project=atlas"

  Stage 2 — Header parse   (always runs; no override)

  Stage 3 — Vault rules + validation
    --vault-path PATH   Explicit vault root (otherwise resolved from env vars).
                        Skipped silently when vault is not configured.

  Stage 4 — AI transcription
    --handler NAME      AI handler name (default: settings default_handler).

Examples:
  python tools/ingest.py scan.png -v
  python tools/ingest.py scan.png --first-line "WORK TASK" --handler ollama-gemma -v
  python tools/ingest.py scan.png --vault-path ~/vaults/work -o out.md
"""

from __future__ import annotations

import argparse
import sys
import textwrap
import time
from pathlib import Path

# Allow running from the project root without installing as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.business_logic.engines.diagram_engine       import DiagramEngine
from app.business_logic.engines.transcription_engine import TranscriptionEngine
from app.business_logic.engines.validation_engine    import ValidationEngine
from app.business_logic.engines.vision_engine        import VisionEngine
from app.resource_access.vault_access                import VaultAccess
from app.utilities.handler_registry                  import HandlerRegistry, OllamaHandler
from app.utilities.models                            import DiagramConfig, NoteHeader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _info(verbose: bool, section: str) -> None:
    if verbose:
        print(f"\n─── {section}", file=sys.stderr)


def _detail(verbose: bool, key: str, value: str) -> None:
    if verbose:
        print(f"    {key}: {value}", file=sys.stderr)


def _parse_header(first_line: str) -> NoteHeader | None:
    """Replicates IngestManager._parse_header without requiring the full manager."""
    tokens = first_line.strip().split()
    if len(tokens) < 2:
        return None
    fields: dict[str, str] = {}
    for token in tokens[2:]:
        if "=" in token:
            key, _, val = token.partition("=")
            fields[key.lower()] = val
    return NoteHeader(vault_name=tokens[0].upper(), doc_type=tokens[1].upper(), fields=fields)


def _format_markdown(header: NoteHeader, body: str, timestamp: int) -> str:
    created     = time.strftime("%Y-%m-%d %H:%M", time.gmtime(timestamp))
    field_lines = "\n".join(f"{k}: {v}" for k, v in header.fields.items())
    separator   = "\n" + field_lines if field_lines else ""
    return textwrap.dedent(f"""\
        ---
        type: {header.doc_type}
        vault: {header.vault_name}
        created: {created}
        source: bamboo-slate{separator}
        ---

        {body}
    """).strip()


def _build_registry(handler_override: str | None) -> tuple[HandlerRegistry, str]:
    """Loads handler config from Settings; falls back to a default Gemma handler."""
    try:
        from app.utilities.settings import Settings
        settings     = Settings()
        settings.apply_on_startup()
        handlers     = settings.get_handlers()
        default_name = handler_override or settings.get_default_handler()
    except Exception:
        handlers     = []
        default_name = handler_override or "ollama-gemma"

    registry = HandlerRegistry()
    for h in handlers:
        if not h.get("enabled"):
            continue
        name  = h.get("name", "").strip()
        url   = h.get("url", "http://localhost:11434").strip()
        model = h.get("model", "").strip()
        if name and model:
            registry.register(name, OllamaHandler(model=model, base_url=url))

    if not registry.names():
        registry.register("ollama-gemma", OllamaHandler(model="gemma4:26b"))

    return registry, default_name or "ollama-gemma"


def _resolve_vault(name: str, explicit_path: Path | None) -> Path | None:
    if explicit_path:
        return explicit_path
    try:
        from app.utilities.config import resolve_vault_path
        return resolve_vault_path(name)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run the OCR/ingest pipeline on a PNG and print Markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("png",           type=Path,
                   help="Input PNG file.")
    p.add_argument("-o", "--output", type=Path, metavar="FILE",
                   help="Write Markdown to FILE instead of stdout.")
    p.add_argument("--first-line",   metavar="TEXT",
                   help="Override Vision OCR with a literal header line.")
    p.add_argument("--handler",      metavar="NAME",
                   help="AI handler name (default: from settings).")
    p.add_argument("--vault-path",   type=Path, metavar="PATH",
                   help="Vault root for rule validation.")
    p.add_argument("--timestamp",    type=int,  metavar="UNIX",
                   help="Override note timestamp (default: file mtime).")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Print step-by-step diagnostic output to stderr.")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args     = _parse_args()
    png_path = args.png.resolve()
    verbose  = args.verbose

    if not png_path.exists():
        print(f"error: file not found: {png_path}", file=sys.stderr)
        sys.exit(1)

    # ── Stage 1: Vision / override ───────────────────────────────────────
    if args.first_line:
        _info(verbose, "Stage 1 — First line (override)")
        first_line = args.first_line
    else:
        _info(verbose, "Stage 1 — Apple Vision OCR")
        first_line = VisionEngine().extract_first_line(png_path)

    _detail(verbose, "first_line", repr(first_line))

    if not first_line:
        print(
            "error: Vision returned no text.\n"
            "  Tip: add --first-line 'VAULT_NAME DOC_TYPE' to bypass OCR.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Stage 2: Header parse ─────────────────────────────────────────────
    _info(verbose, "Stage 2 — Header parse")
    header = _parse_header(first_line)

    if header is None:
        print(
            f"error: cannot parse header: {first_line!r}\n"
            "  Expected: VAULT_NAME  DOC_TYPE  [key=value ...]",
            file=sys.stderr,
        )
        sys.exit(1)

    _detail(verbose, "vault",  header.vault_name)
    _detail(verbose, "type",   header.doc_type)
    _detail(verbose, "fields", str(header.fields) if header.fields else "(none)")

    # ── Stage 3: Vault rules + validation ────────────────────────────────
    _info(verbose, "Stage 3 — Vault rules")
    diagram_config: DiagramConfig | None = None
    vault_path = _resolve_vault(header.vault_name, args.vault_path)

    if vault_path:
        _detail(verbose, "vault_path", str(vault_path))
        try:
            rules  = VaultAccess().read_rules(vault_path)
            result = ValidationEngine().validate(header, rules)
            if result.is_valid:
                _detail(verbose, "validation", "OK")
            else:
                _detail(verbose, "validation", f"missing: {result.missing_fields}")
                if verbose:
                    print(
                        "    (continuing — validation failures are informational in CLI mode)",
                        file=sys.stderr,
                    )
            if header.doc_type == "DIAGRAM":
                diagram_type   = header.fields.get("type", "")
                diagram_config = rules.diagram_types.get(diagram_type)
                _detail(verbose, "diagram_config",
                        f"{diagram_config.format}" if diagram_config else "not found")
        except Exception as exc:
            _detail(verbose, "vault error", str(exc))
    else:
        _detail(verbose, "vault_path", "not resolved — skipping validation")

    # ── Stage 4: AI transcription ─────────────────────────────────────────
    _info(verbose, "Stage 4 — AI transcription")
    registry, handler_name = _build_registry(args.handler)
    _detail(verbose, "handler", handler_name)

    try:
        if header.doc_type == "DIAGRAM" and diagram_config is not None:
            body = DiagramEngine(registry).transcribe_diagram(
                png_path, diagram_config, handler_name
            )
        else:
            body = TranscriptionEngine(registry).transcribe(png_path, handler_name)
    except Exception as exc:
        print(f"error: transcription failed: {exc}", file=sys.stderr)
        sys.exit(1)

    _detail(verbose, "output", f"{len(body or '')} chars")

    # ── Format and output ─────────────────────────────────────────────────
    ts       = args.timestamp or int(png_path.stat().st_mtime)
    markdown = _format_markdown(header, body or "", ts)

    if args.output:
        args.output.write_text(markdown, encoding="utf-8")
        if verbose:
            print(f"\nwrote {len(markdown)} chars → {args.output}", file=sys.stderr)
    else:
        print(markdown)


if __name__ == "__main__":
    main()
