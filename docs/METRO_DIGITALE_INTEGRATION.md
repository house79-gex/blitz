# Metro Digitale Bluetooth Integration

## Overview

The Metro Digitale integration adds wireless Bluetooth Low Energy (BLE) support for the ESP32-S3 digital caliper with 5" touch display. This allows operators to send measurements directly from the metro device to the Blitz CNC saw application with automatic routing to Semi-Auto or Automatico pages based on the mode selected on the metro's display.

## Features

- **Wireless BLE Connection**: No cables needed, operator can move freely
- **Automatic Mode Routing**: Metro sends target mode ("semi_auto" or "automatico") in JSON payload
- **Manual Input Preserved**: Bluetooth is complementary, not required - manual input always available
- **Auto-Reconnect**: Automatically reconnects to last known device on app startup
- **Global Status Widget**: Connection status visible in all pages (header)
- **Measurement History**: Tracks last 10 measurements with timestamps and target modes
- **Multi-Sensory Feedback**: Visual (LED) and audio (buzzer) feedback on metro device

## Hardware Specifications

### Metro Digitale ESP32-S3

- **Display**: 5" capacitive touch screen (800x480)
- **Encoder**: AS5600 magnetic encoder for precision measurements
- **Bluetooth**: BLE 5.0
- **Physical Controls**: SEND button (GPIO 25) to transmit measurement
- **Indicators**: Status LED (GPIO 27)
- **Audio**: Buzzer (GPIO 14) for feedback

### Touch UI Mode Switch

The metro has a touch UI switch on its display to select target mode:

```
┌──────────────────────────────────┐
│  ╔═══════════╗   ┌───────────┐  │
│  ║ SEMI-AUTO ║   │ AUTOMATICO│  │
│  ║    🔧     ║   │    ⚙️     │  │
│  ╚═══════════╝   └───────────┘  │
│   🟢 ATTIVO       ⚪ Non attivo  │
└──────────────────────────────────┘
```

## BLE Protocol

### Service & Characteristics

```python
SERVICE_UUID = "12345678-1234-1234-1234-123456789abc"
CHAR_TX_UUID = "12345678-1234-1234-1234-123456789abd"  # Metro → App
CHAR_RX_UUID = "12345678-1234-1234-1234-123456789abe"  # App → Metro
DEVICE_NAME  = "Metro-Digitale"
```

### JSON Payload Format

```json
{
  "type": "fermavetro",
  "misura_mm": 1250.5,
  "auto_start": true,
  "mode": "semi_auto"
}
```

**Fields**:
- `type`: Metro's internal mode ("fermavetro", "vetri", "astine", "calibro") - informational only
- `misura_mm`: Measurement in millimeters (required)
- `auto_start`: If true, app can auto-trigger positioning (user preference)
- `mode`: **Target mode** - "semi_auto" or "automatico" (set by operator on metro's touch UI)

## Architecture

### Singleton Pattern

The `MetroDigitaleManager` is a singleton service that manages the global BLE connection:

```
┌─────────────────────────────────────────────────┐
│  MetroDigitaleManager (Singleton)               │
│  ├─ Single BLE connection shared across pages   │
│  ├─ Auto-reconnect on app startup               │
│  ├─ Parse JSON payload                          │
│  ├─ Route measurements by "mode" field          │
│  └─ Emit Qt signals: measurement_received()     │
└──────────────┬──────────────────────────────────┘
               │
      ┌────────┴────────┐
      ▼                 ▼
┌─────────────┐   ┌─────────────┐
│ Semi-Auto   │   │ Automatico  │
│ (Page)      │   │ (Page)      │
├─────────────┤   ├─────────────┤
│ If mode=    │   │ If mode=    │
│ "semi_auto" │   │ "automatico"│
│ → Populate  │   │ → Add to    │
│   length    │   │   batch     │
│ → Auto-pos  │   │   list      │
│   (optional)│   │             │
└─────────────┘   └─────────────┘
```

## Usage

### Initial Setup

1. **Install Dependencies**:
   ```bash
   pip install bleak>=0.21.0
   ```

2. **Power On Metro Digitale**: The device will start advertising as "Metro-Digitale"

### Connecting

#### Semi-Auto Page

1. Navigate to **Semi-Auto** page
2. Locate the **Metro Digitale Bluetooth** section (blue border)
3. Click **🔍 Cerca** to scan for devices
4. Select the metro from the dropdown (e.g., "Metro-Digitale-XX")
5. Click **🔌 Connetti** to connect
6. Status changes to **🟢 Connesso**

#### Automatico Page

1. Navigate to **Automatico** page
2. Locate the **Metro Digitale** section in the right panel
3. Follow same connection steps as Semi-Auto

### Sending Measurements

1. **On Metro Device**:
   - Select mode on touch UI (SEMI-AUTO or AUTOMATICO)
   - Take measurement
   - Press physical **SEND** button
   - Metro gives feedback (buzzer beep + LED blink)

2. **In Blitz App**:
   - **Semi-Auto**: Length field populated with measurement
   - **Automatico**: Measurement added to cutlist table
   - Toast notification confirms receipt
   - History updated with timestamp

### Auto-Position (Semi-Auto Only)

Enable the **⚡ Auto-Posiziona al ricevimento misura** checkbox to automatically start positioning when a measurement is received.

## Global Status Widget

The metro connection status is visible in the header of all pages:

- **📡 ⚪ Metro**: Disconnected
- **📡 🟢 Metro**: Connected
- **❌ Button**: Click to disconnect (visible when connected)

## Settings

Settings are automatically saved:

- `metro_auto_reconnect`: Enable/disable auto-reconnect (default: `true`)
- `metro_last_device_address`: Last connected device address (saved automatically)

Settings are stored in `~/.blitz/settings.json`.

## Measurement History

### Semi-Auto Page
- Shows last **10 measurements**
- Format: `✓ 1250.5mm → SEMI-AUTO @ 14:23:45`

### Automatico Page
- Shows last **5 measurements** (compact)
- Format: `1250.5mm @ 14:23:45`

## Troubleshooting

### Metro Device Not Found

1. Ensure metro is powered on
2. Check metro is advertising (Bluetooth enabled)
3. Device name must contain "Metro-Digitale"
4. Try moving closer to reduce interference

### Connection Fails

1. Restart metro device
2. Click **🔍 Cerca** to scan again
3. Check Bluetooth is enabled on computer
4. Verify no other app is connected to metro

### Measurements Not Received

1. Check connection status (should be 🟢)
2. Verify correct mode selected on metro display
3. Check page is visible (signals only connected when page shown)
4. Look for errors in logs

### Bleak Not Available

If you see "Metro Digitale non disponibile (bleak non installato)":

```bash
pip install bleak>=0.21.0
```

## Development

### Files Structure

```
qt6_app/ui_qt/
├── services/
│   └── metro_digitale_manager.py    # Singleton BLE manager
├── widgets/
│   └── metro_status_widget.py       # Global status widget
└── pages/
    ├── semi_auto_page.py            # Semi-Auto integration
    └── automatico_page.py           # Automatico integration

tests/
└── test_metro_digitale_manager.py   # Unit tests
```

### Testing

Run unit tests:

```bash
python -m pytest tests/test_metro_digitale_manager.py -v
```

All 9 tests should pass:
- Singleton pattern
- Initialization
- Availability check
- Page management
- JSON parsing
- Error handling
- Connection status
- History management

### Manual Testing (Hardware Required)

1. Power on Metro Digitale
2. Start Blitz app: `python qt6_app/main_qt.py`
3. Connect metro from Semi-Auto page
4. Switch mode on metro display
5. Send measurements
6. Verify routing and population

## Benefits

✅ **Wireless Operation**: Operator freedom of movement  
✅ **No Transcription Errors**: Direct digital measurement  
✅ **Operator Controls Routing**: Switch mode on metro display  
✅ **Multi-Sensory Feedback**: Visual (LED) + Audio (buzzer)  
✅ **Manual Input Preserved**: Bluetooth is optional, complementary  
✅ **Auto-Reconnect**: Seamless workflow continuation  
✅ **History Tracking**: Audit trail of measurements

## Future Enhancements

- [ ] Measurement list export (CSV/Excel)
- [ ] Configurable validation rules
- [ ] Multiple metro device support
- [ ] Measurement statistics
- [ ] Custom measurement profiles
