# Demo walkthrough (≈5 minutes)

Start everything: `scripts/stack.sh start stub` → open **http://127.0.0.1:5180** (backend mode). Stop with `scripts/stack.sh stop`.
`stub` wires the backend to a **local stand-in** for the vision model (every observation is labelled `[STUB]`); it exercises the real HTTP path but is **not Meta**. For real Meta analysis, start the backend with `META_API_KEY` + `META_MODEL` instead (see `backend/README.md`) and verify first with `backend/scripts/check_meta_live.py photo.jpg`.
Offline? The map shows a "tiles unavailable" notice and still draws the road network.

## 1. A recommendation that depends on the vehicle — *Route Investigation*
1. Origin **Fort Kochi**, destination **Aluva**, vehicle **Ashok Leyland Ecomet** (heavy truck) → *Investigate route*.
2. The map shows the recommended route (amber), rejected routes (red dotted) and alternatives (grey), plus defect and restriction markers.
3. Read **Route B**: *rejected, weight limit 10 t on Thoppumpady Old Bridge Rd, your vehicle is 14 t*. It's the second-fastest route but unusable for this truck.
4. Click an alternative to highlight it on the map.
5. Left panel → **Vehicle restrictions**: 3 verified blockers, 2 unverified "may block". Change vehicle to **Force Traveller**: height and weight are *unknown*, so those restrictions say "cannot confirm", never "fits".

## 2. How fragile is that recommendation? — *Autopsy Lab*
1. Vyttila Hub → Kakkanad, **Ecomet** → *Run autopsy*.
2. **Step 2** baseline: route S6 → S13, 20.1 min. Unverified evidence on it: defect D12.
3. **Step 4** sensitivity **0.15**: 3 of 23 tested changes alter the recommendation. The yellow note states what the number is *not* (an accident probability). Open "What does this score mean?" for the formula.
4. The first *changed* scenario is selected: **"defect D10 is resolved"** → recommendation moves S6→S13 to S6→S7→S15 (+4.9 min) because that route's score falls from 2101 s to 1501 s. The table compares baseline/revised duration, distance, severe defects, score and lead over the runner-up; the map overlays both routes.
5. Switch the filter to **stable**, pick any scenario: the explanation says why nothing changed (e.g. its score lead over the runner-up stays at 297 s).
6. **Step 5** what-if: close segment **S13** (picked from real segments) → run; it joins the list. Nothing is written to the database.

## 3. From a photo to an unverified report — *Evidence Lab*
1. The green banner shows the configured model. Upload `frontend/e2e/fixtures/road.jpg` (or any JPEG/PNG/WebP up to 10 MB).
2. Your photo appears beside the model's observations, each tagged **AI candidate · unverified** with "visual confidence … (not verification)".
3. The **restriction sign** candidate has a disabled checkbox and an explanation: it never changes routing and needs an authorized verification workflow.
4. Tick the **pothole**: *Confirm* stays disabled and asks for a location. **Click the map** (or type coordinates). Severity is pre-filled from the model's suggestion; change it if you disagree (required when none is suggested).
5. *Confirm* → a **Report ID** (e.g. `U-1A2B3C4D`) appears with **Verification: unverified**, re-read from the backend.
6. Upload the same photo again and confirm: it's flagged as a duplicate and creates no second report.

## 4. Failure behaviour (worth showing)
Stop the backend and reload any page: you get an error with *Try again*, never fake data. `VITE_APP_MODE=demo` (http://127.0.0.1:5181) is a separate mode with an amber "synthetic data" badge.
