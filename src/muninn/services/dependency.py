"""Per-pack dependency environment management."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time

from .operations import (
    CancellationToken,
    OperationCancelled,
    ProgressCallback,
    emit,
)

SUBPROCESS_TIMEOUT = 300


class DependencyEnvironment:
    """Create and remove isolated dependency environments for packs."""

    def __init__(self, venvs_dir: str | None = None) -> None:
        self.venvs_dir = venvs_dir or os.path.expanduser("~/.muninn/venvs")
        os.makedirs(self.venvs_dir, exist_ok=True)

    def get_pack_venv_dir(self, pack_id: str, version: str | None = None) -> str:
        if version is None:
            return os.path.join(self.venvs_dir, pack_id)
        return os.path.join(self.venvs_dir, pack_id, version)

    def get_site_packages(self, pack_id: str, version: str | None = None) -> str:
        return sysconfig.get_path(
            "purelib",
            scheme="venv",
            vars={"base": self.get_pack_venv_dir(pack_id, version)},
        )

    def prepare(
        self,
        pack_dir: str,
        pack_id: str,
        version: str,
        progress: ProgressCallback | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> str | None:
        """Build a new environment in staging and return its path."""

        req_path = os.path.join(pack_dir, "requirements.txt")
        if not os.path.isfile(req_path) or os.path.getsize(req_path) == 0:
            return None

        self._raise_if_cancelled(cancel_token)
        temp_dir = tempfile.mkdtemp(dir=self.venvs_dir, prefix=".temp_")
        try:
            venv_python = self._create_venv(temp_dir, cancel_token)
            pip = os.path.join(os.path.dirname(venv_python), "pip")
            emit(progress, f"Installing dependencies for '{pack_id}'.")
            try:
                self._run_subprocess(
                    [pip, "install", "--quiet", "-r", req_path],
                    timeout=SUBPROCESS_TIMEOUT,
                    cancel_token=cancel_token,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"Timed out installing dependencies for '{pack_id}' "
                    f"after {SUBPROCESS_TIMEOUT} seconds"
                ) from exc
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(
                    f"Failed to install dependencies for '{pack_id}': "
                    f"{exc.stderr.strip()}"
                ) from exc
            return temp_dir
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise

    def remove_pack(self, pack_id: str) -> None:
        venv_dir = self.get_pack_venv_dir(pack_id)
        if os.path.exists(venv_dir):
            shutil.rmtree(venv_dir, ignore_errors=True)

    def _create_venv(
        self,
        venv_dir: str,
        cancel_token: CancellationToken | None,
    ) -> str:
        exe_name = os.path.basename(sys.executable)
        python_exe = os.path.join(
            venv_dir,
            "Scripts" if os.name == "nt" else "bin",
            exe_name,
        )
        self._raise_if_cancelled(cancel_token)
        try:
            self._run_subprocess(
                [sys.executable, "-m", "venv", "--clear", venv_dir],
                timeout=SUBPROCESS_TIMEOUT,
                cancel_token=cancel_token,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Timed out creating dependency environment at '{venv_dir}' "
                f"after {SUBPROCESS_TIMEOUT} seconds"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Failed to create dependency environment at "
                f"'{venv_dir}'. Your Python installation may not include "
                f"'venv'. Original error: {exc.stderr.strip()}"
            ) from exc
        return python_exe

    @staticmethod
    def _raise_if_cancelled(cancel_token: CancellationToken | None) -> None:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()

    def _run_subprocess(
        self,
        args: list[str],
        *,
        timeout: int,
        cancel_token: CancellationToken | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if cancel_token is None:
            return subprocess.run(
                args,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        communication: dict[str, str] = {}

        def collect_output() -> None:
            stdout, stderr = process.communicate()
            communication["stdout"] = stdout
            communication["stderr"] = stderr

        reader = threading.Thread(target=collect_output, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout
        while reader.is_alive():
            if cancel_token.cancelled:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                reader.join(timeout=1)
                raise OperationCancelled("Operation cancelled.")
            if time.monotonic() >= deadline:
                process.kill()
                process.wait()
                reader.join(timeout=1)
                raise subprocess.TimeoutExpired(
                    args,
                    timeout,
                    output=communication.get("stdout", ""),
                    stderr=communication.get("stderr", ""),
                )
            time.sleep(0.05)

        stdout = communication.get("stdout", "")
        stderr = communication.get("stderr", "")
        completed = subprocess.CompletedProcess(
            args,
            process.returncode,
            stdout,
            stderr,
        )
        if process.returncode:
            raise subprocess.CalledProcessError(
                process.returncode,
                args,
                output=stdout,
                stderr=stderr,
            )
        return completed
