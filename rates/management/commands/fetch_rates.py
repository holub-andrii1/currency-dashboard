from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from rates.services.nbu import sync_rates


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise CommandError(f"Invalid date {value!r}, expected YYYY-MM-DD") from exc


class Command(BaseCommand):
    help = "Download official NBU exchange rates into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=365,
            help="How many days back from today to load (default: 365).",
        )
        parser.add_argument("--start", type=parse_date, help="Start date, YYYY-MM-DD.")
        parser.add_argument("--end", type=parse_date, help="End date, YYYY-MM-DD (default: today).")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-download days that are already stored.",
        )
        parser.add_argument("--workers", type=int, default=8, help="Parallel downloads.")

    def handle(self, *args, **options):
        end = options["end"] or date.today()
        start = options["start"] or end - timedelta(days=options["days"] - 1)
        if start > end:
            raise CommandError("--start must not be after --end")

        self.stdout.write(f"Syncing NBU rates from {start} to {end}...")
        result = sync_rates(start, end, force=options["force"], workers=options["workers"])

        if result.days_requested == 0:
            self.stdout.write(self.style.SUCCESS("Already up to date."))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Fetched {result.days_fetched}/{result.days_requested} days, "
                f"saved {result.rates_saved} rates."
            )
        )
        if result.failed_days:
            failed = ", ".join(day.isoformat() for day in result.failed_days)
            self.stderr.write(self.style.WARNING(f"Failed days (run again to retry): {failed}"))
