# Medium Feed Fetcher

Fetch articles from any Medium reading list via Medium's public GraphQL API — no API key or authentication required.

## Requirements

- Python 3.7+
- `requests` (`pip install requests`)

## Usage

```bash
# Discover your available lists
py medium_feed.py --user YOUR_USERNAME

# Fetch articles from a list by name
py medium_feed.py --user YOUR_USERNAME "list name"

# Fetch from a specific list URL
py medium_feed.py --user YOUR_USERNAME --list https://medium.com/@USERNAME/list/name-abc123
```

## Output

Creates `medium_articles.md` with all article titles and links.

## How It Works

1. **Discovery** — Queries `user` -> `viewerEdge` -> `catalogsConnection` via GraphQL to find all lists
2. **Fetch** — Paginates through `catalogById` -> `itemsConnection` (cursor-based, 300ms delay between pages)
3. **Export** — Saves as clean markdown

## Limitation

List discovery only works for your **own** lists (Medium returns null for other users). Use a full list URL for lists created by others.
