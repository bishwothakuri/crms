import paho.mqtt.client as mqtt

broker = "localhost"
port = 1883
topic = "build/task"

def on_connect(client, userdata, flags, rc):
    print("Connected with result code " + str(rc))
    client.subscribe(topic)

def on_message(client, userdata, msg):
    print(f"Message received: {msg.payload.decode()}")

client = mqtt.Client("Builder")
client.on_connect = on_connect
client.on_message = on_message
client.connect(broker, port, 60)

client.loop_forever()
