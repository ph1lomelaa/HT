"""Read-only catalog diagnostics; never print credentials or passenger rows."""
from pathlib import Path

from pligrim_bot.config import settings


def main():
    print('Code:', Path(__file__).resolve().parent)
    try:
        sheets = settings.get_all_accessible_sheets()
        print('Accessible spreadsheets:', len(sheets))
        for title in sorted(sheets):
            print(' -', title)
        months = settings.detect_pilgrim_months(sheets)
        print('Detected months:', len(months))
        for label in sorted(months):
            print(' -', label)
        if not months:
            print('Check spreadsheet access and English month names in document titles.')
    except Exception as error:
        print('Catalog check failed:', type(error).__name__)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
