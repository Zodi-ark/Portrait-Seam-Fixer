"""
fix_portrait_seam.py  —  Ivalice Chronicles Portrait Seam Fixer
================================================================
FIRST TIME SETUP
  1. Install Python from https://python.org  (check "Add to PATH")
  2. Double-click this file — it installs its own dependencies
     automatically on the first run.

EVERY TIME AFTER THAT
  Just double-click this file and use the window that opens.
"""

# ── auto-install dependencies ────────────────────────────────────────────────
import sys, subprocess, importlib

REQUIRED = {
    "numpy":        "numpy",
    "PIL":          "pillow",
    "imageio":      "imageio",
    "scipy":        "scipy",
}

def _install(pkg):
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

missing = []
for module, pkg in REQUIRED.items():
    try:
        importlib.import_module(module)
    except ImportError:
        missing.append(pkg)

if missing:
    import tkinter as tk
    from tkinter import messagebox
    _root = tk.Tk(); _root.withdraw()
    messagebox.showinfo(
        "First-time setup",
        f"Installing required libraries:\n\n  {', '.join(missing)}\n\n"
        "This only happens once. Click OK to continue."
    )
    _root.destroy()
    for pkg in missing:
        _install(pkg)

# ── core imports ─────────────────────────────────────────────────────────────
import pathlib, threading, traceback
import tkinter as tk
from tkinter import filedialog, scrolledtext

import numpy as np
import imageio.v2 as imageio
from PIL import Image
from scipy import ndimage


# ── fix logic (identical to before) ─────────────────────────────────────────
def _fix_array(arr: np.ndarray):
    """Return (fixed_array, n_promoted).  Input must be RGBA uint8."""
    h, w = arr.shape[:2]
    result = arr.copy()
    alpha  = arr[:, :, 3].astype(np.int32)

    has_color = alpha > 0
    if not has_color.any():
        return result, 0

    # Stage 1 — colour dilation
    _, nearest = ndimage.distance_transform_edt(~has_color, return_indices=True)
    for ch in range(3):
        result[:, :, ch] = arr[:, :, ch][nearest[0], nearest[1]]

    # Stage 2 — BC7 block alpha promotion
    opaque   = alpha > 128
    bh, bw   = (h + 3) // 4, (w + 3) // 4
    promoted = 0
    for by in range(bh):
        for bx in range(bw):
            r0, r1 = by * 4, min(by * 4 + 4, h)
            c0, c1 = bx * 4, min(bx * 4 + 4, w)
            if opaque[r0:r1, c0:c1].any():
                blk  = result[r0:r1, c0:c1, 3]
                mask = blk == 0
                if mask.any():
                    result[r0:r1, c0:c1, 3][mask] = 4
                    promoted += int(mask.sum())

    return result.astype(np.uint8), promoted


def _load(path: pathlib.Path) -> np.ndarray:
    if path.suffix.lower() == ".dds":
        arr = imageio.imread(str(path))
    else:
        arr = np.array(Image.open(str(path)).convert("RGBA"))
    if arr.shape[2] == 3:
        alpha = np.full((*arr.shape[:2], 1), 255, dtype=np.uint8)
        arr   = np.concatenate([arr, alpha], axis=2)
    return arr.astype(np.uint8)


def process_file(path: pathlib.Path, log):
    log(f"  {'─'*48}")
    log(f"  File   : {path.name}")

    if not path.exists():
        log(f"  ERROR  : file not found.\n"); return False
    if path.suffix.lower() not in (".dds", ".png"):
        log(f"  SKIP   : not a .dds or .png file.\n"); return False

    try:
        arr = _load(path)
    except Exception as e:
        log(f"  ERROR  : could not read — {e}\n"); return False

    h, w = arr.shape[:2]
    log(f"  Size   : {w} × {h} px")

    alpha    = arr[:, :, 3]
    opaque   = alpha > 128
    bk_trans = (alpha == 0) & (arr[:, :, :3].sum(axis=2) == 0)
    bh, bw_  = (h + 3) // 4, (w + 3) // 4
    n_problem = sum(
        int(bk_trans[by*4:min(by*4+4,h), bx*4:min(bx*4+4,w)].sum())
        for by in range(bh) for bx in range(bw_)
        if opaque[by*4:min(by*4+4,h), bx*4:min(bx*4+4,w)].any()
           and bk_trans[by*4:min(by*4+4,h), bx*4:min(bx*4+4,w)].any()
    )

    if n_problem == 0:
        log(f"  CHECK  : No seam problem detected — saving anyway as precaution.")
    else:
        log(f"  FOUND  : {n_problem} problem pixels → black seam line in game")

    log(f"  FIX    : Applying fix…")
    try:
        fixed, promoted = _fix_array(arr)
    except Exception as e:
        log(f"  ERROR  : Fix failed — {e}\n"); traceback.print_exc(); return False

    unchanged = np.array_equal(arr[arr[:,:,3]>128], fixed[arr[:,:,3]>128])
    log(f"  FIX    : {promoted} pixels promoted, visible pixels unchanged: {'YES ✓' if unchanged else 'WARNING!'}")

    out = path.parent / (path.stem + "_fixed.png")
    try:
        Image.fromarray(fixed, "RGBA").save(str(out))
    except Exception as e:
        log(f"  ERROR  : Could not save — {e}\n"); return False

    log(f"  SAVED  : {out.name}")
    log(f"  NEXT   : Encode  {out.name}  →  .tex  with your tool.\n")
    return True


# ── GUI ──────────────────────────────────────────────────────────────────────
class App(tk.Tk):
    BG      = "#1e1f26"
    PANEL   = "#2a2b35"
    ACCENT  = "#5b8cff"
    SUCCESS = "#4caf7d"
    ERROR   = "#e05c5c"
    TEXT    = "#d4d6e0"
    SUBTEXT = "#7a7d8e"
    FONT    = ("Segoe UI", 10)
    MONO    = ("Consolas", 9)

    def __init__(self):
        super().__init__()
        self.title("Portrait Seam Fixer — The Ivalice Chronicles")
        self.configure(bg=self.BG)
        self.resizable(True, True)
        self.minsize(560, 420)
        self._build()
        self.geometry("660x520")

        # If files were dropped onto the script, process them immediately
        if len(sys.argv) > 1:
            paths = [pathlib.Path(p) for p in sys.argv[1:]]
            self.after(200, lambda: self._run(paths))

    def _build(self):
        # ── header ──────────────────────────────────────────────
        hdr = tk.Frame(self, bg=self.BG)
        hdr.pack(fill="x", padx=20, pady=(18, 0))

        tk.Label(hdr, text="Portrait Seam Fixer",
                 font=("Segoe UI", 16, "bold"),
                 bg=self.BG, fg=self.TEXT).pack(anchor="w")
        tk.Label(hdr, text="The Ivalice Chronicles mod tool",
                 font=self.FONT, bg=self.BG, fg=self.SUBTEXT).pack(anchor="w")

        tk.Frame(self, bg=self.PANEL, height=1).pack(fill="x", padx=20, pady=12)

        # ── drop zone / browse button ────────────────────────────
        zone_frame = tk.Frame(self, bg=self.PANEL, bd=0)
        zone_frame.pack(fill="x", padx=20)

        inner = tk.Frame(zone_frame, bg=self.PANEL)
        inner.pack(pady=18)

        tk.Label(inner,
                 text="Select one or more portrait files to fix",
                 font=("Segoe UI", 11), bg=self.PANEL, fg=self.TEXT
                 ).pack()
        tk.Label(inner,
                 text="Accepts  .dds  and  .png  portrait textures",
                 font=("Segoe UI", 9), bg=self.PANEL, fg=self.SUBTEXT
                 ).pack(pady=(2, 12))

        btn_frame = tk.Frame(inner, bg=self.PANEL)
        btn_frame.pack()

        self.browse_btn = tk.Button(
            btn_frame,
            text="  Browse Files…  ",
            font=("Segoe UI", 11, "bold"),
            bg=self.ACCENT, fg="white",
            activebackground="#4070e0", activeforeground="white",
            relief="flat", bd=0, padx=16, pady=8,
            cursor="hand2",
            command=self._browse
        )
        self.browse_btn.pack(side="left", padx=(0, 8))

        self.fix_all_btn = tk.Button(
            btn_frame,
            text="  Fix All in Folder…  ",
            font=("Segoe UI", 11),
            bg=self.PANEL, fg=self.SUBTEXT,
            activebackground="#3a3b48", activeforeground=self.TEXT,
            relief="flat", bd=0, padx=16, pady=8,
            highlightbackground=self.SUBTEXT, highlightthickness=1,
            cursor="hand2",
            command=self._browse_folder
        )
        self.fix_all_btn.pack(side="left")

        tk.Frame(self, bg=self.PANEL, height=1).pack(fill="x", padx=20, pady=0)

        # ── log area ────────────────────────────────────────────
        log_hdr = tk.Frame(self, bg=self.BG)
        log_hdr.pack(fill="x", padx=20, pady=(10, 4))
        tk.Label(log_hdr, text="Output", font=("Segoe UI", 9, "bold"),
                 bg=self.BG, fg=self.SUBTEXT).pack(side="left")
        tk.Button(log_hdr, text="Clear", font=("Segoe UI", 8),
                  bg=self.BG, fg=self.SUBTEXT, relief="flat",
                  activebackground=self.BG, cursor="hand2",
                  command=self._clear_log).pack(side="right")

        self.log_box = scrolledtext.ScrolledText(
            self, font=self.MONO,
            bg=self.PANEL, fg=self.TEXT,
            insertbackground=self.TEXT,
            relief="flat", bd=0,
            selectbackground=self.ACCENT,
            wrap="word", state="disabled",
            padx=10, pady=8
        )
        self.log_box.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # colour tags for log
        self.log_box.tag_config("ok",      foreground=self.SUCCESS)
        self.log_box.tag_config("err",     foreground=self.ERROR)
        self.log_box.tag_config("accent",  foreground=self.ACCENT)
        self.log_box.tag_config("sub",     foreground=self.SUBTEXT)

        # ── status bar ──────────────────────────────────────────
        self.status_var = tk.StringVar(value="Ready — browse for portrait files to fix.")
        tk.Label(self, textvariable=self.status_var,
                 font=("Segoe UI", 8), bg=self.BG, fg=self.SUBTEXT,
                 anchor="w").pack(fill="x", padx=22, pady=(0, 8))

        self._log_intro()

    # ── logging ──────────────────────────────────────────────────
    def _log(self, text, tag=None):
        self.log_box.configure(state="normal")
        if tag:
            self.log_box.insert("end", text + "\n", tag)
        else:
            self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self.update_idletasks()

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self._log_intro()

    def _log_intro(self):
        self._log("Ivalice Chronicles Portrait Seam Fixer", "accent")
        self._log("Fixes the black seam line on animated portrait textures.", "sub")
        self._log("Output is saved as  <original_name>_fixed.png  next to your file.", "sub")
        self._log("")

    # ── file selection ───────────────────────────────────────────
    def _browse(self):
        paths = filedialog.askopenfilenames(
            title="Select portrait textures to fix",
            filetypes=[
                ("Portrait textures", "*.dds *.png"),
                ("DDS textures",      "*.dds"),
                ("PNG images",        "*.png"),
                ("All files",         "*.*"),
            ]
        )
        if paths:
            self._run([pathlib.Path(p) for p in paths])

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Select folder to fix all portraits in")
        if folder:
            paths  = list(pathlib.Path(folder).glob("*.dds"))
            paths += [p for p in pathlib.Path(folder).glob("*.png")
                      if not p.stem.endswith("_fixed")]
            if not paths:
                self._log("No .dds or .png files found in that folder.", "err")
            else:
                self._run(paths)

    # ── processing ───────────────────────────────────────────────
    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.browse_btn.configure(state=state)
        self.fix_all_btn.configure(state=state)

    def _run(self, paths):
        self._set_busy(True)
        threading.Thread(target=self._process_thread,
                         args=(paths,), daemon=True).start()

    def _process_thread(self, paths):
        ok = 0
        self.status_var.set(f"Processing {len(paths)} file(s)…")
        self._log(f"Processing {len(paths)} file(s)…", "sub")
        for p in paths:
            if process_file(p, self._log):
                ok += 1
        summary = f"Done — {ok}/{len(paths)} fixed successfully."
        self._log(summary, "ok" if ok == len(paths) else "err")
        self.status_var.set(summary)
        self._set_busy(False)


# ── entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
