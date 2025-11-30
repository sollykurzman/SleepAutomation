from gpiozero import PWMOutputDevice, Button
from time import sleep
import subprocess

# --- Configuration ---
BUZZER_PIN = 23
BUTTON_PIN = 24  # New button connected here

# Setup devices


VOLUME = 1.0
SPEED_MULTIPLIER = 1.0

ALARM_PATTERN = [
    (0.1, 0.1),
    (0.1, 0.6)
]

def schedule_alarm(time):
    timer_file = "/etc/systemd/system/alarm.timer"

    new_contents = f"""[Unit]
Description=Alarm timer

[Timer]
OnCalendar=*-*-* {time}
Persistent=true

[Install]
WantedBy=timers.target"""
    
    subprocess.run(["sudo", "/usr/local/bin/update_alarm_timer", new_contents])
    subprocess.run(["sudo", "systemctl", "daemon-reload"])
    subprocess.run(["sudo", "systemctl", "restart", "alarm.timer"])

def run_active_alarm():
    buzzer = PWMOutputDevice(BUZZER_PIN, frequency=2000)
    stop_button = Button(BUTTON_PIN)
    alarm_running = True

    try:
        while alarm_running:
            # Check button at the start of the cycle
            if stop_button.is_pressed:
                print("\nButton pressed. Ending alarm.")
                alarm_running = False
                break

            for on_time, off_time in ALARM_PATTERN:
                # Check button before the beep
                if stop_button.is_pressed:
                    alarm_running = False
                    break
                
                actual_on = on_time / SPEED_MULTIPLIER
                actual_off = off_time / SPEED_MULTIPLIER

                if actual_on > 0:
                    buzzer.value = VOLUME
                    sleep(actual_on)
                
                buzzer.off()
                
                # Check button during the silence (responsive feel)
                if stop_button.is_pressed:
                    alarm_running = False
                    break
                    
                sleep(actual_off)

    except KeyboardInterrupt:
        print("\nAlarm stopped via Keyboard.")
    
    finally:
        # Ensure buzzer is off regardless of how we exited
        buzzer.off()
        print("System cleanup complete.")

if __name__ == "__main__":
    run_active_alarm()