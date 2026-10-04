"""
train.py  (v2)

Run:
    python train.py --quick     (2-minute smoke test on a few storms, run this FIRST)
    python train.py             (full training)

Writes to checkpoints_v2/ (the old checkpoints_astgcn/ folder is left untouched):
    best_model.pt, last_checkpoint.pt, checkpoint_epoch_XX.pth, dry_baseline.npy
"""
import argparse
import glob
import os

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from dataset import (UrbanFloodDataset, compute_dry_baseline, rolling_rain_mm,
                     FLOOD_MAX_M, DEPTH_MAX_M, WET_M, SEQ_LEN)
from model import FloodASTGCN, rollout

# ---------------- settings (safe defaults for a 6 GB GPU) ----------------
HORIZON = 4            # steps the model is trained to roll out on its own (4 x 5 min = 20 min)
WARMUP_EPOCHS = 3      # first epochs train 1 step only, then switch to HORIZON steps
EPOCHS = 40
BATCH_SIZE = 16        # if you get "CUDA out of memory", change to 8 or 4
LR = 1e-3
HIDDEN = 32
N_DRY_WINDOWS = 1500   # extra "nothing happens" samples
BLOCK_M = 0.15         # same as FLOOD_ROUTE_BLOCK_M in app.py
CKPT_DIR = "checkpoints_v2"


def to_dev(batch, device):
    return {k: v.to(device) for k, v in batch.items()}


def get_latest_checkpoint(d):
    cks = glob.glob(f"{d}/checkpoint_epoch_*.pth")
    if not cks:
        return None
    cks.sort(key=lambda x: int(x.split("_epoch_")[-1].split(".pth")[0]))
    return cks[-1]


def save_checkpoint(path, epoch, model, optimizer, best_score, dry_baseline):
    torch.save({
        "epoch": epoch,
        "model_state": model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "best_score": best_score,
        "config": model.config,
        "dry_baseline": dry_baseline,
    }, path)


def compute_loss(results, b, k_active, pos_weight):
    total = 0.0
    for j in range(k_active):
        o = results[j]["out"]
        y_f, y_d = b["flood_fut"][:, :, j], b["depth_fut"][:, :, j]
        wet = (y_f >= WET_M).float()
        bce = F.binary_cross_entropy_with_logits(o["wet_logit"], wet, pos_weight=pos_weight)
        amt_err = o["flood_amt"] * FLOOD_MAX_M - y_f                                # metres
        flood_l = (F.smooth_l1_loss(amt_err, torch.zeros_like(amt_err), beta=0.05, reduction="none") * wet).sum() \
            / wet.sum().clamp(min=1.0)
        d_err = o["depth"] * DEPTH_MAX_M - y_d                                      # metres
        depth_l = F.smooth_l1_loss(d_err, torch.zeros_like(d_err), beta=0.1)
        total = total + bce + 4.0 * flood_l + depth_l
    return total / k_active


@torch.no_grad()
def evaluate(model, loader, k, device):
    model.eval()
    steps = sorted({0, k - 1})
    st = {s: dict(tp=0, fp=0, fn=0, wet_abs=0.0, wet_n=0, dry_fp=0, dry_n=0) for s in steps}
    sens_abs = mae_real = mae_ones = 0.0
    sens_n = 0
    for batch in loader:
        b = to_dev(batch, device)
        res = rollout(model, b["flood_hist"], b["depth_hist"], b["rain"], b["cum"], b["cap"], k, hard=True)
        for s in steps:
            pred, true = res[s]["flood"], b["flood_fut"][:, :, s]
            tb, pb = true > BLOCK_M, pred > BLOCK_M
            st[s]["tp"] += int((tb & pb).sum()); st[s]["fp"] += int((pb & ~tb).sum()); st[s]["fn"] += int((tb & ~pb).sum())
            wet = true >= WET_M
            st[s]["wet_abs"] += float((pred - true).abs()[wet].sum()); st[s]["wet_n"] += int(wet.sum())
            dry = ~wet
            st[s]["dry_fp"] += int(((pred >= WET_M) & dry).sum()); st[s]["dry_n"] += int(dry.sum())
        blocked = b["cap"].min(dim=1).values < 1.0
        if blocked.any():
            sub = {key: v[blocked] for key, v in b.items()}
            alt = rollout(model, sub["flood_hist"], sub["depth_hist"], sub["rain"], sub["cum"],
                          torch.ones_like(sub["cap"]), k, hard=True)[k - 1]["flood"]
            real = res[k - 1]["flood"][blocked]
            true = sub["flood_fut"][:, :, k - 1]
            sens_abs += float((real - alt).abs().sum()); sens_n += real.numel()
            mae_real += float((real - true).abs().sum()); mae_ones += float((alt - true).abs().sum())

    print("   --- validation (model feeds on its own outputs) ---")
    f1_last = 0.0
    for s in steps:
        d = st[s]
        rec = d["tp"] / max(1, d["tp"] + d["fn"]); prec = d["tp"] / max(1, d["tp"] + d["fp"])
        f1 = 2 * rec * prec / max(1e-9, rec + prec)
        print(f"   +{(s + 1) * 5:>3} min | blocked(>15cm) recall {rec:.2f} precision {prec:.2f} F1 {f1:.2f} | "
              f"MAE on wet nodes {100 * d['wet_abs'] / max(1, d['wet_n']):.1f} cm | "
              f"false-wet on dry nodes {100 * d['dry_fp'] / max(1, d['dry_n']):.3f} %")
        f1_last = f1
    if sens_n:
        print(f"   blockage test | mean |change in predicted flood| when blockage is removed: "
              f"{100 * sens_abs / sens_n:.3f} cm | MAE real blockage {100 * mae_real / sens_n:.3f} cm vs "
              f"blockage=1 {100 * mae_ones / sens_n:.3f} cm  (real should be LOWER, change should be > 0)")
    return 1.0 - f1_last


@torch.no_grad()
def cold_start_check(model, baseline, device, rains=(0, 30, 60, 120), steps=36):
    """Server after Reset: resting state, rain jumps to a constant value. Prints max flood in cm."""
    model.eval()
    N, E, L = model.n_nodes, model.n_edges, SEQ_LEN
    base = torch.tensor(baseline, dtype=torch.float32, device=device)[None, :, None].repeat(1, 1, L)
    print("   cold start (max flood cm / nodes>15cm) at +1 h and +3 h:")
    for r in rains:
        rain_np = np.concatenate([np.zeros(L - 1), np.full(steps + 1, float(r))]).astype(np.float32)
        rain = torch.tensor(rain_np, device=device)[None]
        cum = torch.tensor(rolling_rain_mm(rain_np), device=device)[None]
        res = rollout(model, torch.zeros(1, N, L, device=device), base, rain, cum,
                      torch.ones(1, E, device=device), steps, hard=True)
        cells = []
        for s in (11, 35):
            f = res[s]["flood"][0]
            cells.append(f"{100 * float(f.max()):.1f}/{int((f > BLOCK_M).sum())}")
        print(f"      rain {r:>3} mm/hr: +1h {cells[0]:>10}   +3h {cells[1]:>10}")


def train(quick=False):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Hardware target: {device.type.upper()}")
    train_ids = range(0, 20) if quick else range(0, 210)
    val_ids = range(210, 220) if quick else range(210, 250)
    epochs = 2 if quick else EPOCHS

    baseline = compute_dry_baseline(storm_indices=train_ids)
    print(f"dry baseline depth (m): min {baseline.min():.3f} median {np.median(baseline):.3f} max {baseline.max():.3f}")
    train_ds = UrbanFloodDataset(storm_indices=train_ids, horizon=HORIZON,
                                 n_dry_windows=200 if quick else N_DRY_WINDOWS, dry_baseline=baseline)
    val_ds = UrbanFloodDataset(storm_indices=val_ids, horizon=HORIZON)
    pin = device.type == "cuda"
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, pin_memory=pin)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, pin_memory=pin)

    model = FloodASTGCN(train_ds.edge_index, train_ds.n_nodes, train_ds.node_static, train_ds.edge_static,
                        hidden=HIDDEN, seq_len=SEQ_LEN).to(device)
    print(f"model parameters: {sum(p.numel() for p in model.parameters()):,}")
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)

    p = max(train_ds.wet_fraction, 1e-4)
    pos_weight = torch.tensor(min(20.0, (1 - p) / p), device=device)
    print(f"positive weight for wet/dry loss: {float(pos_weight):.1f}")

    start_epoch, best_score = 0, float("inf")
    ckpt_dir = CKPT_DIR + ("_quick" if quick else "")
    os.makedirs(ckpt_dir, exist_ok=True)
    np.save(os.path.join(ckpt_dir, "dry_baseline.npy"), baseline)
    latest = get_latest_checkpoint(ckpt_dir)
    if latest:
        print(f"Resuming from {latest}...")
        ck = torch.load(latest, map_location=device)
        model.load_state_dict(ck["model_state"])
        optimizer.load_state_dict(ck["optimizer_state"])
        start_epoch = ck["epoch"] + 1
        best_score = ck.get("best_score", float("inf"))

    print("\nStarting gradient descent...")
    for epoch in range(start_epoch, epochs):
        model.train()
        k_active = 1 if epoch < WARMUP_EPOCHS else HORIZON
        total = 0.0
        for bi, batch in enumerate(train_loader):
            b = to_dev(batch, device)
            optimizer.zero_grad()
            res = rollout(model, b["flood_hist"], b["depth_hist"], b["rain"], b["cum"], b["cap"],
                          k_active, hard=False)
            loss = compute_loss(res, b, k_active, pos_weight)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total += loss.item()
            if bi % 50 == 0:
                print(f"   Train batch {bi:04d}/{len(train_loader)} | loss {loss.item():.4f} | rollout steps {k_active}")

        print(f"Epoch {epoch + 1:02d}/{epochs} | train loss {total / len(train_loader):.4f}")
        score = evaluate(model, val_loader, HORIZON, device)   # lower is better (= 1 - F1 at the last step)
        cold_start_check(model, baseline, device)

        save_checkpoint(os.path.join(ckpt_dir, f"checkpoint_epoch_{epoch:02d}.pth"), epoch, model, optimizer, best_score, baseline)
        save_checkpoint(os.path.join(ckpt_dir, "last_checkpoint.pt"), epoch, model, optimizer, best_score, baseline)
        if score < best_score:
            best_score = score
            save_checkpoint(os.path.join(ckpt_dir, "best_model.pt"), epoch, model, optimizer, best_score, baseline)
            print(f"   -> new best (1-F1 = {best_score:.3f}), saved best_model.pt")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="tiny smoke test, 2 epochs")
    train(quick=ap.parse_args().quick)