import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
csv_morsetti = ROOT / "tabella_morsetti_blitz.csv"
csv_modbus = ROOT / "mappa_io_modbus_blitz.csv"
xlsx_out = ROOT / "blitz_mapping.xlsx"

def main():
    df_morsetti = pd.read_csv(csv_morsetti)
    df_modbus = pd.read_csv(csv_modbus)
    with pd.ExcelWriter(xlsx_out, engine="xlsxwriter") as writer:
        df_morsetti.to_excel(writer, sheet_name="Morsetti", index=False)
        df_modbus.to_excel(writer, sheet_name="I/O Modbus", index=False)
    print(f"Creato: {xlsx_out}")

if __name__ == "__main__":
    main()
