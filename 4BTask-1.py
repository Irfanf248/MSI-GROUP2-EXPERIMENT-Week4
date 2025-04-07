import usb.core
import usb.util
import serial
import serial.tools.list_ports
import json
import time
from threading import Thread

class RFIDServoController:
    def __init__(self):
        # Configuration
        self.config = {
            "vendor_id": 0x1234,        # Replace with your RFID reader's vendor ID
            "product_id": 0x5678,       # Replace with your RFID reader's product ID
            "authorized_cards": ["A1B2C3D4", "E5F6G7H8"],
            "servo_default_pos": 90,
            "servo_allowed_pos": 180,
            "baud_rate": 9600,
            "led_pins": {"green": 3, "red": 4}
        }
        
        # System state
        self.servo_control_enabled = False
        self.current_servo_pos = self.config["servo_default_pos"]
        
        # Initialize hardware
        self.init_rfid_reader()
        self.init_serial_connection()
        self.load_config()
        
        # Start status thread
        self.running = True
        self.status_thread = Thread(target=self.send_status_updates)
        self.status_thread.start()

    def init_rfid_reader(self):
        """Initialize the USB RFID reader"""
        self.dev = usb.core.find(
            idVendor=self.config["vendor_id"],
            idProduct=self.config["product_id"]
        )
        
        if self.dev is None:
            raise ValueError("RFID reader not found")
            
        if self.dev.is_kernel_driver_active(0):
            self.dev.detach_kernel_driver(0)
            
        self.dev.set_configuration()
        self.endpoint = self.dev[0][(0, 0)][0]

    def init_serial_connection(self):
        """Initialize connection to Arduino"""
        ports = serial.tools.list_ports.comports()
        for port in ports:
            try:
                self.ser = serial.Serial(port.device, self.config["baud_rate"], timeout=1)
                print(f"Connected to Arduino on {port.device}")
                return
            except serial.SerialException:
                continue
        raise ConnectionError("Could not connect to Arduino")

    def load_config(self, filename="config.json"):
        """Load configuration from JSON file"""
        try:
            with open(filename, 'r') as f:
                new_config = json.load(f)
                self.config.update(new_config)
                print("Configuration loaded successfully")
        except FileNotFoundError:
            print("No config file found, using defaults")
        except json.JSONDecodeError:
            print("Invalid config file, using defaults")

    def save_config(self, filename="config.json"):
        """Save configuration to JSON file"""
        with open(filename, 'w') as f:
            json.dump(self.config, f, indent=4)
        print("Configuration saved")

    def handle_rfid_data(self, data):
        """Process RFID card reads"""
        try:
            card_id = ''.join([chr(byte) for byte in data]).strip()
            print(f"Card read: {card_id}")
            
            if card_id in self.config["authorized_cards"]:
                self.grant_access()
            else:
                self.deny_access()
                
        except Exception as e:
            print(f"Error processing RFID data: {e}")

    def grant_access(self):
        """Actions for authorized cards"""
        print("Access granted")
        self.control_led("green", True)
        self.enable_servo_control()
        time.sleep(1)  # LED feedback duration
        self.control_led("green", False)

    def deny_access(self):
        """Actions for unauthorized cards"""
        print("Access denied")
        self.control_led("red", True)
        self.disable_servo_control()
        time.sleep(1)  # LED feedback duration
        self.control_led("red", False)

    def control_led(self, color, state):
        """Control LED states"""
        pin = self.config["led_pins"].get(color)
        if pin is not None:
            command = {"led": {color: state}}
            self.send_command(command)

    def enable_servo_control(self):
        """Enable servo control"""
        self.servo_control_enabled = True
        self.current_servo_pos = self.config["servo_allowed_pos"]
        self.send_command({"servo": {"enable": True}})

    def disable_servo_control(self):
        """Disable servo control"""
        self.servo_control_enabled = False
        self.current_servo_pos = self.config["servo_default_pos"]
        self.send_command({"servo": {"enable": False}})

    def set_servo_position(self, angle):
        """Set servo to specific angle"""
        if 0 <= angle <= 180:
            self.current_servo_pos = angle
            self.send_command({"servo": {"set_position": angle}})
            return True
        return False

    def send_command(self, command):
        """Send JSON command to Arduino"""
        try:
            json_str = json.dumps(command) + "\n"
            self.ser.write(json_str.encode())
        except serial.SerialException as e:
            print(f"Error sending command: {e}")

    def send_status_updates(self):
        """Periodically send system status"""
        while self.running:
            status = {
                "status": {
                    "servo": {
                        "position": self.current_servo_pos,
                        "enabled": self.servo_control_enabled
                    },
                    "rfid": {
                        "cards_registered": len(self.config["authorized_cards"])
                    }
                }
            }
            self.send_command(status)
            time.sleep(2)

    def process_user_input(self):
        """Handle user commands from console"""
        print("\nControl commands:")
        print("1 - Enable servo control")
        print("2 - Disable servo control")
        print("3 - Set servo position")
        print("4 - Add authorized card")
        print("5 - Save configuration")
        print("q - Quit")
        
        while self.running:
            cmd = input("Enter command: ").strip().lower()
            
            if cmd == '1':
                self.enable_servo_control()
            elif cmd == '2':
                self.disable_servo_control()
            elif cmd == '3':
                try:
                    pos = int(input("Enter position (0-180): "))
                    if self.set_servo_position(pos):
                        print(f"Servo set to {pos} degrees")
                    else:
                        print("Invalid position")
                except ValueError:
                    print("Please enter a number")
            elif cmd == '4':
                card = input("Enter new card ID: ").strip()
                if card and card not in self.config["authorized_cards"]:
                    self.config["authorized_cards"].append(card)
                    print(f"Card {card} added")
                else:
                    print("Invalid or duplicate card ID")
            elif cmd == '5':
                self.save_config()
            elif cmd == 'q':
                self.running = False
                print("Exiting...")
            else:
                print("Invalid command")

    def run(self):
        """Main execution loop"""
        try:
            # Start user input thread
            input_thread = Thread(target=self.process_user_input)
            input_thread.start()
            
            print("RFID-Servo Controller started. Waiting for cards...")
            
            # Main RFID reading loop
            while self.running:
                try:
                    data = self.dev.read(
                        self.endpoint.bEndpointAddress,
                        self.endpoint.wMaxPacketSize
                    )
                    self.handle_rfid_data(data)
                except usb.core.USBError:
                    pass
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            self.running = False
        finally:
            self.ser.close()
            print("System shutdown complete")

if __name__ == "__main__":
    controller = RFIDServoController()
    controller.run()