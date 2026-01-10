"""
Motor driver test script.

Tests the MD25HV motor driver with various speed profiles:
- Forward/reverse direction
- Speed ramping
- Emergency stop
- Enable/disable

Usage:
    python -m tests.hardware.test_motor_driver

⚠️  WARNING: Motor will spin during test!
    - Ensure motor is disconnected from load
    - Test in safe environment
    - Keep emergency stop button ready

Requirements:
    - pigpiod daemon running
    - Motor driver connected to GPIO 12/13/16
    - Motor properly connected with power supply
"""

import time
import signal
import sys

try:
    from qt6_app.ui_qt.hardware.md25hv_driver import MD25HVDriver
except ImportError:
    print("Error: Could not import motor driver")
    print("Run from repository root: python -m tests.hardware.test_motor_driver")
    sys.exit(1)


class MotorTester:
    """Interactive motor driver tester."""
    
    def __init__(self):
        self.motor = None
        self.running = False
        
        # Setup signal handler
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, sig, frame):
        """Handle Ctrl+C gracefully."""
        print("\n\n🛑 Emergency stop activated!")
        if self.motor:
            self.motor.emergency_stop()
        self.running = False
    
    def _print_state(self):
        """Print current motor state."""
        state = self.motor.get_state()
        print(f"\n📊 Motor State:")
        print(f"   Connected:     {state['connected']}")
        print(f"   Enabled:       {state['enabled']}")
        print(f"   Current Speed: {state['current_speed']:.1f}%")
        print(f"   Target Speed:  {state['target_speed']:.1f}%")
        print(f"   Direction:     {state['direction']}")
        print(f"   Ramping:       {state['ramping']}")
        print(f"   Emergency:     {state['emergency_stop']}")
    
    def test_basic_control(self):
        """Test basic motor control."""
        print("\n" + "=" * 70)
        print("TEST 1: Basic Control")
        print("=" * 70)
        
        print("\n1. Enabling motor...")
        self.motor.enable()
        time.sleep(0.5)
        self._print_state()
        
        print("\n2. Forward 20% speed (smooth ramp)...")
        self.motor.set_speed(20.0, smooth=True)
        time.sleep(3.0)
        self._print_state()
        
        print("\n3. Increase to 40% speed...")
        self.motor.set_speed(40.0, smooth=True)
        time.sleep(3.0)
        self._print_state()
        
        print("\n4. Stopping (smooth ramp)...")
        self.motor.stop(immediate=False)
        time.sleep(2.0)
        self._print_state()
        
        print("\n✅ Test 1 complete")
    
    def test_direction_change(self):
        """Test direction changes."""
        print("\n" + "=" * 70)
        print("TEST 2: Direction Changes")
        print("=" * 70)
        
        print("\n1. Forward 30% speed...")
        self.motor.set_speed(30.0, smooth=True)
        time.sleep(3.0)
        self._print_state()
        
        print("\n2. Stopping before direction change...")
        self.motor.stop(immediate=False)
        time.sleep(2.0)
        
        print("\n3. Reverse 30% speed (negative value)...")
        self.motor.set_speed(-30.0, smooth=True)
        time.sleep(3.0)
        self._print_state()
        
        print("\n4. Stopping...")
        self.motor.stop(immediate=False)
        time.sleep(2.0)
        self._print_state()
        
        print("\n✅ Test 2 complete")
    
    def test_speed_profiles(self):
        """Test different speed profiles."""
        print("\n" + "=" * 70)
        print("TEST 3: Speed Profiles")
        print("=" * 70)
        
        speeds = [10, 20, 30, 40, 30, 20, 10, 0]
        
        for speed in speeds:
            print(f"\nSetting speed to {speed}%...")
            self.motor.set_speed(speed, smooth=True)
            time.sleep(1.5)
            self._print_state()
        
        print("\n✅ Test 3 complete")
    
    def test_emergency_stop(self):
        """Test emergency stop."""
        print("\n" + "=" * 70)
        print("TEST 4: Emergency Stop")
        print("=" * 70)
        
        print("\n1. Accelerating to 50% speed...")
        self.motor.set_speed(50.0, smooth=True)
        time.sleep(2.0)
        self._print_state()
        
        print("\n2. EMERGENCY STOP!")
        self.motor.emergency_stop()
        time.sleep(0.5)
        self._print_state()
        
        print("\n3. Resetting emergency stop...")
        self.motor.reset_emergency()
        time.sleep(0.5)
        
        print("\n4. Re-enabling motor...")
        self.motor.enable()
        time.sleep(0.5)
        self._print_state()
        
        print("\n✅ Test 4 complete")
    
    def run(self):
        """Run all motor tests."""
        print("=" * 70)
        print("MD25HV MOTOR DRIVER TEST SUITE")
        print("=" * 70)
        print()
        print("⚠️  WARNING: Motor will spin during this test!")
        print("   Make sure:")
        print("   - Motor is disconnected from load")
        print("   - Test area is clear and safe")
        print("   - Emergency stop is available")
        print()
        input("Press ENTER to continue or Ctrl+C to abort...")
        print()
        
        # Initialize motor driver
        print("Initializing MD25HV driver...")
        self.motor = MD25HVDriver(
            pwm_gpio=12,
            dir_gpio=13,
            enable_gpio=16,
            max_speed_percent=60.0,  # Limit to 60% for safety during tests
            ramp_time_s=0.8
        )
        
        if not self.motor.is_connected():
            print("❌ Failed to connect to motor driver")
            print("   Make sure pigpiod daemon is running: sudo pigpiod")
            return
        
        print("✅ Motor driver connected successfully")
        print()
        
        self.running = True
        
        try:
            # Run test sequence
            self.test_basic_control()
            time.sleep(2.0)
            
            self.test_direction_change()
            time.sleep(2.0)
            
            self.test_speed_profiles()
            time.sleep(2.0)
            
            self.test_emergency_stop()
            
            print("\n" + "=" * 70)
            print("ALL TESTS COMPLETE")
            print("=" * 70)
            
        except Exception as e:
            print(f"\n❌ Error during testing: {e}")
            if self.motor:
                self.motor.emergency_stop()
        
        finally:
            # Cleanup
            print("\nCleaning up...")
            if self.motor:
                self.motor.close()
            print("✅ Motor driver test completed")


def main():
    """Main entry point."""
    tester = MotorTester()
    tester.run()


if __name__ == "__main__":
    main()
