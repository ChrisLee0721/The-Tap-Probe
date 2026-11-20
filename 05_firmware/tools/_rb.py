
import time, json
import paho.mqtt.client as mqtt
c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.connect("192.168.3.12",1883,30); c.loop_start()
time.sleep(1.5)
c.publish("probe/probe-01/cmd", json.dumps({"cmd":"reboot"}), qos=1)
time.sleep(16)
c.loop_stop(); c.disconnect()
