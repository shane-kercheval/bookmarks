"""
Live penetration tests against deployed API.

These tests verify security controls by making real HTTP requests to the
deployed API with actual authentication tokens.

SETUP:
1. Create two separate user accounts (different logins)
2. Generate a PAT for each user via the web UI
3. Add to your .env file:

    SECURITY_TEST_API_URL=https://your-deployed-api.com
    SECURITY_TEST_USER_A_PAT=bm_xxxxxxxxxxxxxxxx
    SECURITY_TEST_USER_B_PAT=bm_yyyyyyyyyyyyyyyy

IMPORTANT: The two PATs MUST be from DIFFERENT user accounts.

RUN:
    make pen_tests
"""
import asyncio
import os
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

# Load .env file from project root
_project_root = Path(__file__).parent.parent.parent.parent.parent
load_dotenv(_project_root / ".env")

# Configuration - all must be set via environment variables
API_URL = os.environ.get("SECURITY_TEST_API_URL", "")
USER_A_PAT = os.environ.get("SECURITY_TEST_USER_A_PAT", "")
USER_B_PAT = os.environ.get("SECURITY_TEST_USER_B_PAT", "")

# Fail fast if required env vars not configured
if not API_URL:
    raise ValueError("SECURITY_TEST_API_URL must be set in .env to run deployed tests")
if not USER_A_PAT:
    raise ValueError("SECURITY_TEST_USER_A_PAT must be set in .env to run deployed tests")
if not USER_B_PAT:
    raise ValueError("SECURITY_TEST_USER_B_PAT must be set in .env to run deployed tests")


@pytest.fixture
def headers_user_a() -> dict[str, str]:
    """Auth headers for User A."""
    return {"Authorization": f"Bearer {USER_A_PAT}"}


@pytest.fixture
def headers_user_b() -> dict[str, str]:
    """Auth headers for User B."""
    return {"Authorization": f"Bearer {USER_B_PAT}"}


class TestAuthenticationEnforcement:
    """Verify authentication is required on protected endpoints."""

    async def test__unauthenticated_request__returns_401(self) -> None:
        """Requests without authentication are rejected."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/users/me")

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    async def test__invalid_token__returns_401(self) -> None:
        """Requests with invalid tokens are rejected."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/users/me",
                headers={"Authorization": "Bearer bm_invalid_token_12345"},
            )

        assert response.status_code == 401

    async def test__valid_token_user_a__returns_user(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """User A's token is valid and returns user data."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/users/me",
                headers=headers_user_a,
            )

        assert response.status_code == 200
        assert "id" in response.json()

    async def test__valid_token_user_b__returns_user(
        self,
        headers_user_b: dict[str, str],
    ) -> None:
        """User B's token is valid and returns user data."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/users/me",
                headers=headers_user_b,
            )

        assert response.status_code == 200
        assert "id" in response.json()

    async def test__user_a_and_user_b__are_different_users(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User A and User B are distinct accounts (prevents false-positive IDOR tests)."""
        async with httpx.AsyncClient() as client:
            response_a = await client.get(
                f"{API_URL}/users/me",
                headers=headers_user_a,
            )
            response_b = await client.get(
                f"{API_URL}/users/me",
                headers=headers_user_b,
            )

        assert response_a.status_code == 200
        assert response_b.status_code == 200
        assert response_a.json()["id"] != response_b.json()["id"], (
            "CONFIGURATION ERROR: User A and User B PATs resolve to the same user! "
            "IDOR tests require two DIFFERENT user accounts."
        )


class TestBookmarkIDOR:
    """Verify users cannot access other users' bookmarks."""

    async def test__cross_user_bookmark_access__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot access User A's bookmark by ID."""
        async with httpx.AsyncClient() as client:
            # User A creates a bookmark
            create_response = await client.post(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                json={
                    "url": "https://idor-test-unique-12345.example.com/",
                    "title": "User A's Private Bookmark",
                    "tags": ["idor-test"],
                },
            )

            # Handle case where URL already exists
            if create_response.status_code == 409:
                # Clean up: find and delete existing bookmark first
                list_response = await client.get(
                    f"{API_URL}/bookmarks/",
                    headers=headers_user_a,
                    params={"q": "idor-test-unique-12345"},
                )
                if list_response.status_code == 200:
                    items = list_response.json().get("items", [])
                    for item in items:
                        await client.delete(
                            f"{API_URL}/bookmarks/{item['id']}",
                            headers=headers_user_a,
                            params={"permanent": "true"},
                        )
                # Retry creation
                create_response = await client.post(
                    f"{API_URL}/bookmarks/",
                    headers=headers_user_a,
                    json={
                        "url": "https://idor-test-unique-12345.example.com/",
                        "title": "User A's Private Bookmark",
                        "tags": ["idor-test"],
                    },
                )

            assert create_response.status_code == 201, f"Failed to create bookmark: {create_response.text}"
            bookmark_id = create_response.json()["id"]

            try:
                # User B tries to access User A's bookmark
                access_response = await client.get(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_b,
                )

                # Should return 404 (not 403) to prevent ID enumeration
                assert access_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B accessed User A's bookmark! "
                    f"Status: {access_response.status_code}, Body: {access_response.text}"
                )

            finally:
                # Cleanup: User A deletes the bookmark
                await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_bookmark_update__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot update User A's bookmark."""
        async with httpx.AsyncClient() as client:
            # User A creates a bookmark
            create_response = await client.post(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                json={
                    "url": "https://idor-update-test-67890.example.com/",
                    "title": "Original Title",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Bookmark already exists, skipping test")

            assert create_response.status_code == 201
            bookmark_id = create_response.json()["id"]

            try:
                # User B tries to update User A's bookmark
                update_response = await client.patch(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_b,
                    json={"title": "HACKED BY USER B"},
                )

                assert update_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B updated User A's bookmark! "
                    f"Status: {update_response.status_code}"
                )

                # Verify the bookmark was NOT modified
                verify_response = await client.get(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                )
                assert verify_response.json()["title"] == "Original Title"

            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_bookmark_delete__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot delete User A's bookmark."""
        async with httpx.AsyncClient() as client:
            # User A creates a bookmark
            create_response = await client.post(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                json={
                    "url": "https://idor-delete-test-11111.example.com/",
                    "title": "Should Not Be Deleted",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Bookmark already exists, skipping test")

            assert create_response.status_code == 201
            bookmark_id = create_response.json()["id"]

            try:
                # User B tries to delete User A's bookmark
                delete_response = await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_b,
                )

                assert delete_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B deleted User A's bookmark! "
                    f"Status: {delete_response.status_code}"
                )

                # Verify the bookmark still exists
                verify_response = await client.get(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                )
                assert verify_response.status_code == 200, "Bookmark was deleted!"

            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__bookmark_list__excludes_other_users_data(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B's bookmark list does not include User A's bookmarks."""
        async with httpx.AsyncClient() as client:
            # User A creates a bookmark with unique identifier
            unique_tag = "isolation-test-98765"
            create_response = await client.post(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                json={
                    "url": "https://isolation-test-98765.example.com/",
                    "title": "User A Secret Bookmark",
                    "tags": [unique_tag],
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Bookmark already exists, skipping test")

            assert create_response.status_code == 201
            bookmark_id = create_response.json()["id"]

            try:
                # User B searches for User A's bookmark
                search_response = await client.get(
                    f"{API_URL}/bookmarks/",
                    headers=headers_user_b,
                    params={"q": "isolation-test-98765"},
                )

                assert search_response.status_code == 200
                items = search_response.json()["items"]

                # User B should NOT find User A's bookmark
                found_ids = [item["id"] for item in items]
                assert bookmark_id not in found_ids, (
                    "SECURITY VULNERABILITY: User B found User A's bookmark in search!"
                )

            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_bookmark_str_replace__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot str-replace User A's bookmark content."""
        async with httpx.AsyncClient() as client:
            # User A creates a bookmark with content
            create_response = await client.post(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                json={
                    "url": "https://idor-str-replace-test-bookmark.example.com/",
                    "title": "Str-Replace Test Bookmark",
                    "content": "Original content that should not be modified",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Bookmark already exists, skipping test")

            assert create_response.status_code == 201
            bookmark_id = create_response.json()["id"]

            try:
                # User B tries to str-replace User A's bookmark content
                str_replace_response = await client.patch(
                    f"{API_URL}/bookmarks/{bookmark_id}/str-replace",
                    headers=headers_user_b,
                    json={"old_str": "Original", "new_str": "HACKED"},
                )

                assert str_replace_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B str-replaced User A's bookmark! "
                    f"Status: {str_replace_response.status_code}"
                )

                # Verify the bookmark content was NOT modified
                verify_response = await client.get(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                )
                assert verify_response.json()["content"] == "Original content that should not be modified"

            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )


class TestNoteIDOR:
    """
    Verify users cannot access other users' notes.

    Tests str-replace endpoint for proper tenant isolation.
    OWASP Reference: A01:2021 - Broken Access Control
    """

    async def test__cross_user_note_str_replace__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot str-replace User A's note content."""
        async with httpx.AsyncClient() as client:
            # User A creates a note with content
            create_response = await client.post(
                f"{API_URL}/notes/",
                headers=headers_user_a,
                json={
                    "title": "Str-Replace Test Note",
                    "content": "Original content that should not be modified",
                },
            )

            assert create_response.status_code == 201
            note_id = create_response.json()["id"]

            try:
                # User B tries to str-replace User A's note content
                str_replace_response = await client.patch(
                    f"{API_URL}/notes/{note_id}/str-replace",
                    headers=headers_user_b,
                    json={"old_str": "Original", "new_str": "HACKED"},
                )

                assert str_replace_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B str-replaced User A's note! "
                    f"Status: {str_replace_response.status_code}"
                )

                # Verify the note content was NOT modified
                verify_response = await client.get(
                    f"{API_URL}/notes/{note_id}",
                    headers=headers_user_a,
                )
                assert verify_response.json()["content"] == "Original content that should not be modified"

            finally:
                await client.delete(
                    f"{API_URL}/notes/{note_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )


class TestPromptIDOR:
    """
    Verify users cannot access other users' prompts.

    Tests all prompt endpoints for proper tenant isolation.
    OWASP Reference: A01:2021 - Broken Access Control
    """

    async def test__cross_user_prompt_access_by_id__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot access User A's prompt by ID."""
        async with httpx.AsyncClient() as client:
            # User A creates a prompt
            create_response = await client.post(
                f"{API_URL}/prompts/",
                headers=headers_user_a,
                json={
                    "name": "idor-test-prompt-12345",
                    "content": "This is User A's private prompt",
                    "tags": ["idor-test"],
                },
            )

            # Handle case where name already exists (409 conflict)
            if create_response.status_code == 409:
                # Clean up: find and delete existing prompt first
                list_response = await client.get(
                    f"{API_URL}/prompts/",
                    headers=headers_user_a,
                    params={"q": "idor-test-prompt-12345"},
                )
                if list_response.status_code == 200:
                    items = list_response.json().get("items", [])
                    for item in items:
                        await client.delete(
                            f"{API_URL}/prompts/{item['id']}",
                            headers=headers_user_a,
                            params={"permanent": "true"},
                        )
                # Retry creation
                create_response = await client.post(
                    f"{API_URL}/prompts/",
                    headers=headers_user_a,
                    json={
                        "name": "idor-test-prompt-12345",
                        "content": "This is User A's private prompt",
                        "tags": ["idor-test"],
                    },
                )

            assert create_response.status_code == 201, f"Failed to create prompt: {create_response.text}"
            prompt_id = create_response.json()["id"]

            try:
                # User B tries to access User A's prompt by ID
                access_response = await client.get(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_b,
                )

                # Should return 404 (not 403) to prevent ID enumeration
                assert access_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B accessed User A's prompt! "
                    f"Status: {access_response.status_code}, Body: {access_response.text}"
                )

            finally:
                # Cleanup: User A deletes the prompt
                await client.delete(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_prompt_access_by_name__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot access User A's prompt by name."""
        prompt_name = "idor-name-test-unique-67890"

        async with httpx.AsyncClient() as client:
            # User A creates a prompt
            create_response = await client.post(
                f"{API_URL}/prompts/",
                headers=headers_user_a,
                json={
                    "name": prompt_name,
                    "content": "User A's secret prompt content",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Prompt already exists, skipping test")

            assert create_response.status_code == 201
            prompt_id = create_response.json()["id"]

            try:
                # User B tries to access User A's prompt by name
                access_response = await client.get(
                    f"{API_URL}/prompts/name/{prompt_name}",
                    headers=headers_user_b,
                )

                # Should return 404 - cannot discover prompts by name
                assert access_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B accessed User A's prompt by name! "
                    f"Status: {access_response.status_code}"
                )

            finally:
                await client.delete(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_prompt_update__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot update User A's prompt."""
        async with httpx.AsyncClient() as client:
            # User A creates a prompt
            create_response = await client.post(
                f"{API_URL}/prompts/",
                headers=headers_user_a,
                json={
                    "name": "idor-update-test-prompt",
                    "content": "Original Content",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Prompt already exists, skipping test")

            assert create_response.status_code == 201
            prompt_id = create_response.json()["id"]

            try:
                # User B tries to update User A's prompt
                update_response = await client.patch(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_b,
                    json={"content": "HACKED BY USER B"},
                )

                assert update_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B updated User A's prompt! "
                    f"Status: {update_response.status_code}"
                )

                # Verify the prompt was NOT modified
                verify_response = await client.get(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                )
                assert verify_response.json()["content"] == "Original Content"

            finally:
                await client.delete(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_prompt_str_replace__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot str-replace User A's prompt content."""
        async with httpx.AsyncClient() as client:
            # User A creates a prompt with content
            create_response = await client.post(
                f"{API_URL}/prompts/",
                headers=headers_user_a,
                json={
                    "name": "idor-str-replace-test-prompt",
                    "content": "Original content that should not be modified",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Prompt already exists, skipping test")

            assert create_response.status_code == 201
            prompt_id = create_response.json()["id"]

            try:
                # User B tries to str-replace User A's prompt content
                str_replace_response = await client.patch(
                    f"{API_URL}/prompts/{prompt_id}/str-replace",
                    headers=headers_user_b,
                    json={"old_str": "Original", "new_str": "HACKED"},
                )

                assert str_replace_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B str-replaced User A's prompt! "
                    f"Status: {str_replace_response.status_code}"
                )

                # Verify the prompt content was NOT modified
                verify_response = await client.get(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                )
                assert verify_response.json()["content"] == "Original content that should not be modified"

            finally:
                await client.delete(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_prompt_delete__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot delete User A's prompt."""
        async with httpx.AsyncClient() as client:
            # User A creates a prompt
            create_response = await client.post(
                f"{API_URL}/prompts/",
                headers=headers_user_a,
                json={
                    "name": "idor-delete-test-prompt",
                    "content": "Should Not Be Deleted",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Prompt already exists, skipping test")

            assert create_response.status_code == 201
            prompt_id = create_response.json()["id"]

            try:
                # User B tries to delete User A's prompt
                delete_response = await client.delete(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_b,
                )

                assert delete_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B deleted User A's prompt! "
                    f"Status: {delete_response.status_code}"
                )

                # Verify the prompt still exists
                verify_response = await client.get(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                )
                assert verify_response.status_code == 200, "Prompt was deleted!"

            finally:
                await client.delete(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_prompt_archive__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot archive User A's prompt."""
        async with httpx.AsyncClient() as client:
            # User A creates a prompt
            create_response = await client.post(
                f"{API_URL}/prompts/",
                headers=headers_user_a,
                json={
                    "name": "idor-archive-test-prompt",
                    "content": "Should Not Be Archived by B",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Prompt already exists, skipping test")

            assert create_response.status_code == 201
            prompt_id = create_response.json()["id"]

            try:
                # User B tries to archive User A's prompt
                archive_response = await client.post(
                    f"{API_URL}/prompts/{prompt_id}/archive",
                    headers=headers_user_b,
                )

                assert archive_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B archived User A's prompt! "
                    f"Status: {archive_response.status_code}"
                )

                # Verify the prompt is NOT archived
                verify_response = await client.get(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                )
                assert verify_response.json()["archived_at"] is None

            finally:
                await client.delete(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_prompt_unarchive__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot unarchive User A's prompt."""
        async with httpx.AsyncClient() as client:
            # User A creates and archives a prompt
            create_response = await client.post(
                f"{API_URL}/prompts/",
                headers=headers_user_a,
                json={
                    "name": "idor-unarchive-test-prompt",
                    "content": "Should Stay Archived",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Prompt already exists, skipping test")

            assert create_response.status_code == 201
            prompt_id = create_response.json()["id"]

            try:
                # Archive it first
                archive_response = await client.post(
                    f"{API_URL}/prompts/{prompt_id}/archive",
                    headers=headers_user_a,
                )
                assert archive_response.status_code == 200

                # User B tries to unarchive User A's prompt
                unarchive_response = await client.post(
                    f"{API_URL}/prompts/{prompt_id}/unarchive",
                    headers=headers_user_b,
                )

                assert unarchive_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B unarchived User A's prompt! "
                    f"Status: {unarchive_response.status_code}"
                )

                # Verify the prompt is still archived
                verify_response = await client.get(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                )
                assert verify_response.json()["archived_at"] is not None

            finally:
                await client.delete(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_prompt_restore__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot restore User A's deleted prompt."""
        async with httpx.AsyncClient() as client:
            # User A creates a prompt
            create_response = await client.post(
                f"{API_URL}/prompts/",
                headers=headers_user_a,
                json={
                    "name": "idor-restore-test-prompt",
                    "content": "Should Stay Deleted",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Prompt already exists, skipping test")

            assert create_response.status_code == 201
            prompt_id = create_response.json()["id"]

            try:
                # Soft delete it first
                delete_response = await client.delete(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                )
                assert delete_response.status_code == 204

                # User B tries to restore User A's prompt
                restore_response = await client.post(
                    f"{API_URL}/prompts/{prompt_id}/restore",
                    headers=headers_user_b,
                )

                assert restore_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B restored User A's prompt! "
                    f"Status: {restore_response.status_code}"
                )

            finally:
                await client.delete(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_prompt_track_usage__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot track usage on User A's prompt."""
        async with httpx.AsyncClient() as client:
            # User A creates a prompt
            create_response = await client.post(
                f"{API_URL}/prompts/",
                headers=headers_user_a,
                json={
                    "name": "idor-track-usage-test",
                    "content": "Track usage test prompt",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Prompt already exists, skipping test")

            assert create_response.status_code == 201
            prompt_id = create_response.json()["id"]

            try:
                # User B tries to track usage on User A's prompt
                track_response = await client.post(
                    f"{API_URL}/prompts/{prompt_id}/track-usage",
                    headers=headers_user_b,
                )

                assert track_response.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B tracked usage on User A's prompt! "
                    f"Status: {track_response.status_code}"
                )

            finally:
                await client.delete(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__prompt_list__excludes_other_users_data(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B's prompt list does not include User A's prompts."""
        async with httpx.AsyncClient() as client:
            # User A creates a prompt with unique identifier
            unique_name = "isolation-test-prompt-98765"
            create_response = await client.post(
                f"{API_URL}/prompts/",
                headers=headers_user_a,
                json={
                    "name": unique_name,
                    "content": "User A Secret Prompt",
                    "tags": ["isolation-test"],
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Prompt already exists, skipping test")

            assert create_response.status_code == 201
            prompt_id = create_response.json()["id"]

            try:
                # User B searches for User A's prompt
                search_response = await client.get(
                    f"{API_URL}/prompts/",
                    headers=headers_user_b,
                    params={"q": "isolation-test-prompt-98765"},
                )

                assert search_response.status_code == 200
                items = search_response.json()["items"]

                # User B should NOT find User A's prompt
                found_ids = [item["id"] for item in items]
                assert prompt_id not in found_ids, (
                    "SECURITY VULNERABILITY: User B found User A's prompt in search!"
                )

                # Also check by tag
                tag_search = await client.get(
                    f"{API_URL}/prompts/",
                    headers=headers_user_b,
                    params={"tags": ["isolation-test"]},
                )
                tag_items = tag_search.json()["items"]
                tag_ids = [item["id"] for item in tag_items]
                assert prompt_id not in tag_ids, (
                    "SECURITY VULNERABILITY: User B found User A's prompt by tag!"
                )

            finally:
                await client.delete(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__prompt_name_isolation__users_can_have_same_name(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """
        Different users can create prompts with the same name.

        This tests that the unique constraint on prompt names is scoped to users,
        not global. A global constraint would be a security/privacy issue.
        """
        shared_name = "same-name-test-prompt"

        async with httpx.AsyncClient() as client:
            # Cleanup: Delete any existing prompts with this name for both users
            for headers in [headers_user_a, headers_user_b]:
                list_resp = await client.get(
                    f"{API_URL}/prompts/",
                    headers=headers,
                    params={"q": shared_name},
                )
                if list_resp.status_code == 200:
                    for item in list_resp.json().get("items", []):
                        await client.delete(
                            f"{API_URL}/prompts/{item['id']}",
                            headers=headers,
                            params={"permanent": "true"},
                        )

            prompt_a_id = None
            prompt_b_id = None

            try:
                # User A creates a prompt
                create_a = await client.post(
                    f"{API_URL}/prompts/",
                    headers=headers_user_a,
                    json={"name": shared_name, "content": "User A's version"},
                )
                assert create_a.status_code == 201, f"User A failed: {create_a.text}"
                prompt_a_id = create_a.json()["id"]

                # User B creates a prompt with the SAME name
                create_b = await client.post(
                    f"{API_URL}/prompts/",
                    headers=headers_user_b,
                    json={"name": shared_name, "content": "User B's version"},
                )
                # This should succeed - names are per-user, not global
                assert create_b.status_code == 201, (
                    f"ISSUE: User B couldn't create prompt with same name. "
                    f"Status: {create_b.status_code}. "
                    f"Names should be scoped per-user, not global."
                )
                prompt_b_id = create_b.json()["id"]

                # Verify both prompts exist independently
                get_a = await client.get(
                    f"{API_URL}/prompts/{prompt_a_id}",
                    headers=headers_user_a,
                )
                assert get_a.status_code == 200
                assert get_a.json()["content"] == "User A's version"

                get_b = await client.get(
                    f"{API_URL}/prompts/{prompt_b_id}",
                    headers=headers_user_b,
                )
                assert get_b.status_code == 200
                assert get_b.json()["content"] == "User B's version"

            finally:
                if prompt_a_id:
                    await client.delete(
                        f"{API_URL}/prompts/{prompt_a_id}",
                        headers=headers_user_a,
                        params={"permanent": "true"},
                    )
                if prompt_b_id:
                    await client.delete(
                        f"{API_URL}/prompts/{prompt_b_id}",
                        headers=headers_user_b,
                        params={"permanent": "true"},
                    )


class TestPromptRaceConditions:
    """Test for race condition vulnerabilities in prompts."""

    async def test__concurrent_prompt_creation__no_duplicates(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Rapid duplicate POSTs don't create multiple prompts with same name."""
        prompt_name = "race-condition-prompt-test"

        # Cleanup first
        async with httpx.AsyncClient() as client:
            list_resp = await client.get(
                f"{API_URL}/prompts/",
                headers=headers_user_a,
                params={"q": prompt_name},
            )
            if list_resp.status_code == 200:
                for item in list_resp.json().get("items", []):
                    await client.delete(
                        f"{API_URL}/prompts/{item['id']}",
                        headers=headers_user_a,
                        params={"permanent": "true"},
                    )

        async def create_prompt() -> httpx.Response:
            async with httpx.AsyncClient() as client:
                return await client.post(
                    f"{API_URL}/prompts/",
                    headers=headers_user_a,
                    json={
                        "name": prompt_name,
                        "content": "Race condition test content",
                    },
                )

        # Fire 5 concurrent requests
        results = await asyncio.gather(
            *[create_prompt() for _ in range(5)],
            return_exceptions=True,
        )

        # Expect exactly 1 success (201), rest should be 409 conflict
        status_codes = [r.status_code for r in results if isinstance(r, httpx.Response)]
        assert status_codes.count(201) == 1, (
            f"Race condition: expected 1 success, got {status_codes.count(201)}! "
            f"Statuses: {status_codes}"
        )
        assert all(code in (201, 409) for code in status_codes), (
            f"Unexpected status codes: {status_codes}"
        )

        # Cleanup
        async with httpx.AsyncClient() as client:
            search = await client.get(
                f"{API_URL}/prompts/",
                headers=headers_user_a,
                params={"q": prompt_name},
            )
            for item in search.json().get("items", []):
                await client.delete(
                    f"{API_URL}/prompts/{item['id']}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )


class TestPromptAuthentication:
    """Verify authentication is required on prompt endpoints."""

    async def test__unauthenticated_prompt_list__returns_401(self) -> None:
        """Prompt list requires authentication."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/prompts/")

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    async def test__unauthenticated_prompt_create__returns_401(self) -> None:
        """Prompt creation requires authentication."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/prompts/",
                json={"name": "test", "content": "test"},
            )

        assert response.status_code == 401

    async def test__unauthenticated_prompt_get__returns_401(self) -> None:
        """Getting a prompt requires authentication."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/prompts/1")

        assert response.status_code == 401

    async def test__unauthenticated_prompt_get_by_name__returns_401(self) -> None:
        """Getting a prompt by name requires authentication."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/prompts/name/test")

        assert response.status_code == 401


class TestCORSProtection:
    """Verify CORS is properly configured."""

    async def test__malicious_origin__is_rejected(self) -> None:
        """Requests from unauthorized origins are rejected."""
        async with httpx.AsyncClient() as client:
            response = await client.options(
                f"{API_URL}/bookmarks/",
                headers={
                    "Origin": "https://evil-attacker-site.com",
                    "Access-Control-Request-Method": "POST",
                },
            )

        # Should either return 400 or not include CORS headers
        if response.status_code == 200:
            # If 200, should NOT have Access-Control-Allow-Origin for evil domain
            allowed_origin = response.headers.get("Access-Control-Allow-Origin", "")
            assert "evil-attacker-site.com" not in allowed_origin, (
                "SECURITY VULNERABILITY: Malicious origin is allowed!"
            )
        else:
            # 400 is the expected response for disallowed origins
            assert response.status_code == 400


class TestRaceConditions:
    """Test for race condition vulnerabilities."""

    async def test__concurrent_bookmark_creation__no_duplicates(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Rapid duplicate POSTs don't create multiple bookmarks."""
        url = "https://race-condition-test-unique.example.com/"

        async def delete_existing() -> None:
            """Remove any bookmark matching this test's URL."""
            async with httpx.AsyncClient() as client:
                search = await client.get(
                    f"{API_URL}/bookmarks/",
                    headers=headers_user_a,
                    params={"q": "race-condition-test-unique"},
                )
                for item in search.json().get("items", []):
                    await client.delete(
                        f"{API_URL}/bookmarks/{item['id']}",
                        headers=headers_user_a,
                        params={"permanent": "true"},
                    )

        async def create_bookmark() -> httpx.Response:
            async with httpx.AsyncClient() as client:
                return await client.post(
                    f"{API_URL}/bookmarks/",
                    headers=headers_user_a,
                    json={"url": url},
                )

        # Ensure a clean starting state: a leftover from a prior run would make every
        # concurrent POST conflict (0 successes), failing the test spuriously.
        await delete_existing()

        try:
            # Fire 5 concurrent requests
            results = await asyncio.gather(
                *[create_bookmark() for _ in range(5)],
                return_exceptions=True,
            )

            # Expect exactly 1 success (201), rest should be 409 conflict
            status_codes = [r.status_code for r in results if isinstance(r, httpx.Response)]
            assert status_codes.count(201) == 1, (
                f"Race condition: expected 1 success, got {status_codes.count(201)}! "
                f"Statuses: {status_codes}"
            )
            assert all(code in (201, 409) for code in status_codes), (
                f"Unexpected status codes: {status_codes}"
            )
        finally:
            # Always clean up, even if an assertion fails — otherwise the created
            # bookmark persists and breaks every subsequent run (the original bug).
            await delete_existing()


class TestConsentEnforcement:
    """Verify consent enforcement is working in production."""

    async def test__consent_status__returns_valid_structure(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """GET /consent/status returns expected structure."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/consent/status",
                headers=headers_user_a,
            )

        assert response.status_code == 200
        data = response.json()
        # Verify expected fields exist
        assert "needs_consent" in data
        assert "current_privacy_version" in data
        assert "current_terms_version" in data
        assert "current_consent" in data
        # Test user should have consented (needs_consent = False)
        assert data["needs_consent"] is False, (
            "Test user hasn't consented - protected endpoint tests may fail with 451"
        )

    async def test__authenticated_user_with_consent__not_blocked(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Users with valid consent can access protected endpoints (no 451)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
            )

        # Should NOT get 451 (consent required)
        assert response.status_code != 451, (
            f"User got 451 despite having PAT. Response: {response.json()}"
        )
        assert response.status_code == 200

    async def test__consent_can_be_updated(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """User can re-consent (update their consent record)."""
        async with httpx.AsyncClient() as client:
            # Get current versions
            status_resp = await client.get(
                f"{API_URL}/consent/status",
                headers=headers_user_a,
            )
            assert status_resp.status_code == 200
            current_versions = status_resp.json()

            # Re-consent with current versions
            consent_resp = await client.post(
                f"{API_URL}/consent/me",
                headers=headers_user_a,
                json={
                    "privacy_policy_version": current_versions["current_privacy_version"],
                    "terms_of_service_version": current_versions["current_terms_version"],
                },
            )

            assert consent_resp.status_code == 201
            data = consent_resp.json()
            assert data["privacy_policy_version"] == current_versions["current_privacy_version"]
            assert data["terms_of_service_version"] == current_versions["current_terms_version"]

    async def test__unauthenticated_consent_status__returns_401(self) -> None:
        """Consent status requires authentication."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_URL}/consent/status")

        assert response.status_code == 401


class TestPATRestrictedEndpoints:
    """
    Verify PAT-restricted endpoints reject PAT tokens.

    These endpoints require session authentication and block Personal Access Tokens
    to help prevent unintended programmatic use. Note: this does NOT prevent all
    programmatic access - users can extract session JWTs from browser DevTools.
    Rate limiting provides the additional layer to cap any abuse.
    """

    async def test__fetch_metadata__rejects_pat(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """
        The fetch-metadata endpoint rejects PAT tokens with 403.

        This endpoint blocks PAT access to help prevent PAT-based SSRF abuse.
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/bookmarks/fetch-metadata",
                headers=headers_user_a,
                params={"url": "https://example.com/"},
            )

        assert response.status_code == 403, (
            f"SECURITY: fetch-metadata should reject PATs with 403. "
            f"Got {response.status_code}: {response.text}"
        )
        assert "not available for API tokens" in response.json()["detail"]

    async def test__tokens_create__rejects_pat(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Token creation endpoint rejects PATs - prevents token proliferation attacks."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_URL}/tokens/",
                headers=headers_user_a,
                json={"name": "should-not-be-created"},
            )

        assert response.status_code == 403, (
            f"SECURITY: POST /tokens/ should reject PATs with 403. "
            f"Got {response.status_code}: {response.text}"
        )
        assert "not available for API tokens" in response.json()["detail"]

    async def test__tokens_list__rejects_pat(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Token listing endpoint rejects PATs."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/tokens/",
                headers=headers_user_a,
            )

        assert response.status_code == 403, (
            f"SECURITY: GET /tokens/ should reject PATs with 403. "
            f"Got {response.status_code}: {response.text}"
        )
        assert "not available for API tokens" in response.json()["detail"]

    async def test__tokens_delete__rejects_pat(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Token deletion endpoint rejects PATs."""
        async with httpx.AsyncClient() as client:
            # Try to delete a non-existent token - should get 403 before 404
            response = await client.delete(
                f"{API_URL}/tokens/00000000-0000-0000-0000-000000000000",
                headers=headers_user_a,
            )

        assert response.status_code == 403, (
            f"SECURITY: DELETE /tokens/{{id}} should reject PATs with 403. "
            f"Got {response.status_code}: {response.text}"
        )
        assert "not available for API tokens" in response.json()["detail"]

    async def test__settings_sidebar_get__rejects_pat(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Settings sidebar GET endpoint rejects PATs."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{API_URL}/settings/sidebar",
                headers=headers_user_a,
            )

        assert response.status_code == 403, (
            f"SECURITY: GET /settings/sidebar should reject PATs with 403. "
            f"Got {response.status_code}: {response.text}"
        )
        assert "not available for API tokens" in response.json()["detail"]

    async def test__settings_sidebar_update__rejects_pat(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Settings sidebar PUT endpoint rejects PATs."""
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{API_URL}/settings/sidebar",
                headers=headers_user_a,
                json={"items": []},
            )

        assert response.status_code == 403, (
            f"SECURITY: PUT /settings/sidebar should reject PATs with 403. "
            f"Got {response.status_code}: {response.text}"
        )
        assert "not available for API tokens" in response.json()["detail"]


class TestHistoryIDOR:
    """
    Verify users cannot access other users' content history.

    Tests history, diff, content-at-version, and restore endpoints
    for proper tenant isolation.
    OWASP Reference: A01:2021 - Broken Access Control
    """

    async def test__cross_user_entity_history__returns_empty(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot view User A's bookmark history."""
        async with httpx.AsyncClient() as client:
            # User A creates a bookmark (which generates history)
            create_response = await client.post(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                json={
                    "url": "https://history-idor-test-entity.example.com/",
                    "title": "History IDOR Test",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Bookmark already exists, skipping test")

            assert create_response.status_code == 201
            bookmark_id = create_response.json()["id"]

            try:
                # Verify User A can see history
                history_a = await client.get(
                    f"{API_URL}/history/bookmark/{bookmark_id}",
                    headers=headers_user_a,
                )
                assert history_a.status_code == 200
                assert history_a.json()["total"] > 0, "User A should have history"

                # User B tries to access User A's bookmark history
                history_b = await client.get(
                    f"{API_URL}/history/bookmark/{bookmark_id}",
                    headers=headers_user_b,
                )

                assert history_b.status_code == 200
                assert history_b.json()["total"] == 0, (
                    "SECURITY VULNERABILITY: User B can see User A's bookmark history! "
                    f"Found {history_b.json()['total']} records"
                )

            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_version_diff__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot view diffs of User A's bookmark versions."""
        async with httpx.AsyncClient() as client:
            # User A creates a bookmark
            create_response = await client.post(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                json={
                    "url": "https://history-idor-test-diff.example.com/",
                    "title": "Diff IDOR Test",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Bookmark already exists, skipping test")

            assert create_response.status_code == 201
            bookmark_id = create_response.json()["id"]

            try:
                # Verify User A can see version 1 diff
                diff_a = await client.get(
                    f"{API_URL}/history/bookmark/{bookmark_id}/version/1/diff",
                    headers=headers_user_a,
                )
                assert diff_a.status_code == 200

                # User B tries to access User A's version diff
                diff_b = await client.get(
                    f"{API_URL}/history/bookmark/{bookmark_id}/version/1/diff",
                    headers=headers_user_b,
                )

                assert diff_b.status_code == 404, (
                    "SECURITY VULNERABILITY: User B accessed User A's version diff! "
                    f"Status: {diff_b.status_code}, Body: {diff_b.text}"
                )

            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_content_at_version__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot reconstruct User A's content at a version."""
        async with httpx.AsyncClient() as client:
            # User A creates a bookmark
            create_response = await client.post(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                json={
                    "url": "https://history-idor-test-content.example.com/",
                    "title": "Content At Version IDOR Test",
                    "content": "Secret content User B should not see",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Bookmark already exists, skipping test")

            assert create_response.status_code == 201
            bookmark_id = create_response.json()["id"]

            try:
                # Verify User A can reconstruct version 1
                content_a = await client.get(
                    f"{API_URL}/history/bookmark/{bookmark_id}/version/1",
                    headers=headers_user_a,
                )
                assert content_a.status_code == 200

                # User B tries to reconstruct User A's content
                content_b = await client.get(
                    f"{API_URL}/history/bookmark/{bookmark_id}/version/1",
                    headers=headers_user_b,
                )

                assert content_b.status_code == 404, (
                    "SECURITY VULNERABILITY: User B reconstructed User A's content! "
                    f"Status: {content_b.status_code}, Body: {content_b.text}"
                )

            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )

    async def test__cross_user_restore__returns_404(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot restore User A's bookmark to a previous version."""
        async with httpx.AsyncClient() as client:
            # User A creates a bookmark
            create_response = await client.post(
                f"{API_URL}/bookmarks/",
                headers=headers_user_a,
                json={
                    "url": "https://history-idor-test-restore.example.com/",
                    "title": "Original Title",
                },
            )

            if create_response.status_code == 409:
                pytest.skip("Bookmark already exists, skipping test")

            assert create_response.status_code == 201
            bookmark_id = create_response.json()["id"]

            try:
                # User A updates the bookmark to create version 2
                update_response = await client.patch(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    json={"title": "Updated Title"},
                )
                assert update_response.status_code == 200

                # User B tries to restore User A's bookmark to version 1
                restore_b = await client.post(
                    f"{API_URL}/history/bookmark/{bookmark_id}/restore/1",
                    headers=headers_user_b,
                )

                assert restore_b.status_code == 404, (
                    "SECURITY VULNERABILITY: User B restored User A's bookmark! "
                    f"Status: {restore_b.status_code}, Body: {restore_b.text}"
                )

                # Verify the bookmark was NOT restored
                verify_response = await client.get(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                )
                assert verify_response.json()["title"] == "Updated Title", (
                    "SECURITY VULNERABILITY: Bookmark was restored to version 1 by User B!"
                )

            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{bookmark_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )


class TestPromptSSTI:
    """
    Verify prompt template rendering is sandboxed against server-side template injection.

    Prompt content is a user-authored Jinja2 template rendered server-side. A non-sandboxed
    environment would let attribute traversal (__class__/__mro__/__subclasses__) escape to
    arbitrary Python. The render path uses SandboxedEnvironment, which must reject the escape
    as a 400 rather than rendering the object graph (or 500ing).
    OWASP Reference: A03:2021 - Injection
    """

    async def test__render_attribute_traversal_escape__returns_400(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """An SSTI escape template renders as a 400, not a 500 or a leaked object graph."""
        async with httpx.AsyncClient() as client:
            payload = {
                "name": "ssti-test-prompt-12345",
                "content": "{{ x.__class__.__mro__[1].__subclasses__() }}",
                "arguments": [{"name": "x", "required": False}],
                "tags": ["ssti-test"],
            }

            create_response = await client.post(
                f"{API_URL}/prompts/",
                headers=headers_user_a,
                json=payload,
            )

            # Handle case where name already exists (409 conflict): clean up and retry.
            if create_response.status_code == 409:
                list_response = await client.get(
                    f"{API_URL}/prompts/",
                    headers=headers_user_a,
                    params={"q": "ssti-test-prompt-12345"},
                )
                if list_response.status_code == 200:
                    for item in list_response.json().get("items", []):
                        await client.delete(
                            f"{API_URL}/prompts/{item['id']}",
                            headers=headers_user_a,
                            params={"permanent": "true"},
                        )
                create_response = await client.post(
                    f"{API_URL}/prompts/",
                    headers=headers_user_a,
                    json=payload,
                )

            assert create_response.status_code == 201, f"Failed to create prompt: {create_response.text}"
            prompt_id = create_response.json()["id"]

            try:
                render_response = await client.post(
                    f"{API_URL}/prompts/{prompt_id}/render",
                    headers=headers_user_a,
                    json={"arguments": {}},
                )

                # The sandbox must block the escape: 400, not a 500 and not a 200 that
                # leaked the Python object graph.
                assert render_response.status_code == 400, (
                    f"SECURITY VULNERABILITY: SSTI escape was not blocked! "
                    f"Status: {render_response.status_code}, Body: {render_response.text}"
                )
                body = render_response.text
                assert "__subclasses__" not in body, (
                    f"SECURITY VULNERABILITY: render leaked the object graph! Body: {body}"
                )
                assert "<class" not in body, (
                    f"SECURITY VULNERABILITY: render leaked the object graph! Body: {body}"
                )

            finally:
                await client.delete(
                    f"{API_URL}/prompts/{prompt_id}",
                    headers=headers_user_a,
                    params={"permanent": "true"},
                )


class TestPublicShareSurface:
    """
    Verify the unauthenticated public-share surface in production.

    Public reads must work without auth yet leak no owner fields; the clone
    endpoint must require auth; and share management must stay owner-scoped.
    These run against prod (the only place Railway's edge + real auth exist).
    """

    async def _create_and_publish(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        url: str,
        title: str,
    ) -> tuple[str, str]:
        """Create a bookmark as the given user and publish it; return (id, public_token)."""
        payload = {"url": url, "title": title, "tags": ["pubshare-test"]}
        create = await client.post(f"{API_URL}/bookmarks/", headers=headers, json=payload)
        if create.status_code == 409:
            listing = await client.get(
                f"{API_URL}/bookmarks/", headers=headers, params={"q": "pubshare-test"},
            )
            for item in listing.json().get("items", []):
                await client.delete(
                    f"{API_URL}/bookmarks/{item['id']}",
                    headers=headers, params={"permanent": "true"},
                )
            create = await client.post(f"{API_URL}/bookmarks/", headers=headers, json=payload)
        assert create.status_code == 201, f"Failed to create bookmark: {create.text}"
        item_id = create.json()["id"]
        published = await client.post(f"{API_URL}/bookmarks/{item_id}/share", headers=headers)
        assert published.status_code == 200, published.text
        return item_id, published.json()["public_token"]

    async def test__public_read__no_auth_required_and_excludes_owner_fields(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """Anyone can read a published item, but owner-only fields never appear."""
        async with httpx.AsyncClient() as client:
            item_id, token = await self._create_and_publish(
                client, headers_user_a,
                "https://pubshare-test-read.example.com/", "Public Read Target",
            )
            try:
                # No Authorization header at all.
                resp = await client.get(f"{API_URL}/public/bookmarks/{token}")
                assert resp.status_code == 200, resp.text
                body = resp.json()
                for leaked in ("user_id", "public_token", "is_public", "tags", "id", "archived_at"):
                    assert leaked not in body, (
                        f"SECURITY VULNERABILITY: public response leaked '{leaked}': {body}"
                    )
            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{item_id}",
                    headers=headers_user_a, params={"permanent": "true"},
                )

    async def test__public_read__unknown_token_returns_404(self) -> None:
        """An unknown/invalid token returns 404 (no owner-field or 403 oracle)."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{API_URL}/public/bookmarks/this-token-does-not-exist-000000000000",
            )
            assert resp.status_code == 404

    async def test__clone__requires_authentication(
        self,
        headers_user_a: dict[str, str],
    ) -> None:
        """The clone ('Save a copy') endpoint rejects unauthenticated callers."""
        async with httpx.AsyncClient() as client:
            item_id, token = await self._create_and_publish(
                client, headers_user_a,
                "https://pubshare-test-clone.example.com/", "Public Clone Target",
            )
            try:
                resp = await client.post(f"{API_URL}/public/bookmarks/{token}/save")
                assert resp.status_code == 401, (
                    f"SECURITY VULNERABILITY: clone allowed without auth! {resp.status_code}"
                )
            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{item_id}",
                    headers=headers_user_a, params={"permanent": "true"},
                )

    async def test__rotate_share_token__returns_404_for_other_users_item(
        self,
        headers_user_a: dict[str, str],
        headers_user_b: dict[str, str],
    ) -> None:
        """User B cannot rotate the share token on User A's bookmark."""
        async with httpx.AsyncClient() as client:
            item_id, _ = await self._create_and_publish(
                client, headers_user_a,
                "https://pubshare-test-rotate.example.com/", "Public Rotate Target",
            )
            try:
                resp = await client.post(
                    f"{API_URL}/bookmarks/{item_id}/rotate-share-token",
                    headers=headers_user_b,
                )
                assert resp.status_code == 404, (
                    f"SECURITY VULNERABILITY: User B rotated User A's share token! "
                    f"Status: {resp.status_code}, Body: {resp.text}"
                )
            finally:
                await client.delete(
                    f"{API_URL}/bookmarks/{item_id}",
                    headers=headers_user_a, params={"permanent": "true"},
                )


if __name__ == "__main__":
    # Allow running directly: python test_live_penetration.py
    pytest.main([__file__, "-v"])
