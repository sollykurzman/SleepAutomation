from gpiozero import PWMOutputDevice
from time import sleep

BUZZER_PIN = 14

buzzer = PWMOutputDevice(BUZZER_PIN, frequency=2000)

VOLUME = 1.0

SPEED_MULTIPLIER = 1.0

ALARM_PATTERN = [
    (0.1, 0.1),
    (0.1, 0.6)
]

def run_active_alarm():
    print(f"Active Alarm running on GPIO {BUZZER_PIN}")
    print(f"Volume: {VOLUME*100}% | Speed: {SPEED_MULTIPLIER}x")
    print("Press Ctrl+C to stop")

    try:
        while True:
            for on_time, off_time in ALARM_PATTERN:
                
                actual_on = on_time / SPEED_MULTIPLIER
                actual_off = off_time / SPEED_MULTIPLIER

                if actual_on > 0:
                    buzzer.value = VOLUME
                    sleep(actual_on)
                
                buzzer.off()
                sleep(actual_off)

    except KeyboardInterrupt:
        print("\nAlarm stopped.")
        buzzer.off()

if __name__ == "__main__":
    run_active_alarm()
