import paho.mqtt.client as mqtt

broker = "localhost"
port = 1883
topic = "build/task"

def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))
    client.publish(topic, "Run Docker to build Prometheus")

client = mqtt.Client("Coordinator")
client.on_connect = on_connect
client.connect(broker, port, 60)

client.loop_start()
