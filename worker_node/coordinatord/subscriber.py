import paho.mqtt.client as mqtt
import yaml
import subprocess
import os


def on_connect(client, userdata, flags, rc):
    client.subscribe("build/config")

def on_message(client, userdata, msg):
    yaml_filename = msg.payload.decode()
    print(f"Received YAML configuration file: {yaml_filename}")

    # Load the YAML file and run the Docker commands
    try:
        with open(yaml_filename, 'r') as file:
            config = yaml.safe_load(file)

        # Example: Navigating to the directory where the YAML file is located
        project_directory = os.path.dirname(os.path.abspath(yaml_filename))
        os.chdir(project_directory)

        # Build and run the Docker containers using docker-compose
        command = f"docker-compose -f {yaml_filename} up --build"
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        print(f"Build and run output: {result.stdout.decode()}")

    except FileNotFoundError:
        print(f"YAML file {yaml_filename} not found.")
    except yaml.YAMLError as exc:
        print(f"Error parsing YAML file: {exc}")
    except subprocess.CalledProcessError as e:
        print(f"Error occurred: {e.stderr.decode()}")

# Set up the MQTT client
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

# Connect to the broker running on localhost
client.connect("localhost", 1883, 60)

# Start the loop to process messages
client.loop_forever()
