# Cloudless Resource Monitoring System (CRMS) v2.0

**Distributed Fog Computing & Autonomous Resource Orchestration**

CRMS is a decentralized resource management framework designed for edge/fog computing environments. By integrating Software-Defined Networking (SDN) with a MAPE-K autonomic control loop, the system eliminates single points of failure (SPOF) and optimizes resource allocation across distributed nodes with sub-millisecond coordination requirements.

##  Architectural Design

The system transitions from traditional centralized cloud logic to a distributed microservices architecture. Each worker node operates as an autonomous unit running a four-tier stack:

<div align="center">

![CRMS Architecture](https://raw.githubusercontent.com/bishwothakuri/crms/main/static/images/crma-architecture.png#gh-light-mode-only)
![CRMS Architecture](https://raw.githubusercontent.com/bishwothakuri/crms/main/Static/Images/crma-architecture.png#gh-dark-mode-only)

</div>

- **Coordinator**: Manages node-level state and consensus
- **Builder**: Orchestrates containerized workloads via Docker Engine
- **Monitor**: Real-time telemetry ingestion
- **Query**: High-availability data retrieval for distributed state awareness

##  Tech Stack & Engineering Choices

- **Infrastructure**: Docker, Kubernetes, SDN (Software Defined Networking)
- **Communication**: MQTT & UDP
  - *Choice*: UDP was selected for low-latency health heartbeats, while MQTT ensures reliable asynchronous state updates across high-latency fog links
- **Observability**: Prometheus, cAdvisor, Node Exporter, and Grafana
- **Storage**: XFS Filesystem (Optimized for high-concurrency container I/O)

##  Key Engineering Challenges Solved

### 1. Fault Tolerance & Decentralization

We implemented a peer-to-peer management model where worker nodes function autonomously. This prevents the "cascading failure" common in centralized orchestrators.

### 2. Low-Latency Telemetry

Using a MAPE-K (Monitor-Analyze-Plan-Execute) loop, the system performs self-healing. By leveraging Prometheus for metrics and MQTT for the control plane, the system achieves real-time task scheduling at the network edge.

### 3. Resource Constraints

Designed specifically for Fog nodes where CPU/RAM are finite. The microservice footprint was minimized to ensure the monitoring overhead does not starve the actual workloads.

##  Getting Started (Production Setup)

### Prerequisites

- **Host OS**: Ubuntu with XFS Filesystem (Critical for container volume performance)
- **Engine**: Docker & Docker Compose

### Deployment
```bash
# Clone the distributed stack
git clone git@github.com:bishwothakuri/crms.git && cd worker_node

# Build the autonomous microservice layers
docker-compose build

# Launch the distributed node
docker-compose up -d
```

##  Observability

The system exports metrics to a pre-configured Grafana dashboard, providing visibility into:

- **Node Saturation**: CPU/Memory pressure via cAdvisor
- **Network Latency**: UDP heartbeat frequency and MQTT broker throughput
- **MAPE-K Cycle Time**: Latency between resource detection and autonomous re-planning
