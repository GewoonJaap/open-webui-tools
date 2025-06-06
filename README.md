# Open WebUI Tools

[![License](https://img.shields.io/github/license/GewoonJaap/open-webui-tools)](LICENSE)
[![Issues](https://img.shields.io/github/issues/GewoonJaap/open-webui-tools)](https://github.com/GewoonJaap/open-webui-tools/issues)
[![Stars](https://img.shields.io/github/stars/GewoonJaap/open-webui-tools)](https://github.com/GewoonJaap/open-webui-tools/stargazers)

A collection of open-source tools and utilities to extend and enhance [Open WebUI](https://github.com/open-webui/open-webui), a modern front-end interface for self-hosted large language models (LLMs). Open WebUI is similar to ChatGPT but designed for local or self-hosted LLMs, supporting connections to models via the OpenAI API interface.

This project provides reusable, modular, and easy-to-integrate components for developers working with custom LLM setups through Open WebUI.

## What is Open WebUI?

Open WebUI is a sleek, extensible front-end for interacting with LLMs (such as Llama, Mistral, etc.) that are self-hosted or run on your own infrastructure. It offers a familiar chat interface like ChatGPT, but is focused on privacy, flexibility, and the ability to connect to any LLM supporting the OpenAI API standard.

**Learn more:** [Open WebUI on GitHub](https://github.com/open-webui/open-webui)

## Features

- **Modular Components**: Each tool is designed as a standalone module for easy integration in Open WebUI.
- **Modern Stack**: Built using up-to-date web technologies and best practices.
- **Open Source**: Community contributions and ideas are welcome!
- **Flexible**: Use only the tools you need; all modules are independent and customizable.

## Getting Started

### Prerequisites
- An Open WebUI instance (optional, for integration)

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create your branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -am 'Add new feature'`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Issues & Support

If you encounter any problems or have suggestions, please open an [issue](https://github.com/GewoonJaap/open-webui-tools/issues).

---

## Available Tools

This repository provides the following tools, each with its own folder and documentation:

### Tools
- **Flight Data Provider** (`tools/flight_tracker/flight_tracker.py`)
  - Fetches flight data for a specified flight number using flight-status.com via the Jina API.
  - See: `tools/flight_tracker/DESCRIPTION.md` and `FUNCTIONS.md`
- **Google Maps Text Search** (`tools/google_maps/google-maps-tool.py`)
  - Returns place suggestions for a specified query and location using the Google Maps Text Search API.
  - See: `tools/google_maps/DESCRIPTION.md` and `FUNCTIONS.md`
- **Google Veo Video Generator** (`tools/veo_2/veo-video-gen.py`)
  - Generates videos using Google's Veo API based on text prompts or images.
  - See: `tools/veo_2/DESCRIPTION.md` and `FUNCTIONS.md`
- **Replicate VEO 3 Video Generator** (`tools/veo_3/veo-3-replicate-video-gen.py`)
  - Generates videos using Replicate's VEO 3 API based on text prompts.
  - See: `tools/veo_3/DESCRIPTION.md` and `FUNCTIONS.md`

### Functions
- **x_to_nitter** (`functions/x-to-nitter/x-to-nitter.py`)
  - Converts a Twitter/X URL to its equivalent Nitter URL for privacy-friendly viewing.
  - See: `functions/x-to-nitter/FUNCTIONS.md`

Each tool and function is documented in its respective folder. For details on usage, configuration (valves), and API, see the `DESCRIPTION.md` and `FUNCTIONS.md` files in each tool's directory.

---

Built and maintained by [GewoonJaap](https://github.com/GewoonJaap).
