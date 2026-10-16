# Chat workflow coverage in the website

The bot opens the Mini App, authenticates browser sign-in, and delivers PDFs.
Document creation and correction are available in the website.

| Previous chat operation | Website equivalent |
| --- | --- |
| Start, cancel, create another voucher | Home, Back, Create another voucher |
| Refresh accessible Google documents | Refresh beside package selection |
| Select month, worksheet, package | Month/table and group selectors, package cards |
| Show older worksheets | Show past trips inside the selected document |
| Review people and room types | Pilgrims step: names, placement, adults, selection |
| Apply a room type to the group | Placement for selected rooms |
| Edit shared hotels, dates, check-in, city order | Accommodation step; night calculation and chronological normalization |
| Add/remove the second city | Second-city toggle |
| Edit services, transport, meals, guide, excursions and technical contact | Services step, including explicit exclusions |
| Choose the program image | Three program cards with full-page preview |
| Generate a PDF for each room | One document per selected room, ZIP download |
| Edit one already generated voucher | Edit beside each PDF; owner-scoped immutable saved draft |
| Repeat after a delivery error | Retry remaining files on the result page |
| Create manually | Individual voucher card |
| Flight voucher from package dates and schedule | Flight voucher card → Google Sheets → route → review |
| Four Air Astana route combinations and charter codes | Shared `core/parsers/flight_parser.py`; same schedule mapping as the chat |
| Independent flight PDF | Standalone one-page flight job; no accommodation required |
| Change flight details | Editable outbound/return fields; any airline in manual mode |
| Return to a sent document | My documents: latest 50 jobs in the previous 24 hours |

Passenger vouchers can also load flight details from their selected group's schedule
and include those details as a third page. Standalone flight documents remain one page.
Dates of arrival must be confirmed when importing legacy schedules that only list
departure dates. Changes in the website do not modify the Google spreadsheet.

Validation covers isolated per-document edits, all four legacy flight routes,
charter codes, one-way/return flight PDFs, history ownership/expiry, batch reopening,
partial delivery retries, and client workflow transitions. Real Telegram delivery
and a phone WebView still need checking after deploying this update.
