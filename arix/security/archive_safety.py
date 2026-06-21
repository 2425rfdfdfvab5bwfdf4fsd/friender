"""ArchiveSafetyValidator — Zip Slip prevention and archive safety checks."""
from __future__ import annotations
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

EXECUTABLE_EXTENSIONS = {
    ".exe", ".sh", ".bat", ".ps1", ".py", ".rb", ".pl",
    ".dmg", ".pkg", ".deb", ".rpm", ".msi", ".cmd", ".vbs",
}


class ArchiveSafetyError(Exception):
    pass


@dataclass
class ArchiveSafetyReport:
    archive_path: str
    destination: str
    entry_count: int = 0
    total_uncompressed_bytes: int = 0
    max_compression_ratio: float = 0.0
    has_symlink_entries: bool = False
    has_absolute_paths: bool = False
    has_traversal_paths: bool = False
    executable_entries: list[str] = field(default_factory=list)
    overwrite_targets: list[str] = field(default_factory=list)
    blocked: bool = False
    block_reason: str | None = None
    needs_confirmation: bool = False
    confirmation_reason: str | None = None


class ArchiveSafetyValidator:
    MAX_FILES: int = 1000
    MAX_TOTAL_BYTES: int = 500_000_000
    MAX_COMPRESSION_RATIO: float = 100.0

    def validate(self, archive_path: str, destination: str) -> ArchiveSafetyReport:
        report = ArchiveSafetyReport(
            archive_path=archive_path,
            destination=destination,
        )

        dest_real = os.path.realpath(destination)

        if not zipfile.is_zipfile(archive_path):
            report.blocked = True
            report.block_reason = "Not a valid ZIP file"
            return report

        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                entries = zf.infolist()
                report.entry_count = len(entries)

                if len(entries) > self.MAX_FILES:
                    report.blocked = True
                    report.block_reason = (
                        f"Archive contains {len(entries)} entries (max {self.MAX_FILES})"
                    )
                    return report

                for entry in entries:
                    fname = entry.filename

                    if fname.startswith("/") or (len(fname) >= 2 and fname[1] == ":"):
                        report.has_absolute_paths = True
                        report.blocked = True
                        report.block_reason = f"Archive contains absolute path entry: {fname}"
                        return report

                    normalized = os.path.normpath(fname)
                    if ".." in normalized.split(os.sep):
                        report.has_traversal_paths = True
                        report.blocked = True
                        report.block_reason = f"Archive contains path traversal entry: {fname}"
                        return report

                    target = os.path.realpath(os.path.join(destination, fname))
                    # Ensure destination and fname combined don't escape dest_real
                    # The os.sep check is good, but let's be even more explicit with commonpath
                    if os.path.commonpath([dest_real, target]) != dest_real:
                        report.blocked = True
                        report.block_reason = (
                            f"Zip Slip: entry escapes destination: {fname}"
                        )
                        return report

                    is_symlink = (entry.external_attr >> 16) & 0xFFFF == 0xA1ED
                    if is_symlink:
                        report.has_symlink_entries = True
                        report.blocked = True
                        report.block_reason = f"Archive contains symlink entry: {fname}"
                        return report

                    uncompressed = entry.file_size
                    compressed = entry.compress_size
                    report.total_uncompressed_bytes += uncompressed

                    if compressed > 0:
                        ratio = uncompressed / compressed
                        if ratio > report.max_compression_ratio:
                            report.max_compression_ratio = ratio
                        if ratio > self.MAX_COMPRESSION_RATIO:
                            report.blocked = True
                            report.block_reason = (
                                f"Possible zip bomb: {fname} ratio {ratio:.0f}:1"
                            )
                            return report

                    ext = Path(fname).suffix.lower()
                    if ext in EXECUTABLE_EXTENSIONS:
                        report.executable_entries.append(fname)

                    dest_target = os.path.join(destination, fname)
                    if os.path.exists(dest_target):
                        report.overwrite_targets.append(fname)

                if report.total_uncompressed_bytes > self.MAX_TOTAL_BYTES:
                    report.blocked = True
                    report.block_reason = (
                        f"Archive uncompressed size {report.total_uncompressed_bytes:,} bytes "
                        f"exceeds limit {self.MAX_TOTAL_BYTES:,}"
                    )
                    return report

                if report.executable_entries:
                    report.needs_confirmation = True
                    report.confirmation_reason = (
                        f"Archive contains {len(report.executable_entries)} executable/script "
                        f"entries: {', '.join(report.executable_entries[:5])}"
                        + (" and more..." if len(report.executable_entries) > 5 else "")
                    )

                if report.overwrite_targets:
                    report.needs_confirmation = True
                    existing = report.confirmation_reason or ""
                    report.confirmation_reason = (
                        existing + f"\nWould overwrite {len(report.overwrite_targets)} existing files"
                    ).strip()

        except zipfile.BadZipFile as e:
            report.blocked = True
            report.block_reason = f"Invalid ZIP file: {e}"

        return report
