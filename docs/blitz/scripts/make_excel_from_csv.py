import pandas as pd
from pathlib import Path

# Paths relative to docs/blitz/scripts/
SCRIPT_DIR = Path(__file__).resolve().parent
TABLES_DIR = SCRIPT_DIR.parent / "tables"
OUTPUTS_DIR = SCRIPT_DIR.parent / "outputs"

csv_morsetti = TABLES_DIR / "tabella_morsetti_blitz.csv"
csv_modbus = TABLES_DIR / "mappa_io_modbus_blitz.csv"
xlsx_out = OUTPUTS_DIR / "blitz_mapping.xlsx"

def main():
    df_morsetti = pd.read_csv(csv_morsetti)
    df_modbus = pd.read_csv(csv_modbus)
    
    # Dati per il terzo foglio "Lista componenti"
    componenti = [
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
    
    # Fusibili da appendere dopo 3 righe vuote
    fusibili = [
        ["", "", "", ""],
        ["", "", "", ""],
        ["", "", "", ""],
        ["Fusibile", "Ramo", "Valore indicativo", "Note"],
        ["F1", "24V I/O + Sensori", "1–2 A", "Adeguare a carico reale; LED guasto consigliato"],
        ["F2", "24V EV Testa SX", "1–2 A", "Inclinazioni + morsa SX; doppie bobine"],
        ["F3", "24V EV Testa DX", "1–2 A", "Inclinazioni + morsa DX; doppie bobine"],
        ["F4", "24V Frizione + Freno", "2–3 A", "Bobine con assorbimento maggiore"],
        ["F5", "5V Servizi", "1 A", "Arduino/ESP32; RPi su PSU dedicata 230V"],
        ["F6", "12V Aux", "1–2 A", "Servizi ausiliari"],
    ]
    
    # Unisci componenti e fusibili
    lista_completa = componenti + fusibili
    df_lista = pd.DataFrame(lista_completa[1:], columns=lista_completa[0])
    
    with pd.ExcelWriter(xlsx_out, engine="xlsxwriter") as writer:
        df_morsetti.to_excel(writer, sheet_name="Morsetti", index=False)
        df_modbus.to_excel(writer, sheet_name="IO Modbus", index=False)
        df_lista.to_excel(writer, sheet_name="Lista componenti", index=False)
    
    print(f"Creato: {xlsx_out}")

if __name__ == "__main__":
    main()
