#!/usr/bin/env python3
"""Local MQTT broker for the tap-probe demo.

Exposes two listeners:
  tcp://0.0.0.0:1883       the ESP32 publishes here
  ws://0.0.0.0:8080/mqtt   the browser dashboard subscribes here

Anonymous access is allowed on purpose: this is a bench demo on a trusted LAN,
and the report says so.  Swap this process for a self-hosted Beaver IoT broker
by changing PROBE_MQTT_BROKER_URI_DEFAULT in probe_config.h -- the topic layout
is identical.
"""
import argparse
import asyncio
import logging
import sys

from amqtt.broker import Broker

DEFAULT_TCP_PORT = 1883
DEFAULT_WS_PORT = 8080


def broker_config(host: str, tcp_port: int, ws_port: int) -> dict:
    return {
        "listeners": {
            "default": {"type": "tcp", "bind": "%s:%d" % (host, tcp_port),
                        "max_connections": 50},
            "ws-mqtt": {"type": "ws", "bind": "%s:%d" % (host, ws_port),
                        "max_connections": 50},
        },
        "sys_interval": 20,
        "auth": {"allow-anonymous": True, "password-file": None},
        "topic-check": {"enabled": False},
    }


async def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        description="Local MQTT broker for the tap-probe demo (defaults: 1883/8080)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT)
    ap.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    broker = Broker(broker_config(args.host, args.tcp_port, args.ws_port))
    await broker.start()
    print("broker listening: tcp/%d and ws/%d" % (args.tcp_port, args.ws_port),
          flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        await broker.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
