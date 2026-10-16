"""Render the project learning guide with embedded Vietnamese fonts."""
from pathlib import Path
import re
from html import escape

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted
from reportlab.lib.pagesizes import A4

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/pdf/ViToxic-Analyzer.pdf'
OUT.parent.mkdir(parents=True, exist_ok=True)
for name, file in [('Arial', 'arial.ttf'), ('Arial-Bold', 'arialbd.ttf'),
                   ('Arial-Italic', 'ariali.ttf'), ('Mono', 'consola.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(Path('C:/Windows/Fonts') / file)))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold', italic='Arial-Italic', boldItalic='Arial-Bold')
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyVI', fontName='Arial', fontSize=10, leading=15, spaceAfter=7))
styles.add(ParagraphStyle(name='CellVI', fontName='Arial', fontSize=8.3, leading=12, spaceAfter=1))
styles.add(ParagraphStyle(name='CodeVI', fontName='Mono', fontSize=7.1, leading=10, spaceBefore=6, spaceAfter=8))
for style, size in [('Title', 25), ('Heading1', 17), ('Heading2', 12)]:
    styles[style].fontName = 'Arial-Bold'
    styles[style].fontSize = size
    styles[style].leading = size * 1.3
    styles[style].textColor = colors.HexColor('#163b51')
    styles[style].spaceBefore = 14
    styles[style].spaceAfter = 9

def inline(text):
    text = escape(text.replace('\u2011', '-'))
    text = re.sub(r'`([^`]+)`', r'<font name="Mono">\1</font>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    return text

def paragraph(text, style='BodyVI'):
    return Paragraph(inline(text), styles[style])

lines = (ROOT / 'ViToxic-Analyzer.md').read_text(encoding='utf-8').splitlines()
story = []
i = 0
while i < len(lines):
    line = lines[i]
    if not line.strip():
        i += 1
        continue
    if line.startswith('```'):
        block = []
        i += 1
        while i < len(lines) and not lines[i].startswith('```'):
            block.append(lines[i])
            i += 1
        if any('😊' in row for row in block):
            story.append(paragraph('Trong đoạn mã PDF, emoji được biểu diễn bằng escape Unicode \\U0001f60a để hiển thị và sao chép ổn định.'))
            block = [row.replace('😊', r'\U0001f60a') for row in block]
        # Preserve diagrams; wrap long commands without losing characters.
        wrapped = []
        for row in block:
            while len(row) > 103:
                wrapped.append(row[:103])
                row = '    ' + row[103:]
            wrapped.append(row)
        story.append(Preformatted('\n'.join(wrapped), styles['CodeVI']))
        i += 1
        continue
    if line.startswith('|'):
        rows = []
        while i < len(lines) and lines[i].startswith('|'):
            cells = [s.strip() for s in lines[i].strip().strip('|').split('|')]
            if not all(re.fullmatch(r':?-+:?', c) for c in cells):
                rows.append([paragraph(c, 'CellVI') for c in cells])
            i += 1
        n = len(rows[0])
        available = A4[0] - 88
        ratios = {2: [0.32, 0.68], 3: [0.23, 0.37, 0.40], 4: [0.12, 0.22, 0.30, 0.36],
                  5: [0.17, 0.30, 0.17, 0.18, 0.18]}.get(n, [1 / n] * n)
        table = Table(rows, colWidths=[available * r for r in ratios], repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dcebf2')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f8fa')]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#cedae0')),
            ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.extend([table, Spacer(1, 10)])
        continue
    if line.startswith('# '):
        story.append(paragraph(line[2:], 'Title'))
    elif line.startswith('## '):
        story.append(paragraph(line[3:], 'Heading1'))
    elif line.startswith('### '):
        story.append(paragraph(line[4:], 'Heading2'))
    elif line.startswith('>'):
        story.append(paragraph(line.lstrip('> ').strip()))
    elif line.startswith('- [ ] '):
        story.append(paragraph('[  ] ' + line[6:]))
    elif line.startswith('- '):
        story.append(paragraph('• ' + line[2:]))
    else:
        story.append(paragraph(line))
    i += 1

def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('Arial', 8)
    canvas.setFillColor(colors.HexColor('#536773'))
    canvas.drawString(44, 25, 'ViToxic-Analyzer | Vừa làm project vừa học')
    canvas.drawRightString(A4[0] - 44, 25, str(doc.page))
    canvas.restoreState()

doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=44, rightMargin=44,
                        topMargin=38, bottomMargin=45, title='ViToxic-Analyzer',
                        author='ViToxic-Analyzer', pageCompression=1)
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
