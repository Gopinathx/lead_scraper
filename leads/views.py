import asyncio
from django.shortcuts import render
from django.http import HttpResponse, StreamingHttpResponse
from django.db import close_old_connections
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from .models import Lead
from .scraper import async_stream_gmaps_scraper


def dashboard(request):
    close_old_connections()
    leads = Lead.objects.all().order_by("-created_at")
    return render(request, "leads/dashboard.html", {"leads": leads})


async def stream_logs(request):
    query = request.GET.get("query", "")
    max_results = int(request.GET.get("max_results", 5))

    async_queue = asyncio.Queue()

    # Worker task executing the scraper
    async def worker():
        try:
            await async_stream_gmaps_scraper(async_queue, query, max_results)
        except Exception as e:
            await async_queue.put(f"data: ❌ Error: {str(e)}\n\n")
        finally:
            await async_queue.put("data: COMPLETE\n\n")
            await async_queue.put(None)

    # Fire off worker in the active ASGI event loop
    asyncio.create_task(worker())

    # Native async generator for StreamingHttpResponse
    async def event_stream():
        while True:
            item = await async_queue.get()
            if item is None:
                break
            yield item

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


def export_excel(request):
    close_old_connections()
    leads = Lead.objects.all().order_by("-created_at")

    wb = Workbook()
    ws = wb.active
    ws.title = "Scraped Leads"

    ws.append(['Name', 'Phone', 'Website', 'Emails', 'Address'])

    for lead in leads:
        ws.append([lead.name, lead.phone, lead.website, lead.emails, lead.address])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = 'attachment; filename="scraped_leads.xlsx"'
    wb.save(response)
    return response


def export_pdf(request):
    close_old_connections()
    leads = Lead.objects.all().order_by("-created_at")

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="scraped_leads.pdf"'

    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Scraped Leads", styles['Heading1']))
    elements.append(Spacer(1, 12))

    data = [['Name', 'Phone', 'Website', 'Emails']]

    for lead in leads:
        data.append([
            Paragraph(lead.name or "N/A", styles['Normal']),
            Paragraph(lead.phone or "N/A", styles['Normal']),
            Paragraph(lead.website or "N/A", styles['Normal']),
            Paragraph(lead.emails or "N/A", styles['Normal']),
        ])

    table = Table(data, colWidths=[150, 100, 150, 140])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))

    elements.append(table)
    doc.build(elements)
    return response

# import queue
# import asyncio
# import threading
# import traceback
# from django.shortcuts import render
# from django.http import HttpResponse, StreamingHttpResponse
# from django.db import close_old_connections
# from openpyxl import Workbook
# from reportlab.lib.pagesizes import letter
# from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
# from reportlab.lib.styles import getSampleStyleSheet
# from reportlab.lib import colors

# from .models import Lead
# from .scraper import async_stream_gmaps_scraper


# def dashboard(request):
#     close_old_connections()
#     leads = Lead.objects.all().order_by("-created_at")
#     return render(request, "leads/dashboard.html", {"leads": leads})


# def stream_logs(request):
#     query = request.GET.get("query", "")
#     max_results = int(request.GET.get("max_results", 5))

#     q = queue.Queue()

#     def worker():
#         loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(loop)
#         try:
#             close_old_connections()
#             loop.run_until_complete(async_stream_gmaps_scraper(q, query, max_results))
#         except Exception as e:
#             print("❌ WORKER THREAD ERROR:")
#             traceback.print_exc()
#             q.put(f"data: ❌ Thread Error: {str(e)}\n\n")
#         finally:
#             loop.close()
#             close_old_connections()
#             q.put("data: COMPLETE\n\n")
#             q.put(None)

#     thread = threading.Thread(target=worker, daemon=True)
#     thread.start()

#     def event_stream():
#         while True:
#             item = q.get()
#             if item is None:
#                 break
#             yield item

#     response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
#     response['Cache-Control'] = 'no-cache'
#     response['X-Accel-Buffering'] = 'no'
#     return response


# def export_excel(request):
#     close_old_connections()
#     leads = Lead.objects.all().order_by("-created_at")

#     wb = Workbook()
#     ws = wb.active
#     ws.title = "Scraped Leads"

#     # Category removed from headers
#     ws.append(['Name', 'Phone', 'Website', 'Emails', 'Address'])

#     for lead in leads:
#         ws.append([lead.name, lead.phone, lead.website, lead.emails, lead.address])

#     response = HttpResponse(
#         content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#     )
#     response['Content-Disposition'] = 'attachment; filename="scraped_leads.xlsx"'
#     wb.save(response)
#     return response


# def export_pdf(request):
#     close_old_connections()
#     leads = Lead.objects.all().order_by("-created_at")

#     response = HttpResponse(content_type='application/pdf')
#     response['Content-Disposition'] = 'attachment; filename="scraped_leads.pdf"'

#     doc = SimpleDocTemplate(response, pagesize=letter)
#     elements = []
#     styles = getSampleStyleSheet()

#     elements.append(Paragraph("Scraped Leads", styles['Heading1']))
#     elements.append(Spacer(1, 12))

#     # Category removed from table
#     data = [['Name', 'Phone', 'Website', 'Emails']]

#     for lead in leads:
#         data.append([
#             Paragraph(lead.name, styles['Normal']),
#             Paragraph(lead.phone, styles['Normal']),
#             Paragraph(lead.website, styles['Normal']),
#             Paragraph(lead.emails, styles['Normal']),
#         ])

#     table = Table(data, colWidths=[150, 100, 150, 140])
#     table.setStyle(TableStyle([
#         ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
#         ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
#         ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
#         ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#         ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
#         ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
#     ]))

#     elements.append(table)
#     doc.build(elements)
#     return response