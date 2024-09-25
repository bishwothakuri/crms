import paho.mqtt.client as mqtt

# Create an MQTT client instance
client = mqtt.Client()

# Connect to the MQTT broker running on localhost
client.connect("localhost", 1883, 60)

# Publish the YAML configuration filename to the topic 'build/config'
yaml_filename = "config.yaml"
client.publish("build/config", payload=yaml_filename, qos=1)

print(f"Sent YAML configuration file name: {yaml_filename}")

# Disconnect cleanly
client.disconnect()
