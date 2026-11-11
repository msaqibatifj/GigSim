import functools, os, pathlib, yaml
ROOT = pathlib.Path(__file__).resolve().parents[1]

@functools.cache
def cfg() -> dict:
    return yaml.safe_load((ROOT / "agent" / "config.yaml").read_text())

@functools.cache
def policy() -> dict:
    return yaml.safe_load((ROOT / cfg()["policy_file"]).read_text())

def profile() -> str:
    return os.getenv("MODEL_PROFILE", "open")

def model_for(node: str) -> dict:
    """Model is config, never code: node -> tier -> {provider, model}."""
    return cfg()["profiles"][profile()][cfg()["nodes"][node]]
