from pligrim_bot.core.parsers.people_parser import human_room


def voucher_caption(title, room):
    people = room['people']
    text = f'📄 {title}\n🛏 {human_room(room["kind"])} · {len(people)} pax\n👥 ' + ', '.join(people)
    # Leave margin below Telegram's caption limit, measured in UTF-16 units.
    encoded = text.encode('utf-16-le')
    return text if len(encoded) <= 2000 else encoded[:1994].decode('utf-16-le', errors='ignore') + '…'
