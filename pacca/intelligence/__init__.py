"""PACCA Intelligence layer — proactive briefings, pattern detection, notifications, advisory, supervisor."""
from pacca.intelligence.morning_brief import generate_morning_brief
from pacca.intelligence.pattern_detector import get_nudges
from pacca.intelligence.notifications import NotificationManager
from pacca.intelligence.advisor import AdvisoryIntentDetector, is_chitchat
from pacca.intelligence.supervisor import GoalSupervisor, is_multi_step_goal

__all__ = [
    "generate_morning_brief",
    "get_nudges",
    "NotificationManager",
    "AdvisoryIntentDetector",
    "is_chitchat",
    "GoalSupervisor",
    "is_multi_step_goal",
]
