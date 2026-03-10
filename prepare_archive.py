#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import mimetypes
import re
import shutil
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, unquote


STAGE = "PREPARE"
MANIFEST_VERSION = 2
HASH_CHUNK_SIZE = 1024 * 1024
PAGE_OUTPUT_SUFFIX = ".html"
PAGE_SCRIPT_EXTENSIONS = {".asp", ".php", ".aspx", ".jsp", ".cfm", ".cgi", ".pl"}
ASSET_IMAGE_EXTENSIONS = {".gif", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".svg", ".ico"}
ASSET_SCRIPT_EXTENSIONS = {".js"}
ASSET_STYLE_EXTENSIONS = {".css"}
ASSET_OTHER_EXTENSIONS = {".swf", ".xml", ".txt", ".json", ".woff", ".woff2", ".ttf", ".eot"}


@dataclass
class ManifestError:
    code: str
    message: str


@dataclass
class DirectoryEntry:
    source_key: str
    entry_type: str
    relative_path: str
    absolute_path: str
    parent_relative_path: str
    status: str
    warnings: List[str] = field(default_factory=list)
    errors: List[ManifestError] = field(default_factory=list)


@dataclass
class FileEntry:
    source_key: str
    entry_type: str
    original_relative_path: str
    original_absolute_path: str
    original_filename: str
    decoded_filename: str
    normalized_relative_path: Optional[str]
    normalized_absolute_path: Optional[str]
    normalized_filename: Optional[str]
    engine_family: str
    page_type_guess: str
    classification_confidence: str
    file_nature: str
    relevance_preliminary: str
    should_materialize_normalized: bool
    materialization_reason: str
    detected_ids: Dict[str, List[str]]
    normalization: Dict[str, object]
    size_bytes: int
    sha256: Optional[str]
    physical_duplicate_group: Optional[str]
    is_physical_duplicate: bool
    logical_group_key: Optional[str]
    canonical_candidate_preliminary: bool
    status: str
    warnings: List[str] = field(default_factory=list)
    errors: List[ManifestError] = field(default_factory=list)


class AuditLogger:
    def __init__(self, log_file: Path) -> None:
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(f"prepare_archive::{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()
        self.logger.propagate = False

        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)

    def write(self, level: str, message: str, source_key: str = "", relative_path: str = "") -> None:
        ts = datetime.now(timezone.utc).isoformat()
        line = f"{ts} | {STAGE} | {level.upper()} | {message} | {source_key} | {relative_path}"
        self.logger.info(line)

    def info(self, message: str, source_key: str = "", relative_path: str = "") -> None:
        self.write("INFO", message, source_key, relative_path)

    def warning(self, message: str, source_key: str = "", relative_path: str = "") -> None:
        self.write("WARNING", message, source_key, relative_path)

    def error(self, message: str, source_key: str = "", relative_path: str = "") -> None:
        self.write("ERROR", message, source_key, relative_path)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def progress(message: str) -> None:
    print(f"[{STAGE}] {message}")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_rel(path: Path, base: Path) -> str:
    return str(path.relative_to(base)).replace("\\", "/")


def json_dump(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sanitize_token(value: str) -> str:
    text = unquote(value or "")
    text = text.replace("&amp;", "&")
    text = text.strip()
    text = re.sub(r'[<>:"|?*\x00-\x1f]', "_", text)
    text = text.replace("/", "_").replace("\\", "_")
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text)
    text = text.strip("._ ")
    return text or "empty"


def sanitize_path_component(value: str) -> str:
    text = value.strip()
    text = re.sub(r'[<>:"|?*\x00-\x1f]', "_", text)
    text = text.replace("/", "_").replace("\\", "_")
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text)
    text = text.strip("._ ")
    return text or "empty"


def decode_filename(raw_name: str) -> str:
    return unquote(raw_name).replace("&amp;", "&")


def split_decoded_name(decoded_name: str) -> Tuple[str, str]:
    if "?" in decoded_name:
        left, right = decoded_name.split("?", 1)
        return left, right
    return decoded_name, ""


def guess_engine_and_page_type(base_name: str, query_pairs: List[Tuple[str, str]]) -> Tuple[str, str, str]:
    lower = base_name.lower()

    asp_map = {
        "default.asp": "index",
        "forum.asp": "forum",
        "topic.asp": "topic",
        "members.asp": "members",
        "pop_profile.asp": "profile",
        "post.asp": "post",
    }
    phpbb_map = {
        "index.php": "index",
        "viewforum.php": "viewforum",
        "viewtopic.php": "viewtopic",
        "memberlist.php": "memberlist",
        "profile.php": "profile",
        "login.php": "login",
        "search.php": "search",
        "faq.php": "faq",
        "groupcp.php": "groupcp",
        "posting.php": "posting",
    }

    if lower in asp_map:
        return "asp", asp_map[lower], "high"
    if lower in phpbb_map:
        page_type = phpbb_map[lower]
        if lower == "profile.php":
            mode_map = {
                "viewprofile": "profile",
                "editprofile": "profile_edit",
                "register": "register",
                "sendpassword": "password_recovery",
            }
            for key, value in query_pairs:
                if key == "mode" and value.lower() in mode_map:
                    return "phpbb", mode_map[value.lower()], "high"
        return "phpbb", page_type, "high"

    if lower.endswith(".asp"):
        return "asp", "unknown_page", "medium"
    if lower.endswith(".php"):
        return "phpbb", "unknown_page", "medium"
    if Path(lower).suffix.lower() in PAGE_SCRIPT_EXTENSIONS:
        return "unknown", "unknown_page", "medium"

    return "unknown", "unknown", "low"


def classify_file_nature(base_name: str) -> Tuple[str, bool]:
    suffix = Path(base_name).suffix.lower()
    if suffix in PAGE_SCRIPT_EXTENSIONS:
        return "html_page", True
    if suffix in ASSET_IMAGE_EXTENSIONS:
        return "asset_image", False
    if suffix in ASSET_SCRIPT_EXTENSIONS:
        return "asset_script", False
    if suffix in ASSET_STYLE_EXTENSIONS:
        return "asset_stylesheet", False
    if suffix in ASSET_OTHER_EXTENSIONS:
        return "asset_other", False
    mime_guess, _ = mimetypes.guess_type(base_name)
    if mime_guess and mime_guess.startswith("image/"):
        return "asset_image", False
    return "unknown", False


def preliminary_relevance(file_nature: str, page_type_guess: str) -> Tuple[str, bool, str]:
    if file_nature == "html_page":
        high_types = {"topic", "viewtopic", "forum", "viewforum", "profile", "profile_edit", "memberlist", "members", "index"}
        low_types = {"login", "register", "password_recovery", "faq", "groupcp", "search", "posting"}
        if page_type_guess in high_types:
            return "high", True, "relevant_page_type"
        if page_type_guess in low_types:
            return "low", False, "low_value_page_type"
        return "medium", True, "unknown_page_but_html_like"

    if file_nature.startswith("asset_"):
        return "low", False, "asset_not_materialized_by_default"

    return "unknown", False, "unknown_file_nature"


def parse_query_pairs(query: str) -> List[Tuple[str, str]]:
    if not query:
        return []
    normalized_query = query.replace("&amp;", "&").strip("&")
    return [(sanitize_token(k), sanitize_token(v)) for k, v in parse_qsl(normalized_query, keep_blank_values=True)]


def extract_detected_ids(pairs: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    found = {
        "topic_id": [],
        "forum_id": [],
        "post_id": [],
        "user_id": [],
        "cat_id": [],
    }
    mappings = {
        "topic_id": {"TOPIC_ID", "t"},
        "forum_id": {"FORUM_ID", "f"},
        "post_id": {"REPLY_ID", "p", "POST_ID"},
        "user_id": {"id", "u", "USER_ID", "userid"},
        "cat_id": {"CAT_ID", "c"},
    }

    for key, value in pairs:
        if not value.isdigit():
            continue
        for target, aliases in mappings.items():
            if key in aliases:
                found[target].append(value)

    for bucket, values in found.items():
        found[bucket] = sorted(set(values), key=lambda x: int(x)) if values else []
    return found


def build_preserved_name(base_name: str, query_pairs: List[Tuple[str, str]], file_nature: str) -> Tuple[str, Dict[str, object]]:
    normalization = {
        "url_decoded": True,
        "invalid_chars_sanitized": True,
        "extension_forced_html": False,
        "collision_suffix_added": False,
        "query_preserved_order": True,
        "original_extension_preserved": True,
    }

    safe_base = sanitize_path_component(base_name)
    suffix = Path(base_name).suffix
    stem = Path(safe_base).stem
    ext = suffix.lower() if suffix else ""

    query_fragments: List[str] = []
    for key, value in query_pairs:
        if value == "empty":
            query_fragments.append(key)
        else:
            query_fragments.append(f"{key}_{value}")

    if query_fragments:
        preserved_core = f"{safe_base}__{'__'.join(query_fragments)}"
    else:
        preserved_core = safe_base

    preserved_core = re.sub(r"_+", "_", preserved_core).strip("._") or "empty"

    if file_nature == "html_page":
        normalization["extension_forced_html"] = True
        normalization["original_extension_preserved"] = bool(ext)
        return f"{preserved_core}{PAGE_OUTPUT_SUFFIX}", normalization

    if ext:
        return preserved_core, normalization

    normalization["original_extension_preserved"] = False
    return preserved_core, normalization


def build_logical_group_key(engine: str, page_type: str, ids: Dict[str, List[str]]) -> Optional[str]:
    if engine == "asp" and page_type == "topic" and ids["topic_id"]:
        return f"asp:topic:{ids['topic_id'][0]}"
    if engine == "phpbb" and page_type == "viewtopic":
        if ids["topic_id"]:
            return f"phpbb:viewtopic:{ids['topic_id'][0]}"
        if ids["post_id"]:
            return f"phpbb:viewtopic:post:{ids['post_id'][0]}"
    if engine == "asp" and page_type == "forum" and ids["forum_id"]:
        return f"asp:forum:{ids['forum_id'][0]}"
    if engine == "phpbb" and page_type == "viewforum" and ids["forum_id"]:
        return f"phpbb:viewforum:{ids['forum_id'][0]}"
    if page_type in {"profile", "profile_edit"} and ids["user_id"]:
        return f"{engine}:profile:{ids['user_id'][0]}"
    return None


def canonical_rank_key(entry: FileEntry) -> Tuple[int, int, int, str]:
    penalties = 10 if entry.is_physical_duplicate else 0
    confidence_score = {"high": 0, "medium": 1, "low": 2}.get(entry.classification_confidence, 3)
    warning_score = len(entry.warnings)
    norm_name = entry.normalized_filename or ""
    return (penalties, confidence_score, warning_score, norm_name)


class PrepareArchive:
    def __init__(self, archive_root: Path, normalized_root: Path, work_root: Path, logger: AuditLogger, progress_every: int) -> None:
        self.archive_root = archive_root
        self.normalized_root = normalized_root
        self.work_root = work_root
        self.logger = logger
        self.progress_every = progress_every

        self.directories: List[DirectoryEntry] = []
        self.files: List[FileEntry] = []
        self.exceptions: List[dict] = []
        self.summary = {
            "directories_scanned": 0,
            "files_scanned": 0,
            "files_materialized": 0,
            "files_not_materialized": 0,
            "physical_duplicate_groups": 0,
            "physical_duplicate_files": 0,
            "logical_topic_groups_preliminary": 0,
            "unknown_files": 0,
            "warnings": 0,
            "errors": 0,
        }

        self.hash_first_seen: Dict[str, int] = {}
        self.logical_groups: Dict[str, List[int]] = {}
        self.normalized_name_counters: Dict[str, int] = {}
        self.duplicate_group_counts: Dict[str, int] = {}

    def add_exception(self, source_key: str, relative_path: str, reason: str, exc: Exception) -> None:
        item = {
            "timestamp": utc_now(),
            "stage": STAGE,
            "source_key": source_key,
            "relative_path": relative_path,
            "reason": reason,
            "exception": f"{exc.__class__.__name__}: {exc}",
        }
        self.exceptions.append(item)
        self.summary["errors"] += 1
        self.logger.error(f"{reason}: {exc}", source_key, relative_path)

    def scan_source(self, source_key: str) -> None:
        source_root = self.archive_root / source_key
        if not source_root.exists() or not source_root.is_dir():
            raise FileNotFoundError(f"Source root not found: {source_root}")

        all_dirs = sorted([p for p in source_root.rglob("*") if p.is_dir()])
        all_files = sorted([p for p in source_root.rglob("*") if p.is_file()])

        progress(f"source={source_key} directories={len(all_dirs)} files={len(all_files)}")
        self.logger.info(f"start source scan directories={len(all_dirs)} files={len(all_files)}", source_key, "")

        for directory in all_dirs:
            rel = safe_rel(directory, source_root)
            parent_rel = safe_rel(directory.parent, source_root) if directory.parent != source_root else ""
            self.directories.append(
                DirectoryEntry(
                    source_key=source_key,
                    entry_type="directory",
                    relative_path=rel,
                    absolute_path=str(directory.resolve()),
                    parent_relative_path=parent_rel,
                    status="scanned",
                )
            )
            self.summary["directories_scanned"] += 1

        processed = 0
        for file_path in all_files:
            rel = safe_rel(file_path, source_root)
            try:
                self.files.append(self.process_file(source_key, source_root, file_path))
            except Exception as exc:  # noqa: BLE001
                self.add_exception(source_key, rel, "file_processing_failed", exc)
                self.files.append(
                    FileEntry(
                        source_key=source_key,
                        entry_type="file",
                        original_relative_path=rel,
                        original_absolute_path=str(file_path.resolve()),
                        original_filename=file_path.name,
                        decoded_filename=decode_filename(file_path.name),
                        normalized_relative_path=None,
                        normalized_absolute_path=None,
                        normalized_filename=None,
                        engine_family="unknown",
                        page_type_guess="unknown",
                        classification_confidence="low",
                        file_nature="unknown",
                        relevance_preliminary="unknown",
                        should_materialize_normalized=False,
                        materialization_reason="processing_error",
                        detected_ids={"topic_id": [], "forum_id": [], "post_id": [], "user_id": [], "cat_id": []},
                        normalization={},
                        size_bytes=file_path.stat().st_size if file_path.exists() else 0,
                        sha256=None,
                        physical_duplicate_group=None,
                        is_physical_duplicate=False,
                        logical_group_key=None,
                        canonical_candidate_preliminary=False,
                        status="error",
                        warnings=[],
                        errors=[ManifestError(code="file_processing_failed", message=str(exc))],
                    )
                )

            processed += 1
            if processed == 1 or processed % self.progress_every == 0 or processed == len(all_files):
                progress(
                    f"source={source_key} processed {processed} / {len(all_files)} files | "
                    f"materialized={self.summary['files_materialized']} | "
                    f"physical_duplicates={self.summary['physical_duplicate_files']} | "
                    f"logical_groups={len(self.logical_groups)} | warnings={self.summary['warnings']} | errors={self.summary['errors']}"
                )

    def process_file(self, source_key: str, source_root: Path, file_path: Path) -> FileEntry:
        rel = safe_rel(file_path, source_root)
        self.summary["files_scanned"] += 1

        decoded_name = decode_filename(file_path.name)
        base_name, query = split_decoded_name(decoded_name)
        query_pairs = parse_query_pairs(query)
        file_nature, is_page_candidate = classify_file_nature(base_name)
        engine_family, page_type_guess, confidence = guess_engine_and_page_type(base_name, query_pairs)

        if file_nature == "unknown":
            self.summary["unknown_files"] += 1

        relevance_preliminary, should_materialize, materialization_reason = preliminary_relevance(file_nature, page_type_guess)
        detected_ids = extract_detected_ids(query_pairs)
        preserved_name, normalization = build_preserved_name(base_name, query_pairs, file_nature)

        normalized_relative_path = None
        normalized_absolute_path = None
        normalized_filename = None
        sha256 = None
        physical_duplicate_group = None
        is_physical_duplicate = False

        warnings: List[str] = []
        if confidence != "high":
            warnings.append("classification_low_confidence")
        if engine_family == "unknown":
            warnings.append("engine_family_unknown")
        if page_type_guess in {"unknown", "unknown_page"}:
            warnings.append("page_type_unknown")
        if file_nature == "unknown":
            warnings.append("file_nature_unknown")
        if not should_materialize:
            warnings.append("not_materialized_by_default")

        logical_group_key = build_logical_group_key(engine_family, page_type_guess, detected_ids)

        if should_materialize:
            normalized_subdir = self.build_normalized_dir(source_key, engine_family, file_nature, page_type_guess)
            ensure_dir(normalized_subdir)
            normalized_filename, collision_added = self.make_unique_filename(normalized_subdir, preserved_name)
            normalization["collision_suffix_added"] = collision_added
            if collision_added:
                warnings.append("name_collision_detected")

            normalized_path = normalized_subdir / normalized_filename
            shutil.copy2(file_path, normalized_path)
            sha256 = compute_sha256(normalized_path)
            physical_duplicate_group = f"sha256:{sha256}"
            normalized_relative_path = safe_rel(normalized_path, self.normalized_root)
            normalized_absolute_path = str(normalized_path.resolve())

            if physical_duplicate_group in self.duplicate_group_counts:
                self.duplicate_group_counts[physical_duplicate_group] += 1
                is_physical_duplicate = True
                self.summary["physical_duplicate_files"] += 1
            else:
                self.duplicate_group_counts[physical_duplicate_group] = 1

            self.summary["files_materialized"] += 1
        else:
            self.summary["files_not_materialized"] += 1

        if logical_group_key:
            self.logical_groups.setdefault(logical_group_key, []).append(len(self.files))

        self.summary["warnings"] += len(warnings)

        status = "classified"
        if confidence != "high" or file_nature == "unknown" or page_type_guess in {"unknown", "unknown_page"}:
            status = "classified_with_low_confidence"
        if not should_materialize:
            status = "inventoried_only"

        entry = FileEntry(
            source_key=source_key,
            entry_type="file",
            original_relative_path=rel,
            original_absolute_path=str(file_path.resolve()),
            original_filename=file_path.name,
            decoded_filename=decoded_name,
            normalized_relative_path=normalized_relative_path,
            normalized_absolute_path=normalized_absolute_path,
            normalized_filename=normalized_filename,
            engine_family=engine_family,
            page_type_guess=page_type_guess,
            classification_confidence=confidence,
            file_nature=file_nature,
            relevance_preliminary=relevance_preliminary,
            should_materialize_normalized=should_materialize,
            materialization_reason=materialization_reason,
            detected_ids=detected_ids,
            normalization=normalization,
            size_bytes=file_path.stat().st_size,
            sha256=sha256,
            physical_duplicate_group=physical_duplicate_group,
            is_physical_duplicate=is_physical_duplicate,
            logical_group_key=logical_group_key,
            canonical_candidate_preliminary=False,
            status=status,
            warnings=warnings,
            errors=[],
        )

        self.logger.info(
            f"inventoried nature={file_nature} materialized={should_materialize} engine={engine_family} page_type={page_type_guess}",
            source_key,
            rel,
        )
        return entry

    def build_normalized_dir(self, source_key: str, engine_family: str, file_nature: str, page_type_guess: str) -> Path:
        if file_nature == "html_page":
            page_bucket = sanitize_path_component(page_type_guess or "unknown_page")
            return self.normalized_root / source_key / sanitize_path_component(engine_family) / "page" / page_bucket

        asset_bucket_map = {
            "asset_image": "images",
            "asset_script": "scripts",
            "asset_stylesheet": "styles",
            "asset_other": "other",
            "unknown": "unknown",
        }
        bucket = asset_bucket_map.get(file_nature, "unknown")
        return self.normalized_root / source_key / sanitize_path_component(engine_family) / "asset" / bucket

    def make_unique_filename(self, target_dir: Path, preserved_name: str) -> Tuple[str, bool]:
        key = str((target_dir / preserved_name).resolve()).lower()
        if key not in self.normalized_name_counters:
            self.normalized_name_counters[key] = 1
            return preserved_name, False

        self.normalized_name_counters[key] += 1
        counter = self.normalized_name_counters[key]
        stem = Path(preserved_name).stem
        suffix = Path(preserved_name).suffix
        return f"{stem}__collision_{counter}{suffix}", True

    def finalize_canonical_candidates(self) -> None:
        for _, indexes in self.logical_groups.items():
            if not indexes:
                continue
            ranked = sorted(indexes, key=lambda idx: canonical_rank_key(self.files[idx]))
            chosen_idx = ranked[0]
            for idx in indexes:
                self.files[idx].canonical_candidate_preliminary = idx == chosen_idx

        self.summary["physical_duplicate_groups"] = sum(1 for count in self.duplicate_group_counts.values() if count > 1)
        self.summary["logical_topic_groups_preliminary"] = len(
            [k for k in self.logical_groups.keys() if ":topic:" in k or ":viewtopic:" in k]
        )

    def build_manifest(self) -> dict:
        return {
            "manifest_version": MANIFEST_VERSION,
            "generated_at": utc_now(),
            "sources": [
                {"source_key": "sobresites_com", "root_path": str((self.archive_root / "sobresites_com").resolve())},
                {"source_key": "sobresites_com_br", "root_path": str((self.archive_root / "sobresites_com_br").resolve())},
            ],
            "summary": self.summary,
            "directories": [self.directory_to_dict(x) for x in self.directories],
            "files": [self.file_to_dict(x) for x in self.files],
        }

    @staticmethod
    def directory_to_dict(entry: DirectoryEntry) -> dict:
        data = asdict(entry)
        data["errors"] = [asdict(x) for x in entry.errors]
        return data

    @staticmethod
    def file_to_dict(entry: FileEntry) -> dict:
        data = asdict(entry)
        data["errors"] = [asdict(x) for x in entry.errors]
        return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory archive files, materialize relevant pages conservatively, and generate an auditable manifest.")
    parser.add_argument("--archive-root", required=True, type=Path, help="Root folder containing sobresites_com and sobresites_com_br.")
    parser.add_argument("--normalized-root", default=Path("normalized"), type=Path, help="Destination root for normalized files.")
    parser.add_argument("--work-root", default=Path("work"), type=Path, help="Directory for manifest and summaries.")
    parser.add_argument("--logs-root", default=Path("logs"), type=Path, help="Directory for log file.")
    parser.add_argument("--progress-every", default=250, type=int, help="Print progress every N files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    archive_root = args.archive_root.resolve()
    normalized_root = args.normalized_root.resolve()
    work_root = args.work_root.resolve()
    logs_root = args.logs_root.resolve()
    progress_every = max(1, args.progress_every)

    ensure_dir(normalized_root)
    ensure_dir(work_root)
    ensure_dir(logs_root)

    logger = AuditLogger(logs_root / "prepare.log")
    runner = PrepareArchive(archive_root=archive_root, normalized_root=normalized_root, work_root=work_root, logger=logger, progress_every=progress_every)

    try:
        for source_key in ["sobresites_com", "sobresites_com_br"]:
            runner.scan_source(source_key)

        runner.finalize_canonical_candidates()

        manifest = runner.build_manifest()
        json_dump(work_root / "archive_manifest.json", manifest)
        json_dump(work_root / "prepare_summary.json", manifest["summary"])
        json_dump(work_root / "prepare_exceptions.json", runner.exceptions)

        progress(
            "finished "
            f"files={runner.summary['files_scanned']} "
            f"materialized={runner.summary['files_materialized']} "
            f"not_materialized={runner.summary['files_not_materialized']} "
            f"physical_duplicate_groups={runner.summary['physical_duplicate_groups']} "
            f"physical_duplicate_files={runner.summary['physical_duplicate_files']} "
            f"logical_topic_groups={runner.summary['logical_topic_groups_preliminary']} "
            f"warnings={runner.summary['warnings']} "
            f"errors={runner.summary['errors']}"
        )
        logger.info("prepare completed successfully")
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error(f"fatal_error: {exc}")
        progress(f"fatal error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
