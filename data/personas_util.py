import json, pathlib
def profile(persona: str) -> dict:
    return json.loads((pathlib.Path(__file__).parent / "personas" / persona / "profile.json").read_text())
