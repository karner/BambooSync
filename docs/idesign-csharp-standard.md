---
fileHash: 95fe48e1e315f06ee8224c30bb13d5c9
dependencies: []
---

# IDesign C# Coding Standard 2.4 — Compliance Reference

**Standard Version:** 2.4 (July 2011)
**Author:** Juval Lowy, IDesign Inc.
**Hub:** [idesign-method.md](idesign-method.md)

---

## Overview

This document describes how to comply with the IDesign C# Coding Standard 2.4. The standard covers naming conventions, coding practices, project settings, and framework-specific guidelines for C# and .NET development.

**Source:** `IDesign C# Coding Standard 2.4.pdf`

---

## 1. Naming Conventions and Style

### 1.1 Casing Rules

| Element | Convention | Example |
|---|---|---|
| Types (classes, structs, enums) | PascalCase | `SomeClass`, `MyEnum` |
| Methods | PascalCase | `SomeMethod()`, `GetObjectState()` |
| Constants | PascalCase | `DefaultSize` |
| Local variables | camelCase | `someNumber`, `index` |
| Method arguments | camelCase | `fileName`, `chunkSize` |
| **Private member variables** | **`m_` + PascalCase** | **`m_Number`, `m_Name`** |
| Interface names | `I` prefix | `IMyInterface` |
| Custom attribute classes | `Attribute` suffix | `MyCustomAttribute` |
| Custom exception classes | `Exception` suffix | `MyCustomException` |
| Generic type parameters | Capital letters | `LinkedList<K,T>` |

> **Critical:** Private fields use `m_PascalCase` (e.g., `m_Number`), not `_camelCase`. Do not use Hungarian notation for public or protected members.

```csharp
public class SomeClass
{
    private int m_Number;
    private string m_Name;

    public const int DefaultSize = 100;

    public void SomeMethod(int someNumber)
    {
        int localNumber = someNumber;
    }
}
```

### 1.2 Descriptive Names
- Avoid single-character variable names (`i`, `t`); use `index` or `temp`
- Do not abbreviate words (`num` → `number`)
- Use verb-object pairs for method names: `ShowDialog()`, `GetObjectState()`
- Methods returning values: name describes the value returned

### 1.3 Types and Namespaces
- Always use C# predefined types, not .NET aliases: `object` not `Object`, `string` not `String`, `int` not `Int32`
- Use meaningful namespaces (product name or company name)
- Avoid fully qualified type names; use `using` statements
- Never put `using` inside a namespace
- Group framework namespaces first, then custom/third-party namespaces underneath

```csharp
using System;
using System.Collections.Generic;
using MyCompany;
using MyControls;
```

### 1.4 Style
- Strict indentation: 3 or 4 spaces (uniform, no tabs)
- Indent comments at the same level as the code they document
- All comments pass spell-checking
- All member variables declared at the top, one blank line separating them from properties/methods
- Declare local variables as close as possible to first use
- File name reflects the class it contains
- Always place open curly brace `{` on a new line
- Use delegate inference instead of explicit delegate instantiation
- Lambda expressions: mimic regular method layout; omit variable type; use parentheses

---

## 2. Coding Practices

### 2.1 File and Method Size
- Avoid files with more than **500 lines** (excluding machine-generated code)
- Avoid methods with more than **200 lines**
- Avoid methods with more than **5 arguments** (use structures for passing multiple arguments)
- Lines should not exceed **120 characters**

### 2.2 Classes and Namespaces
- Avoid putting multiple classes in a single file
- A single file contributes types to only a single namespace
- Do not manually edit machine-generated code; use partial classes to factor out maintained portions

### 2.3 Comments
- Avoid comments that explain the obvious — code should be self-explanatory
- Document only operational assumptions and algorithm insights
- Avoid method-level documentation
- Use extensive external documentation for API documentation
- Method-level comments serve as tool tips for other developers only
- All comments pass spell-checking

### 2.4 Constants and Variables
- Never hard-code a numeric value (except 0 and 1); always declare a constant
- Use `const` only for natural constants (e.g., days in a week)
- Use `readonly` for read-only variables, not `const`
- No public or protected member variables; use properties instead
- Use automatic properties instead of trivial get/set
- Do not provide public event member variables; use event accessors

### 2.5 Method Overloading and Parameters
- Prefer overloading to default parameters
- When using default parameters, restrict to natural immutable constants: `null`, `false`, `0`

### 2.6 Assertions and Error Handling
- Assert every assumption; on average every 6th line is an assertion
- Every line of code walked through in "white box" testing
- Catch only exceptions with explicit handling
- In a `catch` that throws: always throw the original exception (or one constructed from it) to maintain stack location
- Avoid error codes as method return values
- Avoid defining custom exception classes
- When custom exceptions are required: derive from `Exception`, provide custom serialization

### 2.7 Interfaces
- Always use interfaces
- Classes and interfaces: at least **2:1 ratio of methods to properties**
- Strive for **3–5 members** per interface
- Do not have more than **20 members** per interface (12 is the practical limit)
- Avoid interfaces with only one member
- Avoid events as interface members
- When using abstract classes, offer an interface as well
- Expose interfaces on class hierarchies
- Prefer explicit interface implementation
- Never assume a type supports an interface; defensively query with `as`

### 2.8 Events and Delegates
- Use `EventHandler<T>` or `GenericEventHandler` instead of custom event-handling delegates
- Use `EventsHelper` to publish events defensively
- Always check a delegate for `null` before invoking

### 2.9 Generics
- Use `var` only when the right side of the assignment clearly indicates the type
- Do not assign method return types to a `var` variable (except LINQ anonymous types)
- Do not define constraints in generic interfaces (replace with strong typing)
- Do not define constraints in delegates
- If a class or method offers both generic and non-generic flavors, prefer the generic flavor
- Avoid casting to and from `System.Object` in generic code; use constraints or `as`

### 2.10 Miscellaneous
- Avoid the ternary conditional operator
- Avoid `#if…#endif`; use `[Conditional]` methods instead
- Avoid function calls in Boolean conditions; assign to a local variable first
- Always use a curly brace scope in an `if` statement, even for single statements
- Always have a `default` case in a `switch` statement that asserts
- Never use `goto` except in a `switch` fall-through
- Do not use `this` unless invoking another constructor
- Do not use `base` unless resolving a name conflict or invoking a base constructor
- Do not use `GC.AddMemoryPressure()`
- Implement `Dispose()` and `Finalize()` following the standard template
- Never hardcode strings for end users; use resources
- Never hardcode deployment-dependent strings (e.g., connection strings)
- Use `String.Empty` instead of `""`
- Use `StringBuilder` for building long strings
- Use application logging and tracing

---

## 3. Project Settings and Project Structure

1. Select the **earliest target framework** required (not the default latest)
2. Always build with **warning level 4**
3. Treat warnings as errors in Release builds (also recommended for Debug)
4. Avoid suppressing specific compiler warnings
5. Explicitly state supported runtime versions in the application configuration file
6. No explicit preprocessor definitions (`#define`); use project settings for conditional compilation constants
7. No logic in `AssemblyInfo.cs`; no assembly attributes in any file other than `AssemblyInfo.cs`
8. Populate all fields in `AssemblyInfo.cs` (company, description, copyright)
9. All assembly references in the same solution use relative paths
10. Disallow cyclic references between assemblies
11. Avoid multi-module assemblies
12. Use uniform version numbers via a shared `SolutionInfo.cs`
13. Name the application configuration file `App.config`
14. Release build contains debug symbols
15. Always sign assemblies with password-protected keys

---

## 4. Framework-Specific Guidelines

### 4.1 Data Access
1. Use type-safe datasets or data tables; avoid raw ADO.NET
2. Always use transactions when accessing a database; use WCF, Enterprise Services, or `System.Transactions` — do not enlist ADO.NET transactions explicitly
3. Always use transaction isolation level Serializable; management decision required to use anything else
4. Do not use the Data Source window to drop connections in Windows Forms, ASP.NET forms, or web services — it couples presentation to data tier
5. Avoid SQL Server authentication; use Windows authentication
6. Run components accessing SQL Server under separate identity from the calling client
7. Always wrap stored procedures in a high-level, type-safe class; let that class invoke them
8. Avoid logic inside stored procedures beyond simple query switching

### 4.2 ASP.NET and Web Services
1. Avoid putting code in ASPX files; all code belongs in the code-beside partial class
2. Code-beside partial class calls other components rather than containing direct business logic
3. Always check a session variable for `null` before accessing it
4. In transactional pages or web services, always store session in SQL Server
5. Avoid setting the Auto-Postback property of server controls to True
6. Turn on Smart Navigation for ASP.NET pages
7. Strive to provide interfaces for web services
8. Always provide a namespace and service description for web services
9. Always provide a description for web methods
10. When adding a web service reference, provide a meaningful name for the location
11. In both ASP.NET pages and web services, wrap a session variable in a local property; only that property accesses the session variable — the rest of the code uses the property
12. Always modify a client-side web service wrapper class to support cookies (you cannot know whether the service uses session state)

### 4.3 Multithreading
1. Use Synchronization Domains; avoid manual synchronization (leads to deadlocks and race conditions)
2. Never call outside your synchronization domain
3. Manage asynchronous call completion on a callback method; do not wait, poll, or block for completion
4. Always name your threads (name is traced in the debugger Threads window)
5. Do not call `Suspend()` or `Resume()` on a thread
6. Do not call `Thread.Sleep()` except: `Thread.Sleep(0)` is acceptable to force a context switch; `Thread.Sleep()` is acceptable in testing or simulation code
7. Do not call `Thread.SpinWait()`
8. Do not call `Thread.Abort()` to terminate threads; use a synchronization object to signal the thread to terminate instead
9. Avoid explicitly setting thread priority to control execution; you can set it based on task semantics (e.g., `ThreadPriority.BelowNormal` for a screen saver)
10. Do not read the `ThreadState` property; use `Thread.IsAlive` to determine whether a thread is dead or alive
11. Do not rely on setting the thread type to background for application shutdown; use a watchdog or other monitoring entity to deterministically kill threads
12. Do not use thread local storage unless thread affinity is guaranteed
13. Do not call `Thread.MemoryBarrier()`
14. Never call `Thread.Join()` without first asserting you are not joining your own thread
15. Always use the `lock()` statement rather than explicit `Monitor` manipulation
16. Always encapsulate the `lock()` statement inside the object it protects
17. You can use synchronized methods instead of writing the `lock()` statement yourself
18. Avoid fragmented locking
19. Avoid using a `Monitor` to wait or pulse objects; use manual or auto-reset events instead
20. Do not use volatile variables; lock your object or fields to guarantee deterministic thread-safe access; do not use `Thread.VolatileRead()`, `Thread.VolatileWrite()`, or the `volatile` modifier
21. Avoid increasing the maximum number of threads in the thread pool
22. Never stack `lock` statements (does not provide atomic locking); use `WaitHandle.WaitAll()` instead

### 4.4 Serialization
1. Prefer the binary formatter
2. Mark serialization event handling methods as private
3. Use the generic `IGenericFormatter` interface
4. Mark non-sealed classes as serializable
5. When implementing `IDeserializationCallback` on a non-sealed class, ensure subclasses call the base class implementation of `OnDeserialization()`
6. Always mark un-serializable member variables as non-serializable
7. Always mark delegates on a serialized class as non-serializable fields (`[field:NonSerialized]`)

### 4.5 Remoting
1. Prefer administrative configuration to programmatic configuration
2. Always implement `IDisposable` on single-call objects
3. Always prefer a TCP channel and binary format when using remoting, unless a firewall is present
4. Always provide a `null` lease for a singleton object
5. Always provide a sponsor for a client-activated object; the sponsor should return the initial lease time
6. Always unregister the sponsor on client application shutdown
7. Always put remote objects in class libraries
8. Avoid using SoapSuds
9. Avoid hosting in IIS
10. Avoid uni-directional channels
11. Always load a remoting configuration file in `Main()` even if the file is empty and the application does not use remoting
12. Avoid `Activator.GetObject()` and `Activator.CreateInstance()` for remote object activation; use `new` instead
13. Always register port 0 on the client side to allow callbacks
14. Always elevate type filtering to full on both client and host to allow callbacks

### 4.6 Security
1. Always demand your own strong name on assemblies that are private to the application but public (so only you can use them)
2. Apply encryption and security protection on application configuration files
3. When importing an interop method, assert unmanaged code permission and demand appropriate permission instead
4. Do not suppress unmanaged code access via the `SuppressUnmanagedCodeSecurity` attribute
5. Do not use the `/unsafe` switch of `TlbImp.exe`; wrap the RCW in managed code so you can assert and demand permissions declaratively
6. On server machines, deploy a code access security policy that grants only Microsoft, ECMA, and self (identified by strong name) full trust; code from anywhere else gets nothing implicitly
7. On client machines, deploy a security policy granting the client application only execution, server callback, and user interface permissions; identify with a strong name in the code groups when not using ClickOnce
8. To counter luring attacks, always refuse at assembly level all permissions not required to perform the task at hand
9. Always set the principal policy in every `Main()` method to Windows
10. Never assert a permission without demanding a different permission in its place

### 4.7 System.Transactions
1. Always dispose of a `TransactionScope` object
2. Inside a transaction scope, do not put any code after the call to `Complete()`
3. When setting the ambient transaction, always save the old ambient transaction and restore it when done
4. In Release builds, never set the transaction timeout to zero (infinite timeout)
5. When cloning a transaction, always use `DependentCloneOption.BlockCommitUntilComplete`
6. Create a new dependent clone for each worker thread; never pass the same dependent clone to multiple threads
7. Do not pass a transaction clone to the `TransactionScope`'s constructor
8. Always catch and discard exceptions thrown by a transaction scope set to `TransactionScopeOption.Suppress`

### 4.8 Enterprise Services
1. Do not catch exceptions in a transactional method; use the `AutoComplete` attribute instead
2. Do not call `SetComplete()`, `SetAbort()`, and similar; use the `AutoComplete` attribute
3. Always override `CanBePooled` and return `true` (unless you have a specific reason not to return to pool)
4. Always call `Dispose()` explicitly on pooled objects unless the component is configured to use JITA as well
5. Never call `Dispose()` when the component uses JITA
6. Always set authorization level to application and component
7. Set authentication level to `privacy` on all applications
8. Set impersonation level on client assemblies to `Identity`
9. Always set the `ComponentAccessControl` attribute on serviced components to `true`
10. Always add to the `Marshaler` role the Everyone user
11. Apply the `SecureMethod` attribute to all classes requiring authentication

---

## 5. IDesign Architecture Alignment

The coding standard works in conjunction with the [idesign-method.md](idesign-method.md) component taxonomy. Map component roles to code as follows:

```
Design Standard term   →   Code convention
─────────────────────────────────────────
Client                 →   Class in Commands/ or UI layer; calls one Manager
Manager                →   Class named *Manager; orchestrates Engines + ResourceAccess
Engine                 →   Class named *Engine; pure functions; no I/O
ResourceAccess         →   Class named *Accessor or *ResourceAccess; dumb CRUD
Utility                →   Static helpers; callable from everywhere
```

**Closed architecture call chain:**
```
Client → Manager → Engine
                 → ResourceAccess → Resource
All   → Utility
```

---

## Compliance Checklist

### Naming
- [ ] Private fields use `m_PascalCase` (e.g., `m_Number`, `m_EventBus`)
- [ ] Interfaces prefixed with `I`
- [ ] Types, methods, constants use PascalCase
- [ ] Local variables and parameters use camelCase
- [ ] No Hungarian notation on public/protected members
- [ ] Attribute classes suffixed with `Attribute`
- [ ] Exception classes suffixed with `Exception`

### Code Quality
- [ ] No file exceeds 500 lines
- [ ] No method exceeds 200 lines
- [ ] No method has more than 5 arguments
- [ ] No hard-coded numeric values (except 0 and 1)
- [ ] `const` used only for natural constants; `readonly` for read-only variables
- [ ] No public/protected member variables; properties used instead
- [ ] `String.Empty` used instead of `""`
- [ ] Ternary operator avoided
- [ ] Function calls avoided in Boolean conditions

### Multithreading
- [ ] Use Synchronization Domains; no manual synchronization
- [ ] Never call `Suspend()`, `Resume()`, `Thread.SpinWait()`, `Thread.MemoryBarrier()`
- [ ] Never call `Thread.Abort()`; signal termination via synchronization object
- [ ] Always name threads
- [ ] Always use `lock()` rather than explicit `Monitor`; encapsulate inside the object it protects
- [ ] No volatile variables; no `Thread.VolatileRead/Write()`; no `volatile` modifier
- [ ] Never stack `lock` statements; use `WaitHandle.WaitAll()` instead
- [ ] Assert not joining own thread before `Thread.Join()`

### Transactions
- [ ] Always dispose `TransactionScope`
- [ ] No code after `Complete()` inside a transaction scope
- [ ] Use `DependentCloneOption.BlockCommitUntilComplete` when cloning transactions
- [ ] Each worker thread gets its own dependent clone

### Interfaces and Events
- [ ] All services implement interfaces
- [ ] Interfaces have 3–5 members (max 20, avoid 1)
- [ ] `EventHandler<T>` used instead of custom delegates
- [ ] Delegates checked for `null` before invocation

### Architecture
- [ ] Closed architecture respected (no upward calls, no sideways calls except queued Manager-to-Manager)
- [ ] Clients call only one Manager per use case
- [ ] Engines are pure functions (no I/O, no state, no event publishing)
- [ ] ResourceAccess is dumb CRUD only (no business logic)
- [ ] All components can call Utilities

### Project Settings
- [ ] Warning level 4
- [ ] Warnings as errors in Release
- [ ] Relative assembly references
- [ ] No cyclic assembly references
- [ ] Assemblies signed with password-protected keys

---

## References

- **IDesign C# Coding Standard 2.4:** `IDesign C# Coding Standard 2.4.pdf`
- **IDesign Design Standard 1.0:** `IDesign Design Standard.pdf`
- **Standard Enforcer (VS plugin):** `Standard Enforcer.mht`
- **Hub:** [idesign-method.md](idesign-method.md)

---

**Last Updated:** 2026-03-11
