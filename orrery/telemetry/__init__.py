"""Opt-in telemetry: off by default, anonymous, aggregate, sent only to an endpoint you set.

The default install never phones home: consent is off until the user runs `telemetry on`,
and even then nothing is sent unless an endpoint is configured. All data is assembled in one
place (payload.py) so the set of things that can ever leave is small, fixed, and testable.
This package reads and writes only the durable home from orrery.home.
"""
