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
from urllib.error import HTTPError, URLError
import base64
import zlib
import json

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

# Remove the default Flask logger
if app.logger.handlers:
    app.logger.removeHandler(app.logger.handlers[0])

GFG_BASE_URL = "https://www.geeksforgeeks.org/"
ALLOWED_PROXY_HOSTS = {"media.geeksforgeeks.org", "www.geeksforgeeks.org"}
# Extensiones que nunca pueden ser un artículo de GFG.
# Evita salir a la red por peticiones automáticas del navegador o de escáneres.
NON_ARTICLE_SUFFIXES = (
    ".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".css", ".js", ".map", ".json", ".xml", ".txt", ".php",
    ".env", ".yml", ".yaml", ".sql", ".bak", ".zip",
)
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
MAX_PROXY_BYTES = int(os.getenv("MAX_PROXY_BYTES", str(10 * 1024 * 1024)))

# Identificadores de lenguaje en tio.run, por data-code-lang de GFG.
TIO_LANGUAGES = {
    "python": "python3",
    "python3": "python3",
    "c": "c-gcc",
    "cpp": "cpp-gcc",
    "java": "java-openjdk",
    "javascript": "javascript-node",
    "php": "php",
    "csharp": "cs-core",
}

# Nombres legibles por clave de lenguaje de GFG.
LANGUAGE_NAMES = {
    "c": "C",
    "cpp": "C++",
    "java": "Java",
    "python3": "Python",
    "python": "Python",
    "csharp": "C#",
    "javascript": "JavaScript",
    "php": "PHP",
}


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

    try:
        with urlopen(build_request(url), timeout=REQUEST_TIMEOUT) as response:
            declared_length = response.headers.get("Content-Length")

            if declared_length and int(declared_length) > MAX_PROXY_BYTES:
                logger.warning("Refusing to proxy %s: too large", url)
                return Response("Resource too large", status=502)

            # Se lee un byte de más para detectar respuestas sin Content-Length
            # que superen el límite.
            data = response.read(MAX_PROXY_BYTES + 1)
            content_type = response.headers.get_content_type()
    except HTTPError as e:
        logger.warning("GeeksforGeeks returned %s while proxying %s", e.code, url)
        return Response("Upstream error", status=e.code)
    except URLError:
        logger.exception("Unable to reach GeeksforGeeks while proxying %s", url)
        return Response("Upstream unreachable", status=502)

    if len(data) > MAX_PROXY_BYTES:
        logger.warning("Refusing to proxy %s: exceeded size limit", url)
        return Response("Resource too large", status=502)

    return Response(data, content_type=content_type)


@app.route("/<path:path>")
def article_page(path):
    """Renders the article page.

    Args:
        path (str): The path to the article.

    Returns:
        Text: The rendered article page.
    """
    if not is_plausible_article_path(path):
        return render_template("error.html", code=404), 404

    try:
        with urlopen(
            build_request(urljoin(GFG_BASE_URL, path)), timeout=REQUEST_TIMEOUT
        ) as response:
            soup = BeautifulSoup(response.read(), "html.parser")
    except HTTPError as e:
        logger.warning("GeeksforGeeks returned %s for %s", e.code, path)
        return render_template("error.html", code=e.code), e.code
    except URLError:
        logger.exception("Unable to reach GeeksforGeeks for %s", path)
        return render_template("error.html", code=502), 502

    try:
        content = get_content(soup)
        title = get_title(soup)
    except LookupError:
        logger.exception("Unable to extract article content for %s", path)
        return render_template("error.html", code=502), 502

    return render_template("article.html", content=content, title=title)

def is_plausible_article_path(path: str) -> bool:
    """Checks whether a path could plausibly be a GeeksforGeeks article.

    Rejects paths that are clearly not articles (static asset extensions,
    hidden files, scanner probes) so that they never trigger a network
    request to GeeksforGeeks.

    Args:
        path (str): The requested path.

    Returns:
        bool: True if the path could be an article, False otherwise.
    """
    lowered = path.lower()

    if lowered.endswith(NON_ARTICLE_SUFFIXES):
        return False

    # Ficheros y directorios ocultos: .env, .git/config, .vscode/sftp.json...
    if any(segment.startswith(".") for segment in lowered.split("/")):
        return False

    return True

def transform_code_tabs(article_content: BeautifulSoup) -> None:
    """Rewrites GeeksforGeeks code tab widgets as JavaScript-free tabs.

    GFG groups multi-language code samples in <gfg-tabs>, alternating
    <gfg-tab> labels with <gfg-panel> contents, and switches between them
    with JavaScript that get_content() strips. This rebuilds each group
    using the radio-input pattern so tabs keep working without scripts.

    Args:
        article_content (BeautifulSoup): The article content, modified in place.
    """
    soup = BeautifulSoup("", "html.parser")

    for index, tabs in enumerate(article_content.find_all("gfg-tabs")):
        labels = tabs.find_all("gfg-tab", recursive=False)
        panels = tabs.find_all("gfg-panel", recursive=False)

        if not panels:
            continue

        group = f"codetabs-{index}"
        wrapper = soup.new_tag("div", attrs={"class": "code-tabs"})

        for position, panel in enumerate(panels):
            radio_id = f"{group}-{position}"

            radio = soup.new_tag(
                "input",
                attrs={"type": "radio", "name": group, "id": radio_id},
            )

            if position == 0:
                radio["checked"] = "checked"

            label = soup.new_tag("label", attrs={"for": radio_id})

            if position < len(labels):
                label.string = labels[position].get_text(strip=True)
            else:
                label.string = panel.get("data-code-lang", "code")

            body = soup.new_tag("div", attrs={"class": "code-tabs__panel"})

            for child in list(panel.contents):
                body.append(child.extract())

            code_el = body.find("pre")
            tio_url = None

            if code_el:
                tio_url = build_tio_url(
                    panel.get("data-code-lang", ""), code_el.get_text()
                )

            toolbar = soup.new_tag("div", attrs={"class": "code-tabs__bar"})

            copy_btn = soup.new_tag(
                "button",
                attrs={
                    "type": "button",
                    "class": "code-tabs__btn js-copy",
                    "title": "Copiar código",
                },
            )
            copy_btn.string = "Copiar"
            toolbar.append(copy_btn)

            if tio_url:
                run = soup.new_tag(
                    "a",
                    href=tio_url,
                    target="_blank",
                    rel="noopener noreferrer",
                    attrs={"class": "code-tabs__btn", "title": "Ejecutar en TIO"},
                )
                run.string = "▶ Ejecutar"
                toolbar.append(run)

            body.insert(0, toolbar)

            wrapper.append(radio)
            wrapper.append(label)
            wrapper.append(body)

        tabs.replace_with(wrapper)

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
    transform_code_tabs(article_content)
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

def is_practice_url(url: str) -> bool:
    """Checks whether a URL points to the GeeksforGeeks practice IDE.

    These pages are not articles and cannot be rendered by this frontend,
    so they are kept pointing at GeeksforGeeks.

    Args:
        url (str): The URL to check.

    Returns:
        bool: True if the URL points to the practice IDE, False otherwise.
    """
    return urlparse(url).path.startswith("/problems/")

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

def build_tio_url(
    language: str, code: str, header: str = "", footer: str = ""
) -> str | None:
    """Builds a tio.run permalink carrying the language and source code.

    The payload is a raw-deflate stream of the fields
    `<language>\\xff<header>\\xff<code>\\xff<footer>\\xff`, base64-encoded with
    '+' replaced by '@' and padding stripped. It lives in the URL fragment,
    so it is never sent to tio.run's server.

    Header and footer are shown collapsed in tio.run, which makes them a good
    place for driver code the user should not edit.

    Args:
        language (str): The GFG data-code-lang value.
        code (str): The source code shown in the editor.
        header (str): Optional code prepended before the editor content.
        footer (str): Optional code appended after the editor content.

    Returns:
        str | None: The permalink, or None if the language is unsupported.
    """
    tio_language = TIO_LANGUAGES.get(language)

    if not tio_language:
        return None

    payload = (
        b"\xff".join(
            field.encode("utf-8")
            for field in (tio_language, header, code, footer)
        )
        + b"\xff"
    )

    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    compressed = compressor.compress(payload) + compressor.flush()
    encoded = base64.b64encode(compressed).decode().replace("+", "@").rstrip("=")

    return f"https://tio.run/##{encoded}"


@app.route("/problems/<slug>/<int:number>")
def problem_page(slug: str, number: int):
    """Renders a GeeksforGeeks practice problem with an embedded editor.

    Args:
        slug (str): The problem slug.
        number (int): The problem number.

    Returns:
        Text: The rendered problem page.
    """
    url = urljoin(GFG_BASE_URL, f"problems/{slug}/{number}")

    try:
        with urlopen(build_request(url), timeout=REQUEST_TIMEOUT) as response:
            soup = BeautifulSoup(response.read(), "html.parser")
    except HTTPError as e:
        return render_template("error.html", code=e.code), e.code
    except URLError:
        logger.exception("Unable to reach GeeksforGeeks for %s", url)
        return render_template("error.html", code=502), 502

    try:
        problem = get_problem_data(soup)
    except LookupError:
        logger.exception("Unable to extract problem data for %s", slug)
        return render_template("error.html", code=502), 502

    functions = problem.get("extra", {}).get("initial_user_func", {})
    solutions = []

    for language in functions:
        code, header, footer = build_problem_code(functions, language)
        solutions.append(
            {
                "language": language,
                "name": LANGUAGE_NAMES.get(language, language.title()),
                "code": code,
                "tio_url": build_tio_url(language, code, header, footer),
            }
        )

    return render_template(
        "problem.html",
        title=problem.get("problem_name", slug.replace("-", " ").title()),
        question=problem.get("problem_question", ""),
        difficulty=problem.get("difficulty"),
        solutions=solutions,
    )


def get_problem_data(soup: BeautifulSoup) -> dict:
    """Extracts the practice problem payload from the page's __NEXT_DATA__.

    Args:
        soup (BeautifulSoup): The soup of the problem page.

    Returns:
        dict: The problem data.
    """
    script = soup.find("script", id="__NEXT_DATA__")

    if script is None or not script.string:
        raise LookupError("Unable to find __NEXT_DATA__")

    try:
        state = json.loads(script.string)["props"]["pageProps"]["initialState"]
        return state["problemData"]["allData"]["probData"]
    except (KeyError, TypeError, ValueError) as exc:
        raise LookupError("Unable to find problem data") from exc


def build_problem_code(functions: dict, language: str) -> tuple[str, str, str]:
    """Splits a practice problem into editor content, header and footer.

    GFG divides each problem into `user_code` (the skeleton the user fills in)
    and `initial_code` (a hidden driver that reads input, calls the user's
    function and prints the result), joined at a marker line. Here the driver
    is split at that marker so it can be placed in tio.run's collapsed header
    and footer fields, leaving the editor showing only the skeleton.

    Args:
        functions (dict): The initial_user_func mapping.
        language (str): The language key.

    Returns:
        tuple[str, str, str]: The skeleton, the header and the footer.
    """
    entry = functions.get(language) or {}
    user = entry.get("user_code", "")
    initial = entry.get("initial_code", "")

    if not initial:
        return user, "", ""

    lines = initial.splitlines()

    for position, line in enumerate(lines):
        if "user code will be pasted" in line.lower():
            header = "\n".join(lines[:position])
            footer = "\n".join(lines[position + 1 :])
            return user, header, footer

    # Sin marcador, se separan las directivas de cabecera (imports, includes),
    # que deben preceder al código del usuario, del resto del driver.
    header_lines = []
    footer_lines = []
    in_header = True

    for line in lines:
        stripped = line.strip()

        if in_header and (
            not stripped
            or stripped.startswith(("#include", "#define", "import ", "using "))
        ):
            header_lines.append(line)
        else:
            in_header = False
            footer_lines.append(line)

    return user, "\n".join(header_lines), "\n".join(footer_lines)

def main():
    """Runs the app."""
    port = int(os.getenv("PORT", "8113"))
    debug = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
    app.run(port=port, debug=debug)


if __name__ == "__main__":
    main()
