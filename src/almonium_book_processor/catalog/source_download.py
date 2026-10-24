"""Fetching a public-domain book from an approved free library.

The product API names a text it wants in the catalogue by its download link on
Project Gutenberg or on Wikisource's official EPUB exporter. Only those hosts
are fetched, over HTTPS, and a redirect is followed only while it stays on
them: the processor is never a proxy for an arbitrary URL. Gutenberg links
must name an EPUB, and an exporter link must ask for an EPUB of one page.

A fetch that fails for a reason that may pass (a timeout, a refused connection,
a 5xx or 429 answer) raises ``DownloadUnavailable`` and the worker tries again;
anything else (a 4xx, a file over the size cap, something that is not an EPUB,
a redirect off the list) raises ``DownloadRefused`` and the edition fails with
that sentence.
"""

from __future__ import annotations

import re
import tempfile
import time
from dataclasses import dataclass
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from almonium_book_processor.catalog.models import SourceDownload

USER_AGENT = "AlmoniumBookProcessor/1.0 (tech@almonium.com)"
MAX_BYTES = 60 * 1024 * 1024
# Gutenberg's audiobook records (LibriVox readings) ship a 10 KB EPUB holding the track
# list; Der Schimmelreiter's and Pinocchio's came through the ingest and were adapted and
# translated as books. The shortest text EPUB in the library is many times this.
MIN_BYTES = 24 * 1024
# The exporter builds the EPUB before it sends a byte; a long book takes a
# minute or more, so the first byte may be slow. Every later read is held to
# the same limit, and the whole transfer to the deadline.
READ_TIMEOUT_SECONDS = 300
DEADLINE_SECONDS = 15 * 60
MAX_REDIRECTS = 5
CHUNK = 64 * 1024
EPUB_MAGIC = b"PK\x03\x04"

GUTENBERG_HOSTS = frozenset({"www.gutenberg.org", "gutenberg.org"})
WIKISOURCE_EXPORT_HOSTS = frozenset({"ws-export.wmcloud.org"})
STANDARD_EBOOKS_HOSTS = frozenset({"standardebooks.org"})
HOSTS = {
    SourceDownload.Kind.GUTENBERG: GUTENBERG_HOSTS,
    SourceDownload.Kind.WIKISOURCE: WIKISOURCE_EXPORT_HOSTS,
    SourceDownload.Kind.STANDARD_EBOOKS: STANDARD_EBOOKS_HOSTS,
}
ALLOWED_HOSTS = GUTENBERG_HOSTS | WIKISOURCE_EXPORT_HOSTS | STANDARD_EBOOKS_HOSTS
# standardebooks.org/ebooks/<author>/<title>/downloads/<author>_<title>.epub; without
# ?source=download the site answers a page that says the download has started
STANDARD_EBOOKS_EPUB_PATH = re.compile(
    r"^/ebooks/[a-z0-9-]+/[a-z0-9-]+(?:/[a-z0-9-]+)*/downloads/[a-z0-9_.-]+\.epub$"
)

GUTENBERG_EPUB_PATHS = (
    re.compile(r"^/ebooks/\d+\.epub3?\.(?:images|noimages)$"),
    re.compile(r"^/cache/epub/(\d+)/pg\1(?:-images)?(?:-3)?\.epub$"),
)
EXPORT_FORMATS = re.compile(r"^epub(?:-[23])?$")


class DownloadRefused(ValueError):
    """The link or what it served cannot become a book; trying again will not help."""


class DownloadUnavailable(RuntimeError):
    """The library did not answer usefully this time; a later try may succeed."""


@dataclass(frozen=True)
class Downloaded:
    path: Path
    final_url: str
    size: int


def check_download_url(url: str, source_kind: str) -> None:
    """Refuse a download link that is not an EPUB on the named library's hosts."""

    parts = urlsplit(url)
    if parts.scheme != "https":
        raise DownloadRefused("The download link must use https.")
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError as error:
        raise DownloadRefused("The download link has an invalid port.") from error
    if parts.username or parts.password or port not in (None, 443):
        raise DownloadRefused("The download link must not carry credentials or a port.")
    if host not in HOSTS.get(source_kind, frozenset()):
        allowed = ", ".join(sorted(HOSTS.get(source_kind, ALLOWED_HOSTS)))
        raise DownloadRefused(f"A {source_kind} text is downloaded only from {allowed}.")
    if source_kind == SourceDownload.Kind.GUTENBERG:
        if not any(pattern.match(parts.path) for pattern in GUTENBERG_EPUB_PATHS):
            raise DownloadRefused(
                "A Gutenberg link must name an EPUB: /ebooks/<id>.epub3.images, "
                "/ebooks/<id>.epub.noimages or /cache/epub/<id>/pg<id>-images-3.epub."
            )
        return
    query = parse_qs(parts.query)
    if source_kind == SourceDownload.Kind.STANDARD_EBOOKS:
        if not STANDARD_EBOOKS_EPUB_PATH.match(parts.path) or query.get("source") != ["download"]:
            raise DownloadRefused(
                "A Standard Ebooks link is /ebooks/<author>/<title>/downloads/<file>.epub"
                "?source=download."
            )
        return
    if parts.path not in ("", "/"):
        raise DownloadRefused("A Wikisource export link is the exporter's root with a query.")
    if not query.get("lang") or not query.get("page"):
        raise DownloadRefused("A Wikisource export link names the wiki's lang and the page.")
    if not EXPORT_FORMATS.match((query.get("format") or [""])[0]):
        raise DownloadRefused("A Wikisource export link must ask for format=epub-3.")


def check_page_url(url: str, source_kind: str) -> None:
    """The human page is provenance only, but it must be the named library's."""

    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https":
        raise DownloadRefused("The source page link must use https.")
    if source_kind == SourceDownload.Kind.GUTENBERG:
        ok = host in GUTENBERG_HOSTS
    else:
        ok = host == "wikisource.org" or host.endswith(".wikisource.org")
    if not ok:
        raise DownloadRefused(f"The source page is not a {source_kind} page.")


class _NoRedirect(HTTPRedirectHandler):
    """Hand every redirect back, so each hop is checked against the list first."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_open = build_opener(_NoRedirect).open


def gutenberg_alternates(url: str) -> list[str]:
    """The other EPUB builds Gutenberg may have of the same book, best first.

    Not every book has every build: of a hundred popular books on 2026-10-24 one text had
    no ``.epub3.images`` at all. The plain ``.epub.noimages`` is the one most books have.
    """

    parts = urlsplit(url)
    match = re.match(r"^/ebooks/(\d+)\.(epub3\.images|epub\.images|epub\.noimages)$", parts.path)
    if not match:
        return []
    builds = ["epub3.images", "epub.images", "epub.noimages"]
    later = builds[builds.index(match.group(2)) + 1 :]
    return [parts._replace(path=f"/ebooks/{match.group(1)}.{build}").geturl() for build in later]


def download(url: str, source_kind: str, *, urlopen=None) -> Downloaded:
    """Fetch the EPUB behind ``url`` into a temporary file the caller removes.

    A Gutenberg address that answers 404 is tried in its other builds before it is given up.
    """

    try:
        return _download(url, source_kind, urlopen=urlopen)
    except DownloadRefused as refused:
        if "HTTP 404" not in str(refused) or source_kind != SourceDownload.Kind.GUTENBERG:
            raise
        for alternate in gutenberg_alternates(url):
            try:
                return _download(alternate, source_kind, urlopen=urlopen)
            except DownloadRefused as also_refused:
                if "HTTP 404" not in str(also_refused):
                    raise
        raise refused


def _download(url: str, source_kind: str, *, urlopen=None) -> Downloaded:
    urlopen = urlopen or _open
    check_download_url(url, source_kind)
    started = time.monotonic()
    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        request = Request(current, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            response = urlopen(request, timeout=READ_TIMEOUT_SECONDS)
        except HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                location = error.headers.get("Location", "")
                error.close()
                if not location:
                    raise DownloadRefused(f"{_host(current)} redirected nowhere.") from error
                following = urljoin(current, location)
                if (urlsplit(following).hostname or "").lower() not in ALLOWED_HOSTS or (
                    urlsplit(following).scheme != "https"
                ):
                    raise DownloadRefused(
                        f"{_host(current)} redirected off the approved hosts, to "
                        f"{_host(following) or following}."
                    ) from error
                current = following
                continue
            error.close()
            if error.code == 429 or error.code >= 500:
                raise DownloadUnavailable(
                    f"{_host(current)} answered HTTP {error.code}."
                ) from error
            raise DownloadRefused(
                f"{_host(current)} answered HTTP {error.code}"
                + (": the page may not exist." if error.code == 404 else ".")
            ) from error
        except (URLError, HTTPException, OSError) as error:
            reason = getattr(error, "reason", error)
            raise DownloadUnavailable(f"{_host(current)} could not be reached: {reason}") from error
        with response:
            return _store(response, current, started)
    raise DownloadRefused(f"{_host(url)} redirected more than {MAX_REDIRECTS} times.")


def _store(response, url: str, started: float) -> Downloaded:
    declared = response.headers.get("Content-Length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise DownloadRefused(
            f"The file is {int(declared) // (1024 * 1024)} MB; the limit is "
            f"{MAX_BYTES // (1024 * 1024)} MB."
        )
    size = 0
    with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as temporary:
        path = Path(temporary.name)
        try:
            while True:
                if time.monotonic() - started > DEADLINE_SECONDS:
                    raise DownloadUnavailable(
                        f"{_host(url)} took over {DEADLINE_SECONDS // 60} minutes."
                    )
                try:
                    chunk = response.read(CHUNK)
                except (HTTPException, OSError) as error:
                    raise DownloadUnavailable(
                        f"{_host(url)} stopped sending the file: {error}"
                    ) from error
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise DownloadRefused(
                        f"The file is over the {MAX_BYTES // (1024 * 1024)} MB limit."
                    )
                temporary.write(chunk)
        except BaseException:
            temporary.close()
            path.unlink(missing_ok=True)
            raise
    with path.open("rb") as stored:
        magic = stored.read(len(EPUB_MAGIC))
    if magic != EPUB_MAGIC:
        path.unlink(missing_ok=True)
        content_type = response.headers.get("Content-Type", "unknown type")
        raise DownloadRefused(f"{_host(url)} sent {content_type}, not an EPUB.")
    if size < MIN_BYTES:
        path.unlink(missing_ok=True)
        raise DownloadRefused(
            f"The file is {size // 1024} KB, too small to be a book; a Gutenberg record "
            "this size is an audiobook's track list, not the text."
        )
    return Downloaded(path=path, final_url=url, size=size)


def _host(url: str) -> str:
    return urlsplit(url).hostname or url
