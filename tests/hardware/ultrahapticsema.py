import os, time, threading, signal, sys

TRIG_GPIO = 426
ECHO_GPIO = 485
MOTOR_GPIO = 484

stop_event = threading.Event()
lock = threading.Lock()
obstacle_detected = False
last_seen = 0

def gpio_path(pin): return f"/sys/class/gpio/gpio{pin}"

def export_gpio(pin):
    if not os.path.exists(gpio_path(pin)):
        with open("/sys/class/gpio/export","w") as f: f.write(str(pin))
    return gpio_path(pin)

def unexport_gpio(pin):
    if os.path.exists(gpio_path(pin)):
        with open("/sys/class/gpio/unexport","w") as f: f.write(str(pin))

def set_direction(path, dirn):
    with open(os.path.join(path,"direction"),"w") as f: f.write(dirn)

def write_value(path, val):
    with open(os.path.join(path,"value"),"w") as f: f.write(str(val))

def read_value(path):
    with open(os.path.join(path,"value")) as f: return f.read().strip()

# --- ultrasonic ---
def measure(trig, echo):
    set_direction(trig,"out"); set_direction(echo,"in")
    write_value(trig,0); time.sleep(0.05)
    write_value(trig,1); time.sleep(0.00001)
    write_value(trig,0)

    t0=time.time(); 
    while read_value(echo)=="0":
        if time.time()-t0>0.2: return None
    start=time.time()

    while read_value(echo)=="1":
        if time.time()-start>0.2: return None
    end=time.time()
    return (end-start)*17150   # cm

def ultrasonic_loop(trig, echo):
    global obstacle_detected,last_seen
    while not stop_event.is_set():
        d=measure(trig,echo)
        if d:
            print(f"[ULTRASONIC] {d:.1f} cm")
            with lock:
                if d<20: obstacle_detected=True; last_seen=time.time()
                elif time.time()-last_seen>1.5: obstacle_detected=False
        else: print("[ULTRASONIC] timeout")
        time.sleep(0.2)

def motor_loop(motor):
    set_direction(motor,"out")
    motor_state=False
    while not stop_event.is_set():
        with lock: active=obstacle_detected
        if active and not motor_state:
            write_value(motor,1); motor_state=True
            print("[MOTOR] ON")
        elif not active and motor_state:
            write_value(motor,0); motor_state=False
            print("[MOTOR] OFF")
        time.sleep(0.1)
    # failsafe off
    write_value(motor,0)
    print("[MOTOR] forced OFF")

def cleanup():
    print("\n[CLEANUP] Shutting down safely...")
    for pin in (TRIG_GPIO,ECHO_GPIO,MOTOR_GPIO):
        try: write_value(gpio_path(pin),0)
        except: pass
        unexport_gpio(pin)
    print("[CLEANUP] GPIOs unexported. Goodbye.")
    sys.exit(0)

def handle_signal(sig,frame):
    stop_event.set()
    cleanup()

signal.signal(signal.SIGINT,handle_signal)
signal.signal(signal.SIGTERM,handle_signal)

if __name__=="__main__":
    trig=export_gpio(TRIG_GPIO)
    echo=export_gpio(ECHO_GPIO)
    motor=export_gpio(MOTOR_GPIO)
    t1=threading.Thread(target=ultrasonic_loop,args=(trig,echo))
    t2=threading.Thread(target=motor_loop,args=(motor,))
    t1.start(); t2.start()
    while not stop_event.is_set():
        time.sleep(0.1)

