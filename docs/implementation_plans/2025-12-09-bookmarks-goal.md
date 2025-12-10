There don't seem to be any good bookmark management solutions. I'm currently using Instapaper. It's alright. But I want something better integrated with my workflow. I don't care about offline reading, mainly just want a better way to organize, tag, and retrieve bookmarks. Also, I want to integrate it with AI tools for better search and summarization.

- Implement in python (current project contains project template).
    - Fast API backend.
    - React frontend.
    - Postgres database.
    - Alembic for migrations.
    - Auth0 for authentication.
    - Deploying to Render.com, Railway.app, fly.io, or similar (I need help deciding which is better for this use case).
- Core features:
    - Simple but modern and clean UI
    - Add bookmarks via easy interface (no browser extension initially, just a web form).
        - Copy-paste URL, auto-fetch title/content/description.
        - Allow optional tags, descriptions, notes
        - Option to automatically generate tags/etc using AI
            - LLM will have access other other tags and can consistently generate tags based on existing tags
    - View bookmarks in list
        - Sort by date added, title, etc
        - Filter by tags
    - Search
        - bookmarks by title, tags, content
        - Semantic search using AI embeddings
            - Vector DB?
        - "AI search" that e.g.
            - generates multiple search queries from a single user query (i.e. rephrases user question/query in way that is more likely to semantically match bookmarks)
            - returns "structured output" list of bookmarks sorted by AI (i.e. give LLM the list of search results based on semantic search, search terms terms, etc, and return structured list of best matches)
    - Edit/delete bookmarks
    - View that shows "last clicked" bookmarks (i.e. recently accessed)
        - (shortcut that allows user to "click" a bookmark without marking it as accessed, for cases where user just wants to view bookmark but not have it show up in "recently accessed" list (e.g. wtf is this link?))
        - "Age" bookmarks by e.g. dimming them in the list if they haven't been accessed in a while
        - Archive bookmarks (move to archive, not deleted, but not shown in main list; do not show up in search, unless user specifically searches in archive)
    - Abilit to create custom "views" for bookmarks
        - e.g. "work-related bookmarks", "personal bookmarks", etc
        - saved filters/sorts?? No, these are predefined views that user can create and sort in a specific way
        - Actually, this custom view would be for bookmarks, notes, and todo items (see below)
        - It could even be a single API endpoint that returns a combined list of bookmarks, notes, and todo items for that topic/view 
    - Create one or more notes associated with a bookmark
        - Notes are simple markdown text
        - View/edit notes in markdown editor
            - Optionally use AI to generate summaries of bookmark content, or extract key points, etc; this could be editable by the user since it's just stored in the note as markdown
    - Suggest related bookmarks when adding a bookmark
        - Based on tags, content similarity (embeddings), etc

- REST API endpoints that expose read/write operations for all core features that can be used by, not only the frontend, but also by other tools (e.g. CLI tool, MCP, browser extension in the future, etc)
- MCP integration
    - Wrap REST API endpoints in MCP commands
    - Allow user to add/view/search bookmarks from MCP

- Note taking features (optional/future):
    - Allow user to take notes on bookmarks
    - AI-generated summaries of bookmarks
    - Link related bookmarks together (e.g. "this bookmark is related to that bookmark")
    - Link a note to one or more bookmarks
    - Allow user to create "collections" of bookmarks (i.e. group related bookmarks together)
    - Allow user to snapshot a note at a specific time (i.e. versioned notes)
    - Notes are simply markdown text with view to switch between rendered view and markdown/edit view
        - If AI edits a note, automatically snapshot the previous version before applying changes


- LLM instructions 