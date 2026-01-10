"""
Live encoder monitoring test script.

Tests the 8AL-ZARD encoder reader in real-time, displaying:
- Position in mm
- Raw pulse count
- Index pulse detection
- Update rate

Usage:
    python -m tests.hardware.test_encoder_live

Controls:
    Ctrl+C to exit
    
Requirements:
    - pigpiod daemon running
    - Encoder connected to GPIO 17/27/22
    - Physical access to move encoder
"""

import time
import signal
import sys
from typing import Optional

try:
    from qt6_app.ui_qt.hardware.encoder_reader_8alzard import EncoderReader8ALZARD
except ImportError:
    print("Error: Could not import encoder reader")
    print("Run from repository root: python -m tests.hardware.test_encoder_live")
    sys.exit(1)


class EncoderMonitor:
    """Monitor encoder in real-time."""
    
    def __init__(self):
        self.running = False
        self.encoder: Optional[EncoderReader8ALZARD] = None
        
        # Setup signal handler for graceful exit
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, sig, frame):
        """Handle Ctrl+C gracefully."""
        print("\n\n🛑 Stopping encoder monitor...")
        self.running = False
    
    def run(self):
        """Run the encoder monitoring loop."""
        print("=" * 70)
        print("ENCODER LIVE MONITOR - 8AL-ZARD via ELTRA EH63D")
        print("=" * 70)
        print()
        
        # Initialize encoder
        print("Initializing encoder reader...")
        self.encoder = EncoderReader8ALZARD(
            gpio_a=17,
            gpio_b=27,
            gpio_z=22,
            pulses_per_mm=84.880,
            enable_index=True
        )
        
        if not self.encoder.is_connected():
            print("❌ Failed to connect to encoder")
            print("   Make sure pigpiod daemon is running: sudo pigpiod")
            return
        
        print("✅ Encoder connected successfully")
        print()
        print("Monitor starting... (Press Ctrl+C to exit)")
        print("-" * 70)
        print()
        
        # Setup index pulse callback
        def on_index_pulse(pulse_count):
            print(f"\n🎯 INDEX PULSE DETECTED at pulse count: {pulse_count}\n")
        
        self.encoder.set_index_callback(on_index_pulse)
        
        self.running = True
        last_pulse_count = 0
        last_time = time.time()
        update_count = 0
        
        try:
            while self.running:
                # Get current state
                state = self.encoder.get_state()
                position_mm = state["position_mm"]
                pulse_count = state["pulse_count"]
                
                # Calculate update rate
                now = time.time()
                elapsed = now - last_time
                pulse_diff = pulse_count - last_pulse_count
                
                if elapsed >= 0.1:  # Update display every 100ms
                    # Calculate pulse rate
                    pulse_rate = pulse_diff / elapsed if elapsed > 0 else 0
                    
                    # Clear previous lines (ANSI escape)
                    if update_count > 0:
                        print("\033[F\033[K" * 4, end="")
                    
                    # Display current state
                    print(f"Position:    {position_mm:10.3f} mm")
                    print(f"Pulse Count: {pulse_count:10d}")
                    print(f"Pulse Rate:  {pulse_rate:10.1f} pulses/s")
                    print(f"Index:       {'✅ DETECTED' if state['index_detected'] else '⏳ Waiting...'}")
                    
                    last_pulse_count = pulse_count
                    last_time = now
                    update_count += 1
                
                time.sleep(0.01)  # 100Hz update rate
                
        except Exception as e:
            print(f"\n❌ Error during monitoring: {e}")
        
        finally:
            # Cleanup
            print("\n")
            print("-" * 70)
            print("Final state:")
            final_state = self.encoder.get_state()
            print(f"  Position:    {final_state['position_mm']:.3f} mm")
            print(f"  Pulse Count: {final_state['pulse_count']}")
            print(f"  Index:       {'Detected' if final_state['index_detected'] else 'Not detected'}")
            
            self.encoder.close()
            print("\n✅ Encoder monitor closed")


def main():
    """Main entry point."""
    monitor = EncoderMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
