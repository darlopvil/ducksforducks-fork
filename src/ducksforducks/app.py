from flask import (
    Flask,
    request,
    send_from_directory,
    render_template,
    Response,
)
import os
from bs4 import BeautifulSoup
import logging
from urllib.parse import urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from typing import Text

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

# Remove the default Flask logger
app.logger.removeHandler(app.logger.handlers[0])

GFG_BASE_URL = "https://www.geeksforgeeks.org/"
ALLOWED_PROXY_HOSTS = {"media.geeksforgeeks.org", "www.geeksforgeeks.org"}


@app.route("/static/<path:path>")
def static_files(path: str) -> Response:
    """Serves static files.

    Args:
        path (str): The path to the static file.

    Returns:
        Response: The static file.
    """
    return send_from_directory("static", path)


@app.route("/")
def index() -> Text:
    """Renders the index page.

    Returns:
        Text: The rendered index page.
    """
    host = request.host
    return render_template("index.html", host=host)


@app.route("/proxy")
def proxy() -> Response:
    """A simple proxy for images.

    Returns:
        Response: The content of the proxied URL.
    """
    url = normalize_url(request.args.get("url"))

    if not url or not is_allowed_proxy_url(url):
        logger.error(f"Invalid URL for proxying: {url}")
        return Response("Invalid URL", status=400)

    logger.debug(f"Proxying {url}")

    with urlopen(build_request(url)) as response:
        data = response.read()
        content_type = response.headers.get_content_type()

    return Response(data, content_type=content_type)


@app.route("/<path:path>")
def article_page(path):
    """Renders the article page.

    Args:
        path (str): The path to the article.

    Returns:
        Text: The rendered article page.
    """
    with urlopen(build_request(urljoin(GFG_BASE_URL, path))) as response:
        if response.getcode() == 200:
            soup = BeautifulSoup(response.read(), "html.parser")
            try:
                content = get_content(soup)
                title = get_title(soup)
            except LookupError:
                logger.exception("Unable to extract article content for %s", path)
                return render_template("error.html", code=502), 502
            return render_template("article.html", content=content, title=title)
        else:
            return (
                render_template("error.html", code=response.getcode()),
                response.getcode(),
            )


def get_content(soup: BeautifulSoup) -> BeautifulSoup:
    """Extracts the article content from the soup.

    Args:
        soup (BeautifulSoup): The soup of the article page.

    Returns:
        BeautifulSoup: The article content.
    """
    article_content = (
        soup.find("div", class_="article--viewer_content")
        or soup.find("div", class_="a-wrapper")
        or soup.find("article")
    )

    if article_content is None:
        raise LookupError("Unable to find article content")

    for img in article_content.find_all("img"):
        image_url = None

        for attribute in ("src", "data-src", "data-lazy-src"):
            image_url = normalize_url(img.get(attribute))

            if image_url:
                break

        if image_url and is_allowed_proxy_url(image_url):
            img["src"] = build_proxy_url(image_url)

            for attribute in (
                "srcset",
                "data-src",
                "data-srcset",
                "data-lazy-src",
                "data-lazy-srcset",
            ):
                img.attrs.pop(attribute, None)

    for element in article_content.find_all(["script", "style"]):
        element.decompose()

    for ad in article_content.find_all():
        if ad.get("id") and ad["id"].startswith("GFG_AD_"):
            ad.decompose()

    for link in article_content.find_all("a"):
        href = normalize_href(link.get("href"))

        if href and is_internal_article_url(href):
            if not is_user_profile_url(href):
                link["href"] = build_internal_path(href)

            else:
                classes = link.get("class", [])
                classes.append("gfg-link")
                link["class"] = classes

        else:
            classes = link.get("class", [])
            classes.append("external-link")
            link["class"] = classes

    return article_content


def get_title(soup: BeautifulSoup) -> str:
    """Extracts the article title from the soup.
    
    Args:
        soup (BeautifulSoup): The soup of the article page.

    Returns:
        str: The article title.
    """
    title = soup.find("h1")

    if title and title.get_text(strip=True):
        return title.get_text(strip=True)

    open_graph_title = soup.find("meta", attrs={"property": "og:title"})

    if open_graph_title and open_graph_title.get("content"):
        return open_graph_title["content"]

    raise LookupError("Unable to find article title")


def build_request(url: str) -> Request:
    """Builds a request with a browser-like user agent.
    
    Args:
        url (str): The URL to request.

    Returns:
        Request: The built request.
    """
    return Request(url, headers={"User-Agent": "Ducks for Ducks/0.1"})


def normalize_url(url: str | None) -> str | None:
    """Normalizes protocol-relative and relative GeeksforGeeks URLs.
    
    Args:
        url (str | None): The URL to normalize.

    Returns:
        str | None: The normalized URL, or None if the input was None.
    """
    if not url:
        return None

    if url.startswith("//"):
        return f"https:{url}"

    return urljoin(GFG_BASE_URL, url)


def normalize_href(href: str | None) -> str | None:
    """Normalizes article links while keeping non-HTTP anchors intact.
    
    Args:
        href (str | None): The href to normalize.
    """
    if not href or href.startswith(("#", "mailto:", "javascript:")):
        # HMM: Not sure if we should keep "javascript:" links, but let's not mess with them for now...
        return href

    return normalize_url(href)


def is_allowed_proxy_url(url: str) -> bool:
    """Checks whether the proxy URL points to an allowed GeeksforGeeks host.
    
    Args:
        url (str): The URL to check.

    Returns:
        bool: True if the URL is allowed for proxying, False otherwise.
    """
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_PROXY_HOSTS


def is_internal_article_url(url: str) -> bool:
    """Checks whether a link points to GeeksforGeeks content we can proxy.
    
    Args:
        url (str): The URL to check.

    Returns:
        bool: True if the URL is an "internal" article URL, False otherwise.
    """
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == "www.geeksforgeeks.org"


def is_user_profile_url(url: str) -> bool:
    """Checks whether a URL points to a user profile.
    
    Args:
        url (str): The URL to check.

    Returns:
        bool: True if the URL points to a user profile, False otherwise.
    """
    return urlparse(url).path.startswith("/user/")


def build_internal_path(url: str) -> str:
    """Builds a local application path from a GeeksforGeeks URL.
    
    Args:
        url (str): The URL to convert.

    Returns:
        str: The local path corresponding to the given URL.
    """
    parsed = urlparse(url)
    return urlunparse(("", "", parsed.path, "", parsed.query, parsed.fragment))


def build_proxy_url(url: str) -> str:
    """Builds a local proxy URL for a GeeksforGeeks asset.
    
    Args:
        url (str): The URL of the asset to proxy.

    Returns:
        str: The local proxy URL for the given asset.
    """
    return f"/proxy?{urlencode({'url': url})}"


def main():
    """Runs the app."""
    port = int(os.getenv("PORT", 8113))
    debug = bool(os.getenv("DEBUG", False))
    app.run(port=port, debug=debug)


if __name__ == "__main__":
    main()
