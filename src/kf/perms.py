"""Read permissions modelled on typical Google Drive use.

A path is "<drive path>/<rest>" relative to the corpus root. A user can read a path when
  1. they belong to its drive (by role or by name; "*" means everyone), or
  2. a share covers the path or one of its ancestors (a share on a folder covers its descendants).
Everything else is denied, including unknown users, unknown drives and unsafe paths.
"""

import hashlib
import json
from pathlib import Path

import yaml

ANYONE = "*"


def _parts(path):
    """Split a corpus-relative path into components, or None if it is unsafe or empty."""
    if not isinstance(path, str) or "\\" in path or path.startswith("/"):
        return None
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return tuple(parts)


class Policy:
    def __init__(self, users, drives, shares):
        self._roles = {u: set(v.get("roles", [])) for u, v in users.items()}
        self._drives = {}
        self._by_path = {}
        for drive_id, d in drives.items():
            if not d.get("contact_role"):
                raise ValueError(f"drive {drive_id!r} needs a contact_role")
            parts = _parts(d["path"])
            if parts is None or len(parts) != 1:
                raise ValueError(f"drive {drive_id!r} path must be a single folder name")
            self._drives[drive_id] = d
            self._by_path[parts[0]] = drive_id
        self._shares = []
        for s in shares:
            parts = _parts(s["path"])
            if parts is None:
                raise ValueError(f"bad share path {s['path']!r}")
            self._shares.append((parts, set(s.get("users", [])), set(s.get("roles", []))))

    @classmethod
    def load(cls, directory):
        d = Path(directory)
        read = lambda name: yaml.safe_load((d / name).read_text(encoding="utf-8")) or {}
        return cls(read("users.yaml")["users"], read("drives.yaml")["drives"], read("shares.yaml").get("shares", []))

    def users(self):
        return sorted(self._roles)

    def knows(self, user):
        return user in self._roles

    def roles_of(self, user):
        return sorted(self._roles.get(user, ()))

    def drive_ids(self):
        return list(self._drives)

    def drive_path(self, drive_id):
        return self._drives[drive_id]["path"]

    def drive_of(self, path):
        parts = _parts(path)
        return self._by_path.get(parts[0]) if parts else None

    def drive_name(self, drive_id):
        return self._drives[drive_id]["name"]

    def contact_role(self, drive_id):
        return self._drives[drive_id]["contact_role"]

    def _in_drive(self, user, drive_id):
        m = self._drives[drive_id].get("members", {})
        roles = m.get("roles", [])
        return (
            ANYONE in roles
            or user in m.get("users", [])
            or bool(self._roles[user].intersection(roles))
        )

    def access_descriptor(self, path):
        """Who can read this path, independent of any user's roles: the drive's members plus covering shares."""
        parts = _parts(path)
        drive_id = self._by_path.get(parts[0]) if parts else None
        if drive_id is None:
            return None
        m = self._drives[drive_id].get("members", {})
        shares = [
            {"path": "/".join(sp), "roles": sorted(sr), "users": sorted(su)}
            for sp, su, sr in self._shares
            if parts[: len(sp)] == sp
        ]
        return {
            "drive": drive_id,
            "members": {"roles": sorted(m.get("roles", [])), "users": sorted(m.get("users", []))},
            "shares": sorted(shares, key=lambda s: s["path"]),
        }

    def fingerprint(self, path):
        d = self.access_descriptor(path)
        return None if d is None else hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()

    def drives_with_access(self, user):
        if user not in self._roles:
            return set()
        return {d for d in self._drives if self._in_drive(user, d)}

    def can_read(self, user, path):
        parts = _parts(path)
        if parts is None or user not in self._roles:
            return False
        drive_id = self._by_path.get(parts[0])
        if drive_id is None:
            return False
        if self._in_drive(user, drive_id):
            return True
        roles = self._roles[user]
        return any(
            parts[: len(sp)] == sp and (user in su or ANYONE in su or ANYONE in sr or bool(roles & sr))
            for sp, su, sr in self._shares
        )
