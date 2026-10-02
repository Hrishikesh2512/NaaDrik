package com.naadrik.core.config

import org.snakeyaml.engine.v2.api.Load
import org.snakeyaml.engine.v2.api.LoadSettings
import org.snakeyaml.engine.v2.exceptions.YamlEngineException

/** Typed view of the shared config.yaml; field names follow the YAML keys. */
data class Config(
    val audio: AudioConfig,
    val pitch: PitchConfig,
    val pulse: PulseConfig,
    val colour: ColourConfig,
    val instruments: InstrumentsConfig,
    val spatial: SpatialConfig,
    val objects: ObjectsConfig,
    val camera: CameraConfig,
    val detection: DetectionConfig,
    val depth: DepthConfig,
    val tracking: TrackingConfig,
    val priority: PriorityConfig,
    val training: TrainingConfig,
    val study: StudyConfig,
    val android: AndroidConfig,
) {
    init {
        val longestEvent = pulse.maxGateS + pulse.releaseMs / 1000.0
        require(
            instruments.noteDurationS >= longestEvent,
            "instruments.note_duration_s must be at least pulse.max_gate_s + pulse.release_ms",
        )
    }

    companion object {
        fun parse(yaml: String): Config {
            val data =
                try {
                    Load(LoadSettings.builder().build()).loadFromString(yaml)
                } catch (e: YamlEngineException) {
                    throw ConfigException("Config is not valid YAML: ${e.message}")
                }
            val root = data as? Map<*, *> ?: throw ConfigException("config must be a mapping")
            return YamlSection(root, "config").build { fromYaml() }
        }
    }
}

data class AudioConfig(
    val sampleRate: Int,
    val blockSize: Int,
    val masterGain: Double,
    val device: String?,
    val liveLatencyS: Double,
) {
    init {
        require(sampleRate >= 8000, "audio.sample_rate must be at least 8000")
        require(blockSize > 0, "audio.block_size must be positive")
        require(masterGain > 0.0 && masterGain <= 2.0, "audio.master_gain must be in (0, 2]")
        require(liveLatencyS > 0.0 && liveLatencyS <= 0.5, "audio.live_latency_s must be in (0, 0.5]")
    }
}

data class PitchConfig(
    val baseHz: Double,
    val octaves: Double,
    val scale: List<Int>,
) {
    init {
        require(baseHz > 20.0, "pitch.base_hz must be above 20 Hz")
        require(octaves > 0.0, "pitch.octaves must be positive")
        require(scale.isNotEmpty(), "pitch.scale must not be empty")
        require(
            scale.all { it in 0..11 } && scale[0] == 0,
            "pitch.scale must start at 0 and hold semitone offsets below 12",
        )
    }
}

data class PulseConfig(
    val nearHz: Double,
    val farHz: Double,
    val dutyCycle: Double,
    val maxGateS: Double,
    val attackMs: Double,
    val releaseMs: Double,
) {
    init {
        require(nearHz > farHz && farHz > 0.0, "pulse.near_hz must exceed pulse.far_hz > 0")
        require(dutyCycle > 0.0 && dutyCycle < 1.0, "pulse.duty_cycle must be in (0, 1)")
        require(maxGateS > 0.0, "pulse.max_gate_s must be positive")
        require(attackMs >= 0.0 && releaseMs > 0.0, "pulse envelope times invalid")
    }
}

data class ColourConfig(
    val thresholds: List<Double>,
    val levels: List<Double>,
    val centralFraction: Double,
    val whiteBalance: Boolean,
) {
    init {
        require(thresholds.size == 2, "colour.thresholds must have exactly 2 items")
        require(levels.size == 3, "colour.levels must have exactly 3 items")
        require(centralFraction > 0.0 && centralFraction <= 1.0, "colour.central_fraction must be in (0, 1]")
        val (low, high) = thresholds
        require(0.0 < low && low < high && high < 1.0, "colour.thresholds must satisfy 0 < low < high < 1")
        require(levels[0] == 0.0, "colour.levels[0] must be 0 so 'off' is silent")
        require(levels[0] < levels[1] && levels[1] < levels[2], "colour.levels must increase")
    }
}

data class PluckConfig(
    val gain: Double,
    val decayS: Double,
    val brightness: Double,
    val buzz: Double,
    val drive: Double,
    val sympathetic: Double,
)

data class BowedConfig(
    val gain: Double,
    val vibratoHz: Double,
    val vibratoCents: Double,
    val vibratoDelayS: Double,
    val cutoffHz: Double,
    val bodyResonancesHz: List<Double>,
    val bowNoise: Double,
)

data class PresenceConfig(
    val level: Double,
    val cutoffRatio: Double,
    val noise: Double,
) {
    init {
        require(
            level > 0.0 && level <= 1.0,
            "instruments.presence.level must be in (0, 1]: every object must stay audible, " +
                "including black ones",
        )
        require(cutoffRatio >= 1.0, "instruments.presence.cutoff_ratio must be >= 1")
        require(noise >= 0.0 && noise < 1.0, "instruments.presence.noise must be in [0, 1)")
    }
}

data class FluteConfig(
    val gain: Double,
    val harmonics: List<Double>,
    val breath: Double,
    val chiff: Double,
    val vibratoHz: Double,
    val vibratoCents: Double,
    val tremoloDepth: Double,
)

data class InstrumentsConfig(
    val noteDurationS: Double,
    val pluck: PluckConfig,
    val bowed: BowedConfig,
    val presence: PresenceConfig,
    val flute: FluteConfig,
)

data class SpatialConfig(
    val mode: String,
    val maxAzimuthDeg: Double,
    val headRadiusM: Double,
    val extraIldDb: Double,
    val rearLowpassHz: Double,
    val smoothingMs: Double,
) {
    init {
        require(mode == "head_model" || mode == "pan", "spatial.mode must be head_model or pan")
        require(maxAzimuthDeg > 0.0 && maxAzimuthDeg <= 90.0, "spatial.max_azimuth_deg must be in (0, 90]")
        require(smoothingMs >= 0.0, "spatial.smoothing_ms must not be negative")
    }
}

data class ObjectsConfig(
    val maxObjects: Int,
) {
    init {
        require(maxObjects in 1..8, "objects.max_objects must be between 1 and 8")
    }
}

data class CameraConfig(
    val index: Int,
    val captureWidth: Int,
    val captureHeight: Int,
    val fps: Int,
    val processWidth: Int,
) {
    init {
        require(index >= 0, "camera.index must not be negative")
        require(processWidth in 64..captureWidth, "camera.process_width invalid")
    }
}

data class DetectionConfig(
    val modelPath: String,
    val scoreThreshold: Double,
    val maxResults: Int,
) {
    init {
        require(scoreThreshold > 0.0 && scoreThreshold < 1.0, "detection.score_threshold must be in (0, 1)")
    }
}

data class DepthConfig(
    val modelPath: String,
    val everyNFrames: Int,
    val inputWidth: Int,
    val threads: Int,
    val boxFraction: Double,
    val normalisation: String,
    val calibrationPath: String,
    val levels: Int,
    val hysteresis: Double,
) {
    init {
        require(everyNFrames >= 1, "depth.every_n_frames must be at least 1")
        require(inputWidth % 14 == 0, "depth.input_width must be a multiple of 14")
        require(
            normalisation == "scene" || normalisation == "calibrated",
            "depth.normalisation must be scene or calibrated",
        )
        require(levels == 0 || levels >= 2, "depth.levels must be 0 or at least 2")
        require(hysteresis >= 0.0 && hysteresis < 0.5, "depth.hysteresis must be in [0, 0.5)")
    }
}

data class TrackingConfig(
    val iouThreshold: Double,
    val maxMissedFrames: Int,
    val minHits: Int,
    val positionSmoothing: Double,
    val distanceSmoothing: Double,
    val colourSmoothing: Double,
) {
    init {
        for ((name, value) in listOf(
            "position_smoothing" to positionSmoothing,
            "distance_smoothing" to distanceSmoothing,
            "colour_smoothing" to colourSmoothing,
        )) {
            require(value > 0.0 && value <= 1.0, "tracking.$name must be in (0, 1]")
        }
    }
}

data class PriorityConfig(
    val classImportance: Map<String, Double>,
    val defaultImportance: Double,
    val centreWeight: Double,
    val motionBoost: Double,
    val approachSpeed: Double,
    val movingSpeed: Double,
    val switchMargin: Double,
) {
    init {
        require(centreWeight in 0.0..1.0, "priority.centre_weight must be in [0, 1]")
    }
}

data class TrainingConfig(
    val ttsCommand: String,
    val voice: String,
    val wordsPerMinute: Int,
    val speechGain: Double,
    val spatialiseSpeech: Boolean,
    val duckDb: Double,
    val gapS: Double,
    val repeatS: Double,
    val includeHeight: Boolean,
    val fullSpeechSessions: Int,
    val fadeSessions: Int,
    val progressPath: String?,
) {
    init {
        require(wordsPerMinute in 80..450, "training.words_per_minute must be 80-450")
        require(duckDb >= 0.0, "training.duck_db must not be negative")
        require(fullSpeechSessions >= 0, "training.full_speech_sessions must be >= 0")
        require(fadeSessions >= 0, "training.fade_sessions must be >= 0")
    }
}

data class BaselineSonifierConfig(
    val sweepS: Double,
    val rows: Int,
    val columns: Int,
    val lowHz: Double,
    val highHz: Double,
    val greyscale: String,
    val click: Boolean,
) {
    init {
        require(sweepS > 0.0, "study.baseline_sonifier.sweep_s must be positive")
        require(rows >= 2 && columns >= 2, "baseline sonifier needs >= 2 rows/columns")
        require(lowHz > 0.0 && lowHz < highHz, "baseline sonifier: low_hz < high_hz required")
        require(greyscale == "luma" || greyscale == "mean", "greyscale must be luma or mean")
    }
}

data class StudyConfig(
    val stimulusS: Double,
    val colours: List<String>,
    val baselineTrials: Int,
    val trainingTrials: Int,
    val testTrials: Int,
    val resultsDir: String,
    val baselineSonifier: BaselineSonifierConfig,
) {
    init {
        require(stimulusS > 0.0, "study.stimulus_s must be positive")
        require(colours.size >= 2, "study.colours needs at least two colours")
        require(colours.toSet().size == colours.size, "study.colours has duplicates")
        require(baselineTrials >= 0 && trainingTrials >= 0 && testTrials >= 0, "study trial counts must not be negative")
    }
}

data class AndroidConfig(
    val detectionModel: String,
    val depthModel: String,
    val depthInputSize: Int,
    val depthDelegate: String,
    val depthThreads: Int,
    val detectionDelegate: String,
    val analysisWidth: Int,
    val analysisHeight: Int,
    val useArcoreDepth: Boolean,
) {
    init {
        require(depthDelegate == "cpu" || depthDelegate == "gpu", "android.depth_delegate must be cpu or gpu")
        require(detectionDelegate == "cpu" || detectionDelegate == "gpu", "android.detection_delegate must be cpu or gpu")
        require(depthInputSize > 0, "android.depth_input_size must be positive")
        require(depthThreads >= 1, "android.depth_threads must be at least 1")
    }
}

private fun YamlSection.fromYaml(): Config =
    Config(
        audio =
            child("audio") {
                AudioConfig(int("sample_rate"), int("block_size"), double("master_gain"), device("device"), double("live_latency_s"))
            },
        pitch = child("pitch") { PitchConfig(double("base_hz"), double("octaves"), ints("scale")) },
        pulse =
            child("pulse") {
                PulseConfig(
                    double("near_hz"),
                    double("far_hz"),
                    double("duty_cycle"),
                    double("max_gate_s"),
                    double("attack_ms"),
                    double("release_ms"),
                )
            },
        colour =
            child("colour") {
                ColourConfig(doubles("thresholds"), doubles("levels"), double("central_fraction"), bool("white_balance"))
            },
        instruments =
            child("instruments") {
                InstrumentsConfig(
                    noteDurationS = double("note_duration_s"),
                    pluck =
                        child("pluck") {
                            PluckConfig(
                                double("gain"),
                                double("decay_s"),
                                double("brightness"),
                                double("buzz"),
                                double("drive"),
                                double("sympathetic"),
                            )
                        },
                    bowed =
                        child("bowed") {
                            BowedConfig(
                                double("gain"),
                                double("vibrato_hz"),
                                double("vibrato_cents"),
                                double("vibrato_delay_s"),
                                double("cutoff_hz"),
                                doubles("body_resonances_hz"),
                                double("bow_noise"),
                            )
                        },
                    presence = child("presence") { PresenceConfig(double("level"), double("cutoff_ratio"), double("noise")) },
                    flute =
                        child("flute") {
                            FluteConfig(
                                double("gain"),
                                doubles("harmonics"),
                                double("breath"),
                                double("chiff"),
                                double("vibrato_hz"),
                                double("vibrato_cents"),
                                double("tremolo_depth"),
                            )
                        },
                )
            },
        spatial =
            child("spatial") {
                SpatialConfig(
                    string("mode"),
                    double("max_azimuth_deg"),
                    double("head_radius_m"),
                    double("extra_ild_db"),
                    double("rear_lowpass_hz"),
                    double("smoothing_ms"),
                )
            },
        objects = child("objects") { ObjectsConfig(int("max_objects")) },
        camera =
            child("camera") {
                CameraConfig(int("index"), int("capture_width"), int("capture_height"), int("fps"), int("process_width"))
            },
        detection = child("detection") { DetectionConfig(string("model_path"), double("score_threshold"), int("max_results")) },
        depth =
            child("depth") {
                DepthConfig(
                    string("model_path"),
                    int("every_n_frames"),
                    int("input_width"),
                    int("threads"),
                    double("box_fraction"),
                    string("normalisation"),
                    string("calibration_path"),
                    int("levels"),
                    double("hysteresis"),
                )
            },
        tracking =
            child("tracking") {
                TrackingConfig(
                    double("iou_threshold"),
                    int("max_missed_frames"),
                    int("min_hits"),
                    double("position_smoothing"),
                    double("distance_smoothing"),
                    double("colour_smoothing"),
                )
            },
        priority =
            child("priority") {
                PriorityConfig(
                    doubleMap("class_importance"),
                    double("default_importance"),
                    double("centre_weight"),
                    double("motion_boost"),
                    double("approach_speed"),
                    double("moving_speed"),
                    double("switch_margin"),
                )
            },
        training =
            child("training") {
                TrainingConfig(
                    string("tts_command"),
                    string("voice"),
                    int("words_per_minute"),
                    double("speech_gain"),
                    bool("spatialise_speech"),
                    double("duck_db"),
                    double("gap_s"),
                    double("repeat_s"),
                    bool("include_height"),
                    int("full_speech_sessions"),
                    int("fade_sessions"),
                    stringOrNull("progress_path"),
                )
            },
        study =
            child("study") {
                StudyConfig(
                    double("stimulus_s"),
                    strings("colours"),
                    int("baseline_trials"),
                    int("training_trials"),
                    int("test_trials"),
                    string("results_dir"),
                    child("baseline_sonifier") {
                        BaselineSonifierConfig(
                            double("sweep_s"),
                            int("rows"),
                            int("columns"),
                            double("low_hz"),
                            double("high_hz"),
                            string("greyscale"),
                            bool("click"),
                        )
                    },
                )
            },
        android =
            child("android") {
                AndroidConfig(
                    string("detection_model"),
                    string("depth_model"),
                    int("depth_input_size"),
                    string("depth_delegate"),
                    int("depth_threads"),
                    string("detection_delegate"),
                    int("analysis_width"),
                    int("analysis_height"),
                    bool("use_arcore_depth"),
                )
            },
    )
