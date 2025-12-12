from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
import csv
from pathlib import Path

# Paths relative to docs/blitz/scripts/
SCRIPT_DIR = Path(__file__).resolve().parent
TABLES_DIR = SCRIPT_DIR.parent / "tables"
OUTPUTS_DIR = SCRIPT_DIR.parent / "outputs"

CSV_MORSETTI = TABLES_DIR / "tabella_morsetti_blitz.csv"
CSV_MODBUS = TABLES_DIR / "mappa_io_modbus_blitz.csv"
CSV_DRIVER = TABLES_DIR / "morsetti_driver_dcs810.csv"
PDF_MORSETTI = OUTPUTS_DIR / "pdf_morsetti_blitz.pdf"
PDF_MODBUS = OUTPUTS_DIR / "pdf_mappa_io_modbus_blitz.pdf"
PDF_DRIVER = OUTPUTS_DIR / "pdf_morsetti_driver_dcs810.pdf"
PDF_LISTA = OUTPUTS_DIR / "pdf_lista_componenti_fusibili.pdf"

styles = getSampleStyleSheet()
title_style = styles['Title']
header_style = styles['Heading2']
normal_style = styles['BodyText']

def read_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
    return rows

def make_table(data, col_widths=None, repeat_rows=1):
    tbl = Table(data, colWidths=col_widths, repeatRows=repeat_rows)
    style = TableStyle([
        ('GRID', (0,0), (-1,-1), 0.25, colors.black),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ])
    tbl.setStyle(style)
    return tbl

def build_pdf_table(title_text, csv_path, pdf_path, col_widths=None):
    data = read_csv(csv_path)
    story = []
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 6*mm))
    story.append(make_table(data, col_widths, repeat_rows=1))
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                            leftMargin=12*mm, rightMargin=12*mm,
                            topMargin=12*mm, bottomMargin=15*mm)
    doc.build(story)

def build_pdf_lista_componenti(pdf_path):
    story = []
    story.append(Paragraph("Lista Componenti e Fusibili consigliati", title_style))
    story.append(Spacer(1, 6*mm))

    comp = [
        ["Componente", "Modello", "Funzione", "Note"],
        ["Alimentatore 48V", "Mean Well TDR-960-48", "48V DC per Driver", "Montaggio DIN; ventilazione necessaria"],
        ["Alimentatore 24V", "Mean Well SDR-240-24", "24V DC EV/I/O", "Ramo con fusibili F1..F4"],
        ["Alimentatore 12V", "Mean Well SDR-120-12", "12V ausiliari", "Servizi vari"],
        ["Alimentatore 5V", "Mean Well MDR-10-5", "Arduino/ESP32", "RPi su PSU originale 230V"],
        ["Driver motore", "Leadshine DCS810", "Servo/DC 48V", "Comando RS232; encoder ELTRA"],
        ["Moduli I/O+Relè", "Waveshare 8IN/8OUT (x2)", "I/O campo e relè", "Modbus RTU RS485 (ID 1 e 2)"],
        ["Raspberry Pi 5", "RPi 5 + Waveshare USB 4CH", "Supervisione e logica", "HDMI e USB lato DX"],
        ["Arduino Nano", "Nano + MAX485 + MT6701 (x2)", "Angolo teste SX/DX", "SPI locale, RS485 quadro"],
    ]
    story.append(Paragraph("Componenti principali", header_style))
    story.append(Spacer(1, 3*mm))
    story.append(make_table(comp, col_widths=[40*mm, 50*mm, 40*mm, 60*mm]))
    story.append(Spacer(1, 6*mm))

    fus = [
        ["Fusibile", "Ramo", "Valore indicativo", "Note"],
        ["F1", "24V I/O + Sensori", "1–2 A", "Adeguare a carico reale; LED guasto consigliato"],
        ["F2", "24V EV Testa SX", "1–2 A", "Inclinazioni + morsa SX; doppie bobine"],
        ["F3", "24V EV Testa DX", "1–2 A", "Inclinazioni + morsa DX; doppie bobine"],
        ["F4", "24V Frizione + Freno", "2–3 A", "Bobine con assorbimento maggiore"],
        ["F5", "5V Servizi", "1 A", "Arduino/ESP32; RPi su PSU dedicata 230V"],
        ["F6", "12V Aux", "1–2 A", "Servizi ausiliari"],
    ]
    story.append(Paragraph("Fusibili consigliati", header_style))
    story.append(Spacer(1, 3*mm))
    story.append(make_table(fus, col_widths=[20*mm, 55*mm, 30*mm, 75*mm]))
    story.append(Spacer(1, 6*mm))

    note = [
        ["Note di cablaggio"],
        ["Separare 230VAC e potenze dai segnali/RS485 nelle canalette 40x40."],
        ["Schermi/Calze a PE lato quadro (barra PE) — un solo lato."],
        ["Diodi di flyback sulle bobine EV/frizione/freno se non integrati nei moduli."],
        ["Terminazione 120Ω RS485 solo sull’ultimo nodo (Arduino DX)."],
        ["Interlock software: disabilitare comandi attuatori durante EMERG o taglio in corso."],
        ["Inibizione lama: contatto NC in serie alla bobina EV (SX/DX)."],
        ["Inibizione APRI morsa per lato: contatto NC in serie sul ramo APRI (SX o DX) in modalità speciali."],
    ]
    story.append(Paragraph("Note di cablaggio e sicurezza", header_style))
    story.append(Spacer(1, 3*mm))
    story.append(make_table(note, col_widths=[180*mm]))

    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                            leftMargin=12*mm, rightMargin=12*mm,
                            topMargin=12*mm, bottomMargin=15*mm)
    doc.build(story)


def main():
    build_pdf_table("Tabella morsetti — Blitz retrofit", CSV_MORSETTI, PDF_MORSETTI,
                    col_widths=[20*mm, 20*mm, 45*mm, 20*mm, 55*mm, 20*mm])
    build_pdf_table("Mappa I/O Modbus — Blitz retrofit", CSV_MODBUS, PDF_MODBUS,
                    col_widths=[35*mm, 20*mm, 15*mm, 25*mm, 20*mm, 55*mm, 25*mm, 35*mm])
    build_pdf_table("Morsetti Driver DCS810", CSV_DRIVER, PDF_DRIVER,
                    col_widths=[35*mm, 30*mm, 30*mm, 60*mm, 30*mm])
    build_pdf_lista_componenti(PDF_LISTA)
    print(f"Creati:\n - {PDF_MORSETTI}\n - {PDF_MODBUS}\n - {PDF_DRIVER}\n - {PDF_LISTA}")

if __name__ == "__main__":
    main()
