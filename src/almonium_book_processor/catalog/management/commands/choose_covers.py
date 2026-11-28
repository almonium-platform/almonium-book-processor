from django.core.management.base import BaseCommand

from almonium_book_processor.catalog import covers


class Command(BaseCommand):
    help = (
        "Choose cover art for Almonium's works on the plan (./plan-manage choose_covers): every "
        "work never looked at, or --only these slugs, or --all of the shelf again after the "
        "search or the rules changed. A work whose call the gateway holds stops the run; the "
        "rest stay as they were. Each answer is found again by content, so a run stopped and "
        "started again buys nothing twice. ALMONIUM_API_URL names the environment whose shelf "
        "is covered."
    )

    def add_arguments(self, parser):
        parser.add_argument("--only", default="", help="comma-separated work slugs")
        parser.add_argument("--all", action="store_true", help="every work, decided or not")
        parser.add_argument("--limit", type=int, default=0, help="stop after this many works")

    def handle(self, *args, **options):
        works = [slug.strip() for slug in options["only"].split(",") if slug.strip()]
        if not works:
            works = covers.every_work() if options["all"] else covers.pending()
        if options["limit"]:
            works = works[: options["limit"]]
        self.stdout.write(f"{len(works)} works to look at")
        counts = {"APPROVED": 0, "NONE": 0, "failed": 0}
        spent = 0.0
        for number, slug in enumerate(works, 1):
            try:
                said = covers.choose_cover(slug)
            except covers.Held as held:
                left = len(works) - number + 1
                self.stdout.write(f"The gateway is holding calls: {held}")
                self.stdout.write(f"Stopped; {left} works stay as they were.")
                return
            except Exception as broken:  # noqa: BLE001 - one work must not stop the rest
                counts["failed"] += 1
                self.stdout.write(f"[{number}/{len(works)}] {slug}: failed: {str(broken)[:200]}")
                continue
            counts[said["status"]] = counts.get(said["status"], 0) + 1
            spent += said["cost_usd"]
            line = f"[{number}/{len(works)}] {slug}: {said['status']} {said['reason']}"
            self.stdout.write(line[:260])
        self.stdout.write(
            f"Done: {counts['APPROVED']} covers, {counts['NONE']} without art, "
            f"{counts['failed']} failed. Plan cost recorded: ${spent:.2f}."
        )
