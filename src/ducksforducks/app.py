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
import urllib
from typing import Text

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

# Remove the default Flask logger
app.logger.removeHandler(app.logger.handlers[0])


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
def proxy() -> bytes:
    """A simple proxy for images.

    Returns:
        bytes: The content of the proxied URL.
    """
    url = request.args.get("url")

    if not url or not (url.startswith("https://media.geeksforgeeks.org/")):
        logger.error(f"Invalid URL for proxying: {url}")
        return "Invalid URL"

    logger.debug(f"Proxying {url}")

    with urllib.request.urlopen(url) as response:
        data = response.read()
    return data


@app.route("/<path:path>")
def article_page(path):
    """Renders the article page.

    Args:
        path (str): The path to the article.

    Returns:
        Text: The rendered article page.
    """
    response = urllib.request.urlopen(f"https://www.geeksforgeeks.org/{path}")

    if response.getcode() == 200:
        soup = BeautifulSoup(response, "html.parser")
        content = get_content(soup)
        title = content.find(class_="article-title").text
        return render_template("article.html", content=content, title=title)
    else:
        return (
            render_template("error.html", code=response.getcode()),
            response.getcode(),
        )


def get_content(soup: BeautifulSoup) -> BeautifulSoup:
    article_content = soup.find("div", {"class": "a-wrapper"}).find("article")

    for img in article_content.find_all("img"):
        img["src"] = f"/proxy?url={img['src']}"

    for element in article_content.find_all(["script", "style"]):
        element.decompose()

    for ad in article_content.find_all():
        if ad.get("id") and ad["id"].startswith("GFG_AD_"):
            ad.decompose()

    for link in article_content.find_all("a"):
        if link.get("href") and link["href"].startswith("https://www.geeksforgeeks.org/"):
            if not link["href"].startswith("https://www.geeksforgeeks.org/user/"):
                link["href"] = f"/{link['href'].replace('https://www.geeksforgeeks.org/', '')}"

            else:
                classes = link.get("class", [])
                classes.append("gfg-link")
                link["class"] = classes

        else:
            classes = link.get("class", [])
            classes.append("external-link")
            link["class"] = classes

    return article_content


def main():
    port = int(os.getenv("PORT", 8113))
    debug = bool(os.getenv("DEBUG", False))
    app.run(port=port, debug=debug)


if __name__ == "__main__":
    main()
