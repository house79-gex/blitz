# Hardware Motion Control Stack

This directory contains the hardware abstraction layer for the BLITZ CNC motion control system.

## Overview

The new motion control stack replaces the Leadshine DCS810 driver with a modular, software-controlled solution:

- **MD25HV Motor Driver**: Cytron MD25HV for PWM-based DC motor control
- **8AL-ZARD Encoder Reader**: ELTRA EH63D encoder with galvanic isolation
- **Motion Controller**: PID closed-loop control for ±0.5mm accuracy

## Components

### MD25HVDriver (`md25hv_driver.py`)

Controls the Cytron MD25HV motor driver via GPIO pins.

**Features:**
- PWM speed control (0-100%, configurable max)
- Digital direction control (forward/reverse)
- Enable/brake control
- Smooth speed ramping to prevent mechanical shock
- Emergency stop functionality
- Thread-safe operation

**GPIO Connections:**
- GPIO 12: PWM speed control (20kHz default)
- GPIO 13: Direction (0=forward, 1=reverse)
- GPIO 16: Enable/brake (1=enabled, 0=brake)

**Usage:**
```python
from ui_qt.hardware import MD25HVDriver

motor = MD25HVDriver(
    pwm_gpio=12,
    dir_gpio=13,
    enable_gpio=16,
    max_speed_percent=80.0
)

motor.enable()
motor.set_speed(50.0, smooth=True)  # 50% speed with ramping
time.sleep(5.0)
motor.stop()
motor.close()
```

### EncoderReader8ALZARD (`encoder_reader_8alzard.py`)

Reads ELTRA EH63D encoder signals through 8AL-ZARD optocoupler for galvanic isolation.

**Features:**
- Interrupt-driven quadrature x4 decoding (4000 pulses/rev)
- Index pulse (Z) detection for precise homing
- Thread-safe position tracking
- Galvanic isolation for electrical noise immunity
- High-speed reading (up to 200kHz)

**GPIO Connections:**
- GPIO 17: Encoder channel A
- GPIO 27: Encoder channel B
- GPIO 22: Index pulse Z (optional)

**Usage:**
```python
from ui_qt.hardware import EncoderReader8ALZARD

encoder = EncoderReader8ALZARD(
    gpio_a=17,
    gpio_b=27,
    gpio_z=22,
    pulses_per_mm=84.880
)

position = encoder.get_position_mm()
print(f"Current position: {position:.3f} mm")

# Wait for index pulse
if encoder.wait_for_index(timeout_s=10.0):
    print("Index pulse detected - homing complete")

encoder.close()
```

### MotionController (`motion_controller.py`)

PID-based closed-loop motion controller combining motor driver and encoder feedback.

**Features:**
- PID control for accurate positioning (±0.5mm)
- Software soft limits enforcement
- Emergency stop handling
- Smooth motion profiles
- Homing sequences with index pulse
- Real-time control loop (50Hz default)

**Usage:**
```python
from ui_qt.hardware import MD25HVDriver, EncoderReader8ALZARD, MotionController

motor = MD25HVDriver(pwm_gpio=12, dir_gpio=13, enable_gpio=16)
encoder = EncoderReader8ALZARD(gpio_a=17, gpio_b=27, gpio_z=22)

controller = MotionController(
    motor=motor,
    encoder=encoder,
    min_position_mm=250.0,
    max_position_mm=4000.0,
    pid_kp=2.0,
    pid_ki=0.5,
    pid_kd=0.1
)

# Start control loop
controller.start()

# Move to target position
def on_complete(success, message):
    print(f"Move complete: {message}")

controller.move_to(1000.0, callback=on_complete)

# Wait for completion
while controller.is_moving():
    time.sleep(0.1)

controller.close()
```

## Configuration

Hardware settings are defined in `data/hardware_config.json` under the `motion_control` section:

```json
{
  "motion_control": {
    "gpio_motor": {
      "pwm_pin": 12,
      "dir_pin": 13,
      "enable_pin": 16
    },
    "gpio_encoder": {
      "channel_a_pin": 17,
      "channel_b_pin": 27,
      "index_z_pin": 22
    },
    "encoder_calibration": {
      "pulses_per_mm": 84.880
    },
    "pid_parameters": {
      "kp": 2.0,
      "ki": 0.5,
      "kd": 0.1
    }
  }
}
```

## Integration with RealMachine

The `RealMachine` class automatically uses the new motion stack when available:

```python
from ui_qt.machine.real_machine import RealMachine

machine = RealMachine(
    serial_port="/dev/ttyUSB0",
    use_new_motion_stack=True  # Enable new stack (default)
)

# Use machine as before - motion control is handled automatically
machine.command_move(1500.0, ang_sx=45.0, ang_dx=0.0)
```

The integration maintains backward compatibility with the legacy GPIO-based system.

## Testing

### Live Encoder Monitoring

```bash
python -m tests.hardware.test_encoder_live
```

Displays real-time encoder position, pulse count, and index detection.

### Motor Driver Test Suite

```bash
python -m tests.hardware.test_motor_driver
```

⚠️ **WARNING**: Motor will spin! Ensure motor is disconnected from load.

Tests include:
- Basic speed control
- Direction changes
- Speed ramping profiles
- Emergency stop

### Encoder Calibration

```bash
python tools/calibrate_encoder.py
```

Interactive tool to calibrate the `pulses_per_mm` parameter by measuring actual movement.

## Safety Features

1. **Soft Limits**: Automatic stopping at configured position limits
2. **Emergency Stop**: Immediate motor disable with brake engagement
3. **Speed Ramping**: Smooth acceleration/deceleration to prevent mechanical shock
4. **Thread Safety**: All position tracking is thread-safe
5. **Galvanic Isolation**: Encoder signals isolated via optocoupler
6. **Hardware Interlocks**: Emergency stop integrated with Modbus safety chain

## Dependencies

- `pigpio`: GPIO control library (requires `pigpiod` daemon)
- `simple-pid`: PID controller implementation (v2.0.0+)

## Hardware Setup

### Prerequisites

1. Raspberry Pi with GPIO access
2. `pigpiod` daemon running: `sudo pigpiod`
3. Proper GPIO pin configuration in `hardware_config.json`

### Wiring

**Motor Driver (MD25HV):**
- Connect PWM, DIR, EN pins to RPi GPIO 12, 13, 16
- Motor power supply: 48V DC (separate from RPi)
- Motor outputs to DC motor

**Encoder (8AL-ZARD + ELTRA EH63D):**
- Encoder 12V power → 8AL-ZARD input side
- 8AL-ZARD output (3.3V) → RPi GPIO 17, 27, 22
- Ensure proper grounding

**Modbus I/O (Unchanged):**
- RS485 connection via `/dev/ttyUSB0`
- Brake, clutch, vise controls via Modbus

## Troubleshooting

### "pigpio not available"
- Install: `pip install pigpio`
- Start daemon: `sudo pigpiod`

### "Cannot connect to pigpiod daemon"
- Check daemon status: `sudo systemctl status pigpiod`
- Restart daemon: `sudo systemctl restart pigpiod`

### Encoder not detecting pulses
- Verify GPIO connections (17, 27, 22)
- Check 8AL-ZARD power supply (12V input, 3.3V output)
- Test with `test_encoder_live.py`

### Motor not responding
- Verify GPIO connections (12, 13, 16)
- Check motor driver power supply (48V)
- Test with `test_motor_driver.py` (motor disconnected first)

### Position accuracy issues
- Run encoder calibration: `python tools/calibrate_encoder.py`
- Tune PID parameters (start with Kp, then Ki, then Kd)
- Check for mechanical backlash

## Performance

- **Position Accuracy**: ±0.5mm (with proper calibration)
- **Encoder Resolution**: 84.880 pulses/mm (4000 pulses/rev @ 60mm pulley)
- **Control Loop Frequency**: 50Hz (configurable)
- **Maximum Speed**: 2500 mm/s (hardware limit)
- **Update Latency**: <20ms (interrupt-driven)

## Advantages over DCS810

1. **Software Control**: Flexible PID tuning and motion profiles
2. **Direct Integration**: No RS232 communication overhead
3. **Better Diagnostics**: Real-time state monitoring and logging
4. **Lower Cost**: Commodity hardware vs. proprietary driver
5. **Easier Maintenance**: Standard components, open-source code
6. **Enhanced Safety**: Software-based safety checks

## Future Enhancements

- [ ] Velocity feedforward for smoother acceleration
- [ ] S-curve acceleration profiles
- [ ] Multi-axis coordination
- [ ] Encoder fault detection and recovery
- [ ] Self-tuning PID parameters
- [ ] Motion recording and playback

## License

Part of the BLITZ CNC control system.

---

*Last Updated: 2026-01-10*
*Implemented by: GitHub Copilot*
