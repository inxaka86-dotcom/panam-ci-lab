#!/usr/bin/env python3
"""Build four wholly synthetic offline reverse-engineering targets.

No downloaded code, external modules, secrets, model calls or target execution.
Outputs go to a fresh user-selected directory; builds use a private source tempdir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

CASES = ("LR-E01", "LR-N01", "LR-G01", "LR-D01")
TASKS = {
    "LR-E01": "Analyze only targets/electron-app. Identify the renderer->main start IPC channel and main->renderer change IPC channel. Cite concrete file paths.",
    "LR-N01": "Analyze targets/libcapture_probe.so as ELF without executing it. Name the exported permission-check function, and the effective UID value for which it returns true. Cite symbol/disassembly evidence.",
    "LR-G01": "Analyze targets/go_probe as a compiled Go executable without running it. Report main module path and build toolchain version from binary metadata. Cite the command evidence.",
    "LR-D01": "Analyze only targets/libwire_probe.so statically. Identify the socket path string, the exact accepted handshake message, and the function used for peer identity checking. Cite symbol/string/call evidence.",
}

NATIVE_C = r'''
#include <unistd.h>
__attribute__((visibility("default"),noinline))
int capture_access_check(void) { return geteuid() == 1234; }
__attribute__((visibility("default"),noinline))
int capture_result(void) { return capture_access_check(); }
'''
WIRE_C = r'''
#include <string.h>
#include <sys/types.h>
__attribute__((visibility("default"),noinline))
const char *wire_socket_path(void) { return "/tmp/leanrea-synthetic-v2.sock"; }
__attribute__((visibility("default"),noinline))
int wire_peer_matches(uid_t uid) { return uid == 2468; }
__attribute__((visibility("default"),noinline))
int wire_handshake(const char *message, uid_t peer_uid) {
    if (!wire_peer_matches(peer_uid)) return 0;
    return strcmp(message, "HELLO:2") == 0;
}
'''
GO_MOD = "module example.invalid/leanrea-fixture/tool\n\ngo 1.20\n"
GO_SRC = 'package main\nimport "fmt"\nfunc main() { fmt.Println("synthetic only") }\n'
MAIN_JS = """const { ipcMain } = require('electron');
ipcMain.handle('records:begin-v2', async () => ({ started: true }));
function broadcast(win) { win.webContents.send('records:changed-v2', { count: 1 }); }
module.exports = { broadcast };
"""
PRELOAD_JS = """const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('recordBridge', {
  begin: () => ipcRenderer.invoke('records:begin-v2'),
  onChange: (fn) => ipcRenderer.on('records:changed-v2', fn)
});
"""
PACKAGE = '{"name":"synthetic-offline-electron","version":"0.0.0","main":".webpack/main.js"}\n'


def run(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, check=True, capture_output=True,
                            text=True, timeout=90)
    return result.stdout


def checked_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError("Required local compiler or inspection utility missing: " + name)
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root: Path) -> dict:
    root = root.resolve()
    # Never delete/overwrite an existing directory; avoid following output symlinks.
    if root.exists() or root.is_symlink():
        raise ValueError("Output exists; provide a fresh private directory")
    cc = checked_tool("cc")
    go = checked_tool("go")
    for utility in ("nm", "objdump", "strings", "readelf", "rg"):
        checked_tool(utility)
    root.mkdir(parents=True, mode=0o700)
    targets = root / "targets"
    targets.mkdir(mode=0o700)
    electron = targets / "electron-app"
    (electron / ".webpack").mkdir(parents=True)
    (electron / ".vite").mkdir(parents=True)
    (electron / "package.json").write_text(PACKAGE)
    (electron / ".webpack" / "main.js").write_text(MAIN_JS)
    (electron / ".vite" / "preload.js").write_text(PRELOAD_JS)
    with tempfile.TemporaryDirectory(prefix="leanrea-source-") as td:
        source = Path(td)
        (source / "native.c").write_text(NATIVE_C)
        (source / "wire.c").write_text(WIRE_C)
        for file_name, output_name in (("native.c", "libcapture_probe.so"),
                                       ("wire.c", "libwire_probe.so")):
            run([cc, "-std=c11", "-O0", "-g", "-fno-inline", "-fPIC", "-shared",
                 "-o", str(targets / output_name), str(source / file_name)])
        # Only local Go standard library. Never download a module or toolchain.
        go_src = source / "go"
        go_src.mkdir()
        (go_src / "go.mod").write_text(GO_MOD)
        (go_src / "main.go").write_text(GO_SRC)
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": td,
            "GOCACHE": str(source / "go-cache"),
            "GOPROXY": "off",
            "GOSUMDB": "off",
            "GOTOOLCHAIN": "local",
            "GOWORK": "off",
            "GO111MODULE": "on",
            "GOTELEMETRY": "off",
            "LANG": "C",
        }
        run([go, "build", "-trimpath", "-o", str(targets / "go_probe"), "."],
            cwd=go_src, env=env)
    tasks = {"schema": "panam.leanrea.synthetic-target-pack.v1",
             "data_class": "public-synthetic", "cases": [
                 {"case_id": cid, "task": TASKS[cid]} for cid in CASES]}
    (root / "tasks.json").write_text(json.dumps(tasks, indent=2, ensure_ascii=False) + "\n")
    manifest = {}
    for p in sorted(targets.rglob("*")):
        if p.is_file():
            manifest[str(p.relative_to(root))] = sha256(p)
    manifest["tasks.json"] = sha256(root / "tasks.json")
    return {"schema": "panam.leanrea.target-manifest.v1",
            "status": "SYNTHETIC_NOT_A_MODEL_BENCHMARK",
            "artifacts": manifest,
            "case_ids": list(CASES)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = build(args.out)
    print(json.dumps(report, sort_keys=True))
    print("PANAM_LEANREA_TARGET_BUILD=PASS")


if __name__ == "__main__":
    main()
