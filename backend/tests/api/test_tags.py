"""Tests for tags endpoint."""
from httpx import AsyncClient


async def test_list_tags_empty(client: AsyncClient) -> None:
    """Test listing tags when no bookmarks exist."""
    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    assert "tags" in data
    assert data["tags"] == []


async def test_list_tags_single_bookmark(client: AsyncClient) -> None:
    """Test listing tags from a single bookmark."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://example.com", "title": "Test", "tags": ["python", "web"]},
    )

    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    assert len(data["tags"]) == 2
    # Tags should have name and count
    tag_names = {tag["name"] for tag in data["tags"]}
    assert tag_names == {"python", "web"}
    # Each tag has count of 1
    for tag in data["tags"]:
        assert tag["count"] == 1


async def test_list_tags_multiple_bookmarks(client: AsyncClient) -> None:
    """Test listing tags aggregated across multiple bookmarks."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://example1.com", "tags": ["python", "web"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://example2.com", "tags": ["python", "api"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://example3.com", "tags": ["python"]},
    )

    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    tag_counts = {tag["name"]: tag["count"] for tag in data["tags"]}
    assert tag_counts["python"] == 3
    assert tag_counts["web"] == 1
    assert tag_counts["api"] == 1


async def test_list_tags_sorted_by_count(client: AsyncClient) -> None:
    """Test that tags are sorted by count descending."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex1.com", "tags": ["rare"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex2.com", "tags": ["common", "medium"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex3.com", "tags": ["common", "medium"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex4.com", "tags": ["common"]},
    )

    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    tags = data["tags"]

    # Should be sorted by count descending
    assert tags[0]["name"] == "common"
    assert tags[0]["count"] == 3
    assert tags[1]["name"] == "medium"
    assert tags[1]["count"] == 2
    assert tags[2]["name"] == "rare"
    assert tags[2]["count"] == 1


async def test_list_tags_alphabetical_tiebreak(client: AsyncClient) -> None:
    """Test that tags with same count are sorted alphabetically."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex1.com", "tags": ["zebra", "apple", "banana"]},
    )

    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    tags = data["tags"]

    # All have count 1, should be sorted alphabetically
    tag_names = [tag["name"] for tag in tags]
    assert tag_names == ["apple", "banana", "zebra"]


async def test_list_tags_response_format(client: AsyncClient) -> None:
    """Test that tags response has correct format."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://example.com", "tags": ["test"]},
    )

    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    assert "tags" in data
    assert isinstance(data["tags"], list)
    assert len(data["tags"]) == 1
    assert "name" in data["tags"][0]
    assert "count" in data["tags"][0]
    assert data["tags"][0]["name"] == "test"
    assert data["tags"][0]["count"] == 1


async def test_list_tags_bookmark_without_tags(client: AsyncClient) -> None:
    """Test that bookmarks without tags don't affect tag list."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://no-tags.com", "title": "No tags"},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://with-tags.com", "tags": ["python"]},
    )

    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    assert len(data["tags"]) == 1
    assert data["tags"][0]["name"] == "python"
    assert data["tags"][0]["count"] == 1


async def test_list_tags_excludes_archived_and_deleted_bookmarks(client: AsyncClient) -> None:
    """Test that tags from archived and deleted bookmarks are not counted but still appear."""
    # Create three bookmarks with different tags
    # Active bookmark - tags should be counted
    await client.post(
        "/bookmarks/",
        json={"url": "https://active.com", "tags": ["active-tag", "shared-tag"]},
    )

    # Bookmark to be archived - tags should NOT be counted
    archived_response = await client.post(
        "/bookmarks/",
        json={"url": "https://archived.com", "tags": ["archived-tag", "shared-tag"]},
    )
    archived_id = archived_response.json()["id"]
    await client.post(f"/bookmarks/{archived_id}/archive")

    # Bookmark to be deleted - tags should NOT be counted
    deleted_response = await client.post(
        "/bookmarks/",
        json={"url": "https://deleted.com", "tags": ["deleted-tag", "shared-tag"]},
    )
    deleted_id = deleted_response.json()["id"]
    await client.delete(f"/bookmarks/{deleted_id}")

    # Get tags - returns all tags with correct counts
    response = await client.get("/tags/")
    assert response.status_code == 200

    data = response.json()
    tag_counts = {tag["name"]: tag["count"] for tag in data["tags"]}

    # Active bookmark's tags should have count of 1
    assert "active-tag" in tag_counts
    assert tag_counts["active-tag"] == 1

    # shared-tag should only have count of 1 (from active bookmark only)
    assert "shared-tag" in tag_counts
    assert tag_counts["shared-tag"] == 1

    # Tags exclusive to archived/deleted bookmarks should appear but have count 0
    # (API returns all tags including zero-count; frontend can filter if needed)
    assert "archived-tag" in tag_counts
    assert tag_counts["archived-tag"] == 0
    assert "deleted-tag" in tag_counts
    assert tag_counts["deleted-tag"] == 0


async def test_rename_tag_success(client: AsyncClient) -> None:
    """Test successful tag rename."""
    # Create bookmark with tag
    await client.post(
        "/bookmarks/",
        json={"url": "https://example.com", "tags": ["old-name"]},
    )

    # Rename the tag
    response = await client.patch(
        "/tags/old-name",
        json={"new_name": "new-name"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "new-name"
    assert "id" in data
    assert "created_at" in data

    # Verify tag list shows new name
    tags_response = await client.get("/tags/")
    tag_names = [tag["name"] for tag in tags_response.json()["tags"]]
    assert "new-name" in tag_names
    assert "old-name" not in tag_names


async def test_rename_tag_not_found(client: AsyncClient) -> None:
    """Test renaming a non-existent tag returns 404."""
    response = await client.patch(
        "/tags/nonexistent",
        json={"new_name": "new-name"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_rename_tag_conflict(client: AsyncClient) -> None:
    """Test renaming a tag to an existing name returns 409."""
    # Create two bookmarks with different tags
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex1.com", "tags": ["tag-a"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex2.com", "tags": ["tag-b"]},
    )

    # Try to rename tag-a to tag-b
    response = await client.patch(
        "/tags/tag-a",
        json={"new_name": "tag-b"},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


async def test_rename_tag_validates_format(client: AsyncClient) -> None:
    """Test renaming tag validates new name format."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://example.com", "tags": ["valid-tag"]},
    )

    # Invalid format: contains spaces (not normalized away)
    response = await client.patch(
        "/tags/valid-tag",
        json={"new_name": "invalid name"},
    )
    assert response.status_code == 422


async def test_rename_tag_normalizes_name(client: AsyncClient) -> None:
    """Test renaming tag normalizes the new name."""
    await client.post(
        "/bookmarks/",
        json={"url": "https://example.com", "tags": ["old-tag"]},
    )

    # Mixed case should be normalized to lowercase
    response = await client.patch(
        "/tags/old-tag",
        json={"new_name": "  New-Tag  "},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "new-tag"


async def test_delete_tag_success(client: AsyncClient) -> None:
    """Test successful tag deletion."""
    # Create bookmark with tag
    await client.post(
        "/bookmarks/",
        json={"url": "https://example.com", "tags": ["to-delete", "keep-me"]},
    )

    # Delete the tag
    response = await client.delete("/tags/to-delete")
    assert response.status_code == 204

    # Verify tag list no longer includes deleted tag
    tags_response = await client.get("/tags/")
    tag_names = [tag["name"] for tag in tags_response.json()["tags"]]
    assert "to-delete" not in tag_names
    assert "keep-me" in tag_names


async def test_delete_tag_not_found(client: AsyncClient) -> None:
    """Test deleting a non-existent tag returns 404."""
    response = await client.delete("/tags/nonexistent")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


async def test_delete_tag_removes_from_bookmarks(client: AsyncClient) -> None:
    """Test deleting a tag removes it from all associated bookmarks."""
    # Create multiple bookmarks with the same tag
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex1.com", "tags": ["shared", "unique-1"]},
    )
    await client.post(
        "/bookmarks/",
        json={"url": "https://ex2.com", "tags": ["shared", "unique-2"]},
    )

    # Delete the shared tag
    response = await client.delete("/tags/shared")
    assert response.status_code == 204

    # Verify tag list
    tags_response = await client.get("/tags/")
    tag_names = [tag["name"] for tag in tags_response.json()["tags"]]
    assert "shared" not in tag_names
    assert "unique-1" in tag_names
    assert "unique-2" in tag_names
