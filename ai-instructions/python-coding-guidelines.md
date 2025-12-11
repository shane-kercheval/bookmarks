---
name: python-coding-guidelines
description: Python coding guidelines software development.
category: development
arguments: []
tags:
  - instructions
  - python
  - standards
---
# Python Code Guidelines:

## CODE STYLE & FORMATTING

- Follow PEP 8 style guide strictly
- Use 4 spaces for indentation (no tabs)
- Use clear, descriptive variable and function names that convey purpose
- Use single quotes for internal/code strings ('dict_key', 'variable_value')
- Use double quotes for user-facing strings ("Error: Invalid input", "Welcome!")
- DO NOT place imports inside functions or methods; only place them at the top of the file

## TYPE ANNOTATIONS

- Include type hints for all function parameters and return values, including private/internal/nested/test functions
- Use modern type hint syntax, for example:
  - `list[str]` instead of `List[str]`
  - `int | None` instead of `Optional[int]`
  - `str | int` instead of `Union[str, int]`

## DOCUMENTATION

- Use docstrings when creating files, classes, and functions.
- Use docstrings in the format below when creating functions:
    ```python
    def function_name(param: str, value: int = 0) -> bool:
        """
        Brief one-line description.

        Longer description if needed, explaining the function's purpose,
        behavior, or important implementation details.

        Args:
            param:
              Description of the parameter.
            value:
              Description with default value noted.

        Returns:
            Description of return value and its type/structure.

        Raises:
            ValueError: When input validation fails.
            TypeError: When incorrect types are passed.

        Example:
            >>> result = function_name("test", 42)
            >>> print(result)
            True
        """
    ```
- Include usage examples for non-trivial functions
- Document complex algorithms or business logic

## CODE COMMENTS

- Add comments to code only when they clarify logic or business rules
- Skip comments that simply restate what the code obviously does
- DO NOT add meta-commentary about code changes

## TESTING GUIDELINES

- Use `pytest` for the test framework
- Follow naming convention: `test__<function_name>__<scenario>`
- Document the purpose of non-trivial tests and test/mocking strategies in both the file and individual tests accordingly; do not be overly verbose but provide enough context for engineerings to understand the intent
- Use descriptive assertion messages
- Use fixtures for common setup/teardown logic

## TESTING STRATEGY

- Test behavior and public contracts, not internal implementation details.
- Cover edge cases, error paths, concurrency/race conditions, and representative user workflows.
- Write tests that verify behavior and business logic, not implementation details (i.e. what the code does (its observable behavior) rather than how it does it (the internal mechanics))
- Skip trivial or 'low value' tests (simple getters/setters, obvious assignments)
- Include both unit tests (fast, isolated) and integration/contract tests (real IO, services) when applicable.
- Use mocks/stubs only at architectural boundaries; prefer real objects elsewhere.
- Do **not** use print/debug output as assertions; failures must be explicit and informative.
- **Think strategically about failing tests**:
  1. **First** determine if the test expectations are correct
  2. **Then** check if there's an actual bug in the implementation
  3. **Never** modify a test just to make it pass if it's revealing a real issue
  4. **If you discover a *non-trivial* bug**: Stop immediately, explain the issue clearly, and wait for discussion before proceeding
- Always run tests after writing them to verify they work; always write tests for new code before moving on to the next task/milestone

## UV PACKAGE MANAGER

- Use `uv` for package management (e.g. `uv run <command>`, `uv add <package>`) and `pyproject.toml` for dependency tracking (not `requirements.txt`)
- When adding packages, NEVER modifiy `pyproject.toml` directly, ALWAYS use `uv add <package>` to ensure proper version resolution and lockfile updates

## OUTPUT FORMAT

- Provide a brief overview explaining what the code does
- Highlight any important design decisions or trade-offs
- Discuss any concerns or considerations with the implementation
- No commentary on routine code changes unless specifically noteworthy
