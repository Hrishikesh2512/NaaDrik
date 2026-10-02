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

    live = commands.add_parser("live", help="sonify the webcam in real time")
    live.add_argument("--camera", type=int, help="camera index (overrides config)")
    live.add_argument("--no-window", action="store_true", help="run without the debug window")
    live.add_argument("--duration", type=float, help="stop after this many seconds")
    live.add_argument(
        "--save-debug", type=Path, help="write the debug view to this image each second"
    )
    live.add_argument("--mute", action="store_true", help="start with sound muted")
    live.set_defaults(handler=_run_live)

    train = commands.add_parser("train", help="training mode with spoken labels")
    train.add_argument("--no-camera", action="store_true", help="practise with synthetic objects")
    train.add_argument("--trials", type=int, default=12, help="objects in a --no-camera session")
    train.add_argument("--no-speech", action="store_true", help="sounds only")
    train.add_argument("--always-speak", action="store_true", help="ignore the speech fade-out")
    train.add_argument("--reset-progress", action="store_true", help="start again from session 1")
    train.add_argument("--camera", type=int, help="camera index (overrides config)")
    train.add_argument("--no-window", action="store_true", help="run without the debug window")
    train.add_argument("--duration", type=float, help="stop after this many seconds")
    train.set_defaults(handler=_run_train)

    study = commands.add_parser("study", help="run the evaluation study (no camera needed)")
    study.add_argument("--participant", required=True, help="participant id, e.g. P01")
    study.add_argument(
        "--condition",
        choices=["naadrik", "voice", "both"],
        default="both",
        help="sonification to test (voice = vOICe-style baseline)",
    )
    study.add_argument(
        "--order",
        choices=["naadrik-first", "voice-first"],
        default="naadrik-first",
        help="condition order for --condition both; alternate it across participants",
    )
    study.add_argument(
        "--phases", default="baseline,training,test", help="comma-separated subset of phases"
    )
    study.add_argument(
        "--simulate",
        choices=["oracle", "random"],
        help="simulated participant to validate the protocol (no audio, no keyboard)",
    )
    study.add_argument("--seed", type=int, help="random seed for stimulus order")
    study.set_defaults(handler=_run_study)

    analyse = commands.add_parser("analyse", help="summarise study results with charts")
    analyse.add_argument("paths", nargs="*", type=Path, help="result CSVs or folders")
    analyse.add_argument("--out", type=Path, help="output folder (default: <results>/report)")
    analyse.set_defaults(handler=_run_analyse)

    calibrate = commands.add_parser("calibrate", help="record near/far depth references")
    calibrate.add_argument("--camera", type=int, help="camera index (overrides config)")
    calibrate.set_defaults(handler=_run_calibrate)

    models = commands.add_parser("models", help="show or download the detection and depth models")
    models.add_argument("action", nargs="?", choices=["status", "download"], default="status")
    models.set_defaults(handler=_run_models)

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


def _run_live(args: argparse.Namespace) -> int:
    from naadrik.live import LiveOptions, LiveSession

    options = LiveOptions(
        camera_index=args.camera,
        device=args.device,
        show_window=not args.no_window,
        duration_s=args.duration,
        save_debug=args.save_debug,
        muted=args.mute,
    )
    LiveSession(load_config(args.config), options).run()
    return 0


def _run_train(args: argparse.Namespace) -> int:
    from naadrik.speech import Speaker
    from naadrik.training.progress import TrainingProgress, speech_probability

    config = load_config(args.config)
    progress = TrainingProgress.load(config.training)
    if args.reset_progress:
        progress.reset()
    session = progress.start_session()
    if args.no_speech:
        probability, speaker = 0.0, None
    else:
        probability = 1.0 if args.always_speak else speech_probability(session, config.training)
        speaker = Speaker(config.training, config.audio.sample_rate)
    log.info("training session %d: announcing %.0f%% of objects", session, probability * 100)

    if args.no_camera:
        from naadrik.training.scripted import run_scripted_training

        run_scripted_training(
            config, speaker, probability, args.trials, _output_device(args, config)
        )
        return 0

    from naadrik.live import LiveOptions, LiveSession
    from naadrik.training.coach import TrainingCoach

    coach = TrainingCoach(config, speaker.say, probability) if speaker else None
    options = LiveOptions(
        camera_index=args.camera,
        device=args.device,
        show_window=not args.no_window,
        duration_s=args.duration,
        coach=coach,
    )
    LiveSession(config, options).run()
    return 0


def _run_study(args: argparse.Namespace) -> int:
    import random

    from naadrik import audio_output
    from naadrik.study.responders import KeyboardResponder, SimulatedResponder
    from naadrik.study.session import PHASES, StudySession

    config = load_config(args.config)
    phases = tuple(p.strip() for p in args.phases.split(",") if p.strip())
    unknown = set(phases) - set(PHASES)
    if unknown:
        log.error("Unknown phase(s) %s; choose from %s", sorted(unknown), ", ".join(PHASES))
        return 2
    rng = random.Random(args.seed)
    participant = args.participant
    if args.simulate:
        responder = SimulatedResponder(args.simulate, rng)
        participant = f"sim-{args.simulate}-{participant}"

        def play(_audio):  # type: ignore[no-untyped-def]
            return None

    else:
        responder = KeyboardResponder()
        device = _output_device(args, config)

        def play(audio):  # type: ignore[no-untyped-def]
            audio_output.play(audio, config.audio.sample_rate, config.audio.block_size, device)

    if args.condition == "both":
        conditions = ["naadrik", "voice"]
        if args.order == "voice-first":
            conditions.reverse()
    else:
        conditions = [args.condition]
    for condition in conditions:
        session = StudySession(config, participant, condition, responder, play, rng)
        path = session.run(phases)
        log.info("%s results written to %s", condition, path)
    return 0


def _run_analyse(args: argparse.Namespace) -> int:
    from naadrik.study.analysis import analyse

    config = load_config(args.config)
    results_dir = Path(config.study.results_dir)
    paths = args.paths or [results_dir]
    report, charts = analyse(paths, args.out or results_dir / "report")
    print(report.read_text(encoding="utf-8"))
    for chart in charts:
        log.info("chart: %s", chart)
    log.info("report: %s", report)
    return 0


def _run_calibrate(args: argparse.Namespace) -> int:
    import dataclasses

    from naadrik.calibrate import run_calibration

    config = load_config(args.config)
    if args.camera is not None:
        camera = dataclasses.replace(config.camera, index=args.camera)
        config = dataclasses.replace(config, camera=camera)
    run_calibration(config)
    return 0


def _run_models(args: argparse.Namespace) -> int:
    from naadrik import models

    config = load_config(args.config)
    for spec, path, state in models.model_status(config):
        if args.action == "download" and state == "missing":
            models.download(spec, path)
            state = "downloaded"
        print(f"{state:10} {spec.name} [{spec.licence}]\n           {path}")
    return 0


def _run_devices(_args: argparse.Namespace) -> int:
    from naadrik import audio_output

    print(audio_output.list_devices())
    return 0


if __name__ == "__main__":
    sys.exit(main())
