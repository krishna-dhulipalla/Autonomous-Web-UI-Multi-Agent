
import json

def normalize_plan(plan):
    # Logic to be implemented
    
    # 1. If the model returns a list, unwrap the first item.
    if isinstance(plan, list):
        if len(plan) > 0:
            plan = plan[0]
        else:
            plan = {}

    # 2. If the model returns the correct object, keep it.
    # 3. If the model returns a single action instead of actions[], wrap it in actions[].
    if isinstance(plan, dict):
        if "actions" in plan:
            pass # Correct object
        else:
            # Single action or malformed
            plan = {"actions": [plan], "followup_hint": ""}
    else:
        # Fallback
        plan = {"actions": [], "followup_hint": ""}
        
    # 4. Always ensure params exists.
    actions = plan.get("actions")
    if not isinstance(actions, list):
        actions = []
        
    for action in actions:
        if isinstance(action, dict):
            if "params" not in action:
                action["params"] = {}
                
    return {"actions": actions, "followup_hint": plan.get("followup_hint", "")}

def test():
    # Case 1: Correct object
    case1 = {"actions": [{"action": "click", "target_id": "1", "params": {}}], "followup_hint": "hint"}
    res1 = normalize_plan(case1)
    print(f"Case 1 (Correct): {res1}")
    assert res1["actions"][0]["target_id"] == "1"
    assert res1["followup_hint"] == "hint"

    # Case 2: Wrapper list
    case2 = [{"actions": [{"action": "fill", "target_id": "2", "params": {"text": "hi"}}], "followup_hint": "hint2"}]
    res2 = normalize_plan(case2)
    print(f"Case 2 (Wrapper): {res2}")
    assert res2["actions"][0]["target_id"] == "2"
    assert res2["followup_hint"] == "hint2"

    # Case 3: Single action
    case3 = {"action": "click", "target_id": "3"}
    res3 = normalize_plan(case3)
    print(f"Case 3 (Single): {res3}")
    assert res3["actions"][0]["target_id"] == "3"
    assert res3["actions"][0]["params"] == {} # Params added

    # Case 4: Params missing
    case4 = {"actions": [{"action": "click", "target_id": "4"}]}
    res4 = normalize_plan(case4)
    print(f"Case 4 (Missing Params): {res4}")
    assert res4["actions"][0]["params"] == {}

    print("All tests passed!")

if __name__ == "__main__":
    test()
