"""Look at many books the way ingest would, keep only what was found, and spend nothing."""

from __future__ import annotations

import hashlib
import re
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import requests
from django.core.management.base import BaseCommand

from almonium_book_processor import ingest_processor_version
from almonium_book_processor.catalog.models import SourceShape
from almonium_book_processor.catalog.source_download import HOSTS, download
from almonium_book_processor.catalog.source_shape import judge, measure
from almonium_book_processor.ingest.epub import ingest_epub
from almonium_book_processor.ingest.tei import ingest_tei

GUTENBERG_SEARCH = (
    "https://www.gutenberg.org/ebooks/search/?query=l.{language}&sort_order=downloads"
)
GUTENBERG_EPUB = "https://www.gutenberg.org/ebooks/{id}.epub3.images"
_IDS = re.compile(r'href="/ebooks/(\d+)"')


class Command(BaseCommand):
    help = (
        "Download Gutenberg's most read books per language, cut each as ingest would, judge the "
        "shape, record the verdict (SourceShape) and delete the file. No edition, no AI call. "
        "--urls looks at EPUB addresses, --files at local EPUB or TEI files (ELTeC)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--languages", default="en,fr,de,es,it")
        parser.add_argument("--per-language", type=int, default=20)
        parser.add_argument("--ids", default="", help="Gutenberg ids instead of the popular lists")
        parser.add_argument(
            "--urls", default="", help="EPUB addresses on any library host, comma-separated"
        )
        parser.add_argument(
            "--files", default="", help="local EPUB or TEI files, comma-separated (ELTeC)"
        )
        parser.add_argument(
            "--any-host",
            action="store_true",
            help="fetch --urls from hosts the downloader does not allow: a trial, not an ingest",
        )
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--again", action="store_true", help="measure books already recorded")

    def handle(self, *args, **options):
        session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0 almonium-book-processor shake-down"
        urls = [u.strip() for u in options["urls"].split(",") if u.strip()]
        files = [f.strip() for f in options["files"].split(",") if f.strip()]
        if files:
            urls = [f"file://{Path(f).resolve()}" for f in files]
        if not urls:
            ids = [int(i) for i in options["ids"].split(",") if i.strip()] or self._popular(
                session, options["languages"].split(","), options["per_language"]
            )
            urls = [GUTENBERG_EPUB.format(id=book_id) for book_id in ids]
        if options["limit"]:
            urls = urls[: options["limit"]]
        verdicts: Counter = Counter()
        reasons: Counter = Counter()
        with tempfile.TemporaryDirectory(prefix="shake-down-") as folder:
            for number, url in enumerate(urls, 1):
                if not options["again"] and SourceShape.objects.filter(source_url=url).exists():
                    continue
                row = self._look(session, url, Path(folder) / f"{number}.epub", options["any_host"])
                verdicts[row.verdict] += 1
                for reason in row.reasons:
                    reasons[reason.split(":")[0].split(" is ")[0]] += 1
                metrics = row.metrics
                shape = (
                    f"ch={metrics.get('chapters', '?')} body={metrics.get('body_chapters', '?')}"
                )
                self.stdout.write(
                    f"{number:3}/{len(urls)} {row.verdict:10} {row.language:3} {row.title[:44]:44} "
                    f"{shape} " + "; ".join(row.reasons)
                )
        self.stdout.write(f"\n{dict(verdicts)}")
        for reason, count in reasons.most_common():
            self.stdout.write(f"{count:4}  {reason}")

    def _popular(self, session, languages, per_language) -> list[int]:
        """Gutenberg's own search by language, most downloaded first, 25 a page."""

        ids: list[int] = []
        for language in languages:
            found: list[int] = []
            start = 1
            while len(found) < per_language:
                page = session.get(
                    GUTENBERG_SEARCH.format(language=language.strip()) + f"&start_index={start}",
                    timeout=30,
                )
                page.raise_for_status()
                new = [int(i) for i in _IDS.findall(page.text) if int(i) not in found]
                if not new:
                    break
                found.extend(new)
                start += 25
            ids.extend(found[:per_language])
        return ids

    def _look(self, session, url: str, path: Path, any_host: bool = False) -> SourceShape:
        host = urlsplit(url).hostname or ""
        kind = next((kind for kind, hosts in HOSTS.items() if host in hosts), None)
        label = str(kind) if kind else ("file" if url.startswith("file://") else f"trial:{host}")
        row = SourceShape(
            source_url=url[:500],
            source_kind=label[:40],
            processor_version=ingest_processor_version(),
        )
        local = url.startswith("file://")
        try:
            if local:
                path = Path(url[len("file://") :])
            elif kind is not None:
                fetched = download(url, kind)
                path = fetched.path
                if any(fetched.final_url.endswith(b) for b in ("epub.images", "epub.noimages")):
                    row.metrics = {"fetched_from": fetched.final_url}  # a plain build stood in
            elif any_host:
                response = session.get(url, timeout=120)
                response.raise_for_status()
                path.write_bytes(response.content)
            else:
                raise ValueError(f"{host} is not a library host; pass --any-host for a trial")
            row.source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            if path.suffix.lower() == ".xml":
                artifact = ingest_tei(path, edition_slug="shake-down", work_slug="shake-down")
            else:
                artifact = ingest_epub(path, edition_slug="shake-down", work_slug="shake-down")
            row.title = (artifact.edition.title or "")[:500]
            row.author = (artifact.edition.author or "")[:300]
            row.language = (artifact.edition.language or "")[:16]
            row.metrics = {**row.metrics, **measure(artifact)}
            row.verdict, row.reasons = judge(row.metrics)
        except Exception as error:  # a book that cannot be read is a finding too
            row.verdict = SourceShape.Verdict.UNREADABLE
            row.reasons = [f"{type(error).__name__}: {str(error)[:200]}"]
        finally:
            if not local:
                path.unlink(missing_ok=True)
        SourceShape.objects.update_or_create(
            source_url=row.source_url,
            source_sha256=row.source_sha256,
            defaults={
                field: getattr(row, field)
                for field in (
                    "source_kind",
                    "title",
                    "author",
                    "language",
                    "verdict",
                    "reasons",
                    "metrics",
                    "processor_version",
                )
            },
        )
        return row
