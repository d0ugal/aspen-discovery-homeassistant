# Aspen Discovery Home Assistant Integration

A [Home Assistant](https://www.home-assistant.io/) integration for [Aspen Discovery](https://github.com/Aspen-Discovery/aspen-discovery) library management systems.

## Features

- **Sensors**: books checked out, books overdue, holds ready to collect, holds waiting, outstanding fines
- **Calendar**: due dates for each checked-out item
- **Service**: `aspen_discovery.renew_all` to renew all eligible checkouts
- **Multiple accounts**: add one entry per library account

## Installation

Install via [HACS](https://hacs.xyz/) or copy `custom_components/aspen_discovery` into your HA config directory.

## Configuration

Add the integration via **Settings → Devices & Services → Add Integration → Aspen Discovery**.

You will need:
- Your library catalogue URL (e.g. `https://catalog.yourlibrary.org`)
- Your library card number
- Your PIN / password
