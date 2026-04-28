---
fileHash: 95fe48e1e315f06ee8224c30bb13d5c9
dependencies: []
---

# Code Documentation Standards

**Version:** 2.0
**Last Updated:** 2026-03-11
**Hub:** [idesign-method.md](idesign-method.md)

---

## Overview

This document defines code documentation standards for C# projects following the IDesign C# Coding Standard 2.4. Documentation must serve the developer reading the code — not satisfy a tool or process.

### Style Guide References

- **[IDesign C# Coding Standard 2.4](../IDesign%20C%23%20Coding%20Standard%202.4.pdf)** — Primary Standard
- **[IDesign Design Standard 1.0](../IDesign%20Design%20Standard.pdf)** — Architecture standard
- [Microsoft Style Guide](https://learn.microsoft.com/en-us/style-guide/welcome/)
- [Write the Docs Guide](https://www.writethedocs.org/guide/writing/docs-principles/)

---

## IDesign Philosophy on Documentation

The IDesign C# Coding Standard is explicit (§2.8–2.10):

> **Avoid comments that explain the obvious.** Code should be self-explanatory. Good code with readable variable and method names should not require comments.

> **Document only operational assumptions, algorithm insights, and so on.**

> **Avoid method-level documentation.** Use extensive external documentation for API documentation. Use method-level comments only as tool tips for other developers.

This means:
- Code clarity comes first; comments supplement, they don't substitute
- External API reference docs (generated from XML or a wiki) are preferred over inline `<summary>` saturation
- Inline comments exist to explain **why**, not **what**

---

## When to Document

### Always Document (Required)
- Non-obvious algorithms or business rules
- Operational assumptions (assertions are the code form; comments add context)
- Known workarounds, technical debt, or intentional trade-offs
- Magic numbers that cannot be replaced by a named constant
- IDesign component type and volatility (see Component Documentation below)

### Document Sparingly (as Tool Tips)
- Public API `<summary>` — brief, only when the name alone is insufficient
- `<param>` and `<returns>` — only when the meaning is not obvious from the name and type
- `<exception>` — when the exception condition is not self-evident

### Do Not Document
- Code that explains the obvious (e.g., `// Create a new list`)
- Method-level documentation as primary API reference (use external docs for that)
- Commented-out code — delete it; use version control

---

## Inline Comments

### Style Rules
- Explain **why**, not **what**
- Start with a capital letter
- End with a period for complete sentences
- Keep comments up to date with code changes
- Indent at the same level as the code being documented
- All comments pass spell-checking (sloppy spelling signals sloppy development)

### Good vs. Bad

```csharp
// Good: explains the why and constraint
// Pre-allocate with capacity estimate to reduce reallocations.
// Conservative estimate: average 5 chunks per file.
var entries = new List<IndexEntry>(Math.Max(1, totalFiles * 5));

// Good: explains a non-obvious algorithm step
// Force full GC to establish an accurate baseline before measurement.
GC.Collect(GC.MaxGeneration, GCCollectionMode.Forced, true);

// Bad: states the obvious
// Create a new list
var list = new List<string>();
```

---

## XML Documentation Comments

Use XML comments as **tool tips** for consumers of a component, not as primary documentation. Keep them brief.

### Minimum Required Tags (for public APIs)

```csharp
/// <summary>
/// Brief one-line description of what the class or method does.
/// </summary>
```

Add `<param>`, `<returns>`, and `<exception>` only when they add information beyond what the name and type already convey.

### Full Example — Method

```csharp
/// <summary>
/// Splits text into overlapping word-based chunks.
/// </summary>
/// <param name="text">The text to chunk. Must not be null or empty.</param>
/// <param name="chunkSize">Number of words per chunk. Must be greater than zero.</param>
/// <param name="chunkOverlap">Number of words shared between adjacent chunks.</param>
/// <returns>Ordered list of text chunks.</returns>
/// <exception cref="ArgumentNullException">Thrown when <paramref name="text"/> is null.</exception>
/// <exception cref="ArgumentException">Thrown when <paramref name="chunkSize"/> is not positive.</exception>
public List<string> ChunkText(string text, int chunkSize, int chunkOverlap)
{
```

### Full Example — Class with IDesign Component Note

```csharp
/// <summary>
/// Orchestrates the semantic indexing workflow.
/// </summary>
/// <remarks>
/// Component Type: Manager (Workflow Volatility).
/// Knows "when" — orchestrates DocumentExtractionEngine, TextChunkingEngine,
/// EmbeddingEngine, and VectorStorageAccessor. Does not implement business logic.
/// </remarks>
public class SemanticIndexManager : ISemanticIndexManager
{
```

---

## Component Documentation (IDesign)

Every IDesign component class should carry a `<remarks>` note stating its **component type** and **volatility**. This is the single documentation requirement that the IDesign standard adds beyond basic code clarity.

### Template

```csharp
/// <remarks>
/// Component Type: [Manager | Engine | ResourceAccess | Client | Utility]
/// Volatility: [brief description of what changes this component encapsulates]
/// [Optional: key dependencies or design constraint worth noting]
/// </remarks>
```

### Component Examples

**Manager:**
```csharp
/// <remarks>
/// Component Type: Manager (Workflow Volatility).
/// Encapsulates the indexing workflow — the sequence and coordination of
/// extraction, chunking, embedding, and storage. Orchestrates Engines and
/// ResourceAccess components. Publishes IndexBuiltEvent on completion.
/// </remarks>
```

**Engine:**
```csharp
/// <remarks>
/// Component Type: Engine (Algorithm Volatility).
/// Pure function — accepts text input, returns chunks. No I/O, no state,
/// no event publishing. Called by SemanticIndexManager.
/// </remarks>
```

**ResourceAccess:**
```csharp
/// <remarks>
/// Component Type: ResourceAccess (Storage Volatility).
/// Dumb CRUD over the local vector store. Abstracts the storage format.
/// No business logic.
/// </remarks>
```

**Client:**
```csharp
/// <remarks>
/// Component Type: Client (UI / Initiation Volatility).
/// Entry point for the index command. Validates user input, calls
/// SemanticIndexManager, displays result. Does not call Engines or ResourceAccess directly.
/// </remarks>
```

---

## Code Examples in Documentation

Include `<example>` blocks only when the usage is non-obvious or the API has multiple meaningful modes.

```csharp
/// <example>
/// <code>
/// using var monitor = new MemoryMonitor("Indexing", enabled: true);
/// _indexManager.BuildIndex(sourcePath, outputPath, chunkSize, chunkOverlap);
/// </code>
/// </example>
```

---

## Writing Style

Following Microsoft Style Guide conventions:

- **Active voice:** "The method returns" not "A value is returned"
- **Present tense:** "Returns" not "Will return"
- **Concise:** Remove filler words
- **No contractions:** "does not" not "doesn't"
- **Consistent terminology:** Use the same term throughout (do not alternate "accessor" and "resource access")
- **Code references:** Use `<c>code</c>` for inline code, `<see cref="TypeName"/>` for type references

---

## Documentation Checklist

Before committing code:

- [ ] Complex logic has inline comments explaining **why**
- [ ] No comments stating the obvious
- [ ] All comments spell-checked
- [ ] Public classes have `<summary>` tool-tip
- [ ] IDesign component type and volatility noted in `<remarks>`
- [ ] Exception conditions documented in `<exception>` when non-obvious
- [ ] No commented-out code
- [ ] Argument validation implemented (code documents itself via `ArgumentNullException`)

---

## References

- [idesign-method.md](idesign-method.md)
- [IDesign C# Coding Standard Compliance](idesign-csharp-standard.md)
- [Developer Quick Reference](idesign-quick-reference.md)
- [Microsoft Style Guide](https://learn.microsoft.com/en-us/style-guide/welcome/)
- [Write the Docs Guide](https://www.writethedocs.org/guide/writing/docs-principles/)

---

**Last Updated:** 2026-03-11
