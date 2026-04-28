---
fileHash: 9304475aeb928f5790917a089c4a592b
dependencies: []
---

# Developer Quick Reference

**Standard:** IDesign C# Coding Standard 2.4
**Last Updated:** 2026-03-11
**Hub:** [idesign-method.md](idesign-method.md)

---

## Quick Links

- [idesign-method.md](idesign-method.md) — Architecture, component taxonomy, all standards
- [IDesign C# Coding Standard Compliance](idesign-csharp-standard.md) — Full compliance checklist
- [Code Documentation Standards](idesign-code-documentation.md) — Documentation guidelines

---

## Naming — Critical Rules

| Element | Convention | Example |
|---|---|---|
| Types, methods, constants | PascalCase | `SomeClass`, `BuildIndex` |
| Local variables, parameters | camelCase | `chunkSize`, `fileName` |
| **Private member variables** | **`m_` + PascalCase** | **`m_EventBus`, `m_Logger`** |
| Interfaces | `I` prefix | `ISemanticIndexManager` |
| Attributes | `Attribute` suffix | `MyAttribute` |
| Exceptions | `Exception` suffix | `MyException` |

> `m_PascalCase` for private fields — **not** `_camelCase`.

---

## Code Structure (IDesign VBD)

```
Client        → knows "what" (user intent); calls one Manager per use case
  └─ Manager  → knows "when" (workflow); orchestrates; publishes events
       ├─ Engine         → knows "how" (algorithms); pure functions; no I/O
       └─ ResourceAccess → knows "where" (storage); dumb CRUD only
All → Utility (cross-cutting helpers)
```

**Call direction: downward only.** Managers may queue to one other Manager per use case.

---

## Size Limits

| Scope | Limit |
|---|---|
| File | 500 lines max |
| Method | 200 lines max |
| Method arguments | 5 max |
| Line length | 120 characters max |
| Interface members | 3–5 ideal; 20 absolute max |

---

## Component Skeleton

### Manager

```csharp
/// <summary>Brief description.</summary>
/// <remarks>
/// Component Type: Manager (Workflow Volatility).
/// Encapsulates [workflow description]. Orchestrates [Engines + ResourceAccess].
/// </remarks>
public class SomeManager : ISomeManager
{
    private readonly ISomeEngine m_Engine;
    private readonly ISomeResourceAccess m_Storage;
    private readonly IEventBus m_EventBus;

    public SomeManager(ISomeEngine engine, ISomeResourceAccess storage, IEventBus eventBus)
    {
        m_Engine = engine ?? throw new ArgumentNullException(nameof(engine));
        m_Storage = storage ?? throw new ArgumentNullException(nameof(storage));
        m_EventBus = eventBus ?? throw new ArgumentNullException(nameof(eventBus));
    }
}
```

### Engine

```csharp
/// <summary>Brief description.</summary>
/// <remarks>
/// Component Type: Engine (Algorithm Volatility).
/// Pure function — no I/O, no state, no events.
/// </remarks>
public class SomeEngine : ISomeEngine
{
    public ResultType Process(InputType input)
    {
        if (input == null)
            throw new ArgumentNullException(nameof(input));

        // implementation
    }
}
```

### ResourceAccess

```csharp
/// <summary>Brief description.</summary>
/// <remarks>
/// Component Type: ResourceAccess (Storage Volatility).
/// Dumb CRUD — no business logic.
/// </remarks>
public class SomeResourceAccess : ISomeResourceAccess
{
    public void Save(DataType data, string path)
    {
        if (data == null)
            throw new ArgumentNullException(nameof(data));
        if (string.IsNullOrEmpty(path))
            throw new ArgumentException("Path must not be empty.", nameof(path));

        // storage operation only
    }
}
```

---

## Coding Rules — Quick Checklist

### Must Do
- [ ] Private fields: `m_PascalCase`
- [ ] Validate all arguments; throw `ArgumentNullException` / `ArgumentException`
- [ ] Use `readonly` (not `const`) for non-natural constants
- [ ] Use automatic properties; no public/protected member variables
- [ ] Use `String.Empty` not `""`
- [ ] Use `StringBuilder` for building long strings
- [ ] Check delegate for `null` before invocation
- [ ] Use `EventHandler<T>` not custom delegates
- [ ] Use `as` for defensive casting, check result before use
- [ ] `default` case in every `switch` with `Debug.Assert(false)`
- [ ] Assert every assumption (avg every 6th line)
- [ ] Use `using` statements; never fully qualified type names in code

### Must Not Do
- [ ] No `_camelCase` private fields
- [ ] No ternary operator
- [ ] No `#if…#endif`; use `[Conditional]` methods
- [ ] No function calls in Boolean conditions (assign to local variable first)
- [ ] No `if` without curly braces
- [ ] No `var` unless type is obvious from right side
- [ ] No custom exception classes unless truly necessary
- [ ] No error codes as return values
- [ ] No `goto` except `switch` fall-through
- [ ] No `this.` except in constructor chaining
- [ ] No `base.` except to resolve name conflict or call base constructor
- [ ] No `GC.AddMemoryPressure()`

---

## Documentation Quick Rules

- Comment **why**, not **what** — code explains itself
- Component type + volatility in `<remarks>` — always
- `<summary>` as tool tip — brief, only when name isn't enough
- Spell-check all comments
- Delete commented-out code

```csharp
// Good: explains a non-obvious constraint
// Pre-allocate with capacity estimate to avoid reallocations.
var entries = new List<IndexEntry>(Math.Max(1, totalFiles * 5));

// Bad: obvious
// Create list
var list = new List<string>();
```

---

## Common Patterns

### Argument Validation

```csharp
public void DoWork(string input, int count)
{
    if (input == null)
        throw new ArgumentNullException(nameof(input));
    if (count <= 0)
        throw new ArgumentException("Count must be greater than 0.", nameof(count));
}
```

### Event Publishing (Manager)

```csharp
m_EventBus.Publish(new WorkCompletedEvent
{
    OutputPath = outputPath,
    ItemCount = items.Count
});
```

### Defensive Interface Query

```csharp
var provider = obj as IMyInterface;
if (provider != null)
{
    provider.Method1();
}
```

### Switch with Default Assert

```csharp
switch (status)
{
    case Status.Active:
        HandleActive();
        break;
    case Status.Inactive:
        HandleInactive();
        break;
    default:
        Debug.Assert(false, $"Unhandled status: {status}");
        break;
}
```

---

**Sources:** IDesign C# Coding Standard 2.4 — www.idesign.net
**Last Updated:** 2026-03-11
