"""PACCA Intelligence layer — proactive briefings, pattern detection, notifications."""
from pacca.intelligence.morning_brief import generate_morning_brief
from pacca.intelligence.pattern_detector import get_nudges
from pacca.intelligence.notifications import NotificationManager

__all__ = ["generate_morning_brief", "get_nudges", "NotificationManager"]
