"""
Security test suite for the Bookmarks application.

This module contains security-focused tests that validate:
- Authentication enforcement
- Authorization (IDOR prevention)
- SSRF protection
- Input validation (SQL injection prevention)

These tests should be run as part of CI/CD to prevent security regressions.
"""
