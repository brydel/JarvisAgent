"""Audit statique autorisé, sans exécution du code audité ni décision de droits par modèle."""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import resource
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ID = re.compile(r"RT-[a-zA-Z0-9_-]{1,64}\Z")
RULE = '''rules:
  - id: jarvis-python-shell
    languages: [python]
    severity: WARNING
    message: Appel shell=True à examiner ; exploitabilité non confirmée.
    pattern: subprocess.$FUNC(..., shell=True, ...)
    metadata:
      cwe: CWE-78
      owasp: A03:2021
'''


def canonical(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def preserve(directory: Path, content: bytes) -> None:
    """Publication atomique : un arrêt ne laisse jamais de preuve partielle sous son empreinte."""
    target = directory / digest(content)
    if target.exists():
        if digest(target.read_bytes()) != target.name:
            raise ValueError("Preuve locale altérée.")
        return
    fd, name = tempfile.mkstemp(prefix=".partial-", dir=directory)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o400)
        temporary.replace(target)
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class Policy:
    """Configurée sur le noeud par le propriétaire, jamais fournie dans une mission MCP."""
    root: Path
    state: Path
    semgrep: str = "semgrep"
    sandbox_image: str = ""
    timeout_s: int = 15
    max_files: int = 200
    max_bytes: int = 10_000_000

    def validate(self) -> None:
        if not self.root.is_absolute() or not self.root.is_dir() or self.root.resolve() == Path("/"):
            raise ValueError("Répertoire autorisé absolu requis, distinct de /.")
        if not self.state.is_absolute() or self.state.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("État absolu hors du répertoire audité requis.")
        if type(self.timeout_s) is not int or not 1 <= self.timeout_s <= 15:
            raise ValueError("Délai Semgrep : 1 à 15 secondes.")
        if not 1 <= self.max_files <= 200 or not 1 <= self.max_bytes <= 10_000_000:
            raise ValueError("Bornes de collecte invalides.")

    @classmethod
    def environment(cls) -> Policy:
        root = os.environ.get("JARVIS_REDTEAM_ROOT")
        state = os.environ.get("JARVIS_REDTEAM_STATE")
        if not root or not state:
            raise ValueError("RedTeam désactivé : JARVIS_REDTEAM_ROOT et JARVIS_REDTEAM_STATE requis.")
        return cls(Path(root), Path(state), os.environ.get("JARVIS_REDTEAM_SEMGREP", "semgrep"),
                   os.environ.get("JARVIS_REDTEAM_IMAGE", ""))


def request(data: object) -> dict:
    if not isinstance(data, dict) or set(data) != {"mission_id", "deadline"}:
        raise ValueError("Mission : seuls mission_id et deadline sont acceptés.")
    if not isinstance(data["mission_id"], str) or not ID.fullmatch(data["mission_id"]):
        raise ValueError("Identifiant RT- invalide.")
    deadline = data["deadline"]
    if type(deadline) not in (int, float) or not math.isfinite(deadline) or not time.time() < deadline <= time.time() + 86400:
        raise ValueError("Échéance finie dans les prochaines 24 heures requise.")
    return dict(data)


def snapshot(policy: Policy, dest: Path) -> list[dict]:
    """Copie uniquement des fichiers Python ordinaires ; aucun lien, config ou code exécuté.

    Le propriétaire ne doit pas modifier l'arbre pendant sa collecte. O_NOFOLLOW protège
    le fichier final ; les répertoires sont vérifiés avant et après chaque lecture.
    """
    manifest: list[dict] = []
    total = 0
    visited = 0
    until = time.monotonic() + 3
    root = policy.root.resolve()
    def fail_walk(error: OSError) -> None:
        raise error

    for folder, dirs, files in os.walk(root, followlinks=False, onerror=fail_walk):
        visited += 1 + len(files)
        if visited > 5000 or time.monotonic() > until:
            raise ValueError("Collecte trop longue ou arborescence trop grande.")
        dirs[:] = sorted(d for d in dirs if d not in {".git", "node_modules", ".venv", "venv", "__pycache__"}
                         and not (Path(folder) / d).is_symlink())
        for name in sorted(files):
            if time.monotonic() > until:
                raise ValueError("Budget de collecte dépassé.")
            source = Path(folder) / name
            if source.suffix != ".py" or source.is_symlink():
                continue
            if len(manifest) >= policy.max_files:
                raise ValueError("Trop de fichiers : audit incomplet refusé.")
            # openat et O_NOFOLLOW sur chaque composant : pas de traversée par course de symlink.
            relative = source.relative_to(root)
            directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                for part in relative.parts[:-1]:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    os.close(directory)
                    directory = child
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                with os.fdopen(fd, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise ValueError("Seuls les fichiers ordinaires sont acceptés.")
                    content = stream.read(1_000_001)
            finally:
                os.close(directory)
            total += len(content)
            if len(content) > 1_000_000 or total > policy.max_bytes:
                raise ValueError("Taille maximale de collecte dépassée.")
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(0o444)
            for directory in (target.parent, *target.parent.parents):
                if not directory.is_relative_to(dest):
                    break
                directory.chmod(0o755)
            manifest.append({"path": str(relative), "sha256": digest(content), "bytes": len(content)})
    if not manifest:
        raise ValueError("Aucun fichier Python collecté ; aucune couverture mesurable.")
    return manifest


def scan(policy: Policy, tree: Path) -> dict:
    executable = shutil.which("docker" if policy.sandbox_image else policy.semgrep)
    if not executable:
        raise RuntimeError("Semgrep absent ; aucun audit exécuté.")
    rules = tree.parent / "trusted-rule.yml"
    rules.write_text(RULE)
    rules.chmod(0o444)
    command = [executable, "scan", "--json", "--metrics=off", "--disable-version-check", "--jobs=1",
               "--timeout=3", "--max-memory=512", "--no-git-ignore", "--config", str(rules), str(tree)]
    source_prefix = tree.resolve()
    sandbox = {"mode": "host_process", "network_isolated": False}
    container = "jarvis-rt-" + os.urandom(8).hex()
    if policy.sandbox_image:
        image = subprocess.run([executable, "image", "inspect", policy.sandbox_image, "--format", "{{.Id}}"],
                               capture_output=True, text=True, timeout=5, check=True).stdout.strip()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise ValueError("Empreinte de l'image Docker invalide.")
        command = [executable, "run", "--rm", "--pull=never", "--name", container, "--network=none", "--read-only",
            "--log-driver=none", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=128", "--memory=768m", "--cpus=1",
            "--user=65534:65534", "--tmpfs=/tmp:rw,noexec,nosuid,size=64m,mode=1777",
            "--mount", f"type=bind,src={tree},dst=/source,readonly",
            "--mount", f"type=bind,src={rules},dst=/rules.yml,readonly",
            image, "scan", "--json", "--metrics=off", "--disable-version-check", "--jobs=1", "--timeout=3",
            "--max-memory=512", "--no-git-ignore", "--config=/rules.yml", "/source"]
        source_prefix = Path("/source")
        sandbox = {"mode": "docker", "network_isolated": True, "image_id": image,
                   "memory_mb": 768, "cpus": 1, "pids": 128}
    # Aucune configuration, clé ou variable d'agent héritée dans l'outil.
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tree.parent),
           "SEMGREP_SEND_METRICS": "off", "SEMGREP_ENABLE_VERSION_CHECK": "0"}
    start = time.monotonic()
    def process_limits() -> None:
        resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
        resource.setrlimit(resource.RLIMIT_CPU, (policy.timeout_s + 2, policy.timeout_s + 2))

    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
        # Le client Docker garde sa configuration de registre ; le conteneur ne la reçoit pas.
        process = subprocess.Popen(command, stdout=output, stderr=error,
                                   env=None if policy.sandbox_image else env, start_new_session=True,
                                   preexec_fn=process_limits)
        try:
            process.wait(timeout=policy.timeout_s)
        except BaseException as exc:
            import signal
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            if isinstance(exc, subprocess.TimeoutExpired):
                raise RuntimeError("Délai Semgrep dépassé ; aucun résultat validé.") from None
            raise
        finally:
            if policy.sandbox_image:
                cleanup = subprocess.run([executable, "rm", "-f", container], capture_output=True, timeout=5)
                # --rm a normalement déjà supprimé le conteneur. Une erreur de daemon n'est pas masquée.
                if cleanup.returncode and b"No such container" not in cleanup.stderr:
                    raise RuntimeError("Nettoyage Docker incertain ; intervention propriétaire requise.")
        output.seek(0)
        raw = output.read(2_000_001)
    if process.returncode != 0 or len(raw) > 2_000_000:
        raise RuntimeError("Semgrep en échec ou sortie trop volumineuse ; résultat non validé.")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("errors") or not isinstance(data.get("results"), list):
        raise RuntimeError("Semgrep a renvoyé des erreurs ; audit incomplet.")
    if len(data["results"]) > 100:
        raise RuntimeError("Trop de résultats : rapport tronqué refusé.")
    findings = []
    for result in data["results"]:
        relative = Path(result["path"]).relative_to(source_prefix)
        findings.append({"rule": "jarvis-python-shell", "path": str(relative), "line": result["start"]["line"],
                         "status": "tool_result", "impact": "non confirme", "reproduced": False,
                         "recommendation": "Passer une liste d'arguments avec shell=False ; vérifier les entrées."})
    return {"tool": "semgrep", "version": data.get("version"), "duration_s": time.monotonic() - start,
            "rule_sha256": digest(RULE.encode()), "findings": findings,
            "sandbox": sandbox, "coverage": "Python : subprocess avec shell=True uniquement", "network_targets": []}


class Engine:
    """Étapes persistées sous verrou ; reprise d'une étape incomplète, sans refaire un scan acquis."""
    def __init__(self, policy: Policy):
        policy.validate()
        self.policy = policy
        policy.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(policy.state, 0o700)

    def run(self, data: dict, *, interrupt_after: str = "", observer: Callable[[str], None] | None = None) -> dict:
        data = request(data)
        ident = data["mission_id"]
        # Le verrou est local au noeud ; SSH/MCP ne transporte jamais ce chemin.
        with (self.policy.state / "engine.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with sqlite3.connect(self.policy.state / "missions.sqlite3") as db:
                db.execute("CREATE TABLE IF NOT EXISTS missions (id TEXT PRIMARY KEY, fingerprint TEXT, result TEXT)")
                fingerprint = digest(canonical({"request": data, "root": str(self.policy.root.resolve()),
                                                "rules": RULE, "sandbox_image": self.policy.sandbox_image,
                                                "executable": self.policy.semgrep, "version": 1}))
                row = db.execute("SELECT fingerprint,result FROM missions WHERE id=?", (ident,)).fetchone()
                if row and row[0] != fingerprint:
                    raise ValueError("Identifiant déjà lié à une autre mission ou politique.")
                record = json.loads(row[1]) if row else {"mission_id": ident, "steps": [], "status": "running"}
                if record["status"] == "reported":
                    return record

                def save(stage: str) -> None:
                    record["steps"].append(stage)
                    db.execute("INSERT OR REPLACE INTO missions VALUES (?,?,?)", (ident, fingerprint, canonical(record).decode()))
                    db.commit()
                    if observer:
                        observer(stage)
                    if interrupt_after == stage:
                        raise InterruptedError("Interruption contrôlée après " + stage)

                if "PLAN" not in record["steps"]:
                    record["authorization_scope"] = {"root": str(self.policy.root.resolve()), "tools": ["semgrep"],
                                                       "network_targets": [], "production": False, "merge": False}
                    save("PLAN")
                if "EXECUTE" not in record["steps"]:
                    with tempfile.TemporaryDirectory(prefix="jarvis-redteam-") as tmp:
                        tree = Path(tmp) / "source"
                        tree.mkdir()
                        tree.chmod(0o755)
                        manifest = snapshot(self.policy, tree)
                        if time.time() >= data["deadline"] - self.policy.timeout_s:
                            raise ValueError("Budget de temps insuffisant pour lancer l'outil.")
                        evidence = self.policy.state / "evidence"
                        evidence.mkdir(exist_ok=True, mode=0o700)
                        if sum(f.stat().st_size for f in evidence.iterdir()) > 200_000_000:
                            raise ValueError("Quota des preuves atteint ; archivage propriétaire requis.")
                        for item in manifest:
                            content = (tree / item["path"]).read_bytes()
                            preserve(evidence, content)
                        preserve(evidence, RULE.encode())
                        record["source_evidence"] = "evidence/<sha256 du manifeste>"
                        record["manifest"] = manifest
                        record["audit"] = scan(self.policy, tree)
                    save("EXECUTE")
                if "OBSERVE" not in record["steps"]:
                    record["evidence_sha256"] = digest(canonical({"manifest": record["manifest"], "audit": record["audit"]}))
                    save("OBSERVE")
                if "VERIFY" not in record["steps"]:
                    record["verification"] = {"tool_completed": True, "lab_reproduced": False, "impact_confirmed": False}
                    save("VERIFY")
                if "REFLECT" not in record["steps"]:
                    record["limits"] = ["Exploitabilité non démontrée", "Une règle SAST Python", "Aucune inférence requise"]
                    save("REFLECT")
                if "DELEGATE" not in record["steps"]:
                    record["delegation"] = {"mission_id": ident, "parent_task_id": ident + ":scan",
                        "requested_capability": "security.independent_review", "target_agent": "chef",
                        "evidence_references": ["sha256:" + record["evidence_sha256"]],
                        "expected_output_schema": {"verdict": "confirmed|false_positive|insufficient_evidence", "evidence": "array"},
                        "deadline": data["deadline"], "budget": {"tokens": 2048, "compute_seconds": 60, "max_hops": 1},
                        "authorization_scope": {"tools": [], "network_targets": [], "merge": False},
                        "reason": "validation_independante_requise", "status": "pending"}
                    save("DELEGATE")
                record["status"] = "reported"
                if "REPORT" not in record["steps"]:
                    save("REPORT")
                return record
