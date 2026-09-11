"""
Börü Otonom Öğrenme ve Kendini Geliştirme Paketi (Learning Suite).
Dört temel sütundan oluşur:
1. ImplicitMemoryLearner: Sezgisel & örtük profil öğrenme.
2. SelfReflectionLearner: Hatalardan ders çıkarma & kural oluşturma.
3. CuriosityDaemon: Arka plan otonom merak ve araştırma.
4. DatasetCollector: LoRA ince ayarı için otomatik kaliteli veri toplama.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from boru.learning.implicit_memory import ImplicitMemoryLearner
from boru.learning.self_reflection import SelfReflectionLearner
from boru.learning.curiosity_daemon import CuriosityDaemon
from boru.learning.dataset_collector import DatasetCollector

_GLOBAL_IMPLICIT_LEARNER: Optional[ImplicitMemoryLearner] = None
_GLOBAL_REFLECTION_LEARNER: Optional[SelfReflectionLearner] = None
_GLOBAL_CURIOSITY_DAEMON: Optional[CuriosityDaemon] = None
_GLOBAL_DATASET_COLLECTOR: Optional[DatasetCollector] = None


def get_implicit_learner(storage_path: Optional[Path | str] = None) -> ImplicitMemoryLearner:
    global _GLOBAL_IMPLICIT_LEARNER
    if _GLOBAL_IMPLICIT_LEARNER is None:
        _GLOBAL_IMPLICIT_LEARNER = ImplicitMemoryLearner(storage_path=storage_path)
    return _GLOBAL_IMPLICIT_LEARNER


def get_reflection_learner(storage_path: Optional[Path | str] = None) -> SelfReflectionLearner:
    global _GLOBAL_REFLECTION_LEARNER
    if _GLOBAL_REFLECTION_LEARNER is None:
        _GLOBAL_REFLECTION_LEARNER = SelfReflectionLearner(storage_path=storage_path)
    return _GLOBAL_REFLECTION_LEARNER


def get_curiosity_daemon(storage_path: Optional[Path | str] = None) -> CuriosityDaemon:
    global _GLOBAL_CURIOSITY_DAEMON
    if _GLOBAL_CURIOSITY_DAEMON is None:
        _GLOBAL_CURIOSITY_DAEMON = CuriosityDaemon(
            storage_path=storage_path,
            implicit_memory=get_implicit_learner(),
        )
    return _GLOBAL_CURIOSITY_DAEMON


def get_dataset_collector(storage_path: Optional[Path | str] = None) -> DatasetCollector:
    global _GLOBAL_DATASET_COLLECTOR
    if _GLOBAL_DATASET_COLLECTOR is None:
        _GLOBAL_DATASET_COLLECTOR = DatasetCollector(storage_path=storage_path)
    return _GLOBAL_DATASET_COLLECTOR


__all__ = [
    "ImplicitMemoryLearner",
    "SelfReflectionLearner",
    "CuriosityDaemon",
    "DatasetCollector",
    "get_implicit_learner",
    "get_reflection_learner",
    "get_curiosity_daemon",
    "get_dataset_collector",
]
