---
name: code-review
description: Conduct a comprehensive architectural code review, focusing on design issues, anti-patterns, and ecosystem compliance.
category: development
arguments:
  - name: repo_path
    required: false
    description: The path to the project repository to review.
---
# Architectural Code Review Guidelines

## Scope

This guidance applies to architectural reviews of components, modules, or systems—not line-by-line PR reviews. Focus on decisions with lasting impact on structure and maintainability.

## Core Principle

**Provide high-value feedback on architecture and design.** Identify fundamental design flaws, architectural anti-patterns, structural issues, and actual bugs. Ignore minor stylistic issues or trivial matters.

## Architectural Principles to Review

### SOLID & Design Fundamentals

- **Single Responsibility**: Does each component have one clear purpose?
- **Open/Closed**: Can behavior be extended without modifying existing code?
- **Dependency Inversion**: Do high-level modules depend on abstractions, not implementations?
- **Interface Segregation**: Are interfaces focused and not forcing unnecessary dependencies?

### Coupling & Cohesion

- Are modules loosely coupled with clear boundaries?
- Are related functionalities grouped together (high cohesion)?
- Can components be tested, modified, or replaced independently?

### State & Side Effects

- Is state management explicit and controlled?
- Are side effects isolated and predictable?
- Does this inappropriately create or modify global state?
- Is mutability used appropriately or should immutability be preferred?

### Abstractions & Interfaces

- Are abstractions at the right level (not too high, not too low)?
- Do interfaces expose only what's necessary?
- Are contracts clear and well-defined?
- Are implementation details properly hidden?

### Error Handling & Resilience

- Are error conditions handled appropriately?
- Do errors propagate clearly or fail silently?
- Are failure modes considered and handled?
- Is recovery or cleanup logic present where needed?

### Ecosystem Integration

- How do established libraries in this space solve this?
- What patterns are idiomatic vs. fighting the ecosystem?
- Does this create conflicts with common user setups?
- Is this following or inventing conventions?

### Performance & Scalability

- Are there O(n²) algorithms where O(n) is feasible?
- Will this pattern create bottlenecks under load?
- Are resources (connections, memory, threads) managed appropriately?
- Do costs scale reasonably with usage?

## Review Depth

**Go deep on:**
- Core abstractions and boundaries
- Global state or lifecycle management
- Public APIs and contracts
- Error paths and failure modes
- Integration with ecosystem patterns

**Note and move on:**
- Implementation details within clear interfaces
- Properly isolated components
- Well-tested, understood patterns

## Useful Mental Models

Think about code under review through different lenses:
- **Responsibility**: "Who owns what lifecycle?"
- **Change vectors**: "What changes would ripple through multiple components?"
- **Failure modes**: "What breaks and how does it surface?"
- **Integration**: "How does this fit with established ecosystem patterns?"
- **Assumptions**: "What assumptions could become problems later?"
- **Blast radius**: "If this fails or needs changes, what's affected?"

These are thinking tools, not items to check off.

## What to Raise

**Raise if:**
- Changes would be expensive later but trivial if caught early
- Pattern will force future decisions in problematic directions
- Violates a principle that's important *for this context*
- Creates conflicts with common ecosystem usage
- Introduces bugs or error-prone patterns
- Alternative patterns exist with clear benefits

**Skip if:**
- Stylistic preference without clear advantage
- "Could be done differently" without meaningful benefit
- Micro-optimization without demonstrated need
- Personal taste on subjective matters

## Communicate Findings Clearly

Lead with what matters most. Provide context and alternatives, not just criticism, when possible. Address issues where it makes sense to address them - don't force artificial separation.

**Cover these aspects:**

- **What works well**: Strong patterns worth preserving or extending
- **Critical issues**: Fundamental problems requiring change - include the recommended alternative when you describe the problem
- **Design concerns**: Questionable patterns worth discussing, even if not clearly wrong
- **Bugs**: Actual defects in logic or implementation
- **Context**: Why something matters in this specific situation

Don't feel bound to this structure. If it makes sense to discuss three related issues together, do that. If a bug and a design concern stem from the same root cause, address them together.

The goal is clarity and usefulness, not adherence to a template.
{%- if repo_path %}

---

## Repository Path

```
{{ repo_path }}
```
{%- endif %}
