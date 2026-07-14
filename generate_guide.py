"""
Generate the Swim Balham User Guide PDF.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import os

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "Swim Balham - User Guide.pdf")
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

# Brand colours
NAVY = HexColor("#0A1628")
BLUE = HexColor("#1A8FE3")
CYAN = HexColor("#22D3EE")
GREY = HexColor("#7B9CC4")
WHITE = HexColor("#FFFFFF")

doc = SimpleDocTemplate(
    OUTPUT, pagesize=A4,
    leftMargin=25*mm, rightMargin=25*mm,
    topMargin=25*mm, bottomMargin=20*mm,
    title="Swim Balham — User Guide",
    author="Swim Balham community project",
)

styles = getSampleStyleSheet()

# Custom styles
title_style = ParagraphStyle('CustomTitle', parent=styles['Title'],
    fontSize=28, textColor=BLUE, spaceAfter=4, alignment=TA_CENTER, fontName='Helvetica-Bold')
subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'],
    fontSize=13, textColor=GREY, spaceAfter=20, alignment=TA_CENTER, fontName='Helvetica')
h1 = ParagraphStyle('H1', parent=styles['Heading1'],
    fontSize=18, textColor=BLUE, spaceBefore=20, spaceAfter=8, fontName='Helvetica-Bold')
h2 = ParagraphStyle('H2', parent=styles['Heading2'],
    fontSize=14, textColor=NAVY, spaceBefore=14, spaceAfter=6, fontName='Helvetica-Bold')
body = ParagraphStyle('Body', parent=styles['Normal'],
    fontSize=11, textColor=NAVY, spaceAfter=6, leading=16, fontName='Helvetica')
bullet = ParagraphStyle('Bullet', parent=body,
    leftIndent=20, bulletIndent=8, spaceAfter=4)
note = ParagraphStyle('Note', parent=body,
    fontSize=10, textColor=GREY, leftIndent=12, spaceAfter=8)
credit = ParagraphStyle('Credit', parent=styles['Normal'],
    fontSize=10, textColor=GREY, alignment=TA_CENTER, spaceBefore=30)

story = []

# ── Cover ──
story.append(Spacer(1, 40*mm))

# Logo
logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
if os.path.exists(logo_path):
    img = Image(logo_path, width=60*mm, height=60*mm)
    story.append(img)

story.append(Spacer(1, 10*mm))
story.append(Paragraph("Swim Balham", title_style))
story.append(Paragraph("User Guide", subtitle_style))
story.append(Spacer(1, 5*mm))

# ── What is it ──
story.append(Paragraph("What is Swim Balham?", h1))
story.append(Paragraph(
    "Swim Balham is a free desktop app for Windows that shows <b>live swimming session "
    "availability</b> for Balham Leisure Centre and Tooting Bec Lido. It fetches real-time "
    "data from the Places Leisure OpenActive API, so you always know how many spots are "
    "left before you book.", body))
story.append(Paragraph(
    "The app loads instantly from a saved cache, then silently refreshes in the background "
    "to keep availability up to date.", body))

# ── System Requirements ──
story.append(Paragraph("System Requirements", h1))
story.append(Paragraph("• <b>Windows 10</b> or later (64-bit)", bullet))
story.append(Paragraph("• <b>No installation required</b> — just double-click the .exe file", bullet))
story.append(Paragraph("• <b>Internet connection</b> needed for live data (offline mode shows last cached data)", bullet))
story.append(Paragraph("• No Python, no admin rights, no additional software needed", bullet))

# ── Getting Started ──
story.append(Paragraph("Getting Started", h1))
story.append(Paragraph("<b>1.</b> Double-click <b>SwimBalham.exe</b> to launch the app.", body))
story.append(Paragraph("<b>2.</b> The app will display a loading message while it fetches today's sessions.", body))
story.append(Paragraph("<b>3.</b> Within a few seconds, you'll see a list of available sessions with live availability.", body))
story.append(Paragraph("<b>4.</b> That's it! Browse sessions, filter by date/time, and click any session for details.", body))

# ── The Interface ──
story.append(Paragraph("Understanding the Interface", h1))

story.append(Paragraph("Left Panel — Filters", h2))
story.append(Paragraph("The sidebar on the left contains all your filtering options:", body))
story.append(Paragraph("• <b>Centre</b> — Choose which centre to view (Balham, Tooting Bec Lido, or All)", bullet))
story.append(Paragraph("• <b>View</b> — Switch between Sessions, Facilities, or All", bullet))
story.append(Paragraph("• <b>Search</b> — Type to search session names (e.g. 'Lane Swim')", bullet))
story.append(Paragraph("• <b>Date</b> — Filter by Today, Tomorrow, Next 7 days, or a specific weekday", bullet))
story.append(Paragraph("• <b>Time of Day</b> — Show only Morning (AM), Afternoon (PM), or Evening (Eve) sessions", bullet))
story.append(Paragraph("• <b>Availability</b> — Show only sessions with spots left, or only full sessions", bullet))
story.append(Paragraph("• <b>Category</b> — Filter by activity type (Swimming, Gym, Group Workout, etc.)", bullet))
story.append(Paragraph("• <b>Clear Filters</b> — Reset everything back to defaults", bullet))

story.append(Paragraph("Centre Panel — Session List", h2))
story.append(Paragraph("Each session card shows:", body))
story.append(Paragraph("• <b>Start time</b> (in cyan) and <b>duration</b>", bullet))
story.append(Paragraph("• <b>Session name</b> (e.g. 'Lane Swim', 'All Welcome')", bullet))
story.append(Paragraph("• <b>Date and location</b>", bullet))
story.append(Paragraph("• <b>Availability pill</b> — colour-coded: green = available, orange = low, red = full", bullet))
story.append(Paragraph("• <b>Capacity bar</b> — visual indicator of how full the session is", bullet))
story.append(Paragraph("• <b>Price</b> (if applicable)", bullet))
story.append(Paragraph("<b>Click any session</b> to see full details in the right panel.", body))

story.append(Paragraph("Right Panel — Session Details", h2))
story.append(Paragraph("When you click a session, the right panel shows:", body))
story.append(Paragraph("• Full session name, date, time, and location", bullet))
story.append(Paragraph("• A large availability card with remaining/total capacity", bullet))
story.append(Paragraph("• A <b>Book this session</b> button that opens the booking page", bullet))
story.append(Paragraph("• Activity, category, duration, and price information", bullet))
story.append(Paragraph("• Full session description", bullet))

story.append(Paragraph("Top Bar", h2))
story.append(Paragraph("• <b>Auto toggle</b> — Turn automatic background refresh on/off", bullet))
story.append(Paragraph("• <b>Refresh button</b> — Manually fetch the latest data", bullet))
story.append(Paragraph("• <b>Settings button</b> — Open the settings dialog", bullet))
story.append(Paragraph("• <b>Status indicator</b> — Shows last sync time or connection status", bullet))

# ── Availability Colours ──
story.append(Paragraph("Availability Colour Guide", h1))

avail_data = [
    ['Colour', 'Meaning', 'When it appears'],
    ['GREEN', 'Available', 'More than 25% of spots remaining'],
    ['ORANGE', 'Low availability', '25% or fewer spots remaining'],
    ['RED (FULL)', 'Fully booked', 'No spots remaining'],
]
avail_table = Table(avail_data, colWidths=[35*mm, 45*mm, 75*mm])
avail_table.setStyle(TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), BLUE),
    ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
    ('FONTSIZE', (0, 0), (-1, -1), 10),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
    ('BACKGROUND', (0, 1), (-1, 1), HexColor("#D1FAE5")),
    ('BACKGROUND', (0, 2), (-1, 2), HexColor("#FEF3C7")),
    ('BACKGROUND', (0, 3), (-1, 3), HexColor("#FEE2E2")),
    ('GRID', (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('TOPPADDING', (0, 0), (-1, -1), 6),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ('LEFTPADDING', (0, 0), (-1, -1), 8),
]))
story.append(avail_table)

# ── Settings ──
story.append(Paragraph("Settings", h1))
story.append(Paragraph("Click the <b>Settings</b> button in the top bar to customise:", body))
story.append(Paragraph("• <b>Auto-refresh interval</b> (1–60 minutes): How often the app checks for new availability. "
    "Default is 5 minutes. Set to 1 minute if you're watching for cancellations.", bullet))
story.append(Paragraph("• <b>Days to look ahead</b> (1–14 days): How many days of future sessions to show. "
    "Default is 1 day for the fastest experience. Increase to 7 or 14 to plan further ahead.", bullet))
story.append(Paragraph("Settings are saved automatically and remembered between launches.", body))

# ── Reminders ──
story.append(Paragraph("Session Reminders", h1))
story.append(Paragraph(
    "If a session is <b>FULL</b>, you can set a reminder to get notified when a spot opens up:", body))
story.append(Paragraph("<b>1.</b> Click on any full (red) session in the list", body))
story.append(Paragraph("<b>2.</b> Click the <b>🔔 Remind me when available</b> button in the details panel", body))
story.append(Paragraph("<b>3.</b> Keep the app running — it will check on each auto-refresh", body))
story.append(Paragraph("<b>4.</b> When a spot opens, you'll hear a notification sound and see a popup with a <b>Book now</b> button", body))
story.append(Paragraph("<i>Note: The app must stay open for reminders to work. It checks on each auto-refresh cycle.</i>", note))
story.append(Paragraph(
    "The reminder popup also includes an optional <b>Buy me a coffee</b> link. Supporting the app is never required to use it.", body))

# ── Booking ──
story.append(Paragraph("Booking a Session", h1))
story.append(Paragraph(
    "Swim Balham shows you availability but does not handle booking directly. To book:", body))
story.append(Paragraph("<b>1.</b> Click on the session you want", body))
story.append(Paragraph("<b>2.</b> Click the <b>Book this session ↗</b> button", body))
story.append(Paragraph("<b>3.</b> This opens the Places Leisure booking website where you can complete your booking", body))
story.append(Paragraph("<i>You'll need an existing Places Leisure account to book sessions.</i>", note))

# ── Offline Mode ──
story.append(Paragraph("Offline Mode", h1))
story.append(Paragraph(
    "If you lose internet connection, the app will show <b>\"Offline — showing cached\"</b> in the status bar. "
    "It will continue displaying the last successfully fetched data. When your connection returns, "
    "click Refresh or wait for the next auto-refresh cycle.", body))

# ── Files ──
story.append(Paragraph("Files & Data", h1))
story.append(Paragraph("The app stores two files in <b>%LOCALAPPDATA%\\SwimBalham</b> for the current Windows user:", body))
story.append(Paragraph("• <b>cache.json</b> — Saved session data (enables instant startup)", bullet))
story.append(Paragraph("• <b>settings.json</b> — Your saved preferences", bullet))
story.append(Paragraph("Both files are small and safe to delete if you want a fresh start. The app does not collect analytics or telemetry.", body))

# ── Tips ──
story.append(Paragraph("Tips & Tricks", h1))
story.append(Paragraph("• Set the refresh interval to <b>1 minute</b> when watching for cancellations on popular sessions", bullet))
story.append(Paragraph("• Use the <b>Time of Day</b> filter to quickly find morning or evening swims", bullet))
story.append(Paragraph("• The <b>Facilities</b> view shows bookable courts and activity slots (badminton, etc.)", bullet))
story.append(Paragraph("• Combine filters — e.g. <b>Tooting Bec Lido + Today + AM + Available</b> for this morning's swims", bullet))
story.append(Paragraph("• If the app feels slow on first launch, reduce the <b>Days to look ahead</b> in Settings", bullet))

# ── Support & credit ──
story.append(Spacer(1, 20*mm))
story.append(Paragraph("Found your swim? Brilliant.", h1))
story.append(Paragraph(
    "If Swim Balham has helped you secure a session, stay organised, or avoid missing a swim, "
    "you can support its continued development at <b>https://ko-fi.com/syrexeno</b>.", body))
story.append(Paragraph("Enjoy your session — and thank you for supporting Swim Balham.", body))
story.append(Paragraph("Data source: Places Leisure OpenActive RPDE API (CC-BY v4.0)", credit))
story.append(Paragraph("Powered by Gladstone OWS", credit))

doc.build(story)
print(f"PDF created: {OUTPUT}")
