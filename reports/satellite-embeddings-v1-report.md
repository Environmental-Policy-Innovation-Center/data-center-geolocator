# Finding Data Centers in Illinois with Satellite Embeddings 

*A retrieval study over SkyCLIP/NAIP and SSL4EO/Sentinel-2 embeddings, evaluated against 50
confirmed Illinois data centers. 

---

## Executive summary
- **Use high-resolution NAIP/SkyCLIP, not Sentinel-2.** Whitened NAIP gets **recall@1000 = 0.80**
  vs **0.56** for Sentinel-2; combining the two adds essentially nothing (one extra site). S2 is
  only competitive on large warehouse-style roofs and is worth considering only where sub-meter
  imagery is unavailable.
- **Embeddings can find data centers — but only after one critical fix.** Out of the box, nearest-
  neighbour search over SkyCLIP/NAIP embeddings recovers just **36%** of held-out data centers in
  the top 1000 of 2.9 M candidate tiles. **Whitening the embedding space first lifts that to 80%**
  (and 96% by the top 10,000). Whitening is the single highest-leverage decision in the whole
  pipeline.
- **You can bootstrap with zero labels.** A SkyCLIP *text* prompt ensemble ("a data center …")
  reaches **0.36** with no examples at all — useful to seed the first candidates before you have
  confirmed sites.
- **Recall is not precision.** The dominant false positive is ordinary logistics warehouses, so a
  candidate list needs a verification stage (high-res + a vision-language model or a trained
  classifier) before it is operationally useful.
- **Some data centers are simply not findable from overhead imagery** — urban carrier hotels and
  small edge/PoP sites read as generic buildings; ~1 in 5 of the reference set is missed by both
  sources even at depth. Those require non-imagery signals (registries, power/permit data).

**Bottom line for an operational system:** *embed current high-res imagery with SkyCLIP → whiten
the pool → search with a small prototype of confirmed large data centers → spatially deduplicate
the top few thousand hits → verify with a VLM/analyst → feed confirmations back into the
prototype.* This recovers ~80–96% of the imagery-findable data centers while a human only reviews a
few hundred locations.

---

## 1. What was tested

| | SkyCLIP / NAIP | SSL4EO / Sentinel-2 |
|---|---|---|
| Model | SkyCLIP ViT-B/32 (CLIP, image+text) | SSL4EO DINO ViT-S/16 |
| Embedding | 512-d, L2-normalized | 384-d |
| Tile | 224 m, non-overlapping, **NAIP 2023** | 2.24 km receptive field on a ~200 m grid, **2024** |
| Pool (Illinois) | 2.91 M tiles | 4.69 M chips (20 MGRS tiles covering the sites) |

**Reference truth:** 50 confirmed, currently-built IL data centers, collapsed to four archetypes —
`hyperscale` (2), `large_purpose_built` (6), `warehouse_colo` (19), `other` (23: urban carrier
hotels, enterprise, HPC, small-edge, unclassified).

**Evaluation:** query-by-example retrieval under leave-one-site-out cross-validation (the set is
too small to train a model). A site is "found@K" if any tile within **300 m** is in the top K.
Headline metric **recall@1000**; we also report rank-of-first-hit, per-archetype recall, and
bootstrap CIs. A pool-contamination step removes training sites' own tiles before scoring so we
measure generalisation, not self-retrieval. Search is *exact* cosine, to measure embedding utility
rather than index quality.

> Chance recall@1000 ≈ 0.21%, so the whitened 0.80 is a ~**380× enrichment** over random.

---

## 2. Findings

### 2.1 Embeddings find data centers — after whitening

| method (NAIP, LOO) | recall@100 | recall@1000 | recall@10000 | median rank |
|---|--:|--:|--:|--:|
| raw cosine, prototype = mean of known sites | 0.12 | 0.36 | 0.92 | 1778 |
| **ZCA-whitened cosine** | **0.48** | **0.80** | **0.96** | **150** |

Whitening more than doubles recall@1000, quadruples recall@100, and cuts the median rank from
~1800 to 150. It is computed **unsupervised from the pool covariance** (no labels), so it carries
no leakage and is a one-time preprocessing cost.

### 2.2 Why whitening matters (the mechanism)

These embeddings are strongly *anisotropic*: in raw space two random Illinois tiles already sit at
**0.83 cosine** to each other, while data-center pairs sit at 0.86. The data-center signal (a gap
of ~0.18) is real but rides on a large common-mode baseline that dominates the ranking. Whitening
drives background self-similarity to ~0 while data centers keep a positive mutual cosine, so the
discriminative signal becomes the *whole* ranking rather than a small perturbation on top of it.

A consequence worth knowing: whitening **decouples retrieval from human visual "findability."** The
experts' findability rating predicts *raw* retrieval rank (Spearman ρ = 0.38, p = 0.015) but not
*whitened* retrieval (ρ = 0.13, ns) — whitening rescues visually-subtle sites whose embeddings are
nonetheless distinctive. Don't assume "hard for an analyst to confirm" means "hard to retrieve."

### 2.3 Query design: prototype from canonical data centers

In **raw** space, a prototype averaged over *all* known sites is dominated by the majority archetype
(42 of 50 are warehouse-style or "other"), so it behaves like a generic "industrial building"
query. Building the prototype from one archetype instead reveals strong, **asymmetric** transfer: a
**`large_purpose_built`** prototype is the best raw query — it finds hyperscale (1.00), large (0.83)
and warehouse (0.53) sites, while the reverse (warehouse → large) is weak (0.17). It is the most
internally coherent and central archetype in embedding space.

**But this advantage is a raw-space artifact.** Whitening removes the majority bias directly, so
once you whiten, the prototype-choice ranking flips and *more seeds win*:

| prototype (whitened, LOO) | overall r@1000 | hyperscale | large | warehouse | other |
|---|--:|--:|--:|--:|--:|
| **all 50** | **0.80** | 1.00 | 1.00 | 0.79 | 0.74 |
| `large_purpose_built` only (6) | 0.74 | 1.00 | 1.00 | 0.68 | 0.70 |
| `warehouse_colo` only (19) | 0.56 | 0.50 | 0.83 | 0.84 | 0.26 |

So the operational rule is: **whiten, then prototype from all confirmed sites.** A single-archetype
prototype is for cold-start (few labels) or for *deliberately* biasing the candidate list toward
big purpose-built campuses — which it does cleanly: the `large_purpose_built` candidate list shares
only 64% of locations with the all-50 list, peaks at a higher whitened score (0.735 vs 0.657), and
its raw and whitened rankings agree far more (Spearman 0.54 vs 0.15), i.e. its top candidates are
more canonically data-center-like (plausibly fewer warehouse false positives) at the cost of
missing warehouse-style and urban sites.

Subtracting a negative also helps (the GeoVibes `2·pos − neg` formula reaches 0.54; hard-negative
mining of warehouse-like confusers most helps the ambiguous `other` class). Whitening + a clean
positive prototype is the dominant effect; negatives are a secondary refinement.

### 2.4 NAIP vs Sentinel-2, and fusion

| source (whitened) | recall@1000 | hyperscale | large | warehouse | other |
|---|--:|--:|--:|--:|--:|
| **NAIP/SkyCLIP** | **0.80** | 1.00 | 1.00 | 0.79 | 0.74 |
| Sentinel-2/SSL4EO | 0.56 | 0.00* | 0.50 | **0.79** | 0.43 |

Sentinel-2 ties NAIP only on `warehouse_colo` — big bright roofs are resolved at 10 m — but loses
on everything detail- or context-dependent, and (with n=2*) misses both hyperscale campuses, whose
2.24 km chip is dominated by surrounding farmland. **Fusion barely helps:** spending a fixed review
budget entirely on NAIP (0.80) beats splitting it between sources (0.78); per site, S2 surfaces
exactly **one** data center that NAIP misses. *Caveat:* this is static-2024 similarity; Sentinel-2's
real strength — year-over-year *change* — was not exercised and is the obvious S2 follow-up.

### 2.5 Zero-shot text (no labels)

A SkyCLIP text-prompt **ensemble** reaches **recall@1000 = 0.36 with no training examples** — equal
to the labelled example prototype in raw space, and better balanced across archetypes (it has no
majority bias). It finds the obvious large/hyperscale classes best and the subtle ones worst.
Important limit: **text cannot use whitening** — the transform is fit to the image distribution and
the CLIP modality gap puts text vectors elsewhere, collapsing whitened-text retrieval to 0. So text
is a genuine cold-start option (0.36, raw cosine), but example-based + whitening (0.80) is far
stronger once you have a few confirmed sites.

### 2.6 What is findable, by archetype

| archetype | imagery-findable? | notes |
|---|---|---|
| Hyperscale greenfield campus | **Yes** (NAIP) | huge, distinctive; S2 fails (farmland context, n=2) |
| Large purpose-built / wholesale colo | **Yes** | best class; also the best query seed |
| Industrial-park warehouse-style colo | **Mostly** | findable by NAIP *and* S2, but identical to real warehouses → the precision problem |
| Urban carrier hotels, small edge/PoP, enterprise | **Weak** | the ~1-in-5 hard misses; generic buildings, need non-imagery signals |

### 2.7 Recall is not precision

Every number above is *recall* — does a known data center surface in the top K. It says nothing
about how many of those top-K tiles are **false positives**, and the taxonomy is explicit that the
#1 confuser is ordinary logistics warehouses, which are visually identical to warehouse-style data
centers. A retrieval list is therefore a *candidate* list, not a detection list; it must be paired
with a verification stage. (Measuring precision against a labelled warehouse set was scoped but not
run.)

### 2.8 Use the whitened score to *order validation* too — raw cosine does not help

A natural idea is to re-rank candidates by *raw* (non-whitened) cosine for human review, on the
theory that raw similarity tracks visual obviousness (E8). Tested on the top-1000 candidate list,
using the 28 recovered known sites as a true-positive proxy, **raw cosine makes validation worse,
not better**:

| validation-ordering signal | knowns in top 100 | median rank of the 28 knowns | AUC (known > new) |
|---|--:|--:|--:|
| **whitened score** (the retrieval rank) | **16 / 28** | **62** | **0.81** |
| raw cosine | 5 / 28 | 513 | 0.52 (≈ chance) |

The two orderings barely agree (Spearman 0.15), but the disagreement is raw cosine *losing* signal:
among already-strong candidates every tile sits at 0.94–0.97 raw cosine (mean known-vs-new gap =
0.000), the same anisotropy from E1, so raw similarity cannot separate real data centers from
look-alikes. The whitened score still discriminates (gap 0.089). **Validate in whitened-score
order** — it is simultaneously the best retrieval and the best validation signal. (The whitened
separation is mildly optimistic because the known sites are part of the prototype; the true
known-vs-warehouse margin on unseen sites is what E10 would measure. The top-1000 list ships both
scores so this is inspectable.)

---

## 3. Operational blueprint

A practical embeddings-based pipeline for finding data centers across Illinois (or any new AOI):

1. **Imagery.** Embed the AOI with **SkyCLIP over the most current high-resolution imagery** (NAIP
   2023, or newer Esri/aerial for post-2023 builds). 224 m / 1 m chips. Skip Sentinel-2 for static
   search; reserve it for a separate change-detection track.
2. **Whiten the pool (once).** Compute the pool mean + covariance and apply ZCA whitening to every
   embedding before search. This is unsupervised, label-free, and the biggest single quality lever
   (0.36 → 0.80). `drop-top-5-PC` is a robust, cheaper alternative (0.70) if ZCA's low-variance
   amplification is a concern.
3. **Build the query.** Prototype = mean of **all confirmed data centers** in whitened space
   (whitening already removes the majority bias, so more seeds win — 0.80 vs 0.74 for a
   single-archetype prototype); optionally subtract a mean of mined warehouse-like hard negatives.
   Restrict the prototype to `large_purpose_built` only if you want to *bias* the list toward big
   purpose-built campuses (sharper, fewer warehouse look-alikes, but misses warehouse-style/urban
   sites). With **no labels at all**, cold-start from a SkyCLIP **text** prompt ensemble (raw
   cosine) and promote the first confirmed hits into the prototype.
4. **Search & deduplicate.** Exact cosine over the whitened pool; take the top several thousand
   tiles and **greedily deduplicate by location (~500 m)** so each candidate is a distinct site.
   A 1000-candidate, location-deduplicated list is provided as
   [`top1000_data_center_candidates.geojson`](top1000_data_center_candidates.geojson) (recovered 28
   known sites + 972 new leads; carries both whitened and raw cosine scores — see §2.8).
5. **Verify.** Route candidates through a verification stage — a vision-language model or a small
   classifier trained on the confirmed sites and warehouse hard negatives — to separate true data
   centers from warehouse look-alikes. This is where precision is won.
6. **Close the loop.** Feed verified detections back into the prototype (active learning); recall
   improves as the seed set grows, and the labelling budget is small (utility concentrates in the
   first handful of seeds).

**Operating point.** With whitening, recall@1000 = 0.80 and recall@10000 = 0.96 (0.3% of the
pool); the median true site ranks at ~150. In practice, deduplicating the top ~5–10 k tiles yields
a few hundred distinct candidate locations that contain ~95% of the imagery-findable data centers —
a tractable human/VLM review.

**Index note.** Measure embedding utility with exact search; the *shipped* FAISS index is `IVFPQ`
at `nprobe = 1` (lossy) and should be run at high `nprobe` (or replaced with a flat index — 2.9 M ×
512 fits in ~6 GB) for serious retrieval. Quantifying that recall gap is the one remaining
deployment-readiness experiment (E9).

---

## 4. Limitations

- **Small truth set (n = 50; some archetypes n ≤ 2).** Per-archetype numbers for hyperscale (n=2)
  are case studies, not rates; all headline numbers carry bootstrap CIs (overall recall@1000 95%
  CI ≈ 0.68–0.90 whitened).
- **Recall only.** Precision against the warehouse confuser is unmeasured; the candidate list will
  contain warehouse false positives until a verification stage is added.
- **Region-restricted S2 comparison.** NAIP and S2 were compared over a common 20-MGRS footprint
  covering all sites; whitening stats were full-pool.
- **Static imagery.** Temporal change (S2 year-over-year; pre/post-build) was not used; post-2023
  builds may be invisible in NAIP 2023.
- **Unsupervised whitening on this pool.** The transform is AOI-specific; recompute per region.

## 5. Experiment ledger

| ID | Question | Result |
|---|---|---|
| E0 | Ground truth + contamination process | 50/50 sites, ~6 tiles/site @300 m; pool-contamination scorer (unit-tested) |
| E1 | Do data centers cluster? | Weak real cluster (gap 0.18) hidden by anisotropy (bg–bg 0.83); whitening exposes it |
| E2 | Headline retrieval (raw) | recall@1000 = 0.36, ×183 enrichment; global prototype is majority-biased |
| E3 | Cross-archetype transfer | `large_purpose_built` prototype generalises best; transfer is asymmetric |
| E7 | Query construction | **ZCA whitening → recall@1000 = 0.80** (the key fix) |
| E5 | NAIP vs S2 + fusion | NAIP 0.80 ≫ S2 0.56; fusion adds ~1 site |
| E8 | Do findability ratings predict retrieval? | Raw yes (ρ=0.38); whitened no (ρ=0.13) — whitening decouples from human findability |
| E4 | Zero-shot text | ensemble 0.36 (no labels); text can't be whitened (modality gap) |
| — | Deliverable | top-1000 deduplicated candidate GeoJSON (28 known + 972 new; whitened + raw scores, §2.8) |

*Not run:* E9 (IVFPQ-vs-exact recall cost, buffer sensitivity), E6 (few-shot labelling budget),
E10 (precision vs labelled warehouses). E9 and E10 are the two most valuable for deployment
readiness.

**Reproduce:** `uv run python scripts/build_ground_truth.py` → `run_e2.py` → `run_e7.py` →
`build_s2.py` + `run_e5.py` → `run_e1.py` / `run_e8.py` / `run_e4.py` → `make_candidates.py`.
Tests: `uv run --extra dev pytest -q`.
