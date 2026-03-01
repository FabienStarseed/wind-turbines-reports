"""
taxonomy.py — BDDA Authoritative Defect Taxonomy (Core Knowledge Base)

56 defect types sourced from:
- IEC 61400-23:2014 — Blade structural testing & failure modes
- DNVGL-ST-0376 — Rotor blade design, manufacturing, in-service defects
- GWO Blade Repair Training Standard V5 — Operational damage types
- IEA Wind Task 46 — LEE 4-stage classification system
- IEC 61400-24 — Lightning protection standards
- NREL Research — Delamination/debonding as primary failure mode
- EPRI White Paper — Industry severity categorization practices
"""

# ─── URGENCY / SEVERITY SYSTEM ────────────────────────────────────────────────

URGENCY_LEVELS = {
    "LOG":       {"cat_range": "Cat 1", "color": "#22c55e",  "action": "Document for record only; no intervention"},
    "MONITOR":   {"cat_range": "Cat 2", "color": "#eab308",  "action": "Track at next annual inspection (12 months)"},
    "PLANNED":   {"cat_range": "Cat 3", "color": "#f97316",  "action": "Schedule at next planned service window (6–12 months)"},
    "URGENT":    {"cat_range": "Cat 4", "color": "#ef4444",  "action": "Repair within 3 months; monthly monitoring"},
    "IMMEDIATE": {"cat_range": "Cat 5", "color": "#7f1d1d",  "action": "Stop turbine; emergency work order"},
}

SEVERITY_SCALE = {
    1: {"label": "Cosmetic",          "urgency": "LOG",       "timeframe": "No repair needed",              "cost_multiplier": "1×"},
    2: {"label": "Minor",             "urgency": "MONITOR",   "timeframe": "Next annual inspection (12 mo)", "cost_multiplier": "~2×"},
    3: {"label": "Structural Impact", "urgency": "PLANNED",   "timeframe": "Within 6–12 months",            "cost_multiplier": "~3×"},
    4: {"label": "High Priority",     "urgency": "URGENT",    "timeframe": "Within 3 months",               "cost_multiplier": "~6×"},
    5: {"label": "Critical",          "urgency": "IMMEDIATE", "timeframe": "Stop turbine / 0–30 days",      "cost_multiplier": "~12–15×"},
}

# Escalation rules
ESCALATION_RULES = [
    "If 2+ Cat 3 defects on same blade zone → escalate to URGENT",
    "If defect progression visible vs prior inspection → escalate one level",
    "Cat 5 on structural element (spar cap, root) → stop turbine, no exceptions",
]


# ─── ZONE DEFINITIONS ─────────────────────────────────────────────────────────

BLADE_ZONES = {
    "LE": "Leading Edge — highest erosion exposure; contains lightning receptor system",
    "TE": "Trailing Edge — prone to bond line separation; thin, buckling risk",
    "PS": "Pressure Side — blade underside in operation; less erosion",
    "SS": "Suction Side — blade upper surface; moderate erosion",
}

SPAN_POSITIONS = {
    "Root":       "0–15% span — highest bending stress; primary fatigue initiation zone",
    "Transition": "15–35% span — geometry changes from circular root to airfoil; stress concentration",
    "Mid":        "35–70% span — main load-carrying section; maximum chord width",
    "Tip":        "70–100% span — maximum velocity; maximum erosion and lightning exposure",
}

INTERNAL_ZONES = {
    "Spar Cap":   "Primary load carrier (compression/tension flanges); fiber waviness is catastrophic",
    "Shear Web":  "Internal I-beam connecting spar caps; debonding is critical failure mode",
    "Root Flange":"Bolt circle connection to hub; fatigue crack initiation zone",
}


# ─── DEFECT DATABASE ──────────────────────────────────────────────────────────
# Each entry:
#   id:           numeric ID
#   name:         official defect name (IEC/DNVGL/GWO terminology)
#   system:       blade | nacelle | tower
#   category:     A–G subcategory
#   zones:        list of applicable surface zones
#   positions:    list of applicable span positions
#   cat_range:    [min, max] Vestas severity category
#   urgency:      default urgency (may escalate per rules)
#   timeframe:    recommended maintenance timeframe
#   visual_cue:   what the AI should look for in the drone image
#   standard:     primary standard reference
#   ndt_required: True if drone cannot confirm — needs NDT follow-up

DEFECTS = [
    # ─── BLADE: A. EROSION ────────────────────────────────────────────────────
    {
        "id": 1, "name": "Leading Edge Erosion — Stage 1",
        "system": "blade", "category": "A_erosion",
        "zones": ["LE"], "positions": ["Tip", "Mid"],
        "cat_range": [1, 2], "urgency": "MONITOR", "timeframe": "12 months",
        "visual_cue": "Slight surface roughening, paint dullness, loss of gloss at LE; no coating material loss yet",
        "standard": "IEA Wind Task 46",
        "ndt_required": False,
    },
    {
        "id": 2, "name": "Leading Edge Erosion — Stage 2",
        "system": "blade", "category": "A_erosion",
        "zones": ["LE"], "positions": ["Tip", "Mid"],
        "cat_range": [2, 3], "urgency": "PLANNED", "timeframe": "6–12 months",
        "visual_cue": "Pitting and micro-craters at LE; visible coating material removal; fiberglass appears white/matte",
        "standard": "IEA Wind Task 46",
        "ndt_required": False,
    },
    {
        "id": 3, "name": "Leading Edge Erosion — Stage 3",
        "system": "blade", "category": "A_erosion",
        "zones": ["LE"], "positions": ["Tip", "Mid"],
        "cat_range": [3, 4], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Deep pitting; exposed composite laminate visible; sharp erosion profile at LE cross-section; significant surface roughness",
        "standard": "IEA Wind Task 46",
        "ndt_required": False,
    },
    {
        "id": 4, "name": "Leading Edge Erosion — Stage 4 (Critical)",
        "system": "blade", "category": "A_erosion",
        "zones": ["LE"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [4, 5], "urgency": "IMMEDIATE", "timeframe": "Stop turbine / 30 days",
        "visual_cue": "Structural material removed from LE; deep gouging; laminate layers exposed; blade profile visibly deformed at edge",
        "standard": "IEA Wind Task 46",
        "ndt_required": False,
    },
    {
        "id": 5, "name": "Trailing Edge Erosion",
        "system": "blade", "category": "A_erosion",
        "zones": ["TE"], "positions": ["Tip", "Mid"],
        "cat_range": [1, 3], "urgency": "MONITOR", "timeframe": "6–12 months",
        "visual_cue": "Surface degradation at TE; whitish composite exposure; similar to LEE but at trailing edge",
        "standard": "DNVGL-ST-0376",
        "ndt_required": False,
    },
    {
        "id": 6, "name": "Paint / Gelcoat Chalking",
        "system": "blade", "category": "A_erosion",
        "zones": ["LE", "TE", "PS", "SS"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [1, 2], "urgency": "LOG", "timeframe": "12+ months",
        "visual_cue": "Faded, powdery, dull surface; loss of gloss uniformly across area; UV degradation indicator",
        "standard": "GWO V5",
        "ndt_required": False,
    },
    {
        "id": 7, "name": "Surface Contamination",
        "system": "blade", "category": "A_erosion",
        "zones": ["LE", "TE", "PS", "SS"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [1, 2], "urgency": "LOG", "timeframe": "Next service",
        "visual_cue": "Oil streaks, insect buildup (dark speckling), algae (greenish/brown), bird droppings (white patches)",
        "standard": "GWO V5",
        "ndt_required": False,
    },

    # ─── BLADE: B. COATING & SURFACE ─────────────────────────────────────────
    {
        "id": 8, "name": "Coating Peeling / Delamination",
        "system": "blade", "category": "B_coating",
        "zones": ["LE", "TE", "PS", "SS"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [2, 3], "urgency": "PLANNED", "timeframe": "6–12 months",
        "visual_cue": "Flaking, lifting paint layers; visible as curled/raised edges; exposed composite underneath; discoloration pattern",
        "standard": "DNVGL-ST-0376",
        "ndt_required": False,
    },
    {
        "id": 9, "name": "Coating Chipping / Flaking",
        "system": "blade", "category": "B_coating",
        "zones": ["LE", "TE", "PS", "SS"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [1, 2], "urgency": "LOG", "timeframe": "12+ months",
        "visual_cue": "Small missing coating fragments; sharp-edged chip marks; localized impact or adhesion failure",
        "standard": "GWO V5",
        "ndt_required": False,
    },
    {
        "id": 10, "name": "Discoloration / UV Staining",
        "system": "blade", "category": "B_coating",
        "zones": ["LE", "TE", "PS", "SS"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [1, 2], "urgency": "LOG", "timeframe": "Next service",
        "visual_cue": "Localized color change; streak marks distinct from contamination; yellowing, browning, or UV-whitening pattern",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 11, "name": "Edge Sealant Crack / Loss",
        "system": "blade", "category": "B_coating",
        "zones": ["LE", "TE"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [2, 3], "urgency": "PLANNED", "timeframe": "6–12 months",
        "visual_cue": "Cracked or missing white/gray sealant line running along blade edge; exposed adhesive joint visible",
        "standard": "DNVGL-ST-0376",
        "ndt_required": False,
    },
    {
        "id": 12, "name": "Surface Pitting / Micro-Craters",
        "system": "blade", "category": "B_coating",
        "zones": ["LE", "PS"], "positions": ["Tip", "Mid"],
        "cat_range": [2, 3], "urgency": "MONITOR", "timeframe": "12 months",
        "visual_cue": "Small dark or white depressions in coating surface; random distribution pattern; early erosion indicator",
        "standard": "IEA Wind Task 46",
        "ndt_required": False,
    },
    {
        "id": 13, "name": "Resin-Rich / Resin-Starved Area",
        "system": "blade", "category": "B_coating",
        "zones": ["PS", "SS"], "positions": ["Mid", "Root"],
        "cat_range": [2, 3], "urgency": "MONITOR", "timeframe": "12 months",
        "visual_cue": "White patches (starved: exposed dry fibers, matte texture) or glossy shiny excess resin (rich); manufacturing origin",
        "standard": "DNVGL-ST-0376",
        "ndt_required": False,
    },
    {
        "id": 14, "name": "Moisture Ingress Staining",
        "system": "blade", "category": "B_coating",
        "zones": ["LE", "TE", "PS", "SS"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [2, 3], "urgency": "PLANNED", "timeframe": "3–6 months",
        "visual_cue": "Dark water trail staining; blister swelling near cracks or delaminations; tide marks from water penetration",
        "standard": "NREL",
        "ndt_required": False,
    },

    # ─── BLADE: C. CRACKS ────────────────────────────────────────────────────
    {
        "id": 15, "name": "Surface Crack — Longitudinal",
        "system": "blade", "category": "C_cracks",
        "zones": ["PS", "SS", "TE"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [2, 4], "urgency": "MONITOR", "timeframe": "3–12 months",
        "visual_cue": "Linear fracture parallel to blade span axis; hairline to 3mm+ width; may have dark interior indicating depth",
        "standard": "DNVGL-ST-0376",
        "ndt_required": False,
    },
    {
        "id": 16, "name": "Surface Crack — Transverse",
        "system": "blade", "category": "C_cracks",
        "zones": ["LE", "TE", "PS", "SS"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [4, 5], "urgency": "IMMEDIATE", "timeframe": "Stop turbine / 30 days",
        "visual_cue": "Crack perpendicular to blade span — CRITICAL INDICATOR; stress overload signature; may show widening",
        "standard": "DNVGL-ST-0376",
        "ndt_required": True,
    },
    {
        "id": 17, "name": "Root Transition Crack",
        "system": "blade", "category": "C_cracks",
        "zones": ["PS", "SS", "LE"], "positions": ["Root", "Transition"],
        "cat_range": [4, 5], "urgency": "IMMEDIATE", "timeframe": "Stop turbine / 30 days",
        "visual_cue": "Cracks at circular-to-airfoil geometry transition zone; often radiate from geometry change line; fatigue initiation pattern",
        "standard": "NREL",
        "ndt_required": True,
    },
    {
        "id": 18, "name": "Bond Line Crack",
        "system": "blade", "category": "C_cracks",
        "zones": ["LE", "TE"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [3, 4], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Thin dark crack line precisely at adhesive joint between PS and SS shells; follows blade edge exactly",
        "standard": "DNVGL-ST-0376",
        "ndt_required": False,
    },
    {
        "id": 19, "name": "Root Flange / Bolt Circle Crack",
        "system": "blade", "category": "C_cracks",
        "zones": ["PS", "SS"], "positions": ["Root"],
        "cat_range": [4, 5], "urgency": "IMMEDIATE", "timeframe": "Stop turbine / 30 days",
        "visual_cue": "Cracks or paint fractures in bolt circle pattern near root flange; radial cracking around hub attachment bolts",
        "standard": "IEC 61400-23",
        "ndt_required": True,
    },
    {
        "id": 20, "name": "Trailing Edge Separation",
        "system": "blade", "category": "C_cracks",
        "zones": ["TE"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [3, 5], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Visible linear gap or opening along TE bond line; gap may vary from hairline to several mm; progressive separation pattern",
        "standard": "DNVGL-ST-0376",
        "ndt_required": False,
    },
    {
        "id": 21, "name": "Spar-to-Shell Debonding",
        "system": "blade", "category": "C_cracks",
        "zones": ["PS", "SS"], "positions": ["Mid", "Root", "Transition"],
        "cat_range": [3, 5], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Surface waviness or warping pattern along blade span; localized bulging; altered reflection indicating internal separation",
        "standard": "NREL",
        "ndt_required": True,
    },

    # ─── BLADE: D. DELAMINATION & STRUCTURAL SEPARATION ──────────────────────
    {
        "id": 22, "name": "Inter-ply Delamination",
        "system": "blade", "category": "D_delamination",
        "zones": ["PS", "SS", "TE"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [3, 5], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Blister-like surface bulge; altered surface reflection; whitish or opaque area; may show irregular oval or elongated shape",
        "standard": "NREL",
        "ndt_required": True,
    },
    {
        "id": 23, "name": "Adhesive / Bond Line Failure (Internal)",
        "system": "blade", "category": "D_delamination",
        "zones": ["PS", "SS", "LE", "TE"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [3, 5], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Surface lifting or broad ripple/wave pattern; distinct from crack (no sharp line) — broader wavy surface deformation",
        "standard": "DNVGL-ST-0376",
        "ndt_required": True,
    },
    {
        "id": 24, "name": "Bond Line Exposure",
        "system": "blade", "category": "D_delamination",
        "zones": ["LE", "TE"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [2, 3], "urgency": "PLANNED", "timeframe": "6–12 months",
        "visual_cue": "Visible thin dark adhesive seam line at blade edge; coating worn off revealing adhesive; no gap yet",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 25, "name": "Core Exposure / Core Damage",
        "system": "blade", "category": "D_delamination",
        "zones": ["LE", "PS"], "positions": ["Tip", "Mid"],
        "cat_range": [4, 5], "urgency": "IMMEDIATE", "timeframe": "Stop turbine / 30 days",
        "visual_cue": "Visible foam or balsa core material exposed through laminate; yellow/tan foam or light wood texture visible",
        "standard": "DNVGL-ST-0376",
        "ndt_required": False,
    },
    {
        "id": 26, "name": "Fiber Exposure / Tearing",
        "system": "blade", "category": "D_delamination",
        "zones": ["LE", "TE", "PS", "SS"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [5, 5], "urgency": "IMMEDIATE", "timeframe": "Stop turbine immediately",
        "visual_cue": "Visible white glass fiber strands exposed at surface — CRITICAL; structural failure imminent; frayed fiber texture",
        "standard": "IEC 61400-23",
        "ndt_required": False,
    },
    {
        "id": 27, "name": "Fiber Waviness / Wrinkle",
        "system": "blade", "category": "D_delamination",
        "zones": ["PS", "SS"], "positions": ["Mid", "Root", "Transition"],
        "cat_range": [3, 5], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Undulating/rippling pattern in fiber surface visible as wavy texture; reduces compressive strength up to 75% (DNVGL)",
        "standard": "DNVGL-ST-0376",
        "ndt_required": True,
    },
    {
        "id": 28, "name": "Debonded Repair Patch",
        "system": "blade", "category": "D_delamination",
        "zones": ["PS", "SS"], "positions": ["Tip", "Mid", "Root"],
        "cat_range": [3, 4], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Previously repaired area lifting or peeling; visible raised edges; color/texture mismatch with surrounding surface",
        "standard": "GWO V5",
        "ndt_required": False,
    },

    # ─── BLADE: E. MANUFACTURING DEFECTS ─────────────────────────────────────
    {
        "id": 29, "name": "Dry Spot / Void / Porosity",
        "system": "blade", "category": "E_manufacturing",
        "zones": ["PS", "SS", "LE", "TE"], "positions": ["Mid", "Root", "Transition"],
        "cat_range": [2, 3], "urgency": "MONITOR", "timeframe": "6–12 months",
        "visual_cue": "Whitish matte area with exposed dry fibers OR dark irregular patches/bubbles; poor resin impregnation appearance",
        "standard": "DNVGL-ST-0376",
        "ndt_required": True,
    },
    {
        "id": 30, "name": "Foreign Inclusion",
        "system": "blade", "category": "E_manufacturing",
        "zones": ["PS", "SS", "LE", "TE"], "positions": ["Mid", "Root"],
        "cat_range": [1, 2], "urgency": "LOG", "timeframe": "Next service",
        "visual_cue": "Localized surface anomaly; foreign material visible or color/texture mismatch from manufacturing stage",
        "standard": "DNVGL-ST-0376",
        "ndt_required": False,
    },

    # ─── BLADE: F. IMPACT DAMAGE ──────────────────────────────────────────────
    {
        "id": 31, "name": "Bird / Object Strike",
        "system": "blade", "category": "F_impact",
        "zones": ["LE", "PS", "SS"], "positions": ["Tip", "Mid"],
        "cat_range": [2, 4], "urgency": "MONITOR", "timeframe": "3–12 months",
        "visual_cue": "Impact crater or indentation; localized surface damage; possible surrounding delamination halo; single impact origin",
        "standard": "GWO V5",
        "ndt_required": False,
    },
    {
        "id": 32, "name": "Hail Damage Pattern",
        "system": "blade", "category": "F_impact",
        "zones": ["LE", "PS", "SS"], "positions": ["Tip", "Mid"],
        "cat_range": [1, 3], "urgency": "LOG", "timeframe": "12 months / 6 months",
        "visual_cue": "Multiple small impact points across surface; consistent size and spacing pattern distinguishes from other damage",
        "standard": "GWO V5",
        "ndt_required": False,
    },
    {
        "id": 33, "name": "Leading Edge Gouge",
        "system": "blade", "category": "F_impact",
        "zones": ["LE"], "positions": ["Tip", "Mid"],
        "cat_range": [3, 4], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Material physically removed from LE; sharp-edged cavity; distinct from erosion (abrupt single event vs gradual)",
        "standard": "GWO V5",
        "ndt_required": False,
    },

    # ─── BLADE: G. LIGHTNING DAMAGE ──────────────────────────────────────────
    {
        "id": 34, "name": "Lightning Strike with Surface Burn",
        "system": "blade", "category": "G_lightning",
        "zones": ["LE", "TE"], "positions": ["Tip"],
        "cat_range": [3, 5], "urgency": "URGENT", "timeframe": "3 months / Stop turbine",
        "visual_cue": "Charring, burn marks, or puncture at receptor area; dark discoloration; possible material loss around strike point",
        "standard": "IEC 61400-24",
        "ndt_required": True,
    },
    {
        "id": 35, "name": "Arc / Burn Tracking Marks",
        "system": "blade", "category": "G_lightning",
        "zones": ["LE", "TE", "PS", "SS"], "positions": ["Tip", "Mid"],
        "cat_range": [4, 5], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Black branching/dendritic carbon tracks along surface; lightning discharge path indicator; Lichtenberg-pattern appearance",
        "standard": "IEC 61400-24",
        "ndt_required": True,
    },
    {
        "id": 36, "name": "Lightning Receptor Damage",
        "system": "blade", "category": "G_lightning",
        "zones": ["LE"], "positions": ["Tip"],
        "cat_range": [4, 5], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Absent, deformed, corroded, or detached copper/aluminum receptor disc; receptor hole visible or receptor misaligned",
        "standard": "IEC 61400-24",
        "ndt_required": False,
    },
    {
        "id": 37, "name": "Internal Lightning Conductor Failure",
        "system": "blade", "category": "G_lightning",
        "zones": ["LE"], "positions": ["Tip", "Mid"],
        "cat_range": [5, 5], "urgency": "IMMEDIATE", "timeframe": "Stop turbine / NDT within 7 days",
        "visual_cue": "NOT DRONE-VISIBLE — flag for NDT; suspect when receptor is present but strike damage indicates anomalous discharge path",
        "standard": "IEC 61400-24",
        "ndt_required": True,
    },

    # ─── NACELLE & HUB ────────────────────────────────────────────────────────
    {
        "id": 38, "name": "Nacelle Cover Crack / Paint Loss",
        "system": "nacelle", "category": "H_nacelle",
        "zones": [], "positions": [],
        "cat_range": [2, 3], "urgency": "MONITOR", "timeframe": "12 months",
        "visual_cue": "Faint cracks or dull/degraded surface on fiberglass nacelle cover panels; localized paint loss",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 39, "name": "Oil / Gear Leakage",
        "system": "nacelle", "category": "H_nacelle",
        "zones": [], "positions": [],
        "cat_range": [3, 4], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Dark oily streaks flowing downward from nacelle underside; may stain tower below; seal failure indicator",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 40, "name": "Panel Misalignment / Gap",
        "system": "nacelle", "category": "H_nacelle",
        "zones": [], "positions": [],
        "cat_range": [2, 3], "urgency": "MONITOR", "timeframe": "12 months",
        "visual_cue": "Visible gap between nacelle cover panels; misfit at panel joints; potential water ingress pathway",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 41, "name": "Metal Corrosion / Rust",
        "system": "nacelle", "category": "H_nacelle",
        "zones": [], "positions": [],
        "cat_range": [3, 4], "urgency": "PLANNED", "timeframe": "6 months",
        "visual_cue": "Rust spots; orange-brown staining on bolts, hinges, rails; surface oxidation of metal components",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 42, "name": "Loose / Missing Bolts",
        "system": "nacelle", "category": "H_nacelle",
        "zones": [], "positions": [],
        "cat_range": [4, 5], "urgency": "URGENT", "timeframe": "3 months / Stop",
        "visual_cue": "Shadow gap or absent bolt head in bolt ring; irregular spacing in fastener pattern",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 43, "name": "Hub Crack or Nose Cone Damage",
        "system": "nacelle", "category": "H_nacelle",
        "zones": [], "positions": [],
        "cat_range": [2, 4], "urgency": "MONITOR", "timeframe": "3–12 months",
        "visual_cue": "Visible cracks or missing paint on hub spinner/nose cone; localized impact or fatigue cracking",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 44, "name": "Yaw System Leakage",
        "system": "nacelle", "category": "H_nacelle",
        "zones": [], "positions": [],
        "cat_range": [3, 4], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Drip marks or oil staining at nacelle-tower interface junction; yaw bearing or seal failure",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 45, "name": "Lightning Entry Burn at Hub",
        "system": "nacelle", "category": "H_nacelle",
        "zones": [], "positions": [],
        "cat_range": [4, 5], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Burn marks or blackened paint near hub receptors; indicates lightning bypassed blade protection",
        "standard": "IEC 61400-24",
        "ndt_required": True,
    },

    # ─── TOWER ────────────────────────────────────────────────────────────────
    {
        "id": 46, "name": "Tower Paint Degradation / Rust",
        "system": "tower", "category": "I_tower",
        "zones": [], "positions": [],
        "cat_range": [2, 3], "urgency": "MONITOR", "timeframe": "12 months",
        "visual_cue": "Rust streaks, blistered or peeling paint on tower shell surface; environmental degradation pattern",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 47, "name": "Tower Surface Crack",
        "system": "tower", "category": "I_tower",
        "zones": [], "positions": [],
        "cat_range": [3, 4], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Linear cracks on tower exterior; often near weld seams or section joints; may be hairline to mm-width",
        "standard": "DNVGL-ST-0376",
        "ndt_required": True,
    },
    {
        "id": 48, "name": "Weld Seam Fatigue Crack",
        "system": "tower", "category": "I_tower",
        "zones": [], "positions": [],
        "cat_range": [4, 5], "urgency": "IMMEDIATE", "timeframe": "Stop turbine / structural engineer review",
        "visual_cue": "Fine linear crack along or adjacent to weld line — CRITICAL; follows weld bead precisely; fatigue failure indicator",
        "standard": "DNVGL-ST-0376",
        "ndt_required": True,
    },
    {
        "id": 49, "name": "Flange Bolt Corrosion",
        "system": "tower", "category": "I_tower",
        "zones": [], "positions": [],
        "cat_range": [3, 4], "urgency": "PLANNED", "timeframe": "6 months",
        "visual_cue": "Rusted or heavily stained bolt heads at tower section flange joints; corrosion affects preload integrity",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 50, "name": "Missing / Loose Flange Bolt",
        "system": "tower", "category": "I_tower",
        "zones": [], "positions": [],
        "cat_range": [4, 5], "urgency": "URGENT", "timeframe": "3 months / Stop",
        "visual_cue": "Visible gap in bolt ring pattern at tower flange; missing bolt head shadow; irregular spacing in bolt circle",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 51, "name": "Flange Misalignment / Gap",
        "system": "tower", "category": "I_tower",
        "zones": [], "positions": [],
        "cat_range": [3, 4], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Uneven spacing or visible gap at tower section joint interface; structural misalignment indicator",
        "standard": "EPRI",
        "ndt_required": True,
    },
    {
        "id": 52, "name": "Flange Paint / Coating Damage",
        "system": "tower", "category": "I_tower",
        "zones": [], "positions": [],
        "cat_range": [2, 3], "urgency": "MONITOR", "timeframe": "12 months",
        "visual_cue": "Exposed metal ring at flange face; chipped or missing coating; increases corrosion risk",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 53, "name": "Flange Sealant / Gasket Deterioration",
        "system": "tower", "category": "I_tower",
        "zones": [], "positions": [],
        "cat_range": [2, 3], "urgency": "MONITOR", "timeframe": "12 months",
        "visual_cue": "Cracked or missing gasket/sealant material at flange joint; water ingress pathway forming",
        "standard": "EPRI",
        "ndt_required": False,
    },
    {
        "id": 54, "name": "Tower Lightning Burn Mark",
        "system": "tower", "category": "I_tower",
        "zones": [], "positions": [],
        "cat_range": [4, 5], "urgency": "URGENT", "timeframe": "3 months",
        "visual_cue": "Black traces or paint burn on tower exterior; lightning discharge path from blade/hub down tower",
        "standard": "IEC 61400-24",
        "ndt_required": True,
    },
    {
        "id": 55, "name": "Biological Contamination",
        "system": "tower", "category": "I_tower",
        "zones": [], "positions": [],
        "cat_range": [1, 2], "urgency": "LOG", "timeframe": "Next service",
        "visual_cue": "Bird nesting material, organic buildup near access platforms, ladders, ventilation openings",
        "standard": "GWO V5",
        "ndt_required": False,
    },
    {
        "id": 56, "name": "Foundation Crack / Spalling",
        "system": "tower", "category": "I_tower",
        "zones": [], "positions": [],
        "cat_range": [4, 5], "urgency": "IMMEDIATE", "timeframe": "Stop turbine / structural engineer",
        "visual_cue": "Concrete cracking, spalling, or rebar exposure at tower base; J-tube area damage; structural foundation failure",
        "standard": "DNVGL-ST-0376",
        "ndt_required": True,
    },
]


# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────

def get_defect_by_id(defect_id: int) -> dict:
    for d in DEFECTS:
        if d["id"] == defect_id:
            return d
    raise KeyError(f"No defect with id {defect_id}")


def get_defects_by_system(system: str) -> list:
    return [d for d in DEFECTS if d["system"] == system]


def get_defects_by_urgency(urgency: str) -> list:
    return [d for d in DEFECTS if d["urgency"] == urgency]


def get_urgency_for_category(cat: int) -> str:
    if cat <= 1:
        return "LOG"
    elif cat == 2:
        return "MONITOR"
    elif cat == 3:
        return "PLANNED"
    elif cat == 4:
        return "URGENT"
    else:
        return "IMMEDIATE"


def build_taxonomy_prompt_block() -> str:
    """
    Build the taxonomy section to embed in AI classification prompts.
    Returns a compact text representation of all 56 defects.
    """
    lines = ["VESTAS DEFECT TAXONOMY (56 defect types, IEC/DNVGL/GWO sources)\n"]
    lines.append("Format: ID. NAME | zones | cat_range | urgency | timeframe\n")

    current_system = None
    for d in DEFECTS:
        if d["system"] != current_system:
            current_system = d["system"]
            lines.append(f"\n[{current_system.upper()} DEFECTS]")

        zones_str = "/".join(d["zones"]) if d["zones"] else "all"
        positions_str = "/".join(d["positions"]) if d["positions"] else "all"
        cat_str = f"Cat {d['cat_range'][0]}" if d['cat_range'][0] == d['cat_range'][1] else f"Cat {d['cat_range'][0]}–{d['cat_range'][1]}"
        lines.append(
            f"{d['id']:2d}. {d['name']:<45} | {zones_str:<12} | {cat_str:<10} | {d['urgency']:<9} | {d['timeframe']}"
        )
        lines.append(f"    Visual: {d['visual_cue']}")

    return "\n".join(lines)


if __name__ == "__main__":
    print(f"BDDA Taxonomy loaded: {len(DEFECTS)} defect types")
    blade = get_defects_by_system("blade")
    nacelle = get_defects_by_system("nacelle")
    tower = get_defects_by_system("tower")
    print(f"  Blade: {len(blade)} | Nacelle: {len(nacelle)} | Tower: {len(tower)}")

    immediate = get_defects_by_urgency("IMMEDIATE")
    print(f"\nIMMEDIATE urgency defects ({len(immediate)}):")
    for d in immediate:
        print(f"  #{d['id']} {d['name']}")

    print("\n--- Prompt Block Preview (first 10 lines) ---")
    block = build_taxonomy_prompt_block()
    print("\n".join(block.split("\n")[:10]))
