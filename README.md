
### Cloudless Resource Monitoring System Version 2.0 (Focused on Generation Layer)
We developed the Cloudless Resource Monitoring System (CRMS) as a solution to the limitations of traditional cloud architectures by integrating Software-Defined Networking (SDN) and fog computing. Our system leverages Docker-based containerization to dynamically manage resources across distributed fog nodes, ensuring low latency and high efficiency.

## Requirements

Before you begin, ensure you have the following prerequisites installed on your system:

### System Requirements

- **Operating System:** 
  - Ubuntu
- **Filesystem:** 
  - XFS (required)
- **Docker**
- **Python**

[]([[[[url](url)](url)](url)](url))

#### Clone the Repository

Use the following command to clone the project repository to your local machine:

```bash
git clone https://gitlab.rz.uni-bamberg.de/ktr/proj/st-2024/group-crms/code.git
```

#### Navigate to the Project Directory

After cloning, change into the project directory:

```bash
cd code
```

#### Build the Project

To build the Docker containers, you can choose from the following options:

- **To build all services defined in the `docker-compose.yml`:**

  ```bash
  docker-compose build
  ```

- **To build a specific service:**

  Replace `<service>` with the name of the specific service you want to build:

  ```bash
  docker-compose build <service>
  ```

**Note:** Use the service name as defined in the `docker-compose.yml` file.

#### Run the Project

To start the services defined in the `docker-compose.yml`, execute the following command:

```bash
docker-compose up
```

#### Stopping the Services

To stop the running services, use:

```bash
docker-compose down
```

**Key Features:**

**Decentralized Architecture:** We eliminated the single point of failure by distributing resource management across worker nodes. Each node now runs four microservices—Coordinator, Builder, Monitor, and Query—which allows them to function autonomously and improve the overall scalability and fault tolerance of the system.

**Resource Monitoring:**
Using Prometheus, cadvisor, and Node Exporter, we collect real-time data on CPU, memory, and disk usage, helping us optimize task scheduling and resource allocation.

**Efficient Communication:** We utilize MQTT and UDP protocols to ensure low-latency communication between worker nodes and the CRMA, allowing for real-time task updates, health checks, and resource reporting.

**Autonomic Control:** Following the MAPE-K (Monitor, Analyze, Plan, Execute, Knowledge) model, we’ve enabled self-managing resource optimization, reducing the need for manual intervention.

![Alt text](https://gitlab.rz.uni-bamberg.de/ktr/proj/st-2024/group-crms/code/-/raw/main/Static/Images/CRMA-Diagram.png)

Our system is designed specifically for fog computing environments, where real-time data processing at the network edge is crucial. We’ve integrated Grafana dashboards to provide a visual representation of resource usage, allowing for proactive management of network performance.

With this enhanced CRMS, we’ve significantly improved reliability, scalability, and efficiency, making it ideal for large-scale IoT applications that demand real-time processing and decentralized control.

