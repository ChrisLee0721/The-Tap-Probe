"""Live capture and playback viewer for the ESP32-S3 binary sample stream."""

import argparse
import struct
import time
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import serial


SYNC = b"\xA5\x5A"
PACKET_SIZE = 20
PACKET_FORMAT = "<IiiiH"
FILE_MAGIC = b"TPW1"
FILE_HEADER = FILE_MAGIC + struct.pack("<H", PACKET_SIZE)


def parse_packets(buffer):
    packets = []
    while True:
        start = buffer.find(SYNC)
        if start < 0:
            del buffer[:-1]
            break
        if start:
            del buffer[:start]
        if len(buffer) < PACKET_SIZE:
            break
        payload = bytes(buffer[2:PACKET_SIZE])
        sequence, x, y, z, distance = struct.unpack(PACKET_FORMAT, payload)
        packets.append((sequence, x / 1_000_000, y / 1_000_000,
                        z / 1_000_000, distance))
        del buffer[:PACKET_SIZE]
    return packets


def encode_packet(packet):
    sequence, x, y, z, distance = packet
    return SYNC + struct.pack(
        PACKET_FORMAT, sequence, int(x * 1_000_000), int(y * 1_000_000),
        int(z * 1_000_000), distance
    )


def load_recording(path):
    with open(path, "rb") as stream:
        header = stream.read(len(FILE_HEADER))
        if header != FILE_HEADER:
            raise ValueError(f"{path} is not a tap-probe recording")
        data = bytearray(stream.read())
    return parse_packets(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM4")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--seconds", type=float, default=5.0,
                        help="visible history window")
    parser.add_argument("--record", help="save live samples to a .tpw file")
    parser.add_argument("--playback", help="replay a .tpw file instead of serial")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="playback speed multiplier")
    args = parser.parse_args()

    if args.speed <= 0:
        parser.error("--speed must be greater than zero")
    ser = None
    record = None
    playback = load_recording(args.playback) if args.playback else None
    if playback is None:
        ser = serial.Serial(args.port, args.baud, timeout=0)
        if args.record:
            record = open(args.record, "wb")
            record.write(FILE_HEADER)
    capacity = max(100, int(args.seconds * 2000))
    samples = [deque(maxlen=capacity) for _ in range(4)]
    sequences = deque(maxlen=capacity)
    buffer = bytearray()
    state = {
        "received": 0, "lost": 0, "last": None, "started": time.monotonic(),
        "play_index": 0, "play_started": None, "paused": False,
        "window": capacity,
    }

    fig, axes = plt.subplots(4, 1, sharex=True, figsize=(11, 8))
    labels = ("X dynamic acceleration (g)", "Y dynamic acceleration (g)",
              "Z dynamic acceleration (g)", "Distance (mm)")
    lines = [axis.plot([], [])[0] for axis in axes]
    for axis, label in zip(axes, labels):
        axis.set_ylabel(label)
        axis.grid(True)
    axes[-1].set_xlabel("sample sequence")

    def consume(packet):
        sequence, x, y, z, distance = packet
        if state["last"] is not None and sequence > state["last"] + 1:
            state["lost"] += sequence - state["last"] - 1
        state["last"] = sequence
        sequences.append(sequence)
        for target, value in zip(samples, (x, y, z, distance)):
            target.append(value)
        state["received"] += 1
        if record:
            record.write(encode_packet(packet))

    def update(_):
        if state["paused"]:
            return lines
        if playback is None:
            buffer.extend(ser.read(ser.in_waiting or 1))
            packets = parse_packets(buffer)
        else:
            if state["play_started"] is None:
                state["play_started"] = time.monotonic()
            elapsed = (time.monotonic() - state["play_started"]) * args.speed
            target = min(len(playback), int(elapsed * 2000))
            packets = playback[state["play_index"]:target]
            state["play_index"] = target
        for packet in packets:
            consume(packet)

        if not sequences:
            return lines
        x_values = list(sequences)
        for line, values in zip(lines, samples):
            line.set_data(x_values, list(values))
        axes[-1].set_xlim(
            max(x_values[0], x_values[-1] - state["window"]),
            max(x_values[-1], x_values[0] + 1),
        )
        for axis, values in zip(axes, samples):
            values = list(values)
            low, high = min(values), max(values)
            margin = max((high - low) * 0.1, 0.001)
            axis.set_ylim(low - margin, high + margin)
        elapsed = time.monotonic() - state["started"]
        rate = state["received"] / elapsed if elapsed else 0
        mode = "playback" if playback is not None else "live"
        fig.suptitle(
            f"{mode}  {rate:.0f} Hz   lost: {state['lost']}   "
            f"window: {state['window']} samples   "
            "[+/-] zoom  [space] pause  [r] reset")
        return lines

    def on_key(event):
        if event.key in ("+", "="):
            state["window"] = min(capacity, int(state["window"] * 1.5))
        elif event.key == "-":
            state["window"] = max(50, int(state["window"] / 1.5))
        elif event.key == " ":
            state["paused"] = not state["paused"]
        elif event.key == "r":
            for values in samples:
                values.clear()
            sequences.clear()
            state["last"] = None
            state["received"] = 0
            state["lost"] = 0
            state["started"] = time.monotonic()
            if playback is not None:
                state["play_index"] = 0
                state["play_started"] = time.monotonic()

    fig.canvas.mpl_connect("key_press_event", on_key)
    animation = FuncAnimation(
        fig, update, interval=33, blit=False, cache_frame_data=False
    )
    try:
        plt.show()
    finally:
        if record:
            record.close()
        if ser:
            ser.close()


if __name__ == "__main__":
    main()
