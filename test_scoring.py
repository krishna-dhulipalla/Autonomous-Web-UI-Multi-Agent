from web_agent.dom.scoring import score_element, _classify_intent

# Test 1: Intent Classification
assert _classify_intent("Change my full name to Krish Vamsi in my profile settings") == "profile_settings"
assert _classify_intent("Create a new issue") == "create_new"
assert _classify_intent("Filter by status") == "filter_search"
print("Intent classification passed.")

# Test 2: Profile Settings Scenario
instruction = "Change my full name to Krish Vamsi in my profile settings"

# Candidate 1: "Settings" option (Perfect match)
elem_settings = {"id": "1", "name": "Settings", "role": "option", "landmark": "main"}
score_settings = score_element(elem_settings, instruction)
print(f"Settings Score: {score_settings}")

# Candidate 2: "Add filter" button (Generic action, domain conflict)
elem_filter = {"id": "2", "name": "Add filter", "role": "button", "landmark": "main"}
score_filter = score_element(elem_filter, instruction)
print(f"Add Filter Score: {score_filter}")

# Candidate 3: "Workspace" menu (Related domain)
elem_workspace = {"id": "3", "name": "Workspace", "role": "menu", "landmark": "navigation"}
score_workspace = score_element(elem_workspace, instruction)
print(f"Workspace Score: {score_workspace}")

# Assertions
assert score_settings > score_filter, "Settings should outscore Add Filter"
assert score_workspace > score_filter, "Workspace should outscore Add Filter"
assert score_settings > 5.0, "Settings should have a high score"
assert score_filter < 2.0, "Add Filter should have a low score due to penalties"

print("Profile settings scenario passed.")

# Test 3: Penalty Verification (Existing logic)
elem = {"id": "1", "name": "Submit", "role": "button", "landmark": "main"}
instr_submit = "Click Submit"

# Baseline score
score_base = score_element(elem, instr_submit, tried_ids=[], ui_same=False)
print(f"Base Score: {score_base}")

# Tried ID penalty (normal)
score_tried = score_element(elem, instr_submit, tried_ids=["1"], ui_same=False)
print(f"Tried Score (ui_same=False): {score_tried}")
assert score_tried < score_base

# Tried ID penalty (ui_same=True) - should be much lower
score_stuck = score_element(elem, instr_submit, tried_ids=["1"], ui_same=True)
print(f"Stuck Score (ui_same=True): {score_stuck}")
assert score_stuck < score_tried
assert score_stuck <= score_base - 5.0 # Check for strong penalty

print("Scoring penalty verification passed!")
