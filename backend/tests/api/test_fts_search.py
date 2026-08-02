"""
API-level tests for FTS + ILIKE combined search.

Tests relevance sorting, default sort behavior, and MCP sort_by at the API level.
Also tests resolve_filter_and_sorting with query parameter.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.helpers.filter_utils import resolve_filter_and_sorting
from models.user import User
from core.tier_limits import Tier
from schemas.content_filter import ContentFilterCreate, FilterExpression
from services import content_filter_service


# =============================================================================
# resolve_filter_and_sorting Tests
# =============================================================================


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(external_auth_id='test|fts-filter-utils', email='fts-filter@test.com', tier=Tier.FREE.value)
    db_session.add(user)
    await db_session.flush()
    return user


async def test__resolve_filter_and_sorting__relevance_default_with_query(
    db_session: AsyncSession, user: User,
) -> None:
    """Query present, no explicit sort → returns 'relevance'."""
    result = await resolve_filter_and_sorting(
        db=db_session, user_id=user.id,
        filter_id=None, sort_by=None, sort_order=None,
        query='python',
    )
    assert result.sort_by == 'relevance'
    assert result.sort_order == 'desc'


async def test__resolve_filter_and_sorting__explicit_sort_wins_over_relevance(
    db_session: AsyncSession, user: User,
) -> None:
    """sort_by='title' + query → returns 'title'."""
    result = await resolve_filter_and_sorting(
        db=db_session, user_id=user.id,
        filter_id=None, sort_by='title', sort_order=None,
        query='python',
    )
    assert result.sort_by == 'title'


async def test__resolve_filter_and_sorting__filter_default_wins_without_query(
    db_session: AsyncSession, user: User,
) -> None:
    """Filter has default_sort_by='title', no query → returns 'title'."""
    data = ContentFilterCreate(
        name='Title Sort Filter',
        content_types=['bookmark'],
        filter_expression=FilterExpression(groups=[]),
        default_sort_by='title',
        default_sort_ascending=True,
    )
    content_filter = await content_filter_service.create_filter(db_session, user.id, data)

    result = await resolve_filter_and_sorting(
        db=db_session, user_id=user.id,
        filter_id=content_filter.id, sort_by=None, sort_order=None,
        query=None,
    )
    assert result.sort_by == 'title'


async def test__resolve_filter_and_sorting__relevance_wins_over_filter_default_with_query(
    db_session: AsyncSession, user: User,
) -> None:
    """Filter has default_sort_by='title', query present → returns 'relevance'."""
    data = ContentFilterCreate(
        name='Title Sort Filter 2',
        content_types=['bookmark'],
        filter_expression=FilterExpression(groups=[]),
        default_sort_by='title',
        default_sort_ascending=True,
    )
    content_filter = await content_filter_service.create_filter(db_session, user.id, data)

    result = await resolve_filter_and_sorting(
        db=db_session, user_id=user.id,
        filter_id=content_filter.id, sort_by=None, sort_order=None,
        query='python',
    )
    assert result.sort_by == 'relevance'
    # sort_order should be 'desc' for relevance, not 'asc' from the filter default
    assert result.sort_order == 'desc'


async def test__resolve_filter_and_sorting__no_query_no_filter__global_default(
    db_session: AsyncSession, user: User,
) -> None:
    """No query, no filter → 'created_at' desc."""
    result = await resolve_filter_and_sorting(
        db=db_session, user_id=user.id,
        filter_id=None, sort_by=None, sort_order=None,
        query=None,
    )
    assert result.sort_by == 'created_at'
    assert result.sort_order == 'desc'


# =============================================================================
# API-level Tests
# =============================================================================


async def test__list_bookmarks__sort_by_relevance(client: AsyncClient) -> None:
    """API returns results sorted by relevance when sort_by=relevance&q=..."""
    # Create bookmarks: title match should rank higher
    await client.post('/bookmarks/', json={
        'url': 'https://api-fts-1.example.com',
        'title': 'Python Programming Guide',
    })
    await client.post('/bookmarks/', json={
        'url': 'https://api-fts-2.example.com',
        'title': 'Generic Guide',
        'content': 'A long text about many topics. python is mentioned once.',
    })

    response = await client.get('/bookmarks/', params={
        'q': 'python', 'sort_by': 'relevance',
    })
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 2
    assert data['items'][0]['title'] == 'Python Programming Guide'


async def test__list_bookmarks__default_sort_relevance_with_query(
    client: AsyncClient,
) -> None:
    """API defaults to relevance sort when q is provided without sort_by."""
    await client.post('/bookmarks/', json={
        'url': 'https://api-default-1.example.com',
        'title': 'Django Web Framework',
    })
    await client.post('/bookmarks/', json={
        'url': 'https://api-default-2.example.com',
        'title': 'Random Article',
        'content': 'This mentions django briefly in passing',
    })

    # No sort_by param → should default to relevance since q is present
    response = await client.get('/bookmarks/', params={'q': 'django'})
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 2
    # Title match should rank first (relevance default)
    assert data['items'][0]['title'] == 'Django Web Framework'


async def test__list_bookmarks__relevance_sort_without_query_ok(
    client: AsyncClient,
) -> None:
    """sort_by=relevance without q doesn't error (falls back to created_at)."""
    await client.post('/bookmarks/', json={
        'url': 'https://api-nq-1.example.com',
        'title': 'First',
    })

    response = await client.get('/bookmarks/', params={'sort_by': 'relevance'})
    assert response.status_code == 200


async def test__list_notes__sort_by_relevance(client: AsyncClient) -> None:
    """Notes endpoint supports relevance sort with query."""
    await client.post('/notes/', json={
        'title': 'FastAPI Guide',
        'content': 'Building APIs with FastAPI',
    })
    await client.post('/notes/', json={
        'title': 'Other Note',
        'content': 'Some random content about fastapi configuration',
    })

    response = await client.get('/notes/', params={
        'q': 'fastapi', 'sort_by': 'relevance',
    })
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 2
    assert data['items'][0]['title'] == 'FastAPI Guide'


async def test__list_prompts__sort_by_relevance(client: AsyncClient) -> None:
    """Prompts endpoint supports relevance sort with query."""
    await client.post('/prompts/', json={
        'name': 'code-review',
        'title': 'Code Review Prompt',
        'content': 'Review this code: {{ code }}',
        'arguments': [{'name': 'code', 'required': True}],
    })
    await client.post('/prompts/', json={
        'name': 'other-prompt',
        'title': 'Other Prompt',
        'content': 'Something about code reviewing in a different context',
        'arguments': [],
    })

    response = await client.get('/prompts/', params={
        'q': 'code review', 'sort_by': 'relevance',
    })
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 2
    assert data['items'][0]['name'] == 'code-review'


async def test__list_content__sort_by_relevance(client: AsyncClient) -> None:
    """Content endpoint supports relevance sort with query."""
    await client.post('/bookmarks/', json={
        'url': 'https://content-rel-1.example.com',
        'title': 'Terraform Infrastructure',
    })
    await client.post('/notes/', json={
        'title': 'Random Note',
        'content': 'A long note about many things. terraform is mentioned here.',
    })

    response = await client.get('/content/', params={
        'q': 'terraform', 'sort_by': 'relevance',
    })
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 2
    # Bookmark with title match should rank higher
    assert data['items'][0]['title'] == 'Terraform Infrastructure'


async def test__list_bookmarks__stop_words_return_empty(client: AsyncClient) -> None:
    """Stop-word-only queries return empty results."""
    await client.post('/bookmarks/', json={
        'url': 'https://stop-words.example.com',
        'title': 'The Best Article',
    })

    response = await client.get('/bookmarks/', params={'q': 'the'})
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 0


async def test__list_bookmarks__stemming_match(client: AsyncClient) -> None:
    """FTS stemming: searching 'databases' matches 'database' in title."""
    await client.post('/bookmarks/', json={
        'url': 'https://stemming.example.com',
        'title': 'Database Administration',
    })

    response = await client.get('/bookmarks/', params={'q': 'databases'})
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 1
    assert data['items'][0]['title'] == 'Database Administration'


async def test__list_bookmarks__relevance_with_filter_id(
    client: AsyncClient,
) -> None:
    """Relevance sort works correctly when combined with a content filter."""
    # Create filter via API so it belongs to the same dev_mode user as the client
    filter_resp = await client.post('/filters/', json={
        'name': 'Test FTS Filter',
        'content_types': ['bookmark'],
        'filter_expression': {'groups': []},
        'default_sort_by': 'title',
        'default_sort_ascending': True,
    })
    assert filter_resp.status_code == 201
    filter_id = filter_resp.json()['id']

    # Create bookmarks with different relevance
    await client.post('/bookmarks/', json={
        'url': 'https://filter-fts-1.example.com',
        'title': 'Python Machine Learning',
    })
    await client.post('/bookmarks/', json={
        'url': 'https://filter-fts-2.example.com',
        'title': 'Generic Guide',
        'content': 'This mentions python once in passing.',
    })

    # Query with filter_id — should default to relevance, overriding filter's title sort
    response = await client.get('/bookmarks/', params={
        'q': 'python',
        'filter_id': filter_id,
    })
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 2
    # Title match should rank first (relevance default beats filter's title sort)
    assert data['items'][0]['title'] == 'Python Machine Learning'
