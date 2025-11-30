from gpiozero import PWMOutputDevice, Button
from time import sleep

BUZZER_PIN = 23
BUTTON_PIN = 24

VOLUME = 1.0
SPEED_MULTIPLIER = 1.0

ALARM_PATTERN = [
    (0.1, 0.1),
    (0.1, 0.6)
]

def run_active_alarm():
    buzzer = PWMOutputDevice(BUZZER_PIN, frequency=2000)
    stop_button = Button(BUTTON_PIN)
    alarm_running = True

    try:
        while alarm_running:
            if stop_button.is_pressed:
                print("\nButton pressed. Ending alarm.")
                alarm_running = False
                break

            for on_time, off_time in ALARM_PATTERN:
                if stop_button.is_pressed:
                    alarm_running = False
                    break
                
                actual_on = on_time / SPEED_MULTIPLIER
                actual_off = off_time / SPEED_MULTIPLIER

                if actual_on > 0:
                    buzzer.value = VOLUME
                    sleep(actual_on)
                
                buzzer.off()
                
                if stop_button.is_pressed:
                    alarm_running = False
                    break
                    
                sleep(actual_off)

    except KeyboardInterrupt:
        print("\nAlarm stopped via Keyboard.")
    
    finally:
        buzzer.off()
        print("System cleanup complete.")

if __name__ == "__main__":
    run_active_alarm()