# Picksmart PTL Integration for Odoo 19

This Odoo 19 module integrates Odoo's inventory/stock system with the **Picksmart Pick-to-Light (PTL)** V24 tags/routers. It allows warehouse operators to associate Odoo products with physical Picksmart tags, direct pick operations via LED indicators/quantities on the tag, and dynamically update Odoo stock levels when buttons on the tag are pressed.

---

## Features

- **Product Tag Association**: Links Odoo products (`product.template`) with Picksmart physical tags using the tag's MAC address.
- **Dynamic Hardware Syncing**: Automatically updates tag screens (Product Name, Stock, and Pick/Basket Quantity) when product details change in Odoo.
- **PTL Button Interaction**: Processes callback events from physical tags via a webhook to adjust Odoo inventory levels:
  - **Button 0**: Confirms picking (subtracts the pickup quantity from the current on-hand stock and resets the pickup quantity to 0).
  - **Button 1**: Adjusts on-hand stock (+1).
  - **Button 3**: Adjusts on-hand stock (+3).
- **Real-Time UI Updates**: Leverages Odoo's Gevent/WebSocket Bus (`bus.bus`) to instantly refresh Odoo UI pages when a callback updates inventory values.
- **Offline Resiliency**: Features short request timeouts when communicating with the Picksmart router to prevent the Odoo UI from freezing if the hardware is offline.

---

## Documentation

- [User manual](docs/index.md): simple, step-by-step guide for FP Básica students.
- [Administration manual](docs/admin.md): installation, configuration, networking, Docker, maintenance, and troubleshooting.

The `docs` directory is ready to be used as the publishing source for GitHub Pages.

---

## Repository Structure

```text
├── docker-compose.yml       # Dev environment setup (Odoo 19 + PostgreSQL 15)
├── docs/                    # Manufacturer guides, manuals, and developer steps
├── src/
│   └── om_picksmart_ptl/    # Core Odoo module code
│       ├── controllers/     # API Endpoints (e.g., webhook callback)
│       ├── models/          # Product and Settings model overrides
│       ├── security/        # Access controls
│       └── views/           # Views for configuration and product forms
└── README.md                # This documentation
```

---

## Configuration & Usage

### 1. Settings configuration
Navigate to Odoo General Settings to configure the Picksmart Router connection parameters:
- **Router IP**: The IP address of your Picksmart Router (Default: `192.168.1.200`).
- **Style ID**: The screen template style configuration ID for the tag (Default: `50`).

### 2. Product Setup
1. In Odoo Inventory or Sales, open a **Product**.
2. Assign the **Tag MAC Address** (e.g., `CWT12345678` or `12345678`).
3. Set the desired **Pickup Quantity** (how many units should be picked).
4. Save the product. Odoo will attempt to contact the Picksmart Router and update the physical tag layout.

### 3. Button Callbacks & Webhook
The tag router notifies Odoo of physical button clicks by sending a POST request to Odoo:
- **URL**: `http://<your-odoo-domain>/picksmart/callback`
- **Method**: `POST`
- **Payload format**:
  ```json
  {
    "mac": "12345678",
    "result": 0
  }
  ```

---

## Development Setup

The project includes a `docker-compose.yml` to spin up a local development environment. Odoo is configured in multi-processing mode with `--workers` and `--gevent-port` enabled, which is crucial for handling WebSockets and the Bus system.

### Running locally:
1. Start the container stack:
   ```bash
   docker compose up -d
   ```
2. Open your browser and navigate to `http://localhost:8069`.
3. Log in, activate Developer Mode, and install the **Picksmart PTL Integration** module.
