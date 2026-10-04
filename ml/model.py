"""
model.py  (v2)

Fixes in this file:
  * Blockage can no longer be ignored: every message along a pipe is multiplied by that
    pipe's capacity, and each node also receives its own blocked-fraction as input.
  * 3 message-passing layers (the old model saw only direct neighbours) on a graph where
    every pipe works in both directions, with a direction flag so flow direction is kept.
  * Temporal attention now has positional embeddings (the old one could not tell step order).
  * Outputs are bounded: a wet/dry probability + a bounded flood depth + a bounded node depth.
    No softplus, so no unbounded runaway, and dry nodes can be exactly 0.
  * Static node/edge features are stored inside the model (and inside the checkpoint).
  * rollout() feeds the model's own outputs back (surface flood AND node depth), the same way
    the live server does, so training can use the same loop.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import MessagePassing
from torch_geometric.utils import scatter

from dataset import FLOOD_MAX_M, DEPTH_MAX_M, RAIN_MAX_MMHR, ANTECEDENT_MAX_MM

WET_PROB_THRESHOLD = 0.5
FLOOD_CAP_SCALED = 1.5   # bounded flood output: at most 1.5 * FLOOD_MAX_M
DEPTH_CAP_SCALED = 1.5   # bounded depth output: at most 1.5 * DEPTH_MAX_M


class CapacityGatedConv(MessagePassing):
    """Message i<-j = capacity_ij * MLP([h_i, h_j, edge_features]). capacity 0 => no flow."""

    def __init__(self, channels, edge_dim):
        super().__init__(aggr="add")
        self.msg = nn.Sequential(nn.Linear(2 * channels + edge_dim, channels), nn.ReLU(),
                                 nn.Linear(channels, channels))
        self.self_lin = nn.Linear(channels, channels)
        self.norm = nn.LayerNorm(channels)

    def forward(self, x, edge_index, edge_attr, cap):
        agg = self.propagate(edge_index, x=x, edge_attr=edge_attr, cap=cap)
        return F.relu(self.norm(self.self_lin(x) + agg))

    def message(self, x_i, x_j, edge_attr, cap):
        m = self.msg(torch.cat([x_i, x_j, edge_attr], dim=-1))
        return cap.unsqueeze(-1) * m


class FloodASTGCN(nn.Module):
    N_DYNAMIC = 4   # flood, node depth, rain, antecedent rain
    N_BLOCK = 3     # mean blocked fraction of outgoing pipes, of incoming pipes, max of both

    def __init__(self, edge_index, n_nodes, node_static=None, edge_static=None,
                 hidden=32, n_layers=3, seq_len=12, heads=4):
        super().__init__()
        E = edge_index.shape[1]
        s_node = 0 if node_static is None else node_static.shape[1]
        s_edge = 0 if edge_static is None else edge_static.shape[1]
        self.config = dict(n_nodes=n_nodes, n_edges=E, n_node_static=s_node, n_edge_static=s_edge,
                           hidden=hidden, n_layers=n_layers, seq_len=seq_len, heads=heads)
        self.n_nodes, self.n_edges, self.seq_len = n_nodes, E, seq_len

        if node_static is None:
            node_static = torch.zeros(n_nodes, 0)
        if edge_static is None:
            edge_static = torch.zeros(E, 0)
        self.register_buffer("edge_index_raw", edge_index.long())
        self.register_buffer("ei", torch.cat([edge_index, edge_index.flip(0)], dim=1).long())  # both directions
        self.register_buffer("direction", torch.cat([torch.ones(E), -torch.ones(E)]))
        self.register_buffer("node_static", node_static.float())
        self.register_buffer("edge_static", edge_static.float())

        in_dim = self.N_DYNAMIC + self.N_BLOCK + s_node
        edge_dim = 2 + s_edge   # capacity, direction, static edge features
        self.inp = nn.Linear(in_dim, hidden)
        self.convs = nn.ModuleList([CapacityGatedConv(hidden, edge_dim) for _ in range(n_layers)])
        self.pos = nn.Parameter(torch.zeros(seq_len, hidden))
        nn.init.normal_(self.pos, std=0.02)
        self.attn = nn.MultiheadAttention(hidden, heads, batch_first=True)
        self.attn_norm = nn.LayerNorm(hidden)
        self.head = nn.Sequential(nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, 3))

    def _block_features(self, cap, B):
        """Per-node blocked fractions from the per-pipe capacities. cap: [B, E] -> [B, N, 3]."""
        N, E = self.n_nodes, self.n_edges
        off = (torch.arange(B, device=cap.device) * N)[:, None]
        src = (self.edge_index_raw[0][None, :] + off).reshape(-1)
        dst = (self.edge_index_raw[1][None, :] + off).reshape(-1)
        blocked = (1.0 - cap).reshape(-1)
        out_m = scatter(blocked, src, dim=0, dim_size=B * N, reduce="mean")
        in_m = scatter(blocked, dst, dim=0, dim_size=B * N, reduce="mean")
        both = scatter(torch.cat([blocked, blocked]), torch.cat([src, dst]), dim=0, dim_size=B * N, reduce="max")
        return torch.stack([out_m, in_m, both], dim=-1).reshape(B, N, 3)

    def forward(self, x, cap):
        """x: [B, N, T, 4] scaled dynamic inputs. cap: [B, E] pipe capacity fraction (1 = clear)."""
        B, N, T, _ = x.shape
        E = self.n_edges
        blk = self._block_features(cap, B).unsqueeze(2).expand(B, N, T, self.N_BLOCK)
        feats = [x, blk]
        if self.node_static.shape[1] > 0:
            feats.append(self.node_static[None, :, None, :].expand(B, N, T, -1))
        f = torch.cat(feats, dim=-1)

        # batched graph: B copies of the 2E directed edges
        off = (torch.arange(B, device=x.device) * N)[None, :, None]
        ei_b = (self.ei[:, None, :] + off).reshape(2, -1)
        cap2 = cap.repeat(1, 2)                                              # [B, 2E]
        ea = [cap2.unsqueeze(-1), self.direction[None, :, None].expand(B, 2 * E, 1)]
        if self.edge_static.shape[1] > 0:
            ea.append(self.edge_static.repeat(2, 1)[None].expand(B, 2 * E, -1))
        ea_b = torch.cat(ea, dim=-1).reshape(B * 2 * E, -1)
        cap_b = cap2.reshape(-1)

        steps = []
        for t in range(T):
            h = self.inp(f[:, :, t, :].reshape(B * N, -1))
            for conv in self.convs:
                h = h + conv(h, ei_b, ea_b, cap_b)
            steps.append(h)
        seq = torch.stack(steps, dim=1) + self.pos[:T]                      # [B*N, T, H]
        a, _ = self.attn(seq, seq, seq)
        seq = self.attn_norm(seq + a)
        o = self.head(seq[:, -1, :]).reshape(B, N, 3)
        return dict(
            wet_logit=o[..., 0],
            flood_amt=FLOOD_CAP_SCALED * torch.sigmoid(o[..., 1]),   # scaled, bounded
            depth=DEPTH_CAP_SCALED * torch.sigmoid(o[..., 2]),       # scaled, bounded
        )


def decode(out, hard=True):
    """Model output -> physical units. Returns (flood_m, depth_m, p_wet)."""
    p = torch.sigmoid(out["wet_logit"])
    amt = out["flood_amt"] * FLOOD_MAX_M
    flood = torch.where(p > WET_PROB_THRESHOLD, amt, torch.zeros_like(amt)) if hard else p * amt
    return flood, out["depth"] * DEPTH_MAX_M, p


def build_x(flood_m, depth_m, rain, cum):
    """flood_m, depth_m: [B, N, T] metres. rain (mm/hr), cum (mm over last 6 h): [B, T]."""
    B, N, T = flood_m.shape
    r = rain[:, None, :].expand(B, N, T)
    c = cum[:, None, :].expand(B, N, T)
    return torch.stack([flood_m / FLOOD_MAX_M, depth_m / DEPTH_MAX_M, r / RAIN_MAX_MMHR, c / ANTECEDENT_MAX_MM], -1)


def rollout(model, flood_hist, depth_hist, rain, cum, cap, steps, hard=True):
    """
    Self-fed multi-step prediction. flood_hist/depth_hist: [B, N, L]; rain, cum: [B, L + steps]
    where position j of rain is the rain of the interval leading into the state predicted at step j.
    Returns a list (one entry per step) of dicts: out, flood, depth, p_wet.
    """
    L = flood_hist.shape[2]
    fh, dh = flood_hist, depth_hist
    results = []
    for j in range(steps):
        x = build_x(fh, dh, rain[:, j:j + L], cum[:, j:j + L])
        out = model(x, cap)
        flood, depth, p = decode(out, hard=hard)
        results.append(dict(out=out, flood=flood, depth=depth, p_wet=p))
        fh = torch.cat([fh[:, :, 1:], flood.unsqueeze(-1)], dim=2)
        dh = torch.cat([dh[:, :, 1:], depth.unsqueeze(-1)], dim=2)
    return results


def load_model(path, device="cpu"):
    """Rebuild the model from a checkpoint written by train.py. Returns (model, dry_baseline or None)."""
    ck = torch.load(path, map_location=device, weights_only=False)
    c = ck["config"]
    model = FloodASTGCN(
        edge_index=torch.zeros(2, c["n_edges"], dtype=torch.long), n_nodes=c["n_nodes"],
        node_static=torch.zeros(c["n_nodes"], c["n_node_static"]),
        edge_static=torch.zeros(c["n_edges"], c["n_edge_static"]),
        hidden=c["hidden"], n_layers=c["n_layers"], seq_len=c["seq_len"], heads=c["heads"],
    )
    model.load_state_dict(ck["model_state"])
    model.to(device).eval()
    return model, ck.get("dry_baseline")