import numpy as np

class EditLog:
    """Every stage records exactly which pixels it changed. The Invention Map and manifest read this."""
    def __init__(self, original):
        self.original = original.copy()
        self.stages = []

    def record(self, stage, before, after, params):
        touched = np.any(before != after, axis=-1)
        self.stages.append({"stage": stage, "params": params, "touched": touched})
        return touched

    def summary(self):
        return [{"stage": s["stage"], **s["params"], "pixels_changed": int(s["touched"].sum())}
                for s in self.stages]
