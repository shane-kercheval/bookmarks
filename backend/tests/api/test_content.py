"""Tests for unified content API endpoints."""
from httpx import AsyncClient


async def test__list_all_content__returns_both_bookmarks_and_notes(
    client: AsyncClient,
) -> None:
    """Test that GET /content returns both bookmarks and notes."""
    # Create a bookmark
    await client.post(
        '/bookmarks/',
        json={'url': 'https://example.com', 'title': 'Example Bookmark'},
    )

    # Create a note
    await client.post(
        '/notes/',
        json={'title': 'Example Note'},
    )

    # List all content
    response = await client.get('/content/')
    assert response.status_code == 200

    data = response.json()
    assert data['total'] == 2
    assert len(data['items']) == 2

    types = {item['type'] for item in data['items']}
    assert types == {'bookmark', 'note'}


async def test__list_all_content__returns_empty_for_new_user(
    client: AsyncClient,
) -> None:
    """Test that GET /content returns empty for user with no content."""
    response = await client.get('/content/')
    assert response.status_code == 200

    data = response.json()
    assert data['total'] == 0
    assert data['items'] == []
    assert data['has_more'] is False


async def test__list_all_content__has_correct_type_fields(
    client: AsyncClient,
) -> None:
    """Test that items have correct type-specific fields."""
    # Create bookmark
    await client.post(
        '/bookmarks/',
        json={'url': 'https://test.com', 'title': 'Bookmark'},
    )

    # Create note
    await client.post(
        '/notes/',
        json={'title': 'Note'},
    )

    response = await client.get('/content/')
    data = response.json()

    bookmark_item = next(item for item in data['items'] if item['type'] == 'bookmark')
    note_item = next(item for item in data['items'] if item['type'] == 'note')

    # Bookmark has url, no version
    assert bookmark_item['url'] == 'https://test.com/'
    assert bookmark_item['version'] is None

    # Note has version, no url
    assert note_item['url'] is None
    assert note_item['version'] == 1


async def test__list_all_content__view_active_excludes_deleted(
    client: AsyncClient,
) -> None:
    """Test that view=active excludes deleted content."""
    # Create content
    await client.post(
        '/bookmarks/',
        json={'url': 'https://active.com', 'title': 'Active Bookmark'},
    )
    note_response = await client.post(
        '/notes/',
        json={'title': 'Deleted Note'},
    )

    # Delete the note
    note_id = note_response.json()['id']
    await client.delete(f'/notes/{note_id}')

    # List active content
    response = await client.get('/content/?view=active')
    data = response.json()

    assert data['total'] == 1
    assert data['items'][0]['type'] == 'bookmark'


async def test__list_all_content__view_archived_returns_only_archived(
    client: AsyncClient,
) -> None:
    """Test that view=archived returns only archived content."""
    # Create content
    bookmark_response = await client.post(
        '/bookmarks/',
        json={'url': 'https://archived.com', 'title': 'Archived Bookmark'},
    )
    await client.post(
        '/notes/',
        json={'title': 'Active Note'},
    )

    # Archive the bookmark
    bookmark_id = bookmark_response.json()['id']
    await client.post(f'/bookmarks/{bookmark_id}/archive')

    # List archived content
    response = await client.get('/content/?view=archived')
    data = response.json()

    assert data['total'] == 1
    assert data['items'][0]['type'] == 'bookmark'
    assert data['items'][0]['title'] == 'Archived Bookmark'


async def test__list_all_content__view_deleted_returns_all_deleted(
    client: AsyncClient,
) -> None:
    """Test that view=deleted returns all deleted content."""
    # Create content
    bookmark_response = await client.post(
        '/bookmarks/',
        json={'url': 'https://deleted.com', 'title': 'Deleted Bookmark'},
    )
    note_response = await client.post(
        '/notes/',
        json={'title': 'Deleted Note'},
    )
    await client.post(
        '/notes/',
        json={'title': 'Active Note'},
    )

    # Delete bookmark and note
    bookmark_id = bookmark_response.json()['id']
    note_id = note_response.json()['id']
    await client.delete(f'/bookmarks/{bookmark_id}')
    await client.delete(f'/notes/{note_id}')

    # List deleted content
    response = await client.get('/content/?view=deleted')
    data = response.json()

    assert data['total'] == 2
    types = {item['type'] for item in data['items']}
    assert types == {'bookmark', 'note'}


async def test__list_all_content__text_search_finds_across_types(
    client: AsyncClient,
) -> None:
    """Test that text search finds matches in both bookmarks and notes."""
    # Create content with different titles
    await client.post(
        '/bookmarks/',
        json={'url': 'https://python.com', 'title': 'Python Guide'},
    )
    await client.post(
        '/notes/',
        json={'title': 'Python Tutorial'},
    )
    await client.post(
        '/notes/',
        json={'title': 'JavaScript Guide'},
    )

    # Search for "python"
    response = await client.get('/content/?q=python')
    data = response.json()

    assert data['total'] == 2
    titles = {item['title'] for item in data['items']}
    assert titles == {'Python Guide', 'Python Tutorial'}


async def test__list_all_content__tag_filter_works(
    client: AsyncClient,
) -> None:
    """Test that tag filtering works across types."""
    # Create content with different tags
    await client.post(
        '/bookmarks/',
        json={'url': 'https://python.com', 'title': 'Python', 'tags': ['python']},
    )
    await client.post(
        '/notes/',
        json={'title': 'Web', 'tags': ['web']},
    )
    await client.post(
        '/notes/',
        json={'title': 'Java', 'tags': ['java']},
    )

    # Filter by python or web (ANY mode)
    response = await client.get('/content/?tags=python&tags=web&tag_match=any')
    data = response.json()

    assert data['total'] == 2
    titles = {item['title'] for item in data['items']}
    assert titles == {'Python', 'Web'}


async def test__list_all_content__includes_tags_in_response(
    client: AsyncClient,
) -> None:
    """Test that tags are included in the response items."""
    await client.post(
        '/bookmarks/',
        json={'url': 'https://test.com', 'title': 'Tagged Bookmark', 'tags': ['tag-a', 'tag-b']},
    )
    await client.post(
        '/notes/',
        json={'title': 'Tagged Note', 'tags': ['tag-c']},
    )

    response = await client.get('/content/')
    data = response.json()

    bookmark_item = next(item for item in data['items'] if item['type'] == 'bookmark')
    note_item = next(item for item in data['items'] if item['type'] == 'note')

    assert set(bookmark_item['tags']) == {'tag-a', 'tag-b'}
    assert note_item['tags'] == ['tag-c']


async def test__list_all_content__sorting_works(
    client: AsyncClient,
) -> None:
    """Test that sorting works across types."""
    # Create content with different titles
    await client.post('/bookmarks/', json={'url': 'https://z.com', 'title': 'Zebra'})
    await client.post('/notes/', json={'title': 'Apple'})
    await client.post('/bookmarks/', json={'url': 'https://m.com', 'title': 'Mango'})

    # Sort by title ascending
    response = await client.get('/content/?sort_by=title&sort_order=asc')
    data = response.json()

    titles = [item['title'] for item in data['items']]
    assert titles == ['Apple', 'Mango', 'Zebra']


async def test__list_all_content__pagination_works(
    client: AsyncClient,
) -> None:
    """Test that pagination works correctly."""
    # Create 5 items
    for i in range(3):
        await client.post('/bookmarks/', json={'url': f'https://test{i}.com', 'title': f'B{i}'})
    for i in range(2):
        await client.post('/notes/', json={'title': f'N{i}'})

    # Get first page
    response = await client.get('/content/?limit=2&offset=0')
    data = response.json()

    assert data['total'] == 5
    assert len(data['items']) == 2
    assert data['has_more'] is True

    # Get second page
    response = await client.get('/content/?limit=2&offset=2')
    data = response.json()

    assert data['total'] == 5
    assert len(data['items']) == 2
    assert data['has_more'] is True

    # Get last page
    response = await client.get('/content/?limit=2&offset=4')
    data = response.json()

    assert data['total'] == 5
    assert len(data['items']) == 1
    assert data['has_more'] is False


async def test__list_all_content__response_schema_is_correct(
    client: AsyncClient,
) -> None:
    """Test that response follows the expected schema."""
    await client.post('/bookmarks/', json={'url': 'https://test.com', 'title': 'Test'})

    response = await client.get('/content/')
    data = response.json()

    # Check top-level response fields
    assert 'items' in data
    assert 'total' in data
    assert 'offset' in data
    assert 'limit' in data
    assert 'has_more' in data

    # Check item fields
    item = data['items'][0]
    assert 'type' in item
    assert 'id' in item
    assert 'title' in item
    assert 'description' in item
    assert 'tags' in item
    assert 'created_at' in item
    assert 'updated_at' in item
    assert 'last_used_at' in item
    assert 'deleted_at' in item
    assert 'archived_at' in item
    assert 'url' in item
    assert 'version' in item


async def test__list_all_content__invalid_view_returns_422(
    client: AsyncClient,
) -> None:
    """Test that invalid view parameter returns 422."""
    response = await client.get('/content/?view=invalid')
    assert response.status_code == 422


async def test__list_all_content__invalid_sort_by_returns_422(
    client: AsyncClient,
) -> None:
    """Test that invalid sort_by parameter returns 422."""
    response = await client.get('/content/?sort_by=invalid')
    assert response.status_code == 422


async def test__list_all_content__limit_exceeds_max_is_capped(
    client: AsyncClient,
) -> None:
    """Test that limit parameter validation works."""
    # Limit > 100 should fail
    response = await client.get('/content/?limit=101')
    assert response.status_code == 422


async def test__list_all_content__negative_offset_returns_422(
    client: AsyncClient,
) -> None:
    """Test that negative offset parameter returns 422."""
    response = await client.get('/content/?offset=-1')
    assert response.status_code == 422


# =============================================================================
# List ID Filter Tests (ContentList integration)
# =============================================================================


async def test__list_content_with_list_id__returns_matching_bookmarks_and_notes(
    client: AsyncClient,
) -> None:
    """Test filtering content by list_id returns both types when list includes both."""
    # Create bookmark with 'work' tag
    await client.post(
        '/bookmarks/',
        json={'url': 'https://work.com', 'title': 'Work Bookmark', 'tags': ['work']},
    )
    # Create note with 'work' tag
    await client.post(
        '/notes/',
        json={'title': 'Work Note', 'tags': ['work']},
    )
    # Create bookmark without 'work' tag (should not match)
    await client.post(
        '/bookmarks/',
        json={'url': 'https://personal.com', 'title': 'Personal', 'tags': ['personal']},
    )

    # Create a list that includes both types with 'work' tag filter
    response = await client.post(
        '/lists/',
        json={
            'name': 'Work List',
            'content_types': ['bookmark', 'note'],
            'filter_expression': {'groups': [{'tags': ['work']}], 'group_operator': 'OR'},
        },
    )
    assert response.status_code == 201
    list_id = response.json()['id']

    # Filter content by list_id
    response = await client.get(f'/content/?list_id={list_id}')
    assert response.status_code == 200

    data = response.json()
    assert data['total'] == 2
    types = {item['type'] for item in data['items']}
    assert types == {'bookmark', 'note'}
    titles = {item['title'] for item in data['items']}
    assert titles == {'Work Bookmark', 'Work Note'}


async def test__list_content_with_list_id__respects_content_types_bookmarks_only(
    client: AsyncClient,
) -> None:
    """Test that list_id respects content_types and returns only bookmarks when specified."""
    # Create bookmark and note with same tag
    await client.post(
        '/bookmarks/',
        json={'url': 'https://work.com', 'title': 'Work Bookmark', 'tags': ['work']},
    )
    await client.post(
        '/notes/',
        json={'title': 'Work Note', 'tags': ['work']},
    )

    # Create a list with only bookmark type
    response = await client.post(
        '/lists/',
        json={
            'name': 'Bookmarks Only',
            'content_types': ['bookmark'],
            'filter_expression': {'groups': [{'tags': ['work']}], 'group_operator': 'OR'},
        },
    )
    assert response.status_code == 201
    list_id = response.json()['id']

    # Filter content by list_id
    response = await client.get(f'/content/?list_id={list_id}')
    assert response.status_code == 200

    data = response.json()
    assert data['total'] == 1
    assert data['items'][0]['type'] == 'bookmark'
    assert data['items'][0]['title'] == 'Work Bookmark'


async def test__list_content_with_list_id__respects_content_types_notes_only(
    client: AsyncClient,
) -> None:
    """Test that list_id respects content_types and returns only notes when specified."""
    # Create bookmark and note with same tag
    await client.post(
        '/bookmarks/',
        json={'url': 'https://work.com', 'title': 'Work Bookmark', 'tags': ['work']},
    )
    await client.post(
        '/notes/',
        json={'title': 'Work Note', 'tags': ['work']},
    )

    # Create a list with only note type
    response = await client.post(
        '/lists/',
        json={
            'name': 'Notes Only',
            'content_types': ['note'],
            'filter_expression': {'groups': [{'tags': ['work']}], 'group_operator': 'OR'},
        },
    )
    assert response.status_code == 201
    list_id = response.json()['id']

    # Filter content by list_id
    response = await client.get(f'/content/?list_id={list_id}')
    assert response.status_code == 200

    data = response.json()
    assert data['total'] == 1
    assert data['items'][0]['type'] == 'note'
    assert data['items'][0]['title'] == 'Work Note'


async def test__list_content_with_list_id__not_found(
    client: AsyncClient,
) -> None:
    """Test that non-existent list_id returns 404."""
    response = await client.get('/content/?list_id=99999')
    assert response.status_code == 404
    assert response.json()['detail'] == 'List not found'


async def test__list_content_with_list_id__complex_filter_expression(
    client: AsyncClient,
) -> None:
    """Test complex filter: (work AND priority) OR (urgent)."""
    # Create content
    await client.post(
        '/bookmarks/',
        json={'url': 'https://wp.com', 'title': 'Work Priority', 'tags': ['work', 'priority']},
    )
    await client.post(
        '/notes/',
        json={'title': 'Urgent Note', 'tags': ['urgent']},
    )
    await client.post(
        '/bookmarks/',
        json={'url': 'https://work.com', 'title': 'Just Work', 'tags': ['work']},
    )

    # Create list with complex filter
    response = await client.post(
        '/lists/',
        json={
            'name': 'Complex',
            'content_types': ['bookmark', 'note'],
            'filter_expression': {
                'groups': [
                    {'tags': ['work', 'priority']},
                    {'tags': ['urgent']},
                ],
                'group_operator': 'OR',
            },
        },
    )
    assert response.status_code == 201
    list_id = response.json()['id']

    response = await client.get(f'/content/?list_id={list_id}')
    assert response.status_code == 200

    data = response.json()
    assert data['total'] == 2
    titles = {item['title'] for item in data['items']}
    assert titles == {'Work Priority', 'Urgent Note'}


async def test__list_content_with_list_id__combines_with_text_search(
    client: AsyncClient,
) -> None:
    """Test combining list_id filter with text search."""
    # Create content with 'work' tag
    await client.post(
        '/bookmarks/',
        json={'url': 'https://python.com', 'title': 'Python Work', 'tags': ['work']},
    )
    await client.post(
        '/notes/',
        json={'title': 'JavaScript Work', 'tags': ['work']},
    )

    # Create work list
    response = await client.post(
        '/lists/',
        json={
            'name': 'Work',
            'content_types': ['bookmark', 'note'],
            'filter_expression': {'groups': [{'tags': ['work']}], 'group_operator': 'OR'},
        },
    )
    assert response.status_code == 201
    list_id = response.json()['id']

    # Filter by list AND search for 'Python'
    response = await client.get(f'/content/?list_id={list_id}&q=python')
    assert response.status_code == 200

    data = response.json()
    assert data['total'] == 1
    assert data['items'][0]['title'] == 'Python Work'


async def test__list_content_with_list_id__combines_with_tag_filter(
    client: AsyncClient,
) -> None:
    """Test that list_id filter and tags parameter combine with AND logic."""
    # Create content
    await client.post(
        '/bookmarks/',
        json={'url': 'https://work.com', 'title': 'Work Only', 'tags': ['work']},
    )
    await client.post(
        '/notes/',
        json={'title': 'Work Urgent', 'tags': ['work', 'urgent']},
    )

    # Create work list
    response = await client.post(
        '/lists/',
        json={
            'name': 'Work',
            'content_types': ['bookmark', 'note'],
            'filter_expression': {'groups': [{'tags': ['work']}], 'group_operator': 'OR'},
        },
    )
    assert response.status_code == 201
    list_id = response.json()['id']

    # Filter by list AND additional tag 'urgent'
    response = await client.get(f'/content/?list_id={list_id}&tags=urgent')
    assert response.status_code == 200

    data = response.json()
    assert data['total'] == 1
    assert data['items'][0]['title'] == 'Work Urgent'


async def test__list_content_with_list_id__empty_results(
    client: AsyncClient,
) -> None:
    """Test list_id filter with no matching content."""
    # Create content without 'work' tag
    await client.post(
        '/bookmarks/',
        json={'url': 'https://personal.com', 'title': 'Personal', 'tags': ['personal']},
    )

    # Create work list
    response = await client.post(
        '/lists/',
        json={
            'name': 'Work',
            'content_types': ['bookmark', 'note'],
            'filter_expression': {'groups': [{'tags': ['work']}], 'group_operator': 'OR'},
        },
    )
    assert response.status_code == 201
    list_id = response.json()['id']

    response = await client.get(f'/content/?list_id={list_id}')
    assert response.status_code == 200

    data = response.json()
    assert data['total'] == 0
    assert data['items'] == []
