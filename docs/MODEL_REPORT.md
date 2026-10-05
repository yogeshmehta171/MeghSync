# Flood model report

This report describes the flood-prediction model used by MeghSync: the data it was trained on, how it works, how it was trained, and how well it performs. Every number comes from the code in `ml/`, the data in `data/` and the test outputs in `ml/check_results_v2.txt` and `ml/check_results_v3.txt`. Items that could not be confirmed from the repository are marked **[confirm]**.

## 1. Purpose

A hydraulic simulator such as EPA SWMM can say which streets flood, but it is too slow for a live dashboard. The model is a fast stand-in (a surrogate). It reads the last hour of water levels and the rainfall, and predicts the flood depth at every node of the T. Nagar drainage graph now and for the next 3 hours.

## 2. The drainage graph

| Item | Value |
|---|---|
| Nodes | 662: 358 municipal drain manholes, 283 street nodes from OpenStreetMap, 21 outfalls |
| Links | 661: 198 drain pipes, 193 street channels, 249 short "stub" links joining drains to streets (at least 5 m long), 21 outfall links (10 m each) |
| Shape | one connected graph with no loops |
| Coverage | the catchment areas of the nodes add up to about 680 hectares |
| Coordinates | latitude and longitude (EPSG:4326) and metric UTM zone 44N (EPSG:32644) |

How the municipal drain data and the street network were matched, and the original file formats, are not in the repository **[confirm]**.

## 3. Training data

| Item | Value |
|---|---|
| Storms | 300 synthetic storms, simulated with EPA SWMM (version and routing option **[confirm]**) |
| Rain per storm | 36 steps of 5 minutes (3 hours). Peak intensity 11.6 to 149.4 mm/hr (median 50.4). Total rain 20 to 150 mm (median 55.5). 84 storms have two or more rain pulses (up to three) |
| Simulator output per storm | 59 steps of 5 minutes: surface flood depth and node depth for all 662 nodes. The deepest flood in any storm is 2.4 m. Between 10 and 237 nodes exceed 15 cm per storm (median 99) |
| Pipe blockage | about half of the storms have blockage: 192 pipes, each left at 10 to 90% of its capacity (never fully closed). The same storm is never run with and without blockage |
| Split | storms 0 to 209 train, 210 to 249 validate, 250 to 299 are a test set that is never used for training or for choosing a model |

Gaps: no storm peaks below 11.6 mm/hr, no storm lasts longer than 3 hours of rain, and the data has no real observations.

### Files used by the training code

| File | Content |
|---|---|
| `dataset/flood_storm_XXX.npy` | surface flood depth, shape [time, 662], metres |
| `dataset/depth_storm_XXX.npy` | node (pipe) depth, shape [time, 662], metres |
| `dataset/blockage_storm_XXX.npy` | pipe capacity fraction, shape [661], 1 means clear |
| `dataset/edge_index.pt` | pipe connections, shape [2, 661] |
| `synthetic_storms_mm_hr.npy` | rain for all storms, shape [300, 36], mm/hr |
| `out/nodes.csv` | node properties used as static inputs |

## 4. The model

### Inputs
For every node and each of the last 12 steps (1 hour) the model receives 15 numbers:

* 4 changing values: flood depth (divided by 2.5 m), node depth (divided by 10 m), rain intensity (divided by 150 mm/hr), and rain over the last 6 hours (divided by 200 mm);
* 3 blockage summaries: the mean blocked fraction of the pipes leaving the node, of the pipes entering it, and the larger of the two;
* 8 fixed node properties from `nodes.csv`, standardised: `x_utm`, `y_utm`, `invert_m`, `rim_m`, `max_depth_m`, `ponded_area_m2`, `osm_id`, `catchment_m2`.

Pipe capacities (shape [batch, 661]) are a separate input. The input tensor is [batch, 662 nodes, 12 steps, 4 features].

`osm_id` is an identifier, not a physical property (it is empty for drain manholes). It is probably best removed in a future retrain. The model reads the number of static features from its checkpoint, so this is possible, but it makes the new model incompatible with the existing weights.

### Architecture
1. A linear layer maps the 15 inputs to 32 hidden units.
2. Three residual **capacity-gated graph layers** pass information along the pipes and streets, in both directions. A message from node j to node i is the pipe's capacity multiplied by a small network of the two node states, the capacity and the flow direction. Messages are summed, then passed through layer normalisation and ReLU.
3. A learned time-position embedding is added and a **4-head self-attention** layer looks across the 12 steps.
4. The last time step goes through a small network (32, 32, 3) that produces three values per node: a wet/dry score, a flood-depth value and a pipe-depth value.

### Outputs and why they are always physical
* Flood depth = 1.5 x sigmoid(z) x 2.5 m, so it is never negative and never above 3.75 m.
* Pipe depth = 1.5 x sigmoid(z) x 10 m.
* A node counts as dry when the wet probability is 0.5 or lower, and its flood depth is then set to exactly 0.

There is no softplus layer. This family follows the idea of ASTGCN (Guo et al., 2019) but is not the original model: it uses sparse pipe connections and capacity-gated messages instead of the original Chebyshev filters and spatial-attention matrix.

### Using it as a forecaster
The model predicts one 5-minute step. To look 3 hours ahead it feeds its own prediction back in 36 times ("rollout"). The backend does this every tick and keeps the +30 min, +1 h, +2 h and +3 h results. The forecast assumes the current rainfall continues.

## 5. Training

| | First model (v2) | Fine-tuned model (v3) |
|---|---|---|
| Script | `ml/train.py` | the fine-tuning script (not in the repository **[confirm]**), settings in `ml/checkpoints_v3/run_config.json` |
| Starting point | random | the v2 weights |
| Optimiser | Adam, learning rate 0.001 | learning rate 0.0003 (optimiser type **[confirm]**) |
| Batch size | 16 | 16 |
| Epochs | up to 40 (best saved at epoch index 35) | 16 (best saved at epoch index 13) |
| Rollout length in training | 4 steps (20 min), after 3 epochs of 1 step | up to 36 steps (3 h) in chunks of 4, with a curriculum of growing length **[confirm details]** |
| Samples | all windows plus 1,500 "dry" windows | 3,000 per epoch plus 2,000 dry windows |
| Wet-class weight cap | 20 | 10 |
| Extra | gradient clipping at 1.0 | a monotonicity penalty (every 4 steps, weight 10) **[confirm]** |
| Selection | best validation score at the 20-minute step | **[confirm]** |

**Loss (v2):** for every rolled-out step, binary cross-entropy for wet/dry, plus 4 times a smooth L1 error on flood depth (wet nodes only), plus a smooth L1 error on pipe depth.

**Dry windows:** examples with no rain and no flooding teach the model that a dry city stays dry.

**Why v2 was weak at long range:** it was trained and selected on a 20-minute rollout, so errors compounded over the 3-hour forecast. Training v3 on long rollouts fixed this.

Software: PyTorch 2.6.0 with CUDA 12.4, PyTorch Geometric 2.8.0. Training used a GPU (the script is tuned for 6 GB). The seed of the fine-tune run was 1234.

## 6. Evaluation

**Protocol.** The test uses the 50 unseen storms (250 to 299). For each storm the real simulator provides the first 12 steps, then the model predicts the following 3 hours by itself. A node is a "hazard" when its flood depth is 15 cm or more, the depth at which routing starts avoiding it. "Flooded-only error" is the mean absolute error on nodes that are truly flooded (3 cm or more). "False wet" is the share of dry nodes the model shows with 3 cm or more. "Persistence" is a simple baseline that assumes nothing changes.

### Results on the 50 unseen storms

| Horizon | Recall v2 / v3 | Precision v2 / v3 | F1 v2 / v3 | Error on flooded nodes v2 / v3 | False wet on dry nodes v2 / v3 | Persistence recall |
|---|---|---|---|---|---|---|
| +5 min | 0.97 / 0.96 | 0.98 / 0.98 | 0.97 / 0.97 | 0.8 cm / 1.1 cm | 0.69% / 1.59% | 0.86 |
| +30 min | 0.93 / 0.92 | 0.94 / 0.95 | 0.93 / 0.93 | 2.3 cm / 2.2 cm | 0.83% / 1.81% | 0.47 |
| +1 h | 0.93 / 0.91 | 0.90 / 0.94 | 0.92 / 0.93 | 4.3 cm / 3.1 cm | 0.85% / 1.60% | 0.28 |
| +2 h | 0.95 / 0.92 | 0.78 / 0.95 | 0.86 / 0.94 | 14.9 cm / 4.2 cm | 1.88% / 1.59% | 0.17 |
| +3 h | 0.98 / 0.93 | 0.64 / 0.95 | 0.78 / 0.94 | 42.6 cm / 4.3 cm | 4.96% / 1.47% | 0.17 |

### Other checks

| Check | v2 | v3 |
|---|---|---|
| Zero rain for 3 h: largest node-depth drift | 0.356 m | 0.020 m |
| Zero rain: any flooding | none | none |
| Rain sweep from a cold start: nodes above 15 cm after 1 h at 10 / 30 / 60 / 90 / 120 / 150 mm/hr | 0, 41, 104, 156, 192, 214 | 0, 33, 104, 165, 216, 255 |
| Largest predicted depth in the sweep | 2.49 m | 2.54 m |
| Blockage logic: more blocked pipes never means less flooding | fails (a dip at +3 h) | passes |
| Blockage accuracy on real storms (29 blocked test storms) | fails | fails |
| One step on a CPU | 56 ms | 55 ms |
| 36-step rollout on a CPU | 1.97 s | 2.03 s |

Six of the eight automatic checks pass for v3 and four for v2.

### How to read this
* v3 is much better beyond one hour. At +3 h its error on flooded nodes is 4.3 cm instead of 42.6 cm and its precision is 0.95 instead of 0.64.
* v3 is slightly worse at 5 minutes (1.1 cm against 0.8 cm) and shows more faint false water on dry nodes at short range.
* The route-blocking decision uses the 15 cm line, where both models are almost the same at +5 min (recall 0.96 against 0.97, precision 0.98).
* At +3 h, a "nothing changes" forecast finds only 17% of flooded nodes, against 93% for v3.
* Live in the application, v3 predicts 154, 184, 228 and 270 nodes above 15 cm at +30 min, +1 h, +2 h and +3 h for a steady 60 mm/hr, against 148, 183, 252 and 356 for v2. v2's forecast climbs faster at long range.

## 7. Limitations

1. **Synthetic training data only.** Nothing was compared with real flood records, so real accuracy is unknown.
2. **Light rain.** No training storm peaks below 11.6 mm/hr. At a steady 10 mm/hr v3 predicts up to 12.6 cm of flooding after one hour, probably too much.
3. **Blockage.** The model reacts only weakly to blocked pipes. On real storms it is not more accurate with the true blockage than without it, and the training data has one blockage style and no with/without pairs. The command center's block-node action affects routing, not the model, and the model's blockage input is off by default.
4. **Storm length.** All storms last 3 hours of rain with at most 150 mm. Longer storms are untested. The rolling 6-hour rain input is scaled to 200 mm.
5. **Single area.** The model is tied to this graph. Another area needs its own graph, simulations and training.
6. **Speed.** One step takes about 55 ms on a CPU, just above the 50 ms goal, which does not matter at a 5-second tick.
7. **Forecast labels.** The labels "low" and "trend only" attached to +1 h, +2 h and +3 h were chosen for v2 and are conservative for v3.

## 8. Reproducing and updating

* Rebuild or check the data: `tools/storm_stats.py` and `tools/dataset_qa.py`.
* Train: `ml/train.py` (see the header of the file).
* Check a model file against the real backend code: `backend/verify_model_swap.py`.
* Check the running application: `backend/live_model_test.py`.
* Full retraining process: `docs/RETRAINING_WORKFLOW.md`.

## 9. References

* Guo, S., Lin, Y., Feng, N., Song, C., Wan, H. (2019). Attention Based Spatial-Temporal Graph Convolutional Networks for Traffic Flow Forecasting. AAAI.
* Rossman, L. A. Storm Water Management Model Reference Manual, Volume I: Hydrology and Volume II: Hydraulics. US EPA.
* Fey, M., Lenssen, J. E. (2019). Fast Graph Representation Learning with PyTorch Geometric.
* Paszke, A. et al. (2019). PyTorch: An Imperative Style, High-Performance Deep Learning Library.
