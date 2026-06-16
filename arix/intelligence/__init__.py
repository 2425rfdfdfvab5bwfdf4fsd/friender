"""Arix Intelligence layer — proactive briefings, pattern detection, notifications, advisory, supervisor."""
from arix.intelligence.morning_brief import generate_morning_brief
from arix.intelligence.pattern_detector import get_nudges
from arix.intelligence.notifications import NotificationManager
from arix.intelligence.advisor import AdvisoryIntentDetector, is_chitchat
from arix.intelligence.supervisor import GoalSupervisor, is_multi_step_goal

__all__ = [
    "generate_morning_brief",
    "get_nudges",
    "NotificationManager",
    "AdvisoryIntentDetector",
    "is_chitchat",
    "GoalSupervisor",
    "is_multi_step_goal",
]
