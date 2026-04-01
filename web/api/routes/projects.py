"""Project listing, creation, and management endpoints."""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.clip_state import scan_project_clips
from backend.project import (
    _dedupe_path,
    is_v2_project,
    projects_root,
    read_project_json,
    set_display_name,
    write_project_json,
)

from ..org_isolation import resolve_clips_dir
from ..tier_guard import require_member
from .clips import _clip_to_schema

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(require_member)])


class FolderSchema(BaseModel):
    name: str
    display_name: str
    clips: list[dict] = []


class ProjectSchema(BaseModel):
    name: str
    display_name: str
    path: str
    clip_count: int
    created: str | None = None
    clips: list[dict] = []  # loose clips (no folder)
    folders: list[FolderSchema] = []


class CreateProjectRequest(BaseModel):
    name: str


class RenameProjectRequest(BaseModel):
    display_name: str


def _scan_projects(root: str | None = None) -> list[ProjectSchema]:
    """Scan the projects directory and return project info."""
    root = root or projects_root()
    if not os.path.isdir(root):
        return []

    projects = []
    for item in sorted(os.listdir(root)):
        item_path = os.path.join(root, item)
        if not os.path.isdir(item_path) or item.startswith(".") or item.startswith("_"):
            continue

        # Only include v2 projects (have clips/ subdir)
        if not is_v2_project(item_path):
            continue

        data = read_project_json(item_path) or {}
        display = data.get("display_name", item)
        created = data.get("created")

        # Scan clips inside the project
        try:
            clips = scan_project_clips(item_path)
        except Exception:
            clips = []

        # Group clips: loose (no folder) vs foldered
        loose = [c for c in clips if not c.folder_name]
        folder_map: dict[str, list] = {}
        for c in clips:
            if c.folder_name:
                folder_map.setdefault(c.folder_name, []).append(c)

        folders = [
            FolderSchema(
                name=fn,
                display_name=fn.replace("_", " "),
                clips=[_clip_to_schema(c).__dict__ for c in fc],
            )
            for fn, fc in sorted(folder_map.items())
        ]

        projects.append(
            ProjectSchema(
                name=item,
                display_name=display,
                path=item_path,
                clip_count=len(clips),
                created=created,
                clips=[_clip_to_schema(c).__dict__ for c in loose],
                folders=folders,
            )
        )

    return projects


@router.get("", response_model=list[ProjectSchema])
def list_projects(request: Request):
    return _scan_projects(resolve_clips_dir(request))


@router.post("", response_model=ProjectSchema)
def create_project_endpoint(req: CreateProjectRequest, request: Request):
    """Create a new empty project."""
    root = resolve_clips_dir(request)
    timestamp = datetime.now().strftime("%y%m%d_%H%M%S")

    import re

    name_stem = re.sub(r"[^\w\-]", "_", req.name.strip())
    name_stem = re.sub(r"_+", "_", name_stem).strip("_")[:60]
    folder_name = f"{timestamp}_{name_stem}"

    project_dir, _ = _dedupe_path(root, folder_name)
    clips_dir = os.path.join(project_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    write_project_json(
        project_dir,
        {
            "version": 2,
            "created": datetime.now().isoformat(),
            "display_name": req.name.strip(),
            "clips": [],
        },
    )

    return ProjectSchema(
        name=os.path.basename(project_dir),
        display_name=req.name.strip(),
        path=project_dir,
        clip_count=0,
        created=datetime.now().isoformat(),
    )


@router.patch("/{name}")
def rename_project(name: str, req: RenameProjectRequest, request: Request):
    """Rename a project's display name."""
    root = resolve_clips_dir(request)
    project_dir = os.path.join(root, name)
    if not os.path.isdir(project_dir):
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    set_display_name(project_dir, req.display_name.strip())
    return {"status": "ok", "display_name": req.display_name.strip()}


@router.delete("/{name}")
def delete_project(name: str, request: Request):
    """Delete a project and all its clips."""
    root = resolve_clips_dir(request)
    project_dir = os.path.join(root, name)

    if not os.path.isdir(project_dir):
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    # Safety check
    abs_root = os.path.abspath(root)
    abs_proj = os.path.abspath(project_dir)
    if not abs_proj.startswith(abs_root + os.sep):
        raise HTTPException(status_code=403, detail="Project path outside projects directory")

    try:
        shutil.rmtree(project_dir)
        logger.info(f"Deleted project: {project_dir}")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete") from e

    return {"status": "deleted", "name": name}


# --- Folders ---


class CreateFolderRequest(BaseModel):
    name: str


@router.post("/{project_name}/folders")
def create_folder_endpoint(project_name: str, req: CreateFolderRequest, request: Request):
    """Create a folder inside a project."""
    from backend.project import create_folder

    root = resolve_clips_dir(request)
    project_dir = os.path.join(root, project_name)
    if not os.path.isdir(project_dir):
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
    folder_path = create_folder(project_dir, req.name.strip())
    folder_name = os.path.basename(folder_path)
    return {"name": folder_name, "display_name": folder_name.replace("_", " "), "clips": []}


@router.delete("/{project_name}/folders/{folder_name}")
def delete_folder(project_name: str, folder_name: str, request: Request):
    """Delete a folder. Clips inside are moved to loose clips/."""
    from backend.project import move_clip_to_folder

    root = resolve_clips_dir(request)
    project_dir = os.path.join(root, project_name)
    folder_path = os.path.join(project_dir, "folders", folder_name)
    if not os.path.isdir(folder_path):
        raise HTTPException(status_code=404, detail=f"Folder '{folder_name}' not found")
    # Move all clips inside to loose clips/ first
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if os.path.isdir(item_path) and not item.startswith("."):
            move_clip_to_folder(project_dir, item, None)
    # Remove the now-empty folder
    if os.path.isdir(folder_path):
        shutil.rmtree(folder_path)
    return {"status": "deleted"}
