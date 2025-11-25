from agent_a.scoring import score_element

elem = {"id": "1", "name": "Submit", "role": "button", "landmark": "main"}
instruction = "Click Submit"

# Baseline score
score_base = score_element(elem, instruction, tried_ids=[], ui_same=False)
print(f"Base Score: {score_base}")

# Tried ID penalty (normal)
score_tried = score_element(elem, instruction, tried_ids=["1"], ui_same=False)
print(f"Tried Score (ui_same=False): {score_tried}")
assert score_tried < score_base

# Tried ID penalty (ui_same=True) - should be much lower
score_stuck = score_element(elem, instruction, tried_ids=["1"], ui_same=True)
print(f"Stuck Score (ui_same=True): {score_stuck}")
assert score_stuck < score_tried
assert score_stuck <= score_base - 5.0 # Check for strong penalty

print("Scoring penalty verification passed!")
