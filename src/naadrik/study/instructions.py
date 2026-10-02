"""Participant-facing text for each condition and phase."""

from __future__ import annotations

BASELINE = (
    "Baseline. You will hear a sound that represents one object. Nothing about the sounds "
    "will be explained yet. For each sound, give your best guess of where the object is, "
    "how high, how far and what colour. There is no feedback."
)

TRAINING = {
    "naadrik": (
        "Training. Each object is one sound. Left and right: where the sound comes from. "
        "Height: higher objects have higher pitch. Distance: close objects pulse fast, far "
        "objects pulse slowly; volume does not change with distance. Colour: red is a plucked "
        "string like a sitar, green a bowed string like a violin, blue a flute; mixed colours "
        "play several instruments, and white plays all three loudly. Every object also has "
        "a soft hum underneath, so a black object is just the hum. After each answer you "
        "will be told the correct answer and hear the sound again."
    ),
    "voice": (
        "Training. A tick marks the start of a sweep from left to right, once a second. "
        "Left and right: an object on the left sounds early in the sweep and in the left "
        "ear; on the right, late and in the right ear. Height: higher objects have higher "
        "pitch. Distance: closer objects look bigger, so they sound longer and cover more "
        "pitches. Colour: only brightness is heard; brighter objects are louder. After each "
        "answer you will be told the correct answer and hear the sound again."
    ),
}

TEST = "Test. Same task as before, using what you have learned. There is no feedback."


def intro(phase: str, condition: str) -> str:
    if phase == "baseline":
        return BASELINE
    if phase == "training":
        return TRAINING[condition]
    return TEST
