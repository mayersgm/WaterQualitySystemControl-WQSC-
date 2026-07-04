import time
import board
import displayio
import busio
import json
import terminalio
from adafruit_display_text import label
from adafruit_display_shapes.rect import Rect
import digitalio
import neopixel
from adafruit_bitmap_font import bitmap_font
from adafruit_button import Button
import adafruit_touchscreen
from adafruit_pyportal import PyPortal

# Constants
SLAVE_ADDRESS = 0x41
UPDATE_INTERVAL = 1.0
BUFFER_SIZE = 96  # Match Pico's buffer size


# Colors
WHITE = 0xFFFFFF
RED = 0xFF0000
YELLOW = 0xFFFF00
GREEN = 0x00FF00
BLUE = 0x0000FF
PURPLE = 0xFF00FF
BLACK = 0x000000

# Commands
RUN = 0x11
START = 0x12
STANDBY = 0x13
STOP = 0x14
STERILIZE = 0x15
EMPTY = 0x16
RESET = 0x17

class WQCSMaster:
    def __init__(self):
        self.pyportal = PyPortal()
        self.display = board.DISPLAY
        self.display.rotation = 0

        # Setup NeoPixel
        self.pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=1)

        # Load fonts
        self.main_font = bitmap_font.load_font("/fonts/Arial-ItalicMT-17.bdf")
        self.small_font = terminalio.FONT

        # Initialize display
        self.setup_display()

        # Initialize I2C
        self.i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)

        # Button states
        self.active_button = None
        self.sterilize_active = False
        self.start_active = False
        self.empty_active = False

        # Status tracking
        self.current_command = RUN  # Track current command
        self.status = {}

                # Timer tracking
        self.timers = {
            'distillation': 0,
            'sterilization': 0,
            'standby': 0,
            'refill': 0
        }
        self.standby_resume_time = 300  # 5 minutes before auto-resume
        self.refill_active = False
        self.last_update = time.monotonic()


                # Load fonts with bigger size for sensors
        try:
            self.main_font = bitmap_font.load_font("/fonts/Arial-ItalicMT-17.bdf")
            self.main_font.load_glyphs(b"abcdefghjiklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890-(): °F%.")
            
            # Load larger font for sensor values
            self.sensor_font = bitmap_font.load_font("/fonts/Arial-Bold-24.bdf")
            self.sensor_font.load_glyphs(b"0123456789.: °F%ppm")
        except Exception as e:
            print(f"Font load error: {e}")
            self.main_font = terminalio.FONT
            self.sensor_font = terminalio.FONT

    def setup_display(self):
        self.splash = displayio.Group()

        # Create labels
        self.labels = {}
        label_configs = [
            ("title", "*****DISTILLER WQCS*****", 20, 20, WHITE, self.main_font),
            ("status", "Current Status:", 20, 50, YELLOW, self.main_font),
            ("boiler", "Boiler Status:", 20, 80, RED, self.main_font),
            ("reservoir", "Reservoir Status:", 20, 110, GREEN, self.main_font),
            ("event_timer", "Event Timer:", 20, 140, WHITE, self.main_font),  # Single timer location
            ("timer_value", "--:--:--", 130, 140, WHITE, self.main_font),    # Timer value
            ("timer_type", "", 240, 140, WHITE, self.main_font)              # Timer type indicator
        ]

        for key, text, x, y, color, font in label_configs:
            self.labels[key] = label.Label(
                font,
                text=text,
                color=color,
                x=x,
                y=y
            )
            self.splash.append(self.labels[key])

        self.buttons = []
        button_configs = [
            ("STERILIZE", STERILIZE, (0, 190)),
            ("START", START, (80, 190)),
            ("EMPTY", EMPTY, (160, 190)),
            ("RESET", RESET, (240, 190))
        ]
        
        for text, cmd, pos in button_configs:
            button = Button(
                x=pos[0],
                y=pos[1],
                width=75,
                height=40,
                label=text,
                label_font=self.main_font,
                label_color=0xFF7E00,
                fill_color=0x5C5B5C,
                outline_color=0x767676,
                selected_fill=0x1A1A1A,
                selected_outline=0x2E2E2E,
                selected_label=0x525252
            )
            # Store as tuple of (button, command)
            self.buttons.append([button, cmd])  # Using list instead of tuple for mutability
            self.splash.append(button)

        self.display.show(self.splash)

    def send_command(self, command):
        """Send command and update current command"""
        try:
            print(f"Sending command: 0x{command:02X}")
            self.current_command = command  # Update current command
            
            self.i2c.try_lock()
            self.i2c.writeto(SLAVE_ADDRESS, bytes([command]))
            self.i2c.unlock()
            
            print(f"Command 0x{command:02X} sent successfully")
            return True
            
        except Exception as e:
            print(f"Send command error: {e}")
            return False
        finally:
            try:
                self.i2c.unlock()
            except:
                pass

    def handle_button_press(self, button_index):
        """Handle button press with maintained command state"""
        button = self.buttons[button_index][0]
        command = self.buttons[button_index][1]
        
        try:
            print(f"Button {button_index} pressed: {button.label}")
            self.pyportal.play_file("/sounds/tab.wav")
            button.selected = True
            
            if button_index == 0:  # STERILIZE
                if not self.active_button or self.active_button == button:
                    self.sterilize_active = not self.sterilize_active
                    button.label = "CANCEL" if self.sterilize_active else "STERILIZE"
                    self.active_button = button if self.sterilize_active else None
                    command = STERILIZE if self.sterilize_active else STOP
                    if self.send_command(command):
                        self.pixel.fill(PURPLE if self.sterilize_active else WHITE)
                    
            elif button_index == 1:  # START
                if not self.active_button or self.active_button == button:
                    self.start_active = not self.start_active
                    button.label = "STOP" if self.start_active else "START"
                    self.active_button = button if self.start_active else None
                    command = START if self.start_active else STOP
                    
                    if self.send_command(command):
                        self.pixel.fill(BLUE if self.start_active else WHITE)
                        # Reset relevant timers
                        if not self.start_active:  # If stopping
                            self.timers['distillation'] = 0
                            self.timers['standby'] = 0
                    
            elif button_index == 2:  # EMPTY
                if not self.active_button or self.active_button == button:
                    self.empty_active = not self.empty_active
                    button.label = "CANCEL" if self.empty_active else "EMPTY"
                    self.active_button = button if self.empty_active else None
                    command = EMPTY if self.empty_active else STOP
                    if self.send_command(command):
                        self.pixel.fill(GREEN if self.empty_active else WHITE)
                    
            elif button_index == 3:  # RESET
                if not self.active_button:
                    if self.send_command(RESET):
                        self.pixel.fill(YELLOW)
                        # Reset all states
                        self.sterilize_active = False
                        self.start_active = False
                        self.empty_active = False
                        self.active_button = None
                        # Reset button labels
                        self.buttons[0][0].label = "STERILIZE"
                        self.buttons[1][0].label = "START"
                        self.buttons[2][0].label = "EMPTY"
                        self.current_command = RUN
            
            time.sleep(0.1)
            button.selected = False
            
        except Exception as e:
            print(f"Button press error: {e}")
            button.selected = False

    def read_status(self):
        """Read status from Pico without sending RUN command"""
        try:
            # Only send command if we're in standby mode
            if not (self.sterilize_active or self.start_active or self.empty_active):
                self.current_command = RUN
                
            # Send current command (whether RUN or active command)
            self.i2c.try_lock()
            self.i2c.writeto(SLAVE_ADDRESS, bytes([self.current_command]))
            
            # Read status
            buffer = bytearray(BUFFER_SIZE)
            self.i2c.readfrom_into(SLAVE_ADDRESS, buffer)
            self.i2c.unlock()
            
            # Process response
            raw_str = ""
            for b in buffer:
                if b == 0:  # Stop at null terminator
                    break
                raw_str += chr(b)
            
            try:
                if raw_str:
                    self.status = json.loads(raw_str)
                    print(f"Current command: 0x{self.current_command:02X}")
                    return True
                return False
                
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
                return False
                
        except Exception as e:
            print(f"Status read error: {e}")
            return False
        finally:
            try:
                self.i2c.unlock()
            except:
                pass

    def update_display(self):
        """Update display with larger sensor values"""
        try:
            if not self.status:
                return
            print("Latest Pico Status", self.status)    
            # Parse status
            temp_str = str(self.status.get('t', '0.0'))
            tds = self.status.get('d', 0)
            boiler = self.status.get('b', 0)
            reservoir = self.status.get('r', 0)
            fan = self.status.get('f', 0)
            error = self.status.get('e', 0)
            
            # Create sensor display groups if they don't exist
            if 'sensor_group' not in self.labels:
                self.labels['sensor_group'] = displayio.Group()
                self.splash.append(self.labels['sensor_group'])
                
                # Temperature label (fixed text)
                temp_label = label.Label(
                    self.main_font,
                    text="Temp:",
                    color=BLUE,
                    x=20,
                    y=170
                )
                self.labels['sensor_group'].append(temp_label)
                
                # Temperature value
                self.labels['temp_value'] = label.Label(
                    self.sensor_font,
                    text="--°F",
                    color=BLUE,
                    x=80,
                    y=170
                )
                self.labels['sensor_group'].append(self.labels['temp_value'])
                
                # TDS label (fixed text)
                tds_label = label.Label(
                    self.main_font,
                    text="TDS:",
                    color=BLUE,
                    x=180,
                    y=170
                )
                self.labels['sensor_group'].append(tds_label)
                
                # TDS value
                self.labels['tds_value'] = label.Label(
                    self.sensor_font,
                    text="-- ppm",
                    color=BLUE,
                    x=230,
                    y=170
                )
                self.labels['sensor_group'].append(self.labels['tds_value'])
            
            # Update just the values
            self.labels['temp_value'].text = f"{temp_str}°F"
            self.labels['tds_value'].text = f"{tds} ppm"
            
            # Update other status displays
            boiler_status = "ON" if boiler else "OFF"
            self.labels["boiler"].text = f"Boiler: {boiler_status}"
            
            levels = {0: "Empty", 1: "Low", 2: "Medium", 3: "Full"}
            level = levels.get(reservoir, "Unknown")
            self.labels["reservoir"].text = f"Reservoir: {level}"
            
            # Update status and LED color
            if error:
                self.labels["status"].text = "ERROR STATE"
                self.pixel.fill(RED)
            elif self.sterilize_active:
                self.labels["status"].text = "STERILIZING"
                self.pixel.fill(PURPLE)
            elif self.start_active:
                self.labels["status"].text = "DISTILLING"
                self.pixel.fill(BLUE)
            elif self.empty_active:
                self.labels["status"].text = "EMPTYING"
                self.pixel.fill(GREEN)
            else:
                self.labels["status"].text = "STANDBY"
                self.pixel.fill(WHITE)
                
        except Exception as e:
            print(f"Display update error: {e}")
            print(f"Error details: {type(e).__name__}: {str(e)}")
            self.labels["status"].text = "Display Error"

    def format_time(self, seconds, show_hours=True):
        """Format time as HH:MM:SS or MM:SS"""
        if show_hours:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes:02d}:{secs:02d}"

    def update_timers(self):
        """Update timers based on current state"""
        current_time = time.monotonic()
        elapsed = current_time - self.last_update
        self.last_update = current_time

        # Update active timer based on state
        if self.refill_active:
            # Handle refill timer from Pico status
            if self.status.get('ref_active', False):
                refill_count = self.status.get('ref_count', 0)
                self.timers['refill'] = refill_count
                
                if self.timers['refill'] <= 0:
                    self.handle_refill_error()
                else:
                    # Show refill timer
                    self.labels["timer_value"].text = self.format_time(self.timers['refill'], False)
                    self.labels["timer_type"].text = "(Refill)"
                    self.labels["timer_value"].color = RED
                    self.labels["timer_type"].color = RED
            else:
                self.refill_active = False
                
        elif self.start_active:
            # Update distillation timer
            self.timers['distillation'] += elapsed
            self.labels["timer_value"].text = self.format_time(self.timers['distillation'])
            self.labels["timer_type"].text = "(Distilling)"
            self.labels["timer_value"].color = BLUE
            self.labels["timer_type"].color = BLUE
            
        elif self.sterilize_active:
            # Update sterilization timer
            self.timers['sterilization'] += elapsed
            self.labels["timer_value"].text = self.format_time(self.timers['sterilization'])
            self.labels["timer_type"].text = "(Sterilizing)"
            self.labels["timer_value"].color = PURPLE
            self.labels["timer_type"].color = PURPLE
            
        else:
            # Update standby timer
            self.timers['standby'] += elapsed
            self.labels["timer_value"].text = self.format_time(self.timers['standby'])
            self.labels["timer_type"].text = "(Standby)"
            self.labels["timer_value"].color = WHITE
            self.labels["timer_type"].color = WHITE
            
            # Check for auto-resume from standby
            if self.timers['standby'] >= self.standby_resume_time:
                reservoir_full = self.status.get('r', 0) == 3
                if not reservoir_full:
                    self.auto_resume_distillation()

    def handle_refill_error(self):
        """Handle refill timeout error"""
        error_active = True
        while error_active:
            self.pixel.fill(RED)
            self.labels["timer_value"].text = "ERROR"
            self.labels["timer_type"].text = "(Refill Timeout)"
            self.labels["timer_value"].color = RED
            self.labels["timer_type"].color = RED
            self.pyportal.play_file("/sounds/beep.wav")
            time.sleep(0.5)
            self.pixel.fill(BLACK)
            time.sleep(0.5)
            
            # Check for reset button press
            touch = ts.touch_point
            if touch and self.buttons[3][0].contains(touch):  # Reset button
                error_active = False
                self.handle_button_press(3)  # Process reset

    def auto_resume_distillation(self):
        """Auto-resume distillation after standby with button update"""
        try:
            print("Auto-resuming distillation")
            
            # Update state
            self.start_active = True
            
            # Update button visually
            start_button = self.buttons[1][0]  # Get START/STOP button
            start_button.label = "STOP"
            start_button.selected = True  # Flash button briefly
            time.sleep(0.1)
            start_button.selected = False
            
            # Update active button tracking
            self.active_button = start_button
            
            # Send command to Pico
            self.send_command(START)
            self.current_command = START
            
            # Update display state
            self.pixel.fill(BLUE)
            self.labels["status"].text = "DISTILLING"
            
            # Reset standby timer
            self.timers['standby'] = 0
            
            # Play sound to indicate auto-resume
            self.pyportal.play_file("/sounds/tab.wav")
            
            print("Auto-resume complete - system now distilling")
            
        except Exception as e:
            print(f"Auto-resume error: {e}")
            self.labels["status"].text = "Auto-Resume Error"
            
    def reset_timers(self):
        """Reset timers"""
        self.timers['distillation'] = 0
        self.timers['sterilization'] = 0
        self.timers['standby'] = 0
        # Note: refill timer is controlled by Pico
        
        # Reset timer display
        self.labels["timer_value"].text = "--:--:--"
        self.labels["timer_type"].text = ""
        self.labels["timer_value"].color = WHITE
        self.labels["timer_type"].color = WHITE

    def run(self):
            """Main run loop with debug"""
            # Initialize touchscreen
            ts = adafruit_touchscreen.Touchscreen(
                board.TOUCH_XL, board.TOUCH_XR,
                board.TOUCH_YD, board.TOUCH_YU,
                calibration=((5200, 59000), (5800, 57000)),
                size=(320, 240)
            )
            
            last_update = time.monotonic()
            print("WQCS Master running...")
            
            # Debug print button contents
            print("\nButton array contents:")
            for i, btn_data in enumerate(self.buttons):
                print(f"Button {i}:", btn_data)
        
            while True:
                try:
                    current_time = time.monotonic()
                    
                    # Handle touch input
                    touch = ts.touch_point
                    if touch:
                        for i, (button, _) in enumerate(self.buttons):
                            if button.contains(touch):
                                self.handle_button_press(i)
                                while ts.touch_point:
                                    time.sleep(0.1)
                    
                    # Update status and timers
                    if current_time - last_update >= UPDATE_INTERVAL:
                        if self.read_status():
                            self.update_display()
                            self.update_timers()
                        last_update = current_time
                    
                    time.sleep(0.1)
                
                except Exception as e:
                    print(f"Main loop error: {e}")
                    time.sleep(1)

if __name__ == "__main__":
    while True:
        try:
            master = WQCSMaster()
            master.run()
        except Exception as e:
            print(f"Fatal error: {e}")
            print("Restarting in 5 seconds...")
            time.sleep(5)
