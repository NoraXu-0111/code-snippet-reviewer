"""Small server-owned OpenAI catalog; no provider discovery call is required."""
from .contracts import ModelCatalog, ModelOption

OPENAI_MODELS = {
    "gpt-4.1-mini": "GPT-4.1 mini",
    "gpt-4.1": "GPT-4.1",
    "gpt-4.1-nano": "GPT-4.1 nano",
}


class InvalidModel(Exception):
    pass


def model_catalog(default: str) -> ModelCatalog:
    # Preserve an operator-configured OpenAI model/snapshot as an explicit option.
    choices = {**OPENAI_MODELS}
    choices.setdefault(default, default)
    return ModelCatalog(default_model=default, models=[ModelOption(id=id, name=name) for id, name in choices.items()])


def select_model(requested: str | None, default: str, providers: dict) -> str:
    selected = requested if requested is not None else default
    if selected not in providers:
        raise InvalidModel("Choose an OpenAI model from the available list.")
    return selected
