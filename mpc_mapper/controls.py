"""One view over the controls of every supported device.

Control ids:  APC mini mk2   pad:N track:N scene:N shift fader:N
              X-Touch Compact xt.<kind>:N (see xtouch.py)
"""
from __future__ import annotations

from . import apc, xtouch

ALL_CONTROLS: list[str] = list(apc.ALL_CONTROLS) + list(xtouch.ALL_CONTROLS)
_ALL = set(ALL_CONTROLS)


def exists(control: str) -> bool:
    return control in _ALL


def device(control: str) -> str:
    return "xtouch" if xtouch.is_xtouch(control) else "apc"


def is_button(control: str) -> bool:
    return xtouch.is_button(control) if xtouch.is_xtouch(control) else apc.is_button(control)


def is_value(control: str) -> bool:
    """Faders and encoders (send a value instead of press/release)."""
    if xtouch.is_xtouch(control):
        return xtouch.is_value(control)
    return control.startswith("fader:")


def is_rgb(control: str) -> bool:
    """Only the APC pads have colours; all other LEDs are off / on / blink."""
    return not xtouch.is_xtouch(control) and apc.is_rgb(control)


def has_led(control: str) -> bool:
    if xtouch.is_xtouch(control):
        return xtouch.has_led(control)
    return apc.is_button(control)


def has_motor(control: str) -> bool:
    """Motor fader or encoder ring that can follow grandMA3."""
    return xtouch.is_xtouch(control) and xtouch.is_value(control)


def label(control: str) -> str:
    return xtouch.control_label(control) if xtouch.is_xtouch(control) else apc.control_label(control)
