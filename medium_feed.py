import os, re, json, requests
import sys, time as _time
from datetime import datetime

MAX_ARTICLES = 1000

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

def app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s

def parse_list_url(url):
    m = re.search(r'medium\.com/@[\w-]+/list/([\w-]+)-([a-f0-9]{12})', url)
    if m:
        return m.group(1), m.group(2)
    return None, None

def fetch_list(session, list_url, medium_user=""):
    slug, list_id = parse_list_url(list_url)
    if not list_id:
        print("Invalid list URL")
        return []

    print(f"Fetching list: {slug} ({list_id})")

    LIST_GQL = """
    query CatalogItems($catalogId: ID!, $pagingOptions: CatalogPagingOptionsInput!) {
        catalogById(catalogId: $catalogId) {
            ... on Catalog {
                itemsConnection(pagingOptions: $pagingOptions) {
                    items { catalogItemId entity { ... on Post { id title uniqueSlug } } }
                    paging { count nextPageCursor { id } }
                }
            }
        }
    }
    """

    all_articles = {}
    seen_post_ids = set()
    page = 0

    while True:
        paging = {"cursor": None if page == 0 else {"id": f"offset:{page * 20}"}, "limit": 20}
        gql = {
            "operationName": "CatalogItems",
            "variables": {"catalogId": list_id, "pagingOptions": paging},
            "query": LIST_GQL,
        }

        try:
            r = session.post("https://medium.com/_/graphql", json=gql, timeout=15)
        except:
            break

        if r.status_code != 200:
            print(f"  Page {page}: HTTP {r.status_code}")
            break

        result = r.json()
        if "errors" in result:
            print(f"  Page {page}: {result['errors'][0]['message'][:100]}")
            break

        conn = result.get("data", {}).get("catalogById", {}).get("itemsConnection", {})
        items = conn.get("items", [])
        paging_result = conn.get("paging", {})
        total = paging_result.get("count", 0)
        next_cursor = paging_result.get("nextPageCursor", {})

        new_count = 0
        for item in items:
            entity = item.get("entity") or {}
            post_id = entity.get("id", "")
            slug_val = entity.get("uniqueSlug", "")
            if slug_val and post_id not in seen_post_ids:
                seen_post_ids.add(post_id)
                link = f"https://medium.com/@{medium_user}/{slug_val}"
                all_articles[link] = {
                    "title": entity.get("title", ""),
                    "link": link,
                    "tags": [],
                }
                new_count += 1

        print(f"  Page {page}: {len(items)} items, {new_count} new (total: {len(all_articles)}/{total})")

        if not next_cursor or not next_cursor.get("id"):
            break

        page += 1
        _time.sleep(0.3)

        if page > 20:
            break

    return list(all_articles.values())

def fetch_articles(session, list_url, medium_user=""):
    articles = fetch_list(session, list_url, medium_user=medium_user)
    sorted_articles = sorted(articles, key=lambda a: a.get("title", ""))
    return sorted_articles[:MAX_ARTICLES]

def save_md(articles, list_name="", medium_user="", output=None):
    title = f"Stories by @{medium_user}"
    if list_name:
        title += f" - List: {list_name}"

    lines = [
        f"# {title}",
        f"",
        f"Fetched on: {datetime.now().strftime('%Y-%m-%d %H:%M')} ({len(articles)} articles)",
        f"",
        f"---",
    ]
    for i, a in enumerate(articles, 1):
        lines.append(f"")
        lines.append(f"## {i}. {a['title']}")
        lines.append(f"")
        lines.append(f"{a['link']}")

    output = "\n".join(lines) + "\n"
    filename = os.path.join(app_dir(), "medium_articles.md")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(output)
    return filename

def discover_all_lists(session, medium_user=""):
    """Fetch all user catalogs via GraphQL."""
    CATALOG_GQL = """
    query UserCatalogs($username: ID!, $type: CatalogType!, $pagingOptions: CatalogPagingOptionsInput!) {
        user(username: $username) {
            ... on User {
                viewerEdge {
                    catalogsConnection(type: $type, pagingOptions: $pagingOptions) {
                        catalogs { id name }
                        paging { count nextPageCursor { id } }
                    }
                }
            }
        }
    }
    """
    catalogs = {}
    cursor = None
    limit = 100
    while True:
        paging = {"limit": limit}
        if cursor:
            paging["cursor"] = {"id": cursor}
        gql = {
            "operationName": "UserCatalogs",
            "variables": {"username": medium_user, "type": "LISTS", "pagingOptions": paging},
            "query": CATALOG_GQL,
        }
        try:
            r = session.post("https://medium.com/_/graphql", json=gql, timeout=15)
        except:
            break
        if r.status_code != 200:
            break
        result = r.json()
        if "errors" in result:
            break
        conn = result.get("data", {}).get("user", {}).get("viewerEdge", {}).get("catalogsConnection", {})
        items = conn.get("catalogs", [])
        for c in items:
            cid = c.get("id", "")
            cname = c.get("name", "").strip().lower().replace(" ", "-")
            if cid and cname:
                catalogs[cname] = f"https://medium.com/@{medium_user}/list/{cname}-{cid}"
        next_page = conn.get("paging", {}).get("nextPageCursor")
        if next_page and next_page.get("id"):
            cursor = next_page["id"]
        else:
            break
        if len(catalogs) >= 200:
            break

    return catalogs

def resolve_list_url(session, arg, medium_user=""):
    all_lists = discover_all_lists(session, medium_user=medium_user)
    if not arg:
        print(f"Avaliable lists for @{medium_user}:")
        for name in sorted(all_lists.keys()):
            print(f"  {name}")
        print(f"\nUsage: py medium_feed.py --user {medium_user} \"list name\"")
        sys.exit(0)
    if re.match(r'https?://', arg):
        slug, _ = parse_list_url(arg)
        return arg, slug or arg
    if arg in all_lists:
        return all_lists[arg], arg
    key = arg.strip().lower().replace(" ", "-")
    for name, url in all_lists.items():
        if name.lower() == key:
            return url, name
    print(f"Unknown list '{arg}'.")
    print(f"Available: {', '.join(sorted(all_lists.keys()))}")
    print(f"Or use --list <full_url> for any Medium list URL.")
    sys.exit(1)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch articles from a Medium reading list")
    parser.add_argument('--user', required=True, help='Medium username (from URL: medium.com/@USERNAME)')
    parser.add_argument('--list', nargs='*', default=[], help='List name(s) or URL(s). If omitted, shows available lists.')
    args = parser.parse_args()

    session = make_session()
    user = args.user

    if not args.list:
        all_lists = discover_all_lists(session, medium_user=user)
        print(f"Avaliable lists for @{user}:")
        for name in sorted(all_lists.keys()):
            print(f"  {name}")
        sys.exit(0)

    for list_arg in args.list:
        list_url, list_name = resolve_list_url(session, list_arg, medium_user=user)
        print(f"\nUser: @{user}")
        print(f"Fetching list: {list_name}")

        articles = fetch_articles(session, list_url=list_url, medium_user=user)
        print(f"\n{'='*40}")
        print(f"Total: {len(articles)} articles")
        for i, a in enumerate(articles, 1):
            print(f"{i:>3}. {a['title'][:70]}")

        saved = save_md(articles, list_name=list_name, medium_user=user)
        print(f"Saved: {os.path.abspath(saved)}")
