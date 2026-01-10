"""
Encoder calibration tool.

Helps calibrate the pulses_per_mm parameter for accurate position tracking.

The tool guides you through:
1. Moving the carriage a known distance
2. Recording encoder pulses
3. Calculating accurate pulses_per_mm ratio
4. Saving to configuration file

Usage:
    python tools/calibrate_encoder.py

Requirements:
    - pigpiod daemon running
    - Encoder connected and working
    - Ability to move carriage precisely (measuring tape)
"""

import sys
import os
import json
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from qt6_app.ui_qt.hardware.encoder_reader_8alzard import EncoderReader8ALZARD
except ImportError:
    print("Error: Could not import encoder reader")
    print("Run from repository root: python tools/calibrate_encoder.py")
    sys.exit(1)


class EncoderCalibrator:
    """Interactive encoder calibration tool."""
    
    def __init__(self):
        self.encoder = None
        self.config_path = os.path.join(
            os.path.dirname(__file__),
            "../data/hardware_config.json"
        )
    
    def load_config(self) -> dict:
        """Load hardware configuration."""
        try:
            with open(self.config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load config: {e}")
            return {}
    
    def save_config(self, config: dict):
        """Save hardware configuration."""
        try:
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2)
            print(f"✅ Configuration saved to {self.config_path}")
        except Exception as e:
            print(f"❌ Error saving config: {e}")
    
    def run(self):
        """Run calibration procedure."""
        print("=" * 70)
        print("ENCODER CALIBRATION TOOL")
        print("=" * 70)
        print()
        print("This tool helps you calibrate the encoder pulses_per_mm parameter.")
        print()
        
        # Load current config
        config = self.load_config()
        motion_config = config.get("motion_control", {})
        encoder_cal = motion_config.get("encoder_calibration", {})
        current_ppm = encoder_cal.get("pulses_per_mm", 84.880)
        
        print(f"Current pulses_per_mm: {current_ppm:.3f}")
        print()
        
        # Initialize encoder
        print("Initializing encoder...")
        self.encoder = EncoderReader8ALZARD(
            gpio_a=17,
            gpio_b=27,
            gpio_z=22,
            pulses_per_mm=current_ppm,
            enable_index=True
        )
        
        if not self.encoder.is_connected():
            print("❌ Failed to connect to encoder")
            print("   Make sure pigpiod daemon is running: sudo pigpiod")
            return
        
        print("✅ Encoder connected")
        print()
        
        # Calibration procedure
        print("CALIBRATION PROCEDURE:")
        print("-" * 70)
        print()
        print("1. Position the carriage at a known reference point")
        print("2. We'll reset the encoder to zero")
        print("3. Move the carriage a known distance (e.g., 1000mm)")
        print("4. We'll calculate the actual pulses_per_mm ratio")
        print()
        
        input("Press ENTER when carriage is at reference position...")
        
        # Reset encoder
        print("\nResetting encoder to zero...")
        self.encoder.reset()
        time.sleep(0.5)
        
        start_pulses = self.encoder.get_pulse_count()
        print(f"Starting pulse count: {start_pulses}")
        print()
        
        # Get target distance
        print("How far will you move the carriage?")
        while True:
            try:
                distance_mm = float(input("Enter distance in mm (e.g., 1000): "))
                if distance_mm > 0:
                    break
                print("Distance must be positive")
            except ValueError:
                print("Invalid input, please enter a number")
        
        print()
        print(f"Move the carriage EXACTLY {distance_mm:.1f}mm from the reference point")
        print("Use a measuring tape or caliper for accuracy")
        print()
        input("Press ENTER when carriage is at target position...")
        
        # Read final pulses
        time.sleep(0.5)
        end_pulses = self.encoder.get_pulse_count()
        pulse_diff = abs(end_pulses - start_pulses)
        
        print()
        print("MEASUREMENT RESULTS:")
        print("-" * 70)
        print(f"Start pulses:     {start_pulses}")
        print(f"End pulses:       {end_pulses}")
        print(f"Pulse difference: {pulse_diff}")
        print(f"Distance moved:   {distance_mm:.3f} mm")
        print()
        
        # Calculate new pulses_per_mm
        if pulse_diff > 0:
            new_ppm = pulse_diff / distance_mm
            print(f"Calculated pulses_per_mm: {new_ppm:.3f}")
            print()
            
            # Calculate error
            error_percent = abs(new_ppm - current_ppm) / current_ppm * 100
            print(f"Difference from current: {error_percent:.2f}%")
            print()
            
            # Verify calculation
            theoretical_pulses = encoder_cal.get("pulses_per_revolution", 4000)
            pulley_diameter = encoder_cal.get("pulley_diameter_mm", 60.0)
            pulley_circumference = 3.14159 * pulley_diameter
            theoretical_ppm = theoretical_pulses / pulley_circumference
            
            print(f"Theoretical value: {theoretical_ppm:.3f} pulses/mm")
            print(f"   (based on {theoretical_pulses} PPR and {pulley_diameter}mm pulley)")
            print()
            
            # Ask to save
            save = input("Save this calibration to config? (y/n): ")
            if save.lower() == 'y':
                # Update config
                if "motion_control" not in config:
                    config["motion_control"] = {}
                if "encoder_calibration" not in config["motion_control"]:
                    config["motion_control"]["encoder_calibration"] = {}
                
                config["motion_control"]["encoder_calibration"]["pulses_per_mm"] = round(new_ppm, 3)
                
                # Calculate correction factor
                correction_factor = new_ppm / theoretical_ppm
                config["motion_control"]["encoder_calibration"]["correction_factor"] = round(correction_factor, 6)
                
                self.save_config(config)
                print()
                print("✅ Calibration complete!")
                print(f"   New pulses_per_mm: {new_ppm:.3f}")
                print(f"   Correction factor: {correction_factor:.6f}")
            else:
                print("\nCalibration not saved")
        else:
            print("❌ No pulses detected - check encoder connection")
        
        # Cleanup
        self.encoder.close()
        print()
        print("=" * 70)


def main():
    """Main entry point."""
    calibrator = EncoderCalibrator()
    calibrator.run()


if __name__ == "__main__":
    main()
