"""
Seed script to populate the local dev database with realistic test data.

Usage:
    PYTHONPATH=backend/src uv run python backend/scripts/seed_data.py populate
    PYTHONPATH=backend/src uv run python backend/scripts/seed_data.py populate --force
    PYTHONPATH=backend/src uv run python backend/scripts/seed_data.py clear
"""

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import get_settings
from models import Bookmark, ContentFilter, ContentHistory, Note, Prompt, Tag, User

# Dev user sentinel (matches core/auth.py dev mode; external_auth_id since M6b)
DEV_EXTERNAL_AUTH_ID = 'dev|local-development-user'

TAG_NAMES = [
    'python', 'javascript', 'rust', 'web-dev', 'machine-learning',
    'devops', 'database', 'api-design', 'testing', 'security',
    'performance', 'open-source', 'tutorial', 'reference', 'tools',
]

# ---------------------------------------------------------------------------
# Bookmark data
# ---------------------------------------------------------------------------

BOOKMARKS = [
    {
        'url': 'https://docs.python.org/3/',
        'title': 'Python Official Documentation',
        'description': 'Comprehensive reference for the Python programming language.',
        'content': (
            'The official Python documentation covers the standard library, language reference, '
            'and tutorials for both beginners and experienced developers. It includes detailed '
            'API references for built-in functions, data types, and modules like asyncio, '
            'collections, and pathlib.\n\n'
            'Key sections include the Tutorial, Library Reference, Language Reference, and '
            'the Python HOWTOs for common tasks like logging, regex, and socket programming.'
        ),
        'tags': ['python', 'reference'],
    },
    {
        'url': 'https://developer.mozilla.org/en-US/docs/Web/JavaScript',
        'title': 'MDN Web Docs - JavaScript',
        'description': 'The definitive resource for JavaScript documentation and web APIs.',
        'content': (
            'MDN Web Docs provides comprehensive documentation for JavaScript, HTML, CSS, '
            'and Web APIs. The JavaScript section covers everything from basic syntax and '
            'data types to advanced topics like closures, prototypes, and the event loop.\n\n'
            '## Key Resources\n\n'
            '- **JavaScript Guide**: Step-by-step tutorials from basics to advanced\n'
            '- **JavaScript Reference**: Complete API documentation for built-in objects\n'
            '- **Web APIs**: DOM manipulation, Fetch API, Web Storage, WebSockets\n'
            '- **Compatibility Tables**: Browser support data for every feature\n\n'
            '## Learning Paths\n\n'
            'MDN offers structured learning paths for beginners, covering variables, '
            'functions, objects, and asynchronous JavaScript. The intermediate path covers '
            'client-side frameworks, accessibility, and performance optimization.\n\n'
            'The site is open source and community-maintained, ensuring up-to-date and '
            'accurate documentation for web developers worldwide.'
        ),
        'tags': ['javascript', 'web-dev', 'reference'],
    },
    {
        'url': 'https://doc.rust-lang.org/book/',
        'title': 'Rust Book - Getting Started',
        'description': 'The official guide to learning Rust programming.',
        'content': (
            'The Rust Programming Language book, affectionately known as "The Book," is the '
            'primary resource for learning Rust. It covers ownership, borrowing, lifetimes, '
            'pattern matching, error handling, and concurrency.\n\n'
            'Chapters progress from basic concepts like variables and control flow to advanced '
            'topics like smart pointers, unsafe Rust, and macros.'
        ),
        'tags': ['rust', 'tutorial'],
    },
    {
        'url': 'https://fastapi.tiangolo.com/',
        'title': 'FastAPI Documentation',
        'description': 'Modern Python web framework with automatic OpenAPI docs.',
        'content': (
            'FastAPI is a modern, high-performance web framework for building APIs with '
            'Python 3.7+ based on standard Python type hints. Key features include automatic '
            'interactive API documentation, dependency injection, OAuth2 with JWT, and '
            'WebSocket support.\n\n'
            'Built on Starlette for the web parts and Pydantic for data validation, FastAPI '
            'achieves performance comparable to Node.js and Go.'
        ),
        'tags': ['python', 'api-design', 'web-dev'],
    },
    {
        'url': 'https://docs.docker.com/develop/dev-best-practices/',
        'title': 'Docker Best Practices',
        'description': 'Guidelines for building efficient Docker images and containers.',
        'content': 'Use multi-stage builds, minimize layers, leverage build cache, and avoid running as root.',
        'tags': ['devops', 'tools'],
    },
    {
        'url': 'https://wiki.postgresql.org/wiki/Performance_Optimization',
        'title': 'PostgreSQL Performance Tuning',
        'description': 'In-depth guide to optimizing PostgreSQL for production workloads.',
        'content': (
            'PostgreSQL performance tuning involves multiple layers: query optimization, '
            'index strategy, configuration tuning, and hardware considerations.\n\n'
            '## Query Optimization\n\n'
            'Use EXPLAIN ANALYZE to understand query plans. Look for sequential scans on '
            'large tables, nested loop joins with high row counts, and sort operations that '
            'spill to disk. Common fixes include adding indexes, rewriting subqueries as '
            'JOINs, and using CTEs for complex queries.\n\n'
            '## Index Strategy\n\n'
            '```sql\n'
            '-- Partial index for active records\n'
            'CREATE INDEX idx_orders_active ON orders(created_at)\n'
            '  WHERE status != \'cancelled\';\n\n'
            '-- Covering index to avoid table lookups\n'
            'CREATE INDEX idx_users_email_name ON users(email) INCLUDE (name);\n\n'
            '-- GIN index for JSONB queries\n'
            'CREATE INDEX idx_metadata ON items USING gin(metadata);\n'
            '```\n\n'
            '## Configuration Tuning\n\n'
            '- `shared_buffers`: Set to 25% of available RAM\n'
            '- `effective_cache_size`: Set to 50-75% of available RAM\n'
            '- `work_mem`: Start at 64MB, increase for complex queries\n'
            '- `maintenance_work_mem`: Set to 512MB-1GB for VACUUM and CREATE INDEX\n'
            '- `random_page_cost`: Set to 1.1 for SSD storage\n\n'
            '## Connection Pooling\n\n'
            'Use PgBouncer or built-in connection pooling to manage connections efficiently. '
            'Each PostgreSQL connection consumes ~10MB of memory, so limiting connections and '
            'using a pool is essential for production deployments.'
        ),
        'tags': ['database', 'performance'],
    },
    {
        'url': 'https://owasp.org/www-project-top-ten/',
        'title': 'OWASP Top 10 Security Risks',
        'description': 'Standard awareness document for web application security.',
        'content': (
            'The OWASP Top 10 represents the most critical web application security risks. '
            'The current list includes injection, broken authentication, sensitive data '
            'exposure, XML external entities, broken access control, security misconfiguration, '
            'cross-site scripting, insecure deserialization, using components with known '
            'vulnerabilities, and insufficient logging and monitoring.'
        ),
        'tags': ['security', 'web-dev'],
    },
    {
        'url': 'https://docs.github.com/en/actions',
        'title': 'GitHub Actions CI/CD Guide',
        'description': 'Automate build, test, and deployment workflows with GitHub Actions.',
        'content': (
            'GitHub Actions enables CI/CD directly in your repository. Workflows are defined '
            'in YAML files under `.github/workflows/` and triggered by events like push, '
            'pull_request, or schedule.\n\n'
            'Key concepts include jobs, steps, actions (reusable units), runners (hosted or '
            'self-hosted), and secrets management for secure credential storage.'
        ),
        'tags': ['devops', 'testing'],
    },
    {
        'url': 'https://redis.io/docs/manual/patterns/',
        'title': 'Redis Caching Patterns',
        'description': 'Common patterns for using Redis as a cache and data store.',
        'content': 'Cache-aside, write-through, write-behind, and refresh-ahead patterns for Redis.',
        'tags': ['database', 'performance'],
    },
    {
        'url': 'https://www.tensorflow.org/tutorials',
        'title': 'TensorFlow Getting Started',
        'description': 'Official tutorials for machine learning with TensorFlow.',
        'content': (
            'TensorFlow provides a comprehensive ecosystem for building and deploying ML '
            'models. Start with Keras for high-level model building, then explore TensorFlow '
            'Datasets for data loading, TensorBoard for visualization, and TF Serving for '
            'production deployment.\n\n'
            'The tutorials cover image classification, natural language processing, '
            'generative models, and reinforcement learning.'
        ),
        'tags': ['python', 'machine-learning'],
    },
    {
        'url': 'https://docs.sqlalchemy.org/en/20/changelog/migration_20.html',
        'title': 'SQLAlchemy 2.0 Migration Guide',
        'description': 'Complete guide to migrating from SQLAlchemy 1.x to 2.0.',
        'content': (
            'SQLAlchemy 2.0 introduces significant changes to the ORM and Core APIs.\n\n'
            '## Key Changes\n\n'
            '### Session API\n'
            '```python\n'
            '# Old (1.x)\n'
            'session.query(User).filter(User.name == "alice").first()\n\n'
            '# New (2.0)\n'
            'from sqlalchemy import select\n'
            'stmt = select(User).where(User.name == "alice")\n'
            'result = session.execute(stmt).scalar_one_or_none()\n'
            '```\n\n'
            '### Declarative Mapping\n'
            '```python\n'
            '# Old (1.x)\n'
            'class User(Base):\n'
            '    id = Column(Integer, primary_key=True)\n'
            '    name = Column(String(50))\n\n'
            '# New (2.0)\n'
            'class User(Base):\n'
            '    id: Mapped[int] = mapped_column(primary_key=True)\n'
            '    name: Mapped[str] = mapped_column(String(50))\n'
            '```\n\n'
            '### Async Support\n'
            'SQLAlchemy 2.0 provides first-class async support via `create_async_engine` '
            'and `AsyncSession`. This enables integration with async frameworks like '
            'FastAPI without blocking the event loop.\n\n'
            '```python\n'
            'from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession\n\n'
            'engine = create_async_engine("postgresql+asyncpg://...")\n'
            'async with AsyncSession(engine) as session:\n'
            '    result = await session.execute(select(User))\n'
            '    users = result.scalars().all()\n'
            '```\n\n'
            '## Migration Strategy\n\n'
            '1. Enable `SQLALCHEMY_WARN_20=1` to surface deprecation warnings\n'
            '2. Migrate queries from `session.query()` to `select()` + `session.execute()`\n'
            '3. Update column definitions to use `Mapped[]` and `mapped_column()`\n'
            '4. Replace `relationship()` string references with `Mapped[]` annotations'
        ),
        'tags': ['python', 'database'],
    },
    {
        'url': 'https://tailwindcss.com/docs',
        'title': 'Tailwind CSS Cheat Sheet',
        'description': 'Quick reference for Tailwind CSS utility classes.',
        'content': 'Spacing: p-4, m-2, gap-3. Flex: flex, items-center, justify-between. Colors: bg-blue-500, text-gray-900.',
        'tags': ['web-dev', 'tools', 'reference'],
    },
    {
        'url': 'https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html',
        'title': 'AWS Lambda Best Practices',
        'description': 'Performance and cost optimization tips for serverless functions.',
        'content': (
            'Key best practices for AWS Lambda include minimizing cold starts by keeping '
            'deployment packages small, reusing execution contexts for database connections, '
            'using environment variables for configuration, and setting appropriate memory '
            'and timeout values.\n\n'
            'Monitor with CloudWatch metrics and X-Ray tracing to identify bottlenecks.'
        ),
        'tags': ['devops', 'performance'],
    },
    {
        'url': 'https://choosealicense.com/',
        'title': 'Open Source Licensing Guide',
        'description': 'Simple guide to choosing an open source license.',
        'content': 'MIT for permissive, Apache 2.0 for patent protection, GPL for copyleft, AGPL for network use.',
        'tags': ['open-source'],
    },
    {
        'url': 'https://docs.pytest.org/en/stable/',
        'title': 'pytest Tips and Tricks',
        'description': 'Advanced testing patterns with pytest.',
        'content': (
            'pytest is the most popular Python testing framework. Key features include '
            'powerful fixtures with dependency injection, parametrize for data-driven tests, '
            'markers for test categorization, and plugins like pytest-asyncio and pytest-cov.\n\n'
            'Use conftest.py for shared fixtures, and `tmp_path` for temporary file testing.'
        ),
        'tags': ['python', 'testing'],
    },
    {
        'url': 'https://www.howtographql.com/',
        'title': 'GraphQL vs REST',
        'description': 'Comparing GraphQL and REST API design approaches.',
        'content': (
            'GraphQL offers flexible queries with a single endpoint, while REST uses '
            'resource-based URLs with fixed response shapes. GraphQL eliminates over-fetching '
            'and under-fetching but adds complexity with schema management and caching.\n\n'
            'Choose REST for simple CRUD APIs and GraphQL for complex data requirements '
            'with multiple consumers.'
        ),
        'tags': ['api-design', 'web-dev'],
    },
    {
        'url': 'https://kubernetes.io/docs/concepts/overview/',
        'title': 'Kubernetes Overview',
        'description': 'Container orchestration platform for deploying and managing applications.',
        'content': (
            'Kubernetes (k8s) automates deployment, scaling, and management of '
            'containerized applications.\n\n'
            '## Core Concepts\n\n'
            '- **Pods**: Smallest deployable unit, one or more containers\n'
            '- **Services**: Stable network endpoint for a set of pods\n'
            '- **Deployments**: Declarative updates for pods and replica sets\n'
            '- **ConfigMaps/Secrets**: External configuration management\n'
            '- **Namespaces**: Virtual clusters for resource isolation\n\n'
            '## Architecture\n\n'
            'The control plane (API server, scheduler, controller manager, etcd) manages '
            'the cluster state. Worker nodes run kubelet, kube-proxy, and container runtime.\n\n'
            '## Common Operations\n\n'
            '```bash\n'
            'kubectl get pods -n my-namespace\n'
            'kubectl apply -f deployment.yaml\n'
            'kubectl logs -f pod-name\n'
            'kubectl exec -it pod-name -- /bin/sh\n'
            'kubectl rollout status deployment/my-app\n'
            'kubectl scale deployment/my-app --replicas=3\n'
            '```\n\n'
            '## Helm Charts\n\n'
            'Helm is the package manager for Kubernetes, providing templated manifests '
            'and dependency management for complex deployments.'
        ),
        'tags': ['devops', 'tools'],
    },
    {
        'url': 'https://google.github.io/eng-practices/review/',
        'title': 'Effective Code Reviews',
        'description': 'Best practices for reviewing code changes.',
        'content': 'Focus on correctness, readability, and design. Be constructive. Review in small batches.',
        'tags': ['testing', 'tools'],
    },
    {
        'url': 'https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API',
        'title': 'WebSocket Protocol Guide',
        'description': 'Real-time bidirectional communication for web applications.',
        'content': (
            'WebSockets provide full-duplex communication channels over a single TCP '
            'connection. Unlike HTTP, WebSockets allow the server to push data to clients '
            'without polling.\n\n'
            'Use cases include chat applications, live dashboards, collaborative editing, '
            'and real-time notifications. Consider Server-Sent Events for simpler '
            'unidirectional streaming.'
        ),
        'tags': ['web-dev', 'api-design'],
    },
    {
        'url': 'https://ml-ops.org/content/mlops-principles',
        'title': 'ML Model Deployment Patterns',
        'description': 'Patterns for deploying machine learning models to production.',
        'content': (
            'MLOps bridges the gap between ML development and production deployment. '
            'Key patterns include model versioning, A/B testing, canary deployments, '
            'feature stores, and automated retraining pipelines.\n\n'
            'Monitor for data drift and model degradation using statistical tests '
            'on prediction distributions.'
        ),
        'tags': ['machine-learning', 'devops'],
    },
    # Archived
    {
        'url': 'https://nginx.org/en/docs/beginners_guide.html',
        'title': 'Nginx Configuration Guide',
        'description': 'Basic Nginx configuration for reverse proxy and static serving.',
        'content': 'Configure server blocks, location directives, proxy_pass for reverse proxy, and SSL termination.',
        'tags': ['devops', 'performance'],
        'archived': True,
    },
    {
        'url': 'https://vuejs.org/guide/extras/composition-api-faq.html',
        'title': 'Vue.js 3 Composition API',
        'description': 'Modern Vue.js component patterns with the Composition API.',
        'content': (
            'The Composition API provides a set of function-based APIs for organizing '
            'component logic. Key concepts include `ref()`, `reactive()`, `computed()`, '
            'and lifecycle hooks like `onMounted()`. Use `composables` (custom hooks) '
            'to extract and reuse stateful logic across components.'
        ),
        'tags': ['javascript', 'web-dev'],
        'archived': True,
    },
    {
        'url': 'https://flask.palletsprojects.com/en/2.3.x/patterns/',
        'title': 'Deprecated Flask Patterns',
        'description': 'Legacy patterns from older Flask versions.',
        'content': 'These patterns were common in Flask 1.x but have been superseded by modern approaches.',
        'tags': ['python', 'web-dev'],
        'archived': True,
    },
    # Deleted
    {
        'url': 'https://webpack.js.org/concepts/',
        'title': 'Old Webpack Config Guide',
        'description': None,
        'content': None,
        'tags': ['javascript', 'tools'],
        'deleted': True,
    },
    {
        'url': 'https://example.com/broken-link-404',
        'title': 'Broken Link - Removed',
        'description': None,
        'content': None,
        'tags': [],
        'deleted': True,
    },
]

# ---------------------------------------------------------------------------
# Note data
# ---------------------------------------------------------------------------

NOTES = [
    {
        'title': 'Python Virtual Environments Cheat Sheet',
        'content': (
            '```bash\npython -m venv .venv\nsource .venv/bin/activate\npip install -r requirements.txt\n```'
        ),
        'tags': ['python', 'tools'],
    },
    {
        'title': 'Meeting Notes: API Redesign Discussion',
        'content': (
            '## API Redesign - Jan 2026\n\n'
            '**Attendees:** Alice, Bob, Charlie\n\n'
            '### Decisions\n'
            '- Move to versioned endpoints (`/v2/`)\n'
            '- Adopt JSON:API response format\n'
            '- Add cursor-based pagination for all list endpoints\n'
            '- Deprecate `/search` in favor of query params on list endpoints\n\n'
            '### Action Items\n'
            '- [ ] Alice: Draft OpenAPI spec for v2\n'
            '- [ ] Bob: Prototype pagination changes\n'
            '- [ ] Charlie: Audit current API consumers'
        ),
        'tags': ['api-design'],
    },
    {
        'title': 'Comprehensive Guide to SQL Joins',
        'content': (
            '# SQL Joins Reference\n\n'
            '## INNER JOIN\n'
            'Returns rows that have matching values in both tables.\n\n'
            '```sql\n'
            'SELECT users.name, orders.total\n'
            'FROM users\n'
            'INNER JOIN orders ON users.id = orders.user_id;\n'
            '```\n\n'
            '## LEFT JOIN (LEFT OUTER JOIN)\n'
            'Returns all rows from the left table and matched rows from the right.\n'
            'Non-matching right rows are NULL.\n\n'
            '```sql\n'
            'SELECT users.name, COALESCE(orders.total, 0) as total\n'
            'FROM users\n'
            'LEFT JOIN orders ON users.id = orders.user_id;\n'
            '```\n\n'
            '## RIGHT JOIN\n'
            'Opposite of LEFT JOIN - all rows from right table.\n\n'
            '## FULL OUTER JOIN\n'
            'Returns all rows from both tables, NULLs where no match.\n\n'
            '## CROSS JOIN\n'
            'Cartesian product of both tables (every combination).\n\n'
            '```sql\n'
            'SELECT sizes.name, colors.name\n'
            'FROM sizes\n'
            'CROSS JOIN colors;\n'
            '```\n\n'
            '## SELF JOIN\n'
            'Join a table to itself (e.g., for hierarchical data).\n\n'
            '```sql\n'
            'SELECT e.name AS employee, m.name AS manager\n'
            'FROM employees e\n'
            'LEFT JOIN employees m ON e.manager_id = m.id;\n'
            '```\n\n'
            '## Performance Tips\n\n'
            '- Always JOIN on indexed columns\n'
            '- Use EXPLAIN ANALYZE to verify join strategies\n'
            '- Prefer EXISTS over IN for subquery conditions\n'
            '- Be careful with JOINs that multiply rows (1-to-many)'
        ),
        'tags': ['database', 'tutorial'],
    },
    {
        'title': 'Quick Regex Reference',
        'content': (
            '`\\d` digit, `\\w` word char, `\\s` whitespace, `.` any char, '
            '`*` 0+, `+` 1+, `?` optional, `{n,m}` range'
        ),
        'tags': ['reference', 'tools'],
    },
    {
        'title': 'Machine Learning Project Roadmap',
        'content': (
            '## Phase 1: Data Collection & Exploration\n'
            '- Gather training data from internal APIs\n'
            '- EDA with pandas profiling\n'
            '- Handle missing values and outliers\n\n'
            '## Phase 2: Feature Engineering\n'
            '- Text features: TF-IDF, embeddings\n'
            '- Numerical: normalization, binning\n'
            '- Feature selection with mutual information\n\n'
            '## Phase 3: Model Training\n'
            '- Baseline: logistic regression\n'
            '- Compare: random forest, gradient boosting, neural net\n'
            '- Hyperparameter tuning with Optuna\n\n'
            '## Phase 4: Deployment\n'
            '- Model serialization with ONNX\n'
            '- Serve via FastAPI + Docker\n'
            '- Monitor predictions and retrain on drift'
        ),
        'tags': ['machine-learning', 'python'],
    },
    {
        'title': 'Docker Compose for Local Dev',
        'content': (
            '```yaml\n'
            'version: "3.8"\n'
            'services:\n'
            '  db:\n'
            '    image: postgres:16\n'
            '    environment:\n'
            '      POSTGRES_DB: myapp\n'
            '      POSTGRES_USER: dev\n'
            '      POSTGRES_PASSWORD: dev\n'
            '    ports:\n'
            '      - "5432:5432"\n'
            '    volumes:\n'
            '      - pgdata:/var/lib/postgresql/data\n\n'
            '  redis:\n'
            '    image: redis:7-alpine\n'
            '    ports:\n'
            '      - "6379:6379"\n\n'
            '  app:\n'
            '    build: .\n'
            '    ports:\n'
            '      - "8000:8000"\n'
            '    depends_on:\n'
            '      - db\n'
            '      - redis\n'
            '    env_file: .env\n\n'
            'volumes:\n'
            '  pgdata:\n'
            '```\n\n'
            'Run with `docker compose up -d` and check logs with `docker compose logs -f`.'
        ),
        'tags': ['devops', 'tools'],
    },
    {
        'title': 'Security Audit Checklist',
        'content': (
            '## Authentication & Authorization\n'
            '- [ ] All endpoints require authentication\n'
            '- [ ] Role-based access control implemented\n'
            '- [ ] JWT tokens have appropriate expiry\n'
            '- [ ] Password requirements enforced\n\n'
            '## Input Validation\n'
            '- [ ] SQL injection prevention (parameterized queries)\n'
            '- [ ] XSS prevention (output encoding)\n'
            '- [ ] CSRF tokens on state-changing requests\n'
            '- [ ] File upload validation (type, size)\n\n'
            '## Data Protection\n'
            '- [ ] Sensitive data encrypted at rest\n'
            '- [ ] TLS enforced for all connections\n'
            '- [ ] PII handling compliant with GDPR\n'
            '- [ ] Secrets stored in vault, not code'
        ),
        'tags': ['security', 'testing'],
    },
    {
        'title': 'JavaScript Async/Await Patterns',
        'content': (
            '## Sequential Execution\n'
            '```javascript\n'
            'const user = await getUser(id);\n'
            'const posts = await getPosts(user.id);\n'
            '```\n\n'
            '## Parallel Execution\n'
            '```javascript\n'
            'const [users, posts] = await Promise.all([\n'
            '  getUsers(),\n'
            '  getPosts(),\n'
            ']);\n'
            '```\n\n'
            '## Error Handling\n'
            '```javascript\n'
            'try {\n'
            '  const data = await fetchData();\n'
            '} catch (error) {\n'
            '  if (error instanceof NetworkError) {\n'
            '    // retry logic\n'
            '  }\n'
            '}\n'
            '```'
        ),
        'tags': ['javascript', 'web-dev'],
    },
    {
        'title': 'Database Migration Strategy Notes',
        'content': (
            '# Migration Strategy for Schema v2\n\n'
            '## Principles\n'
            '- Every migration must be reversible\n'
            '- Zero-downtime deployments (expand-contract pattern)\n'
            '- Test migrations against production-like data volumes\n\n'
            '## Phase 1: Expand (Deploy First)\n'
            '1. Add new columns as nullable\n'
            '2. Add new tables\n'
            '3. Create indexes concurrently\n'
            '4. Deploy app code that writes to both old and new schema\n\n'
            '## Phase 2: Migrate Data\n'
            '1. Backfill new columns from old data\n'
            '2. Run in batches of 1000 to avoid long locks\n'
            '3. Verify data consistency between old and new\n\n'
            '## Phase 3: Contract (Deploy Second)\n'
            '1. Deploy app code that only reads from new schema\n'
            '2. Drop old columns and tables\n'
            '3. Remove temporary migration code\n\n'
            '## Tools\n'
            '- Alembic for migration management\n'
            '- `pg_stat_activity` to monitor lock waits\n'
            '- `pg_stat_user_tables` for table statistics\n\n'
            '## Rollback Plan\n'
            'Always test `alembic downgrade -1` in staging before production.'
        ),
        'tags': ['database', 'devops'],
    },
    {
        'title': 'Rust Ownership Mental Model',
        'content': (
            'Each value has exactly one owner. When the owner goes out of scope, the value is dropped. '
            'Borrowing creates references without taking ownership: `&T` (shared) or `&mut T` (exclusive).'
        ),
        'tags': ['rust', 'tutorial'],
    },
    {
        'title': 'Performance Benchmarking Results',
        'content': (
            '# API Performance Benchmarks - 2026-01\n\n'
            '## Test Environment\n'
            '- 4 vCPU, 8GB RAM\n'
            '- PostgreSQL 16, Redis 7\n'
            '- 100 concurrent connections\n\n'
            '## Results\n\n'
            '| Endpoint | p50 | p95 | p99 | RPS |\n'
            '|----------|-----|-----|-----|-----|\n'
            '| GET /bookmarks | 12ms | 45ms | 120ms | 850 |\n'
            '| GET /bookmarks/:id | 5ms | 15ms | 35ms | 2100 |\n'
            '| POST /bookmarks | 25ms | 80ms | 200ms | 420 |\n'
            '| GET /notes | 15ms | 50ms | 130ms | 780 |\n'
            '| GET /search?q=... | 35ms | 120ms | 350ms | 310 |\n\n'
            '## Analysis\n\n'
            '- Search endpoint is the bottleneck due to full-text search\n'
            '- Consider adding tsvector index optimization\n'
            '- Connection pooling (PgBouncer) reduced p99 by 40%\n'
            '- Redis caching for tag lookups improved list endpoints by 25%\n\n'
            '## Load Test Profile\n'
            '```\n'
            'wrk -t4 -c100 -d60s --latency http://localhost:8000/api/bookmarks\n'
            '```\n\n'
            '## Recommendations\n'
            '1. Add materialized view for popular search queries\n'
            '2. Implement cursor pagination to replace offset\n'
            '3. Cache tag counts (invalidate on write)\n'
            '4. Consider read replicas for search traffic'
        ),
        'tags': ['performance', 'testing'],
    },
    {
        'title': 'API Rate Limiting Design',
        'content': (
            '## Algorithm: Sliding Window Counter\n\n'
            'Combines fixed window counters with sliding window for accuracy.\n'
            'Uses Redis MULTI/EXEC for atomic increment + expiry.\n\n'
            '## Tiers\n'
            '- Free: 60 req/min, 1000 req/day\n'
            '- Pro: 300 req/min, 10000 req/day\n'
            '- Enterprise: custom limits\n\n'
            '## Headers\n'
            'Return `X-RateLimit-Limit`, `X-RateLimit-Remaining`, '
            '`X-RateLimit-Reset`, and `Retry-After` on 429.'
        ),
        'tags': ['api-design', 'security'],
    },
    {
        'title': 'Git Workflow Conventions',
        'content': (
            'Branch naming: `feature/`, `fix/`, `chore/`. '
            'Commit format: `type(scope): description`. '
            'Always rebase before merge. Squash WIP commits.'
        ),
        'tags': ['tools', 'reference'],
    },
    {
        'title': 'React vs Vue Comparison',
        'content': (
            '## React\n'
            '- JSX for templates (JavaScript-centric)\n'
            '- Hooks for state and effects\n'
            '- Huge ecosystem, more job market\n'
            '- Meta-frameworks: Next.js, Remix\n\n'
            '## Vue\n'
            '- SFC with template/script/style sections\n'
            '- Composition API (similar to hooks)\n'
            '- Gentler learning curve\n'
            '- Meta-frameworks: Nuxt\n\n'
            '## Decision Factors\n'
            '- Team experience\n'
            '- Project complexity\n'
            '- Ecosystem needs'
        ),
        'tags': ['javascript', 'web-dev'],
    },
    {
        'title': 'SSH Key Setup Guide',
        'content': (
            '```bash\nssh-keygen -t ed25519 -C "your@email.com"\neval "$(ssh-agent -s)"\n'
            'ssh-add ~/.ssh/id_ed25519\ncat ~/.ssh/id_ed25519.pub\n```'
        ),
        'tags': ['devops', 'security'],
    },
    {
        'title': 'Project Architecture Decision Record',
        'content': (
            '# ADR-001: Database Choice\n\n'
            '## Status: Accepted\n\n'
            '## Context\n'
            'We need a primary database for the content management system that supports '
            'full-text search, JSON storage, and strong consistency.\n\n'
            '## Options Considered\n\n'
            '### PostgreSQL\n'
            '- Native full-text search with tsvector/tsquery\n'
            '- JSONB for flexible metadata storage\n'
            '- Mature ecosystem, excellent tooling\n'
            '- Strong ACID compliance\n\n'
            '### MongoDB\n'
            '- Flexible schema for rapid iteration\n'
            '- Built-in text search (less powerful than PG)\n'
            '- Horizontal scaling via sharding\n\n'
            '### SQLite\n'
            '- Zero configuration, embedded\n'
            '- Limited concurrent write support\n'
            '- No native async support\n\n'
            '## Decision\n'
            'PostgreSQL 16 with asyncpg driver.\n\n'
            '## Consequences\n'
            '- Excellent full-text search without external service (Elasticsearch)\n'
            '- JSONB enables schema evolution for prompt arguments\n'
            '- Need connection pooling for high concurrency\n'
            '- Alembic for migration management\n\n'
            '---\n\n'
            '# ADR-002: Authentication Strategy\n\n'
            '## Status: Accepted\n\n'
            '## Context\n'
            'Need authentication supporting both browser sessions and API access.\n\n'
            '## Decision\n'
            'Clerk for browser auth, Personal Access Tokens for API access.\n'
            'Dev mode bypasses auth entirely for local development.\n\n'
            '## Consequences\n'
            '- Two auth paths to maintain and test\n'
            '- PATs need secure storage and rotation\n'
            '- Dev mode must be restricted to local databases only'
        ),
        'tags': ['api-design', 'database'],
    },
    {
        'title': 'Debugging Production Issues Playbook',
        'content': (
            '## Step 1: Assess Severity\n'
            '- P0: Full outage, all users affected\n'
            '- P1: Major feature broken, some users affected\n'
            '- P2: Minor issue, workaround available\n\n'
            '## Step 2: Gather Information\n'
            '- Check error logs (CloudWatch/Datadog)\n'
            '- Check metrics dashboards\n'
            '- Identify recent deployments\n'
            '- Check external service status pages\n\n'
            '## Step 3: Mitigate\n'
            '- Rollback if deployment-related\n'
            '- Scale up if load-related\n'
            '- Failover if infrastructure-related\n\n'
            '## Step 4: Root Cause Analysis\n'
            '- Write a blameless post-mortem\n'
            '- Identify systemic improvements\n'
            '- Create follow-up tickets'
        ),
        'tags': ['devops', 'testing'],
    },
    {
        'title': 'Open Source Contribution Guidelines',
        'content': (
            '## Before Contributing\n'
            '1. Read CONTRIBUTING.md and CODE_OF_CONDUCT.md\n'
            '2. Check existing issues and PRs for duplicates\n'
            '3. For large changes, open an issue for discussion first\n\n'
            '## Making a Contribution\n'
            '1. Fork the repo and create a feature branch\n'
            '2. Write tests for new functionality\n'
            '3. Ensure CI passes (lint, tests, type checks)\n'
            '4. Write a clear PR description with context\n'
            '5. Respond to review feedback promptly'
        ),
        'tags': ['open-source'],
    },
    {
        'title': 'TypeScript Utility Types Reference',
        'content': (
            '`Partial<T>`, `Required<T>`, `Pick<T, K>`, `Omit<T, K>`, '
            '`Record<K, V>`, `Exclude<T, U>`, `Extract<T, U>`, `ReturnType<T>`'
        ),
        'tags': ['javascript', 'reference'],
    },
    {
        'title': 'CI/CD Pipeline Design',
        'content': (
            '## Pipeline Stages\n\n'
            '1. **Lint & Type Check** - Fast feedback, fail early\n'
            '2. **Unit Tests** - Isolated, parallel execution\n'
            '3. **Integration Tests** - Database, Redis, external services\n'
            '4. **Build** - Docker image, frontend bundle\n'
            '5. **Deploy Staging** - Automatic on main branch\n'
            '6. **Smoke Tests** - Verify staging deployment\n'
            '7. **Deploy Production** - Manual approval gate\n\n'
            '## Best Practices\n'
            '- Cache dependencies between runs\n'
            '- Use matrix builds for multiple Python/Node versions\n'
            '- Store secrets in CI provider, never in code\n'
            '- Set timeout limits on all jobs'
        ),
        'tags': ['devops', 'testing'],
    },
    {
        'title': 'Empty Draft Note',
        'content': None,
        'tags': [],
    },
    # Archived
    {
        'title': 'Archived: Old Sprint Retrospective',
        'content': (
            '## Sprint 14 Retro\n\n'
            '**What went well:** Shipped auth feature on time.\n'
            '**What could improve:** Too many meetings.\n'
            '**Action items:** Block focus time on calendars.'
        ),
        'tags': [],
        'archived': True,
    },
    {
        'title': 'Archived: Deprecated API Endpoints',
        'content': 'The `/v1/search` and `/v1/bulk-import` endpoints are removed in v2.',
        'tags': ['api-design'],
        'archived': True,
    },
    {
        'title': 'Archived: Legacy Auth Flow Notes',
        'content': (
            'The old auth flow used session cookies with CSRF tokens. This was replaced '
            'with JWT-based auth via Clerk. The migration required updating all frontend '
            'API calls to include the Authorization header and removing the CSRF middleware.'
        ),
        'tags': ['security', 'python'],
        'archived': True,
    },
    # Deleted
    {
        'title': 'Deleted Draft: Unfinished Thoughts',
        'content': 'Started writing something but never finished...',
        'tags': [],
        'deleted': True,
    },
    {
        'title': 'Deleted: Outdated Setup Instructions',
        'content': (
            'These setup instructions were for the old monolith architecture. '
            'The project has since been restructured into separate backend and frontend '
            'services with Docker Compose for local development.'
        ),
        'tags': ['devops'],
        'deleted': True,
    },
]

# ---------------------------------------------------------------------------
# Prompt data
# ---------------------------------------------------------------------------

PROMPTS = [
    {
        'name': 'code-review',
        'title': 'Code Review Assistant',
        'description': 'Review code for bugs, style issues, and improvements.',
        'content': (
            'Review the following {{ language }} code for potential issues:\n\n'
            '```{{ language }}\n{{ code }}\n```\n\n'
            'Please check for:\n'
            '1. Bugs and logic errors\n'
            '2. Security vulnerabilities\n'
            '3. Performance issues\n'
            '4. Code style and readability\n'
            '5. Missing error handling\n\n'
            'Provide specific suggestions with code examples for each issue found.'
        ),
        'arguments': [
            {'name': 'code', 'description': 'The code to review', 'required': True},
            {'name': 'language', 'description': 'Programming language', 'required': True},
        ],
        'tags': ['python', 'testing'],
    },
    {
        'name': 'summarize-article',
        'title': 'Article Summarizer',
        'description': 'Summarize an article in a specified style.',
        'content': (
            'Summarize the following article in a {{ style }} style:\n\n'
            '{{ article_text }}\n\n'
            'Provide:\n'
            '- A one-sentence TL;DR\n'
            '- 3-5 key points\n'
            '- Any notable quotes or statistics'
        ),
        'arguments': [
            {'name': 'article_text', 'description': 'The article text to summarize', 'required': True},
            {'name': 'style', 'description': 'Summary style (e.g., technical, casual, executive)', 'required': False},
        ],
        'tags': ['tools'],
    },
    {
        'name': 'explain-concept',
        'title': 'Concept Explainer',
        'description': 'Explain a technical concept for a specific audience.',
        'content': (
            'Explain {{ concept }} to a {{ audience }} audience. '
            'Use analogies and examples where helpful.'
        ),
        'arguments': [
            {'name': 'concept', 'description': 'The concept to explain', 'required': True},
            {'name': 'audience', 'description': 'Target audience level (e.g., beginner, expert)', 'required': True},
        ],
        'tags': ['tutorial'],
    },
    {
        'name': 'write-tests',
        'title': 'Test Writer',
        'description': 'Generate test cases for the given code.',
        'content': (
            'Write comprehensive tests for the following {{ language }} code using {{ framework }}:\n\n'
            '```{{ language }}\n{{ code }}\n```\n\n'
            'Include:\n'
            '- Happy path tests\n'
            '- Edge cases (empty input, None/null, boundary values)\n'
            '- Error cases (invalid input, exceptions)\n'
            '- Integration tests if applicable\n\n'
            'Follow these conventions:\n'
            '- Use descriptive test names: `test__function_name__scenario`\n'
            '- One assertion per test where practical\n'
            '- Use fixtures for shared setup\n'
            '- Add docstrings explaining what each test verifies\n\n'
            'Example test structure:\n'
            '```{{ language }}\n'
            'def test__parse_url__returns_components_for_valid_url():\n'
            '    """Verify URL parsing extracts scheme, host, and path."""\n'
            '    result = parse_url("https://example.com/path")\n'
            '    assert result.scheme == "https"\n'
            '    assert result.host == "example.com"\n'
            '```'
        ),
        'arguments': [
            {'name': 'code', 'description': 'The code to write tests for', 'required': True},
            {'name': 'framework', 'description': 'Testing framework (e.g., pytest, jest, cargo test)', 'required': True},
            {'name': 'language', 'description': 'Programming language', 'required': True},
        ],
        'tags': ['testing', 'python'],
    },
    {
        'name': 'refactor-code',
        'title': 'Code Refactoring Assistant',
        'description': 'Suggest refactoring improvements for code.',
        'content': (
            'Refactor the following code with these goals: {{ goals }}\n\n'
            '```\n{{ code }}\n```\n\n'
            'Show the refactored version and explain each change.'
        ),
        'arguments': [
            {'name': 'code', 'description': 'The code to refactor', 'required': True},
            {'name': 'goals', 'description': 'Refactoring goals (e.g., readability, performance, DRY)', 'required': False},
        ],
        'tags': ['tools'],
    },
    {
        'name': 'api-endpoint-design',
        'title': 'API Endpoint Designer',
        'description': 'Design RESTful API endpoints for a resource.',
        'content': (
            'Design RESTful API endpoints for the `{{ resource_name }}` resource.\n\n'
            'Operations needed: {{ operations }}\n\n'
            'For each endpoint, specify:\n'
            '- HTTP method and path\n'
            '- Request body schema (if applicable)\n'
            '- Response schema with example\n'
            '- Status codes\n'
            '- Query parameters for filtering/pagination\n\n'
            'Follow REST best practices and use consistent naming.'
        ),
        'arguments': [
            {'name': 'resource_name', 'description': 'Name of the API resource', 'required': True},
            {'name': 'operations', 'description': 'CRUD operations needed (e.g., list, create, update, delete)', 'required': True},
        ],
        'tags': ['api-design', 'web-dev'],
    },
    {
        'name': 'sql-query-builder',
        'title': 'SQL Query Builder',
        'description': 'Build SQL queries from natural language descriptions.',
        'content': (
            'Write a SQL query for the `{{ table_name }}` table.\n\n'
            'Available columns: {{ columns }}\n\n'
            '{% if conditions %}Conditions: {{ conditions }}{% endif %}\n\n'
            'Provide the query with explanatory comments.'
        ),
        'arguments': [
            {'name': 'table_name', 'description': 'Name of the database table', 'required': True},
            {'name': 'columns', 'description': 'Available columns (comma-separated)', 'required': True},
            {'name': 'conditions', 'description': 'Query conditions in natural language', 'required': False},
        ],
        'tags': ['database'],
    },
    {
        'name': 'debug-error',
        'title': 'Error Debugger',
        'description': 'Help debug an error message with code context.',
        'content': (
            'I encountered this error:\n\n'
            '```\n{{ error_message }}\n```\n\n'
            '{% if code_context %}Here is the relevant code:\n\n'
            '```\n{{ code_context }}\n```\n{% endif %}\n\n'
            'Please:\n'
            '1. Explain what the error means\n'
            '2. Identify the likely cause\n'
            '3. Suggest a fix with code example'
        ),
        'arguments': [
            {'name': 'error_message', 'description': 'The error message or stack trace', 'required': True},
            {'name': 'code_context', 'description': 'Code around where the error occurred', 'required': False},
        ],
        'tags': ['tools', 'testing'],
    },
    {
        'name': 'git-commit-message',
        'title': 'Git Commit Message Writer',
        'description': 'Generate a conventional commit message from a diff.',
        'content': (
            'Write a git commit message for this diff:\n\n'
            '```diff\n{{ diff }}\n```\n\n'
            'Use conventional commit format: type(scope): description'
        ),
        'arguments': [
            {'name': 'diff', 'description': 'The git diff to describe', 'required': True},
        ],
        'tags': ['tools', 'reference'],
    },
    {
        'name': 'documentation-writer',
        'title': 'Documentation Writer',
        'description': 'Generate documentation for code.',
        'content': (
            'Write {{ doc_format }} documentation for the following code:\n\n'
            '```\n{{ code }}\n```\n\n'
            'Include:\n'
            '- Module/class/function overview\n'
            '- Parameter descriptions with types\n'
            '- Return value descriptions\n'
            '- Usage examples\n'
            '- Edge cases and important notes\n\n'
            'For API documentation, also include:\n'
            '- Request/response examples\n'
            '- Error responses\n'
            '- Authentication requirements\n\n'
            'For library documentation, also include:\n'
            '- Installation instructions\n'
            '- Quick start guide\n'
            '- Configuration options\n'
            '- Migration guide from previous versions'
        ),
        'arguments': [
            {'name': 'code', 'description': 'The code to document', 'required': True},
            {'name': 'doc_format', 'description': 'Documentation format (e.g., Google style, JSDoc, Sphinx)', 'required': True},
        ],
        'tags': ['reference'],
    },
    {
        'name': 'security-review',
        'title': 'Security Code Review',
        'description': 'Review code for security vulnerabilities.',
        'content': (
            'Perform a security review of the following {{ language }} code:\n\n'
            '```{{ language }}\n{{ code }}\n```\n\n'
            'Check for:\n'
            '- Injection vulnerabilities (SQL, command, XSS)\n'
            '- Authentication and authorization issues\n'
            '- Sensitive data exposure\n'
            '- Insecure cryptographic practices\n'
            '- Race conditions\n'
            '- Input validation gaps\n\n'
            'Rate each finding: Critical / High / Medium / Low'
        ),
        'arguments': [
            {'name': 'code', 'description': 'The code to review for security', 'required': True},
            {'name': 'language', 'description': 'Programming language', 'required': True},
        ],
        'tags': ['security', 'testing'],
    },
    {
        'name': 'performance-review',
        'title': 'Performance Analyzer',
        'description': 'Analyze code for performance issues.',
        'content': (
            'Analyze the following code for performance issues:\n\n'
            '```\n{{ code }}\n```\n\n'
            '{% if metrics %}Current metrics: {{ metrics }}{% endif %}\n\n'
            'Identify:\n'
            '- Time complexity issues\n'
            '- Memory usage concerns\n'
            '- I/O bottlenecks\n'
            '- Caching opportunities\n\n'
            'Suggest optimizations with expected impact.'
        ),
        'arguments': [
            {'name': 'code', 'description': 'The code to analyze', 'required': True},
            {'name': 'metrics', 'description': 'Current performance metrics if available', 'required': False},
        ],
        'tags': ['performance'],
    },
    {
        'name': 'translate-code',
        'title': 'Code Translator',
        'description': 'Translate code between programming languages.',
        'content': (
            'Translate the following {{ source_lang }} code to {{ target_lang }}:\n\n'
            '```{{ source_lang }}\n{{ code }}\n```\n\n'
            'Preserve the logic and use idiomatic {{ target_lang }} patterns.'
        ),
        'arguments': [
            {'name': 'code', 'description': 'The code to translate', 'required': True},
            {'name': 'source_lang', 'description': 'Source programming language', 'required': True},
            {'name': 'target_lang', 'description': 'Target programming language', 'required': True},
        ],
        'tags': ['tools'],
    },
    {
        'name': 'meeting-agenda',
        'title': 'Meeting Agenda Generator',
        'description': 'Create a structured meeting agenda.',
        'content': (
            'Create a meeting agenda for: {{ topic }}\n\n'
            'Attendees: {{ attendees }}\n'
            'Duration: {{ duration }}\n\n'
            'Include time allocations for each item.'
        ),
        'arguments': [
            {'name': 'topic', 'description': 'Meeting topic', 'required': True},
            {'name': 'attendees', 'description': 'List of attendees', 'required': True},
            {'name': 'duration', 'description': 'Meeting duration (e.g., 30min, 1hr)', 'required': True},
        ],
        'tags': ['tools'],
    },
    {
        'name': 'changelog-entry',
        'title': 'Changelog Entry Writer',
        'description': 'Generate a changelog entry from a list of changes.',
        'content': (
            'Write a changelog entry for version {{ version }}:\n\n'
            'Changes:\n{{ changes }}\n\n'
            'Use Keep a Changelog format with Added/Changed/Fixed/Removed sections.'
        ),
        'arguments': [
            {'name': 'changes', 'description': 'List of changes to include', 'required': True},
            {'name': 'version', 'description': 'Version number (e.g., 1.2.0)', 'required': True},
        ],
        'tags': ['reference', 'open-source'],
    },
    {
        'name': 'dockerfile-generator',
        'title': 'Dockerfile Generator',
        'description': 'Generate a production-ready Dockerfile.',
        'content': (
            'Generate a production-ready Dockerfile for a {{ app_type }} application.\n\n'
            'Base image: {{ base_image }}\n\n'
            'Requirements:\n'
            '- Multi-stage build for smaller final image\n'
            '- Non-root user for security\n'
            '- Proper layer caching for dependencies\n'
            '- Health check endpoint\n'
            '- Signal handling for graceful shutdown\n\n'
            'Include comments explaining each section.'
        ),
        'arguments': [
            {'name': 'app_type', 'description': 'Application type (e.g., Python FastAPI, Node.js Express)', 'required': True},
            {'name': 'base_image', 'description': 'Base Docker image (e.g., python:3.12-slim)', 'required': False},
        ],
        'tags': ['devops', 'tools'],
    },
    {
        'name': 'regex-builder',
        'title': 'Regex Builder',
        'description': 'Build a regex pattern from a description.',
        'content': (
            'Build a regex pattern that: {{ description }}\n\n'
            '{% if test_cases %}Test cases:\n{{ test_cases }}{% endif %}\n\n'
            'Provide the pattern with an explanation of each part.'
        ),
        'arguments': [
            {'name': 'description', 'description': 'What the regex should match', 'required': True},
            {'name': 'test_cases', 'description': 'Example strings to match/reject', 'required': False},
        ],
        'tags': ['tools', 'reference'],
    },
    {
        'name': 'data-model-design',
        'title': 'Data Model Designer',
        'description': 'Design a database schema for an entity.',
        'content': (
            '# Data Model Design: {{ entity_name }}\n\n'
            '## Fields\n{{ fields }}\n\n'
            '## Relationships\n{{ relationships }}\n\n'
            'Please provide:\n\n'
            '### 1. SQL Schema\n'
            'CREATE TABLE statements with appropriate data types, constraints, and indexes.\n\n'
            '### 2. SQLAlchemy Model\n'
            'Python ORM model using SQLAlchemy 2.0 Mapped syntax.\n\n'
            '### 3. Pydantic Schemas\n'
            'Request/response schemas for CRUD operations.\n\n'
            '### 4. Migration\n'
            'Alembic migration script for the new table.\n\n'
            '### 5. Considerations\n'
            '- Indexing strategy for common query patterns\n'
            '- Soft delete vs hard delete\n'
            '- Audit trail requirements\n'
            '- Data validation rules'
        ),
        'arguments': [
            {'name': 'entity_name', 'description': 'Name of the entity to model', 'required': True},
            {'name': 'fields', 'description': 'List of fields with types and constraints', 'required': True},
            {'name': 'relationships', 'description': 'Related entities and relationship types', 'required': True},
        ],
        'tags': ['database', 'api-design'],
    },
    {
        'name': 'error-handling',
        'title': 'Error Handling Designer',
        'description': 'Design error handling for code.',
        'content': (
            'Design error handling for the following code:\n\n'
            '```\n{{ code }}\n```\n\n'
            'Error types to handle: {{ error_types }}\n\n'
            'Provide:\n'
            '- Custom exception classes\n'
            '- Try/except blocks with specific error types\n'
            '- User-friendly error messages\n'
            '- Logging at appropriate levels\n'
            '- Recovery strategies where applicable'
        ),
        'arguments': [
            {'name': 'code', 'description': 'The code to add error handling to', 'required': True},
            {'name': 'error_types', 'description': 'Types of errors to handle (e.g., network, validation, database)', 'required': True},
        ],
        'tags': ['python', 'security'],
    },
    {
        'name': 'rest-api-docs',
        'title': 'REST API Documentation',
        'description': 'Generate API documentation for an endpoint.',
        'content': (
            '## {{ method }} {{ endpoint }}\n\n'
            'Document this API endpoint with:\n\n'
            '### Parameters\n'
            '{{ params }}\n\n'
            '### Request Example\n'
            'Show a curl command and request body example.\n\n'
            '### Response Example\n'
            'Show success and error response bodies.\n\n'
            '### Status Codes\n'
            'List all possible status codes and their meanings.'
        ),
        'arguments': [
            {'name': 'endpoint', 'description': 'API endpoint path (e.g., /users/{id})', 'required': True},
            {'name': 'method', 'description': 'HTTP method (GET, POST, PUT, DELETE)', 'required': True},
            {'name': 'params', 'description': 'Endpoint parameters description', 'required': True},
        ],
        'tags': ['api-design', 'reference'],
    },
    {
        'name': 'simple-greeting',
        'title': 'Simple Greeting',
        'description': 'A minimal greeting prompt.',
        'content': 'Hello, {{ name }}! How can I help you today?',
        'arguments': [
            {'name': 'name', 'description': 'Person to greet', 'required': True},
        ],
        'tags': [],
    },
    {
        'name': 'no-args-prompt',
        'title': 'Quick Help',
        'description': 'A prompt with no arguments.',
        'content': 'What would you like help with? I can assist with coding, writing, analysis, and more.',
        'arguments': [],
        'tags': ['tools'],
    },
    # Archived
    {
        'name': 'archived-legacy-review',
        'title': 'Legacy Code Review (Archived)',
        'description': 'Old code review template, replaced by code-review.',
        'content': (
            'Review this {{ language }} code:\n\n'
            '```\n{{ code }}\n```\n\n'
            'List any issues found.'
        ),
        'arguments': [
            {'name': 'code', 'description': 'Code to review', 'required': True},
            {'name': 'language', 'description': 'Programming language', 'required': False},
        ],
        'tags': ['python'],
        'archived': True,
    },
    {
        'name': 'archived-old-template',
        'title': 'Old Template (Archived)',
        'description': 'Deprecated template, kept for reference.',
        'content': 'Process the following text:\n\n{{ text }}',
        'arguments': [
            {'name': 'text', 'description': 'Text to process', 'required': True},
        ],
        'tags': ['tools'],
        'archived': True,
    },
    # Deleted
    {
        'name': 'deleted-broken-prompt',
        'title': 'Broken Prompt (Deleted)',
        'description': 'This prompt had template errors.',
        'content': 'Review: {{ code }}',
        'arguments': [
            {'name': 'code', 'description': 'Code input', 'required': True},
        ],
        'tags': [],
        'deleted': True,
    },
]


async def get_or_create_dev_user(session: AsyncSession) -> User:
    """Get or create the dev mode user."""
    result = await session.execute(
        select(User).where(User.external_auth_id == DEV_EXTERNAL_AUTH_ID),
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            external_auth_id=DEV_EXTERNAL_AUTH_ID,
            email='dev@localhost',
            tier='free',
        )
        session.add(user)
        await session.flush()
        print(f'  Created dev user: {user.id}')
    else:
        print(f'  Found dev user: {user.id}')
    return user


async def create_tags(session: AsyncSession, user: User) -> dict[str, Tag]:
    """Create tags and return a name->Tag mapping."""
    tag_map: dict[str, Tag] = {}
    for name in TAG_NAMES:
        tag = Tag(user_id=user.id, name=name)
        session.add(tag)
        tag_map[name] = tag
    await session.flush()
    print(f'  Created {len(tag_map)} tags')
    return tag_map


def validate_status(data: dict, context: str) -> None:
    """Raise if both archived and deleted are set."""
    if data.get('archived') and data.get('deleted'):
        raise ValueError(f'{context} has both archived and deleted set')


def resolve_tags(tag_names: list[str], tag_map: dict[str, Tag], *, context: str) -> list[Tag]:
    """Resolve tag names to Tag objects. Raises on unknown names."""
    unknown = [name for name in tag_names if name not in tag_map]
    if unknown:
        raise ValueError(f'Unknown tag(s) {unknown} in {context}')
    return [tag_map[name] for name in tag_names]


async def create_bookmarks(
    session: AsyncSession, user: User, tag_map: dict[str, Tag],
) -> None:
    """Create seed bookmarks."""
    now = datetime.now(UTC)
    counts = {'active': 0, 'archived': 0, 'deleted': 0}
    for data in BOOKMARKS:
        bookmark = Bookmark(
            user_id=user.id,
            url=data['url'],
            title=data.get('title'),
            description=data.get('description'),
            content=data.get('content'),
        )
        ctx = f'bookmark "{data["title"]}"'
        bookmark.tag_objects = resolve_tags(data.get('tags', []), tag_map, context=ctx)
        validate_status(data, ctx)
        if data.get('archived'):
            bookmark.archived_at = now
            counts['archived'] += 1
        elif data.get('deleted'):
            bookmark.deleted_at = now
            counts['deleted'] += 1
        else:
            counts['active'] += 1
        session.add(bookmark)
    await session.flush()
    print(
        f'  Created {len(BOOKMARKS)} bookmarks '
        f'({counts["active"]} active, {counts["archived"]} archived, {counts["deleted"]} deleted)',
    )


async def create_notes(
    session: AsyncSession, user: User, tag_map: dict[str, Tag],
) -> None:
    """Create seed notes."""
    now = datetime.now(UTC)
    counts = {'active': 0, 'archived': 0, 'deleted': 0}
    for data in NOTES:
        note = Note(
            user_id=user.id,
            title=data['title'],
            content=data.get('content'),
        )
        ctx = f'note "{data["title"]}"'
        note.tag_objects = resolve_tags(data.get('tags', []), tag_map, context=ctx)
        validate_status(data, ctx)
        if data.get('archived'):
            note.archived_at = now
            counts['archived'] += 1
        elif data.get('deleted'):
            note.deleted_at = now
            counts['deleted'] += 1
        else:
            counts['active'] += 1
        session.add(note)
    await session.flush()
    print(
        f'  Created {len(NOTES)} notes '
        f'({counts["active"]} active, {counts["archived"]} archived, {counts["deleted"]} deleted)',
    )


async def create_prompts(
    session: AsyncSession, user: User, tag_map: dict[str, Tag],
) -> None:
    """Create seed prompts."""
    now = datetime.now(UTC)
    counts = {'active': 0, 'archived': 0, 'deleted': 0}
    for data in PROMPTS:
        prompt = Prompt(
            user_id=user.id,
            name=data['name'],
            title=data.get('title'),
            description=data.get('description'),
            content=data.get('content'),
            arguments=data.get('arguments', []),
        )
        ctx = f'prompt "{data["name"]}"'
        prompt.tag_objects = resolve_tags(data.get('tags', []), tag_map, context=ctx)
        validate_status(data, ctx)
        if data.get('archived'):
            prompt.archived_at = now
            counts['archived'] += 1
        elif data.get('deleted'):
            prompt.deleted_at = now
            counts['deleted'] += 1
        else:
            counts['active'] += 1
        session.add(prompt)
    await session.flush()
    print(
        f'  Created {len(PROMPTS)} prompts '
        f'({counts["active"]} active, {counts["archived"]} archived, {counts["deleted"]} deleted)',
    )


async def clear_data(session: AsyncSession) -> None:
    """Clear all data for the dev user."""
    result = await session.execute(
        select(User).where(User.external_auth_id == DEV_EXTERNAL_AUTH_ID),
    )
    user = result.scalar_one_or_none()
    if user is None:
        print('No dev user found, nothing to clear.')
        return

    user_id = user.id
    print(f'Clearing data for dev user {user_id}...')

    # Count existing records before deletion
    bm_count = (await session.execute(
        select(func.count()).select_from(Bookmark).where(Bookmark.user_id == user_id),
    )).scalar()
    note_count = (await session.execute(
        select(func.count()).select_from(Note).where(Note.user_id == user_id),
    )).scalar()
    prompt_count = (await session.execute(
        select(func.count()).select_from(Prompt).where(Prompt.user_id == user_id),
    )).scalar()
    tag_count = (await session.execute(
        select(func.count()).select_from(Tag).where(Tag.user_id == user_id),
    )).scalar()

    # Delete content filters first (filter_group_tags has RESTRICT on tag_id).
    # CASCADE handles filter_groups and filter_group_tags junction rows.
    await session.execute(delete(ContentFilter).where(ContentFilter.user_id == user_id))
    # Delete content history (references entities by UUID, would be orphaned).
    await session.execute(delete(ContentHistory).where(ContentHistory.user_id == user_id))
    # Delete entities (CASCADE handles junction tables).
    await session.execute(delete(Bookmark).where(Bookmark.user_id == user_id))
    await session.execute(delete(Note).where(Note.user_id == user_id))
    await session.execute(delete(Prompt).where(Prompt.user_id == user_id))
    await session.execute(delete(Tag).where(Tag.user_id == user_id))
    await session.flush()

    print(f'  Deleted {bm_count} bookmarks, {note_count} notes, {prompt_count} prompts, {tag_count} tags')
    print('Clear complete.')


async def populate(force: bool = False) -> None:
    """Populate the database with seed data."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        try:
            user = await get_or_create_dev_user(session)

            # Check if seed data already exists (tags are created first, so
            # they detect both complete and partial previous runs).
            tag_count = (await session.execute(
                select(func.count()).select_from(Tag).where(Tag.user_id == user.id),
            )).scalar()

            if tag_count and tag_count > 0:
                if force:
                    print('Existing data found, clearing first (--force)...')
                    await clear_data(session)
                    await session.flush()
                else:
                    print(
                        f'Data already exists ({tag_count} tags). '
                        f'Use --force to clear and re-seed.',
                    )
                    return

            print('Populating seed data...')
            tag_map = await create_tags(session, user)
            await create_bookmarks(session, user, tag_map)
            await create_notes(session, user, tag_map)
            await create_prompts(session, user, tag_map)
            await session.commit()
            print('Seed data created successfully.')
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


async def clear() -> None:
    """Clear all dev user data."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        try:
            await clear_data(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


def main() -> None:
    """CLI entry point."""
    settings = get_settings()
    if not settings.dev_mode:
        print(
            "ERROR: Seed script requires VITE_DEV_MODE=true.\n"
            "This script modifies data directly and must only run against a local dev database.",
        )
        raise SystemExit(1)

    parser = argparse.ArgumentParser(description='Seed the dev database with test data.')
    subparsers = parser.add_subparsers(dest='command', required=True)

    populate_parser = subparsers.add_parser('populate', help='Populate database with test data')
    populate_parser.add_argument(
        '--force', action='store_true',
        help='Clear existing data before populating',
    )

    subparsers.add_parser('clear', help='Remove all dev user data')

    args = parser.parse_args()

    if args.command == 'populate':
        asyncio.run(populate(force=args.force))
    elif args.command == 'clear':
        asyncio.run(clear())


if __name__ == '__main__':
    main()
