---
name: unit-tests
description: Guidelines for writing effective unit and integration tests.
category: development
arguments: []
tags:
  - instructions
  - testing
  - standards
---
# Unit & Integration Test Writing Guidelines

## Workflow

- Work **iteratively**: Write tests for one module/class/function at a time and present for review before proceeding
- Run tests immediately after writing to verify they work
- Focus on **high-value tests** that catch real bugs and verify meaningful behavior
- Skip trivial tests (simple getters/setters without logic, pass-through methods)

## Test Strategy

### What to Test:

- **Core functionality**: Primary purpose and expected use cases
- **Edge cases**: Boundary values, empty inputs, null/undefined, zero, negative numbers
- **Error conditions**: Invalid inputs, exceptions, constraint violations, failure scenarios
- **State changes**: Verify state transitions and side effects when applicable
- **Integration points**: How components interact with each other

### What to Skip:

- Framework/library code or third-party dependencies
- Trivial getters/setters without logic
- Private methods directly (test through public interface)
- Redundant tests verifying the same behavior multiple ways

## Quality Standards

- Use clear, descriptive names indicating what scenario is being tested
- Follow Arrange-Act-Assert (AAA) pattern
- Keep tests isolated and independent (no shared state between tests)
- Use meaningful test data reflecting real-world scenarios
- Test behavior and outcomes, not implementation details
- Use fixtures/factories for setup; keep tests deterministic
- Follow existing patterns and conventions in the codebase when available/applicable

## Mocking Guidelines

**When to Mock:**
- External services (APIs, databases, file systems, network)
- Slow or non-deterministic operations
- Resources difficult to set up in tests

**When NOT to Mock:**
- The system under test itself
- Simple data objects or pure functions
- Logic you actually want to verify
- Don't over-mock - it makes tests brittle and meaningless

**Approach:**
- Use stubs for simple return values
- Use mocks when verifying interactions (method called with correct parameters)
- Keep mocking minimal - only what's necessary for isolation

## Key Anti-Patterns to Avoid

- **Test interdependence**: Tests must run independently in any order
- **Testing implementation details**: Test behavior, not how it's implemented
- **Over-mocking**: Mocking everything makes tests verify nothing
- **Shared state**: Hidden dependencies on global state or test execution order
- **Brittle assertions**: Tests that break with harmless changes

## Debugging Protocol

If a test fails:
1. Verify test expectations are correct
2. Check if there's an actual bug in the implementation
3. **Never modify a test just to make it pass** if it's revealing a real issue
4. **If you discover a non-trivial bug**: Stop immediately, explain clearly, and wait for discussion

## Code Coverage Philosophy

- Coverage identifies gaps in testing - use it as a discovery tool
- High coverage doesn't equal quality tests - behavior verification matters more
- Focus coverage efforts on critical paths and business logic
- 100% coverage of trivial code is wasted effort

## Output Format

For each test file, include:
- Brief comment on what aspects are being tested
- Any coverage limitations or assumptions
- Suggestions for integration/E2E tests if unit tests alone are insufficient
