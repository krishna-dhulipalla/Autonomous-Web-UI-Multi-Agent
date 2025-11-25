from agent_a.agent_b import _heuristic_match

# Test heuristic match
print(f"High -> {_heuristic_match('High', '')}")
print(f"Email -> {_heuristic_match('kdhulipalla13@gmail.com', '')}")
print(f"Improvement -> {_heuristic_match('improvement', '')}")
print(f"Priority -> {_heuristic_match('', 'Priority')}")
print(f"Assignee -> {_heuristic_match('', 'Assignee')}")
print(f"Labels -> {_heuristic_match('', 'Labels')}")

assert _heuristic_match("High", "") == "priority"
assert _heuristic_match("kdhulipalla13@gmail.com", "") == "email"
assert _heuristic_match("improvement", "") == "label"
assert _heuristic_match("", "Priority") == "priority"
assert _heuristic_match("", "Assignee") == "other" 
assert _heuristic_match("", "Labels") == "label"

print("Heuristic match tests passed.")

# Mock remapping logic (simplified version of what's in agent_b)
def test_remapping():
    # Scenario: Agent B chose "Assignee" (id=43) for "High" (priority value)
    # But "Priority" (id=42) exists in candidates.
    
    actions = [{"action": "select", "target_id": "43", "params": {"option": "High"}}]
    
    top_elements = [
        {"id": "42", "name": "Priority", "role": "combobox"},
        {"id": "43", "name": "Assignee", "role": "combobox"},
        {"id": "44", "name": "Labels", "role": "combobox"}
    ]
    
    name_by_id = {e["id"]: e["name"] for e in top_elements}
    seen_targets = set()
    
    for a in actions:
        tid = a["target_id"]
        val = a["params"]["option"]
        
        val_type = _heuristic_match(val, "")
        current_name = name_by_id.get(tid, "")
        name_type = _heuristic_match("", current_name)
        
        print(f"Action: {val} ({val_type}) -> {current_name} ({name_type})")
        
        # Relaxed condition: if val_type is known and differs from name_type (even if name_type is 'other')
        if val_type != "other" and val_type != name_type:
            print("Mismatch detected!")
            best_swap = None
            for cand in top_elements:
                c_id = cand["id"]
                c_name = cand["name"]
                c_type = _heuristic_match("", c_name)
                print(f"Candidate {c_id}: {c_name} ({c_type})")
                if c_type == val_type:
                    best_swap = c_id
                    print(f"  -> Match found: {best_swap}")
                    break
            
            if best_swap:
                print(f"Swapping to {best_swap}")
                a["target_id"] = best_swap
                
    print(f"Final target_id: {actions[0]['target_id']}")
    assert actions[0]["target_id"] == "42" # Should swap to Priority
    print("Remapping test passed!")

test_remapping()
