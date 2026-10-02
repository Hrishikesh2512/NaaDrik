"""Command-line entry point: ``naadrik <command>``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from naadrik import __version__
from naadrik.config import Config, load_config
from naadrik.errors import NaadrikError

log = logging.getLogger("naadrik")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s naadrik %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    if not hasattr(args, "handler"):
        parser.print_help()
        return 2
    try:
        code = args.handler(args)
    except NaadrikError as exc:
        log.error("%s", exc)
        code = 1
    except KeyboardInterrupt:
        code = 130
    _exit_past_hung_audio(code)
    return code


def _exit_past_hung_audio(code: int) -> None:
    # PortAudio's own shutdown blocks forever on a stream that already hung, so skip it.
    from naadrik import audio_output

    if audio_output.has_abandoned_streams():
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)


def _device_arg(value: str) -> str | int:
    return int(value) if value.isdigit() else value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="naadrik", description="Naadrik: see through sound.")
    parser.add_argument("--version", action="version", version=f"naadrik {__version__}")
    parser.add_argument("--config", type=Path, help="path to config.yaml")
    parser.add_argument(
        "--device", type=_device_arg, help="audio output device index or name (overrides config)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    commands = parser.add_subparsers(title="commands")

    demo = commands.add_parser("demo", help="play example objects to hear the sound mapping")
    demo.add_argument("scenarios", nargs="*", help="scenario names (default: all)")
    demo.add_argument("--list", action="store_true", help="list scenarios and exit")
    demo.add_argument("--save-dir", type=Path, help="also write each scenario as a WAV file")
    demo.add_argument("--no-play", action="store_true", help="render without playing audio")
    demo.add_argument("--pause", type=float, default=0.8, help="seconds between scenarios")
    demo.set_defaults(handler=_run_demo)

    devices = commands.add_parser("devices", help="list audio output devices")
    devices.set_defaults(handler=_run_devices)
    return parser


def _run_demo(args: argparse.Namespace) -> int:
    from naadrik import audio_output
    from naadrik.demo import SCENARIOS, find_scenario, scenario_names
    from naadrik.sound_engine import SoundEngine

    if args.list:
        for scenario in SCENARIOS:
            print(f"{scenario.name:22} {scenario.description}")
        return 0
    try:
        chosen = [find_scenario(name) for name in args.scenarios] or list(SCENARIOS)
    except KeyError as exc:
        log.error("Unknown scenario %s. Available: %s", exc, ", ".join(scenario_names()))
        return 2

    config = load_config(args.config)
    engine = SoundEngine(config)
    for scenario in chosen:
        print(f"\n▶ {scenario.name}: {scenario.description}", flush=True)
        buffer = engine.render_paths(scenario.paths, scenario.duration_s)
        if args.save_dir:
            path = audio_output.save_wav(
                args.save_dir / f"{scenario.name}.wav", buffer, engine.sample_rate
            )
            log.info("saved %s", path)
        if not args.no_play:
            audio_output.play(
                buffer, engine.sample_rate, config.audio.block_size, _output_device(args, config)
            )
            time.sleep(args.pause)
    return 0


def _output_device(args: argparse.Namespace, config: Config) -> str | int | None:
    return args.device if args.device is not None else config.audio.device


def _run_devices(_args: argparse.Namespace) -> int:
    from naadrik import audio_output

    print(audio_output.list_devices())
    return 0


if __name__ == "__main__":
    sys.exit(main())
