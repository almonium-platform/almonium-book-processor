import json
import sys

from django.core.management.base import BaseCommand

from almonium_book_processor.catalog import outside_calls

HELD = 75  # EX_TEMPFAIL: nothing was paid; ask again later


class Command(BaseCommand):
    help = (
        "Answer one model request from outside this processor through the AI gateway "
        "(./plan-manage ask < request.json). The request is one JSON object on standard input: "
        '{"seat": "antigravity:gemini-4-carbon:medium" (a seat or a bare model; a codex seat may '
        'end in ":search"), "purpose": "lexicon_review_rule", "caller": "review_v4", '
        '"instructions": "...", "input": "...", "schema": {...} (left out, a codex seat answers '
        'in prose), "salt": "" (to ask the same thing again on purpose)}. The answer is one JSON '
        'object on the last line of standard output: {"status": "completed", "text", "cached", '
        '"usage", "cost_usd", "plan_account"} with exit 0; {"status": "held", "reason"} with '
        "exit 75 when a cap, a paused account or a plan's limit refused and nothing was paid; "
        '{"status": "failed", "error"} with exit 1.'
    )

    def handle(self, *args, **options):
        try:
            request = json.loads(sys.stdin.read())
            if not isinstance(request, dict):
                raise outside_calls.Refused("A request is one JSON object")
            said = outside_calls.ask(request)
        except (json.JSONDecodeError, outside_calls.Refused) as refused:
            said = {"status": "failed", "error": str(refused)[:500]}
        self.stdout.write(json.dumps(said, ensure_ascii=False))
        if said["status"] != "completed":
            sys.exit(HELD if said["status"] == "held" else 1)
